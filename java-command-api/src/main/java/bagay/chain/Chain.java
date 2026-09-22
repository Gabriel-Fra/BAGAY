package bagay.chain;

import bagay.chain.Json.JsonValue;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

/**
 * Java port of backend/chain.py's hashing core.
 *
 *     event_hash = SHA-256( prev_hash || stream_prev_hash || int64_be(position) || JCS(envelope) )
 *
 * ARCHITECTURE.md invariant #2 says any other implementation of this formula
 * "must match it byte for byte." This class is that other implementation.
 *
 * Deliberately out of scope here (left to the PostgreSQL-wiring TODO item):
 * reading/writing es_events, the chain-head row lock, optimistic concurrency.
 * This class only computes the hash from already-known inputs, which is the
 * part that has to be provably identical across languages.
 */
public final class Chain {

    /** 64 hex zero characters -- the "no previous event" sentinel, same as
     *  Python's chain.ZERO. */
    public static final String ZERO = "0".repeat(64);

    public static final List<String> ENVELOPE_FIELDS = List.of(
            "event_id", "stream_id", "stream_version", "event_type", "schema_version",
            "occurred_at", "recorded_at", "actor_id", "actor_role", "trust_level",
            "source", "correlation_id", "causation_id", "payload", "attachments");

    private Chain() {
    }

    /**
     * @param prevHash          hex-encoded SHA-256 of the previous event in the whole log (or ZERO)
     * @param streamPrevHash    hex-encoded SHA-256 of the previous event in this stream (or ZERO)
     * @param position          this event's global_position (1-based)
     * @param envelope          the envelope object, containing exactly ENVELOPE_FIELDS as keys
     * @return hex-encoded SHA-256 event_hash
     */
    public static String computeHash(String prevHash, String streamPrevHash, long position,
                                      Json.JObject envelope) {
        for (String field : ENVELOPE_FIELDS) {
            if (!envelope.members().containsKey(field)) {
                throw new IllegalArgumentException("envelope missing field: " + field);
            }
        }
        if (envelope.members().size() != ENVELOPE_FIELDS.size()) {
            throw new IllegalArgumentException("envelope has unexpected extra fields");
        }
        byte[] canonical = Jcs.canonicalize(envelope);
        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            sha256.update(hexToBytes(prevHash));
            sha256.update(hexToBytes(streamPrevHash));
            sha256.update(int64Be(position));
            sha256.update(canonical);
            return bytesToHex(sha256.digest());
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    static byte[] int64Be(long value) {
        byte[] b = new byte[8];
        for (int i = 7; i >= 0; i--) {
            b[i] = (byte) (value & 0xFF);
            value >>>= 8;
        }
        return b;
    }

    static byte[] hexToBytes(String hex) {
        if (hex.length() % 2 != 0) throw new IllegalArgumentException("odd-length hex: " + hex);
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(hex.substring(2 * i, 2 * i + 2), 16);
        }
        return out;
    }

    static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) sb.append(String.format("%02x", b));
        return sb.toString();
    }
}
