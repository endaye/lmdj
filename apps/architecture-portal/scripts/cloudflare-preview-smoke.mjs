import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {smokePortal} from './lib/smoke.mjs';

export async function verifyArtifactFiles(receipt, fetchImpl = fetch) {
const errors = [];
let cursor = 0;
await Promise.all(Array.from({length: 8}, async () => {
  while (cursor < receipt.files.length) {
    const file = receipt.files[cursor++];
    const path = file.path.split('/').map(encodeURIComponent).join('/');
    try {
      const response = await fetchImpl(`${receipt.url}/${path}`);
      if (new URL(response.url).origin !== receipt.url || response.status !== 200) {
        throw new Error('unexpected response target/status');
      }
      const bytes = Buffer.from(await response.arrayBuffer());
      if (bytes.length !== file.bytes || createHash('sha256').update(bytes).digest('hex') !== file.sha256) {
        throw new Error('bytes differ from verified artifact');
      }
    } catch {
      errors.push(`${file.path}: artifact HTTP verification failed`);
    }
  }
}));
return errors;
}

export async function main(receipt) {
if (!/^https:\/\/[0-9a-f]{8}-portal-preview\.lmdj\.workers\.dev$/.test(receipt.url)) {
  throw new Error('unexpected Preview origin');
}
const errors = await smokePortal({baseUrl: receipt.url, productBuild: receipt.product_build,
  revision: receipt.head_sha.slice(0, 12)});
const root = await fetch(receipt.url, {redirect: 'error'});
for (const [header, value] of Object.entries({'x-content-type-options': 'nosniff',
  'referrer-policy': 'strict-origin-when-cross-origin'})) {
  if (root.headers.get(header) !== value) errors.push(`root ${header} mismatch`);
}
errors.push(...await verifyArtifactFiles(receipt));
if (errors.length) {
  console.error(errors.slice(0, 30).join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Preview verified: ${receipt.head_sha} ${receipt.files.length} files`);
}
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main(JSON.parse(await readFile(process.argv[2], 'utf8')));
}
