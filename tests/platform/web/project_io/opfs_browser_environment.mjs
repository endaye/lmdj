import {execFileSync} from "node:child_process";
import {readFileSync, realpathSync, statSync} from "node:fs";
import {join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

export function resolveOpfsWebkit(repoRoot, selected) {
  try {
    let executable = selected;
    if (!executable) {
      const pkg = join(repoRoot, "tests/platform/web/opfs-browser");
      const installer = join(pkg, "node_modules/playwright");
      const expected = JSON.parse(readFileSync(join(pkg, "package.json"))).devDependencies.playwright;
      const installed = JSON.parse(readFileSync(join(installer, "package.json"))).version;
      if (installed !== expected) throw new Error(`installer version ${installed} differs from ${expected}`);
      // Resolve through the isolated installer's API in its own process: changing
      // PLAYWRIGHT_BROWSERS_PATH in the test process would also redirect Chromium.
      executable = execFileSync(process.execPath, ["-e",
        "process.stdout.write(require(process.argv[1]).webkit.executablePath())", installer], {
        encoding: "utf8",
        env: {...process.env, PLAYWRIGHT_BROWSERS_PATH: join(repoRoot, "build/toolchains/opfs-webkit")},
      }).trim();
    }
    const actual = realpathSync(executable);
    if (!statSync(actual).isFile()) throw new Error("browser executable is not a file");
    return actual;
  } catch (error) {
    throw new Error(`why: OPFS WebKit environment unavailable: ${error.message}; remedy: run bash scripts/prepare-opfs-webkit.sh or provide a valid LMDJ_WEBKIT_OPFS_EXECUTABLE`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = fileURLToPath(new URL("../../../..", import.meta.url));
  try {
    console.log(resolveOpfsWebkit(root, process.env.LMDJ_WEBKIT_OPFS_EXECUTABLE));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
