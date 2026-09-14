// Producer-side recovery check. This is not fresh-clone snapshot acceptance.
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {constants} from 'node:fs';
import {lstat, open, realpath} from 'node:fs/promises';
import path from 'node:path';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {createSquashWitness, resolveIntroducingRevision} from './lib/snapshot-provenance.mjs';

const arguments_ = process.argv.slice(2);
const [version, introducing] = arguments_;
if (arguments_.length !== 2 || !/^\d+\.\d+\.\d+\.\d+$/.test(version ?? '') ||
    !/^[0-9a-f]{40}$/.test(introducing ?? '') || /^0+$/.test(introducing)) {
  console.error('usage: scripts/docs-site.sh verify-witness PRODUCT_BUILD INTRODUCING_REVISION');
  process.exit(64);
}

// This process performs passive Git reads only. Inherited redirect/replacement
// settings, external diff commands and lazy network fetches cannot supply proof.
for (const name of Object.keys(process.env)) if (name.startsWith('GIT_')) delete process.env[name];
Object.assign(process.env, {
  GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_NO_LAZY_FETCH: '1',
  GIT_NO_REPLACE_OBJECTS: '1', GIT_GRAFT_FILE: '/dev/null', GIT_ALLOW_PROTOCOL: '',
  GIT_TERMINAL_PROMPT: '0', GIT_OPTIONAL_LOCKS: '0', GIT_EXTERNAL_DIFF: '/usr/bin/false',
  GIT_CONFIG_COUNT: '3', GIT_CONFIG_KEY_0: 'core.fsmonitor', GIT_CONFIG_VALUE_0: 'false',
  GIT_CONFIG_KEY_1: 'core.hooksPath', GIT_CONFIG_VALUE_1: '/dev/null',
  GIT_CONFIG_KEY_2: 'core.attributesFile', GIT_CONFIG_VALUE_2: '/dev/null',
});
const exec = promisify(execFile);
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const MAX_BYTES = 64 * 1024 * 1024;
function require_(condition, reason) {
  if (!condition) throw new Error(reason);
}

async function readArtifact(root, relative) {
  const filename = path.join(root, relative);
  // Canonical archive paths are used directly; compatibility symlinks are not
  // artifact paths. The owning controller must also hold its checkout writer.
  let parent = root;
  const parts = relative.split('/');
  for (const part of parts.slice(0, -1)) {
    parent = path.join(parent, part);
    const info = await lstat(parent);
    require_(info.isDirectory() && !info.isSymbolicLink(), 'artifact parent is not a real directory');
  }
  const handle = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await handle.stat();
    require_(before.isFile() && before.size <= MAX_BYTES, 'artifact is not a bounded regular file');
    const chunks = [];
    let length = 0;
    while (true) {
      const chunk = Buffer.alloc(Math.min(65536, MAX_BYTES + 1 - length));
      const {bytesRead} = await handle.read(chunk);
      if (!bytesRead) break;
      chunks.push(chunk.subarray(0, bytesRead));
      length += bytesRead;
      require_(length <= MAX_BYTES, 'artifact exceeded its read bound');
    }
    const after = await handle.stat();
    const current = await lstat(filename);
    require_(length === before.size && before.size === after.size && before.mtimeMs === after.mtimeMs &&
      before.ctimeMs === after.ctimeMs && current.isFile() && current.dev === after.dev &&
      current.ino === after.ino, 'artifact changed while reading');
    return Buffer.concat(chunks);
  } finally {
    await handle.close();
  }
}

try {
  const repoRoot = await realpath(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
  const metadataPath = `apps/architecture-portal/versioned_metadata/version-${version}.json`;
  const witnessPath = `apps/architecture-portal/versioned_provenance/version-${version}-squash-witness.json`;
  const metadataRaw = await readArtifact(repoRoot, metadataPath);
  const witnessRaw = await readArtifact(repoRoot, witnessPath);
  const metadata = JSON.parse(metadataRaw.toString('utf8'));
  require_(metadata.schema_version === 2 && metadata.product_build === version, 'metadata identity differs');
  require_(await resolveIntroducingRevision({repoRoot, version, headRevision: introducing}) === introducing,
    'revision is not the actual metadata introduction');
  const {stdout: committedMetadata} = await exec('git', ['cat-file', 'blob', `${introducing}:${metadataPath}`],
    {cwd: repoRoot, encoding: 'buffer', maxBuffer: MAX_BYTES});
  require_(metadataRaw.equals(committedMetadata), 'metadata differs from the introducing commit');
  const expected = await createSquashWitness({repoRoot, metadata, introducingRevision: introducing});
  require_(witnessRaw.equals(Buffer.from(`${JSON.stringify(expected, null, 2)}\n`)),
    'witness bytes differ from the official generator');
  require_((await readArtifact(repoRoot, metadataPath)).equals(metadataRaw) &&
    (await readArtifact(repoRoot, witnessPath)).equals(witnessRaw), 'artifacts changed during verification');
  console.log(JSON.stringify({schema: 'lmdj.snapshot-witness-check.v1', status: 'verified-by-retained-source',
    product_build: version, source_revision: metadata.revision, introducing_revision: introducing,
    source_tree: metadata.source_commit.tree,
    metadata: {path: metadataPath, bytes: metadataRaw.length, sha256: sha256(metadataRaw)},
    witness: {path: witnessPath, bytes: witnessRaw.length, sha256: sha256(witnessRaw)}}));
} catch {
  // Do not serialize Git stderr, paths from corrupt data, or inherited secrets.
  console.error('why: retained-source witness verification failed; remedy: retain the original witness, metadata and source objects, verify the exact introducing SHA and inspect drift without regenerating or overwriting evidence');
  process.exitCode = 1;
}
