#!/usr/bin/env node

import { readFileSync } from "node:fs";

import { evaluatePhysicalMatrix } from "./physical-gate.mjs";


function usageError(message) {
  process.stderr.write(`${JSON.stringify({ error: message })}\n`);
  process.exitCode = 64;
}


if (process.argv.length !== 3) {
  usageError("usage: evaluate-physical-evidence.mjs EVIDENCE.json");
} else {
  try {
    const evidence = JSON.parse(readFileSync(process.argv[2], "utf8"));
    const evaluation = evaluatePhysicalMatrix(evidence);
    process.stdout.write(`${JSON.stringify(evaluation, null, 2)}\n`);
    process.exitCode = evaluation.status === "passed"
      ? 0
      : evaluation.status === "failed"
        ? 1
        : 2;
  } catch (error) {
    usageError(error instanceof Error ? error.message : String(error));
  }
}
