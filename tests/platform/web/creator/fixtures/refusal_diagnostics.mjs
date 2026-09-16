import {expect, test as base} from "@playwright/test";

const REFUSAL_DIAGNOSTIC_PREFIX = "lmdj-refusal-diagnostic ";

// Collects the Control Runtime's pre-sanitization refusal diagnostics from the
// page console (the packaged Wasm emits them through Emscripten printErr) and
// attaches the raw lines to the test results, so a failed refusal assertion in
// CI carries the real Facade reason in the uploaded test-results artifact.
export const test = base.extend({
  refusalDiagnostics: [async ({page}, use, testInfo) => {
    const entries = [];
    const onConsole = (message) => {
      const text = message.text();
      if (!text.startsWith(REFUSAL_DIAGNOSTIC_PREFIX)) {
        return;
      }
      let parsed = null;
      try {
        parsed = JSON.parse(text.slice(REFUSAL_DIAGNOSTIC_PREFIX.length));
      } catch {
        parsed = null;
      }
      entries.push({line: text, parsed});
    };
    page.on("console", onConsole);
    await use(entries);
    page.off("console", onConsole);
    if (entries.length > 0) {
      await testInfo.attach("refusal-diagnostics.jsonl", {
        body: entries.map((entry) => entry.line).join("\n") + "\n",
        contentType: "application/x-ndjson",
      });
    }
  }, {auto: true}],
});

export {expect};
