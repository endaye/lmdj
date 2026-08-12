import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import test from "node:test";

import {
  canonicalJson,
  exactKeys,
  sha256Hex,
} from "../web/integrity.mjs";


test("canonical JSON recursively sorts object keys without reordering arrays", () => {
  assert.equal(
    canonicalJson({z: [{b: 2, a: 1}, 3], a: "value"}),
    '{"a":"value","z":[{"a":1,"b":2},3]}',
  );
});

test("exact-key validation rejects missing, additional, and non-object shapes", () => {
  assert.equal(exactKeys({a: 1, b: 2}, ["b", "a"]), true);
  assert.equal(exactKeys({a: 1}, ["a", "b"]), false);
  assert.equal(exactKeys({a: 1, b: 2, c: 3}, ["a", "b"]), false);
  assert.equal(exactKeys(["a", "b"], ["0", "1"]), false);
  assert.equal(exactKeys(null, []), false);
});

test("SHA-256 returns lowercase hex and fails closed when unavailable", async () => {
  const bytes = new TextEncoder().encode("abc");
  assert.equal(
    await sha256Hex(bytes, webcrypto),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
  await assert.rejects(
    sha256Hex(bytes, {}),
    (error) =>
      error.code === "HOST_PROTOCOL_MISMATCH" &&
      error.message === "SHA-256 is unavailable",
  );
});
