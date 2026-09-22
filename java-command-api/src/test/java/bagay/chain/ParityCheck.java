package bagay.chain;

import bagay.chain.Json.JObject;
import bagay.chain.Json.JsonValue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Not a unit test framework test (no JUnit available offline) -- a standalone
 * `main` that proves TODO.md's "Java Command API parity" claim: it hashes the
 * same events Python hashed and diffs the digests.
 *
 * Usage:
 *   java bagay.chain.ParityCheck path/to/hash_vectors.json
 *
 * hash_vectors.json is produced by tools/export_hash_vectors.py against a real
 * seeded log (see java-command-api/README.md). Each element has:
 *   { "global_position": int, "prev_hash": hex, "stream_prev_hash": hex,
 *     "expected_event_hash": hex, "envelope": { ...the 15 envelope fields... } }
 */
public final class ParityCheck {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: ParityCheck <hash_vectors.json>");
            System.exit(2);
        }
        String text = Files.readString(Path.of(args[0]));
        JsonValue root = Json.parse(text);
        if (!(root instanceof Json.JArray arr)) {
            throw new IllegalArgumentException("expected a top-level JSON array");
        }

        int total = 0;
        int mismatches = 0;
        List<String> firstFailures = new java.util.ArrayList<>();

        for (JsonValue item : arr.items()) {
            JObject o = (JObject) item;
            long position = (long) ((Json.JNumber) o.members().get("global_position")).value();
            String prevHash = ((Json.JString) o.members().get("prev_hash")).value();
            String streamPrevHash = ((Json.JString) o.members().get("stream_prev_hash")).value();
            String expected = ((Json.JString) o.members().get("expected_event_hash")).value();
            JObject envelope = (JObject) o.members().get("envelope");

            total++;
            String actual;
            try {
                actual = Chain.computeHash(prevHash, streamPrevHash, position, envelope);
            } catch (RuntimeException e) {
                mismatches++;
                if (firstFailures.size() < 10) {
                    firstFailures.add("position " + position + ": threw " + e);
                }
                continue;
            }
            if (!actual.equals(expected)) {
                mismatches++;
                if (firstFailures.size() < 10) {
                    firstFailures.add("position " + position + ": expected " + expected
                            + " got " + actual);
                }
            }
        }

        System.out.println("events checked: " + total);
        System.out.println("mismatches:     " + mismatches);
        if (!firstFailures.isEmpty()) {
            System.out.println("first failures:");
            for (String f : firstFailures) System.out.println("  " + f);
        }
        if (mismatches > 0) {
            System.exit(1);
        }
        System.out.println("PARITY OK: Java Chain.computeHash reproduced every event_hash from the Python log.");
    }
}
