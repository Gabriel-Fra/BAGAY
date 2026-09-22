package bagay.commands;

import bagay.catalog.Catalog;
import bagay.chain.Chain;
import bagay.chain.Json;
import bagay.chain.Json.JsonValue;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Java port of backend/commands.py's submit(): validate role rights and
 * lifecycle against the stream's own history, then produce the event to
 * append. Mirrors ARCHITECTURE.md invariant #3 -- this never reads a
 * projection to decide anything; the caller supplies the asset's current
 * status (obtained by replaying its stream, same as Python's
 * commands.load_asset) and the stream/chain heads (obtained from es_events /
 * es_chain_head / es_stream_heads, never from proj_*).
 *
 * What is intentionally NOT here yet: the actual JDBC transaction, the
 * SELECT ... FOR UPDATE-equivalent row lock, and idempotency-by-event_id.
 * Those are storage concerns for the PostgreSQL-wiring TODO item; this class
 * is the part that has to produce byte-identical hashes to Python regardless
 * of which storage layer eventually calls it.
 */
public final class Commands {

    private Commands() {
    }

    public static final DateTimeFormatter ISO_MILLIS =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

    /** Mirrors backend/commands.py ROLE_RIGHTS. SYSTEM may record anything. */
    public static final Map<String, Set<String>> ROLE_RIGHTS = Map.ofEntries(
            Map.entry("PUBLIC", Set.of("IssueReported")),
            Map.entry("FIELD_WORKER", Set.of("InspectionRecorded", "DamageRecorded",
                    "RepairStarted", "RepairCompleted")),
            Map.entry("SECRETARY", Set.of("AssetRegistered", "CustodyAssigned", "CustodyTransferred",
                    "IssueTriaged", "WorkOrderOpened", "EntryCorrected", "InspectionRecorded",
                    "DamageRecorded")),
            Map.entry("TREASURER", Set.of("RepairCompleted", "EntryCorrected")),
            Map.entry("KAGAWAD", Set.of("InspectionRecorded", "DamageRecorded", "HazardDeclared",
                    "WorkOrderOpened")),
            Map.entry("PUNONG_BARANGAY", Set.of("AssetDeclaredUnserviceable", "AssetDisposed",
                    "TurnoverSealed", "UserEnrolled", "UserDeactivated", "HazardDeclared",
                    "WorkOrderOpened")),
            Map.entry("VERIFIER", Set.of()),
            Map.entry("ADMIN", Set.of()),
            Map.entry("SYSTEM", Catalog.EVENTS.keySet())
    );

    public static final class Denied extends RuntimeException {
        public Denied(String message) {
            super(message);
        }
    }

    public static final class Conflict extends RuntimeException {
        public final String streamId;
        public final long currentVersion;

        public Conflict(String streamId, long currentVersion) {
            super(streamId + " is at version " + currentVersion);
            this.streamId = streamId;
            this.currentVersion = currentVersion;
        }
    }

    /** The two heads the command side is allowed to consult (never a projection). */
    public record ChainHead(long position, String headHash) {
    }

    public record StreamHead(long version, String headHash) {
    }

    /** What Commands.submit needs from the caller, and what it produces. */
    public record SubmitRequest(
            String streamId, String eventType, Json.JObject payload, String actorRole,
            String actorId, String source, Instant occurredAt, String currentAssetStatus,
            Long expectedVersion, String eventId) {
    }

    public record AppendedEvent(
            long globalPosition, String eventId, String streamId, long streamVersion,
            String eventType, int schemaVersion, String occurredAt, String recordedAt,
            String actorId, String actorRole, String trustLevel, String source,
            String prevHash, String streamPrevHash, String eventHash) {
    }

    public static String assetStream(String assetId) {
        return "asset:" + assetId;
    }

