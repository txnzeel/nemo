import test from "node:test";
import assert from "node:assert/strict";
import {
  exactJSON,
  money,
  percent,
  apiPath,
  sameOrigin,
} from "../lib/contracts.mjs";
test("integer wire values retain exact precision and nulls", () => {
  const v = exactJSON(
    '{"paise":9007199254740993,"ratio":{"numerator":1,"denominator":3},"missing":null}',
  );
  assert.equal(v.paise, "9007199254740993");
  assert.equal(money(v.paise), "₹9,00,71,99,25,47,409.93");
  assert.equal(percent(v.ratio), "33.33%");
  assert.equal(money(v.missing), "Unknown");
});
test("undefined rate stays unknown and rounding is explicit", () => {
  assert.equal(percent({ numerator: "0", denominator: "0" }), "Unknown");
  assert.equal(percent({ numerator: "2", denominator: "3" }), "66.67%");
});
test("proxy path rejects arbitrary paths and SQL", () => {
  assert.equal(
    apiPath("manual", "decision-case"),
    "/datasets/manual/decision-case",
  );
  for (const id of ["../private", "https://evil", "a/b", null])
    assert.throws(() => apiPath(id, "decision-case"));
  assert.throws(() => apiPath("manual", "sql"));
});
test("browser boundary rejects remote hosts and cross-site reads", () => {
  assert.equal(sameOrigin(new Headers({ host: "127.0.0.1:3000" })), true);
  for (const headers of [
    { host: "evil.com" },
    { host: "127.0.0.1:3000", origin: "https://evil.com" },
    { host: "localhost:3000", "sec-fetch-site": "cross-site" },
  ])
    assert.equal(sameOrigin(new Headers(headers)), false);
});
