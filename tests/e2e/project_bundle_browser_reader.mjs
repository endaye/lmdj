// Drive the browser Project Bundle reader over a Bundle the product packed.
//
// This harness stands in for the Host bridge only. The Bundle it is given was
// written by the shipped packer over a Project the shipped CLI created, so the
// container shape under test is the product's, never one an author typed. The
// identity this harness echoes on the final index chunk is read independently
// by the Python driver from the packed file, so a reader that parsed a
// different index fails `validateIdentity` rather than being waved through.
//
// usage: node project_bundle_browser_reader.mjs <request-json-path>

import {readFile} from "node:fs/promises";
import {webcrypto} from "node:crypto";

import {importProjectBundle} from
  "../../packages/web-runtime-platform/web/project_bundle_reader.mjs";


const IMPORT_TOKEN = "44444444-4444-4444-8444-444444444444";

async function main() {
  const [requestPath] = process.argv.slice(2);
  if (requestPath === undefined) {
    throw new Error("usage: project_bundle_browser_reader.mjs <request-json>");
  }
  const request = JSON.parse(await readFile(requestPath, "utf-8"));
  const bytes = await readFile(request.bundle_path);
  const file = new Blob([bytes]);

  const operations = [];
  const summary = await importProjectBundle(file, {
    crypto: {subtle: webcrypto.subtle, randomUUID: () => IMPORT_TOKEN},
    send: async (operation, payload) => {
      operations.push(operation);
      if (operation === "project.import.index" && payload.final) {
        return request.identity;
      }
      if (operation === "project.import.commit") {
        return request.summary;
      }
      return {};
    },
  });

  // These two come back through `normalizeLocalProjectSummary`, which the
  // reader calls with the project_id and bundle_digest it parsed out of the
  // Bundle itself, so a reader that read a different index fails there rather
  // than reaching this line. The values are still the driver's, so the
  // load-bearing signals for the caller are the exit status and the operation
  // order, not these fields. The entry count is omitted outright: the stub
  // echoes it and nothing would cross-check it.
  process.stdout.write(JSON.stringify({
    operations,
    project_id: summary.projectId,
    bundle_digest: summary.bundleDigest,
  }));
}

main().catch((error) => {
  process.stderr.write(
    `browser Bundle reader refused the packed Bundle: ` +
    `${error?.code ?? error?.name ?? "Error"}: ${error?.message ?? error}\n`,
  );
  process.exitCode = 1;
});
