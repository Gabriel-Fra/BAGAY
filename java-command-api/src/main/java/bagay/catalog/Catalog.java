package bagay.catalog;

import java.util.Map;
import java.util.Set;

/**
 * Java mirror of the parts of backend/catalog.py that the command side needs:
 * the trust level per event type, and the lifecycle guard (`can_apply`).
 *
 * Deliberately NOT ported here: `apply`/`rebuild` (folding events into asset
 * state for display) and `summarize` (bilingual UI strings) -- those belong to
 * the query/read side, and ARCHITECTURE.md's module table says read-model
 * concerns don't belong next to command validation. If/when the Java service
 * needs to answer "what is this asset's current state", it should replay the
 * stream itself (same rule the Python command side follows) rather than share
 * this class's job.
 *
 * Keep in sync with backend/catalog.py by hand; both must in turn stay in sync
 * with docs/events/catalog.v1.json (the JSON Schema for payloads).
 */
public final class Catalog {

    public enum Trust {PUBLIC_CLAIM, OFFICER_ATTESTED, APPROVED}

    public record EventDef(Trust trust, boolean publicallyVisible) {
    }

    /** event type -> (trust level it is recorded at, visible on the public QR page) */
    public static final Map<String, EventDef> EVENTS = Map.ofEntries(
            Map.entry("RegistryInitialized", new EventDef(Trust.APPROVED, false)),
            Map.entry("AssetRegistered", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("CustodyAssigned", new EventDef(Trust.OFFICER_ATTESTED, false)),
            Map.entry("CustodyTransferred", new EventDef(Trust.OFFICER_ATTESTED, false)),
            Map.entry("IssueReported", new EventDef(Trust.PUBLIC_CLAIM, true)),
            Map.entry("IssueTriaged", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("InspectionRecorded", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("DamageRecorded", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("WorkOrderOpened", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("RepairStarted", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("RepairCompleted", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("AssetDeclaredUnserviceable", new EventDef(Trust.APPROVED, true)),
            Map.entry("AssetDisposed", new EventDef(Trust.APPROVED, true)),
            Map.entry("EntryCorrected", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("HazardDeclared", new EventDef(Trust.OFFICER_ATTESTED, true)),
            Map.entry("TurnoverSealed", new EventDef(Trust.APPROVED, true)),
            Map.entry("UserEnrolled", new EventDef(Trust.APPROVED, false)),
            Map.entry("UserDeactivated", new EventDef(Trust.APPROVED, false))
    );

    public static final Set<String> APPROVAL_REQUIRED =
            Set.of("AssetDeclaredUnserviceable", "AssetDisposed", "TurnoverSealed");

    // Asset lifecycle states, same spelling as backend/catalog.py.
    public static final String IN_SERVICE = "IN_SERVICE";
    public static final String NEEDS_ATTENTION = "NEEDS_ATTENTION";
    public static final String UNDER_REPAIR = "UNDER_REPAIR";
    public static final String UNSERVICEABLE = "UNSERVICEABLE";
    public static final String DISPOSED = "DISPOSED";

    public record Verdict(boolean ok, String reason) {
    }

    /**
     * Lifecycle guard: observations are accepted in any non-DISPOSED state;
     * transitions have specific preconditions. Mirrors catalog.can_apply
     * exactly, including its error strings (commands.Denied surfaces them).
     *
     * @param status current asset status, or null if the asset has never been registered
     */
    public static Verdict canApply(String status, String eventType) {
        if (eventType.equals("AssetRegistered")) {
            return new Verdict(status == null, "asset already registered");
        }
        if (status == null) {
            return new Verdict(false, "unknown asset");
        }
        if (status.equals(DISPOSED)) {
            return new Verdict(false, "asset is disposed; its history is closed");
        }
        if (eventType.equals("RepairStarted")) {
            return new Verdict(status.equals(NEEDS_ATTENTION) || status.equals(UNDER_REPAIR),
                    "no open need for repair");
        }
        if (eventType.equals("RepairCompleted")) {
            return new Verdict(status.equals(UNDER_REPAIR), "no repair in progress");
        }
        if (eventType.equals("AssetDisposed")) {
            return new Verdict(status.equals(UNSERVICEABLE), "declare the asset unserviceable first");
        }
        if (eventType.equals("AssetDeclaredUnserviceable")) {
            return new Verdict(!status.equals(UNSERVICEABLE), "already unserviceable");
        }
        return new Verdict(true, "");
    }
}
