#!/usr/bin/env node

import { readFileSync } from "node:fs";

import { preparePhysicalEvidence } from "./physical-evidence-preparer.mjs";


function usageError(message) {
  process.stderr.write(`${JSON.stringify({ error: message })}\n`);
  process.exitCode = 64;
}


function parseArguments(arguments_) {
  if (arguments_.length !== 6) {
    throw new TypeError(
      "usage: prepare-physical-evidence.mjs ROW_KEY REPORT.json --os-version VERSION --browser-version VERSION",
    );
  }
  const [rowKey, reportPath, ...options] = arguments_;
  const parsed = {};
  for (let index = 0; index < options.length; index += 2) {
    const name = options[index];
    const value = options[index + 1];
    if (name === "--os-version" && parsed.osVersion === undefined) {
      parsed.osVersion = value;
    } else if (
      name === "--browser-version"
      && parsed.browserVersion === undefined
    ) {
      parsed.browserVersion = value;
    } else {
      throw new TypeError(`unknown or duplicate option: ${name}`);
    }
  }
  return { rowKey, reportPath, options: parsed };
}


try {
  const parsed = parseArguments(process.argv.slice(2));
  const report = JSON.parse(readFileSync(parsed.reportPath, "utf8"));
  const prepared = preparePhysicalEvidence(
    parsed.rowKey,
    report,
    parsed.options,
  );
  process.stdout.write(`${JSON.stringify(prepared, null, 2)}\n`);
} catch (error) {
  usageError(error instanceof Error ? error.message : String(error));
}
