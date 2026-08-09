import assert from "node:assert/strict";
import test from "node:test";

import {
  createDiagnosticClient,
  registerDiagnosticTransport,
} from "../web/diagnostic_client.mjs";


test("exposes only the three conformance mutations through private binding", async () => {
  const calls = [];
  const session = Object.freeze({start() {}});
  registerDiagnosticTransport(session, async (operation, payload, options) => {
    calls.push({operation, payload, options});
    return {project_revision: calls.length};
  });
  const client = createDiagnosticClient(session);
  assert.deepEqual(Object.keys(client).sort(), [
    "assignPad",
    "createProject",
    "importAsset",
  ]);

  assert.deepEqual(await client.createProject({project_id: "project"}), {
    project_revision: 1,
  });
  const bytes = new Uint8Array([1, 2, 3]);
  assert.deepEqual(await client.importAsset({asset_id: "asset"}, bytes), {
    project_revision: 2,
  });
  assert.deepEqual(await client.assignPad({slot: {bank: 0, pad: 0}}), {
    project_revision: 3,
  });
  assert.deepEqual(calls, [
    {
      operation: "project.create",
      payload: {project_id: "project"},
      options: {},
    },
    {
      operation: "asset.import",
      payload: {asset_id: "asset"},
      options: {sidecar: bytes},
    },
    {
      operation: "pad.assign",
      payload: {slot: {bank: 0, pad: 0}},
      options: {},
    },
  ]);
});

test("rejects an unbound or duplicate diagnostic binding", () => {
  assert.throws(() => createDiagnosticClient(Object.freeze({})), TypeError);
  const session = Object.freeze({});
  registerDiagnosticTransport(session, async () => ({}));
  assert.throws(
    () => registerDiagnosticTransport(session, async () => ({})),
    TypeError,
  );
});
