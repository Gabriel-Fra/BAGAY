package bagay.chain;

import bagay.chain.Json.JArray;
import bagay.chain.Json.JBool;
import bagay.chain.Json.JNull;
import bagay.chain.Json.JNumber;
import bagay.chain.Json.JObject;
import bagay.chain.Json.JString;
import bagay.chain.Json.JsonValue;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * RFC 8785 -- JSON Canonicalization Scheme (JCS).
 *
 * This is the piece {@code backend/chain.py} depends on via the `rfc8785` PyPI
 * package (`rfc8785.dumps(env)`). CLAUDE.md rule #2 says any reimplementation
 * of the hash chain must reproduce Python's output byte for byte, so this class
 * exists to do exactly what that package does: nothing more.
 *
 * Two things make JCS non-trivial to reimplement correctly, and both matter for
 * this project because payloads contain money amounts as floats:
 *
 *  1. Object members are sorted by their UTF-16 code unit sequence. Java's
 *     String.compareTo already does this (it is NOT locale-aware collation),
 *     so a TreeMap<String, JsonValue> with natural ordering is sufficient --
 *     see Json.JObject.
 *
 *  2. Every JSON number is canonicalised as if it were an ECMAScript Number,
 *     using the algorithm in ECMA-262 Number::toString (RFC 8785 section
 *     3.2.2.3). This is why "5" and "5.0" canonicalise identically to "5", and
 *     why 21275.55 must not come out as "21275.55000000001" or similar. Java's
 *     Double.toString already computes the same shortest round-tripping digit
 *     string ECMAScript engines do (both are defined as "the shortest decimal
 *     that uniquely round-trips this double"); {@link #numberToString} only
 *     has to reformat Java's digit string into ECMA-262's notation.
 */
public final class Jcs {

    private Jcs() {
    }

    public static byte[] canonicalize(JsonValue value) {
        StringBuilder sb = new StringBuilder();
        write(value, sb);
        return sb.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static void write(JsonValue value, StringBuilder sb) {
        switch (value) {
            case JNull ignored -> sb.append("null");
            case JBool b -> sb.append(b.value() ? "true" : "false");
            case JNumber n -> sb.append(numberToString(n.value()));
            case JString s -> writeString(s.value(), sb);
            case JArray a -> {
                sb.append('[');
                boolean first = true;
                for (JsonValue item : a.items()) {
                    if (!first) sb.append(',');
                    first = false;
                    write(item, sb);
                }
                sb.append(']');
            }
            case JObject o -> {
                sb.append('{');
                boolean first = true;
                // TreeMap iteration order == sorted-by-UTF-16-code-unit order.
                for (Map.Entry<String, JsonValue> e : o.members().entrySet()) {
                    if (!first) sb.append(',');
                    first = false;
                    writeString(e.getKey(), sb);
                    sb.append(':');
                    write(e.getValue(), sb);
                }
                sb.append('}');
            }
        }
    }

    /** Minimal JSON string escaping: only what is structurally required.
     *  Everything at or above U+0020, including non-ASCII, is emitted as raw
     *  UTF-8 -- JCS does NOT \\u-escape non-ASCII the way ensure_ascii=True
     *  Python json.dumps does. */
    private static void writeString(String s, StringBuilder sb) {
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\b' -> sb.append("\\b");
                case '\f' -> sb.append("\\f");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        sb.append('"');
    }

    /**
     * ECMA-262 Number::toString, restricted to finite doubles (JSON has no NaN
     * or Infinity). Implemented by taking Java's own shortest round-trip digit
     * string (via Double.toString) and reformatting it per the ECMA-262
     * algorithm's four cases, rather than re-deriving the digits ourselves.
     */
    static String numberToString(double x) {
        if (Double.isNaN(x) || Double.isInfinite(x)) {
            throw new IllegalArgumentException("NaN/Infinity is not representable in JSON: " + x);
        }
        if (x == 0.0) {
            return "0"; // covers -0.0 too: (-0).toString() === "0" in ECMAScript
        }
        boolean negative = x < 0;
        double abs = Math.abs(x);

        String javaStr = Double.toString(abs); // e.g. "21275.55", "100.0", "1.0E20"
        String mantissa;
        int exp;
        int ePos = javaStr.indexOf('E');
        if (ePos >= 0) {
            mantissa = javaStr.substring(0, ePos);
            exp = Integer.parseInt(javaStr.substring(ePos + 1));
        } else {
            mantissa = javaStr;
            exp = 0;
        }
        int dot = mantissa.indexOf('.');
        String intPart = mantissa.substring(0, dot);
        String fracPart = mantissa.substring(dot + 1);

        String allDigits = intPart + fracPart;
        int n = exp + intPart.length(); // value == 0.allDigits * 10^n, before stripping zeros

        int firstNonZero = 0;
        while (firstNonZero < allDigits.length() - 1 && allDigits.charAt(firstNonZero) == '0') {
            firstNonZero++;
            n--;
        }
        allDigits = allDigits.substring(firstNonZero);

        int lastNonZero = allDigits.length();
        while (lastNonZero > 1 && allDigits.charAt(lastNonZero - 1) == '0') {
            lastNonZero--;
        }
        String s = allDigits.substring(0, lastNonZero);
        int k = s.length();

        StringBuilder out = new StringBuilder();
        if (negative) out.append('-');

        if (k <= n && n <= 21) {
            out.append(s);
            out.append("0".repeat(n - k));
        } else if (0 < n && n <= 21) {
            out.append(s, 0, n).append('.').append(s, n, k);
        } else if (-6 < n && n <= 0) {
            out.append("0.");
            out.append("0".repeat(-n));
            out.append(s);
        } else {
            String digitsOut = k == 1 ? s : s.charAt(0) + "." + s.substring(1);
            int e = n - 1;
            out.append(digitsOut).append('e').append(e >= 0 ? "+" : "-").append(Math.abs(e));
        }
        return out.toString();
    }
}
