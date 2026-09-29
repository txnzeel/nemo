// Integer tokens become strings before a JavaScript Number can lose precision.
export function exactJSON(text) {
  return JSON.parse(text, (_, value, context) =>
    typeof value === "number" && /^-?\d+$/.test(context.source)
      ? context.source
      : value,
  );
}
export function count(value) {
  return value == null ? "Unknown" : BigInt(value).toLocaleString("en-IN");
}
export function money(value) {
  if (value == null) return "Unknown";
  const n = BigInt(value),
    a = n < 0n ? -n : n;
  return (
    (n < 0n ? "−" : "") +
    "₹" +
    (a / 100n).toLocaleString("en-IN") +
    "." +
    String(a % 100n).padStart(2, "0")
  );
}
export function percent(ratio) {
  if (
    !ratio ||
    ratio.numerator == null ||
    ratio.denominator == null ||
    BigInt(ratio.denominator) === 0n
  )
    return "Unknown";
  const n = BigInt(ratio.numerator),
    d = BigInt(ratio.denominator);
  const a = n < 0n ? -n : n,
    scaled = (a * 10000n + d / 2n) / d;
  return (
    (n < 0n ? "−" : "") +
    String(scaled / 100n) +
    "." +
    String(scaled % 100n).padStart(2, "0") +
    "%"
  );
}
export const routes = new Set([
  "decision-case",
  "analyst",
  "opportunities",
  "decisions",
  "measurement-health",
  "acquisition",
]);
export function apiPath(dataset, view) {
  if (view === "datasets") return "/datasets";
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(dataset || "") || !routes.has(view))
    throw new Error("Unsupported request");
  return "/datasets/" + dataset + "/" + view;
}
export function sameOrigin(headers) {
  const host = headers.get("host");
  if (!/^(127\.0\.0\.1|localhost):\d+$/.test(host || "")) return false;
  const origin = headers.get("origin");
  return (
    (!origin || origin === "http://" + host) &&
    headers.get("sec-fetch-site") !== "cross-site"
  );
}
