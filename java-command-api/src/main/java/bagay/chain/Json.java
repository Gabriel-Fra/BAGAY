package bagay.chain;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * A tiny JSON value model and parser, written by hand because this module must
 * compile with nothing but the JDK (no Maven/Gradle, no network in the target
 * environment -- see java-command-api/README.md for why).
 *
 * JsonValue is deliberately minimal: it exists to (a) parse payload/attachments
 * JSON that arrived from elsewhere, and (b) be canonicalised by {@link Jcs}. It
 * is not a general-purpose JSON library.
 *
 * Object members are stored in a TreeMap using String's natural ordering, which
 * compares by UTF-16 code unit -- the exact ordering RFC 8785 requires for
 * canonical member sort. That means a JsonValue built as JsonValue.of(map) is
 * already in canonical key order by construction.
 */
public abstract class Json {

    private Json() {
    }

    public sealed interface JsonValue permits JNull, JBool, JNumber, JString, JArray, JObject {
    }

    public record JNull() implements JsonValue {
        public static final JNull INSTANCE = new JNull();
    }

    public record JBool(boolean value) implements JsonValue {
    }

    /** All JSON numbers are held as double: RFC 8785 canonicalises every number
     *  as an ECMAScript Number regardless of whether the source text had a
     *  decimal point (see Jcs.numberToString). */
    public record JNumber(double value) implements JsonValue {
    }

    public record JString(String value) implements JsonValue {
    }

    public record JArray(List<JsonValue> items) implements JsonValue {
    }

    /** TreeMap so iteration order is already the canonical (sorted) order. */
    public record JObject(TreeMap<String, JsonValue> members) implements JsonValue {
    }

    public static JsonValue jnull() {
        return JNull.INSTANCE;
    }

    public static JsonValue jbool(boolean b) {
        return new JBool(b);
    }

    public static JsonValue jnum(double d) {
        return new JNumber(d);
    }

    public static JsonValue jstr(String s) {
        return s == null ? JNull.INSTANCE : new JString(s);
    }

    public static JObject jobj() {
        return new JObject(new TreeMap<>());
    }

    public static JObject jobj(Map<String, JsonValue> from) {
        JObject o = jobj();
        o.members().putAll(from);
        return o;
    }

    public static JArray jarr(List<JsonValue> items) {
        return new JArray(items);
    }

    // ------------------------------------------------------------------ parse

    public static JsonValue parse(String text) {
        Parser p = new Parser(text);
        p.skipWs();
        JsonValue v = p.parseValue();
        p.skipWs();
        if (!p.atEnd()) {
            throw new IllegalArgumentException("trailing content at position " + p.pos);
        }
        return v;
    }

    private static final class Parser {
        final String s;
        int pos = 0;

        Parser(String s) {
            this.s = s;
        }

        boolean atEnd() {
            return pos >= s.length();
        }

        char peek() {
            return s.charAt(pos);
        }

        void skipWs() {
            while (!atEnd() && Character.isWhitespace(peek())) pos++;
        }

        void expect(char c) {
            if (atEnd() || peek() != c) {
                throw new IllegalArgumentException("expected '" + c + "' at position " + pos);
            }
            pos++;
        }

        JsonValue parseValue() {
            skipWs();
            if (atEnd()) throw new IllegalArgumentException("unexpected end of input");
            char c = peek();
            return switch (c) {
                case '{' -> parseObject();
                case '[' -> parseArray();
                case '"' -> new JString(parseString());
                case 't' -> {
                    expectLiteral("true");
                    yield new JBool(true);
                }
                case 'f' -> {
                    expectLiteral("false");
                    yield new JBool(false);
                }
                case 'n' -> {
                    expectLiteral("null");
                    yield JNull.INSTANCE;
                }
                default -> parseNumber();
            };
        }

        void expectLiteral(String lit) {
            if (!s.regionMatches(pos, lit, 0, lit.length())) {
                throw new IllegalArgumentException("expected '" + lit + "' at position " + pos);
            }
            pos += lit.length();
        }

        JObject parseObject() {
            expect('{');
            JObject obj = jobj();
            skipWs();
            if (!atEnd() && peek() == '}') {
                pos++;
                return obj;
            }
            while (true) {
                skipWs();
                String key = parseString();
                skipWs();
                expect(':');
                JsonValue val = parseValue();
                obj.members().put(key, val);
                skipWs();
                if (!atEnd() && peek() == ',') {
                    pos++;
                    continue;
                }
                expect('}');
                break;
            }
            return obj;
        }

        JArray parseArray() {
            expect('[');
            List<JsonValue> items = new ArrayList<>();
            skipWs();
            if (!atEnd() && peek() == ']') {
                pos++;
                return new JArray(items);
            }
            while (true) {
                items.add(parseValue());
                skipWs();
                if (!atEnd() && peek() == ',') {
                    pos++;
                    continue;
                }
                expect(']');
                break;
            }
            return new JArray(items);
        }

        String parseString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (true) {
                if (atEnd()) throw new IllegalArgumentException("unterminated string");
                char c = s.charAt(pos++);
                if (c == '"') break;
                if (c == '\\') {
                    char e = s.charAt(pos++);
                    switch (e) {
                        case '"' -> sb.append('"');
                        case '\\' -> sb.append('\\');
                        case '/' -> sb.append('/');
                        case 'b' -> sb.append('\b');
                        case 'f' -> sb.append('\f');
                        case 'n' -> sb.append('\n');
                        case 'r' -> sb.append('\r');
                        case 't' -> sb.append('\t');
                        case 'u' -> {
                            String hex = s.substring(pos, pos + 4);
                            pos += 4;
                            sb.append((char) Integer.parseInt(hex, 16));
                        }
                        default -> throw new IllegalArgumentException("bad escape \\" + e);
                    }
                } else {
                    sb.append(c);
                }
            }
            return sb.toString();
        }

        JsonValue parseNumber() {
            int start = pos;
            if (!atEnd() && peek() == '-') pos++;
            while (!atEnd() && Character.isDigit(peek())) pos++;
            if (!atEnd() && peek() == '.') {
                pos++;
                while (!atEnd() && Character.isDigit(peek())) pos++;
            }
            if (!atEnd() && (peek() == 'e' || peek() == 'E')) {
                pos++;
                if (!atEnd() && (peek() == '+' || peek() == '-')) pos++;
                while (!atEnd() && Character.isDigit(peek())) pos++;
            }
            String num = s.substring(start, pos);
            if (num.isEmpty() || num.equals("-")) {
                throw new IllegalArgumentException("invalid number at position " + start);
            }
            return new JNumber(Double.parseDouble(num));
        }
    }
}