    /**
     * Validate, then compute the event to append. Pure: given the same heads
     * and the same asset status, always produces the same envelope and hash.
     * The caller is responsible for the actual INSERT + head updates, inside
     * one transaction, exactly as chain.append() does in Python.
     */
    public static AppendedEvent submit(SubmitRequest req, ChainHead chainHead, StreamHead streamHead) {
        if (!Catalog.EVENTS.containsKey(req.eventType())) {
            throw new Denied("unknown event type " + req.eventType());
        }
        Set<String> allowed = ROLE_RIGHTS.getOrDefault(req.actorRole(), Set.of());
        if (!allowed.contains(req.eventType())) {
            throw new Denied("role " + req.actorRole() + " may not record " + req.eventType());
        }

        boolean isAssetStream = req.streamId().startsWith("asset:");
        if (isAssetStream) {
            Catalog.Verdict verdict = Catalog.canApply(req.currentAssetStatus(), req.eventType());
            if (!verdict.ok()) {
                throw new Denied(verdict.reason());
            }
            if (req.expectedVersion() != null && req.expectedVersion() != streamHead.version()) {
                throw new Conflict(req.streamId(), streamHead.version());
            }
            // Same as Python: having checked it, the current stream version becomes
            // the expected version chain.append() will optimistically re-check.
        }

        Catalog.EventDef def = Catalog.EVENTS.get(req.eventType());
        String eventId = req.eventId() != null ? req.eventId() : UUID.randomUUID().toString();
        String occurredAt = ISO_MILLIS.format(truncateToMillis(req.occurredAt()));
        String recordedAt = ISO_MILLIS.format(truncateToMillis(Instant.now()));

        long globalPosition = chainHead.position() + 1;
        long streamVersion = streamHead.version() + 1;
        String prevHash = chainHead.headHash();
        String streamPrevHash = streamHead.headHash();

        Json.JObject envelope = buildEnvelope(eventId, req.streamId(), streamVersion, req.eventType(),
                1, occurredAt, recordedAt, req.actorId(), req.actorRole(), def.trust().name(),
                req.source(), null, null, req.payload(), Json.jarr(java.util.List.of()));

        String eventHash = Chain.computeHash(prevHash, streamPrevHash, globalPosition, envelope);

        return new AppendedEvent(globalPosition, eventId, req.streamId(), streamVersion, req.eventType(),
                1, occurredAt, recordedAt, req.actorId(), req.actorRole(), def.trust().name(),
                req.source(), prevHash, streamPrevHash, eventHash);
    }

    private static Instant truncateToMillis(Instant t) {
        return Instant.ofEpochMilli(t.toEpochMilli());
    }

    public static Json.JObject buildEnvelope(
            String eventId, String streamId, long streamVersion, String eventType, int schemaVersion,
            String occurredAt, String recordedAt, String actorId, String actorRole, String trustLevel,
            String source, String correlationId, String causationId, JsonValue payload,
            JsonValue attachments) {
        Json.JObject env = Json.jobj();
        env.members().put("event_id", Json.jstr(eventId));
        env.members().put("stream_id", Json.jstr(streamId));
        env.members().put("stream_version", Json.jnum(streamVersion));
        env.members().put("event_type", Json.jstr(eventType));
        env.members().put("schema_version", Json.jnum(schemaVersion));
        env.members().put("occurred_at", Json.jstr(occurredAt));
        env.members().put("recorded_at", Json.jstr(recordedAt));
        env.members().put("actor_id", Json.jstr(actorId));
        env.members().put("actor_role", Json.jstr(actorRole));
        env.members().put("trust_level", Json.jstr(trustLevel));
        env.members().put("source", Json.jstr(source));
        env.members().put("correlation_id", correlationId == null ? Json.jnull() : Json.jstr(correlationId));
        env.members().put("causation_id", causationId == null ? Json.jnull() : Json.jstr(causationId));
        env.members().put("payload", payload);
        env.members().put("attachments", attachments);
        return env;
    }
}
