import {test} from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {resolveOpfsWebkit} from "./opfs_browser_environment.mjs";

function environment(t, installedVersion = "1.2.3") {
  const root = mkdtempSync(join(tmpdir(), "lmdj-opfs-env-"));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  const pkg = join(root, "tests/platform/web/opfs-browser");
  const module = join(pkg, "node_modules/playwright");
  mkdirSync(module, {recursive: true});
  writeFileSync(join(pkg, "package.json"), JSON.stringify({devDependencies: {playwright: "1.2.3"}}));
  writeFileSync(join(module, "package.json"), JSON.stringify({version: installedVersion, main: "index.cjs"}));
  // Characterize executable resolution through the installer's public API,
  // keeping this unit test independent of network/browser downloads.
  writeFileSync(join(module, "index.cjs"), `exports.webkit = {executablePath() {
    return require('node:path').join(process.env.PLAYWRIGHT_BROWSERS_PATH, 'webkit-test', 'pw_run.sh');
  }};`);
  const executable = join(root, "build/toolchains/opfs-webkit/webkit-test/pw_run.sh");
  mkdirSync(join(executable, ".."), {recursive: true});
  writeFileSync(executable, "fixture");
  return {root, executable};
}

test("default resolution uses the isolated browser cache, not the shared cache", t => {
  const {root, executable} = environment(t);
  assert.equal(resolveOpfsWebkit(root, undefined), executable);
});

test("mismatched installer version is refused before browser use", t => {
  const {root} = environment(t, "9.9.9");
  assert.throws(() => resolveOpfsWebkit(root, undefined), /why:.*version.*remedy:/s);
});

test("missing installed executable fails with setup remedy instead of fallback", t => {
  const {root, executable} = environment(t);
  rmSync(executable);
  assert.throws(() => resolveOpfsWebkit(root, undefined), /why:.*remedy:.*prepare-opfs-webkit/s);
});

test("explicit executable override is validated and preserved", t => {
  const {root, executable} = environment(t, "9.9.9");
  assert.equal(resolveOpfsWebkit(root, executable), executable);
  assert.throws(() => resolveOpfsWebkit(root, join(root, "absent")), /why:.*remedy:/s);
});

test("CLI resolves its repository independently of caller working directory", t => {
  const {root, executable} = environment(t);
  const folder = join(root, "tests/platform/web/project_io");
  mkdirSync(folder, {recursive: true});
  const script = join(folder, "opfs_browser_environment.mjs");
  writeFileSync(script, readFileSync(fileURLToPath(new URL("./opfs_browser_environment.mjs", import.meta.url))));
  const env = {...process.env};
  delete env.LMDJ_WEBKIT_OPFS_EXECUTABLE;
  assert.equal(execFileSync(process.execPath, [script], {cwd: tmpdir(), env, encoding: "utf8"}).trim(), executable);
});
