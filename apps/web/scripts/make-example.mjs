// 生成内置示例 patch：从 demo output/testsong 的 patchify 产物拷贝。
// 前置：仓库根目录先运行 `scripts/dev.sh smoke`。
// 约束（spec）：只含 patch.json + samples/*.wav；总体积 ≤ 2MB；不含 preview wav。
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = resolve(webRoot, "../../references/demos/lmdj-song-pipeline/output/testsong");
const DST = resolve(webRoot, "public/example-patch");
const LIMIT = 2 * 1024 * 1024;

if (!existsSync(join(SRC, "patch.json"))) {
  console.error(`missing ${join(SRC, "patch.json")} — 先在仓库根目录运行: scripts/dev.sh smoke`);
  process.exit(1);
}

rmSync(DST, { recursive: true, force: true });
mkdirSync(DST, { recursive: true });
copyFileSync(join(SRC, "patch.json"), join(DST, "patch.json"));

const patch = JSON.parse(readFileSync(join(DST, "patch.json"), "utf8"));
let total = statSync(join(DST, "patch.json")).size;
for (const el of patch.elements) {
  const dst = join(DST, el.source_path);
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(join(SRC, el.source_path), dst);
  total += statSync(dst).size;
}

if (total > LIMIT) {
  console.error(`example patch is ${total} bytes (> ${LIMIT}) — 超出 2MB 上限，拒绝生成`);
  rmSync(DST, { recursive: true, force: true });
  process.exit(1);
}
console.log(`example-patch generated: ${patch.patch_id}, ${total} bytes`);
console.log("provenance: scripts/dev.sh smoke → lmdj-patchify output/testsong");
