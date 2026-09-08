import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {smokePortal} from './lib/smoke.mjs';

export async function verifyArtifactFiles(receipt, fetchImpl = fetch, signal) {
  const errors = [];
  let cursor = 0;
  await Promise.all(Array.from({length: 8}, async () => {
    while (cursor < receipt.files.length) {
      const file = receipt.files[cursor++];
      const path = file.path.split('/').map(encodeURIComponent).join('/');
      try {
        const response = await fetchImpl(`${receipt.url}/${path}`, {signal});
        if (new URL(response.url).origin !== receipt.url || response.status !== 200) {
          throw new Error('unexpected response target/status');
        }
        const digest = createHash('sha256');
        let size = 0;
        for await (const chunk of response.body ?? []) {
          size += chunk.length;
          if (size > file.bytes) throw new Error('response exceeds verified asset length');
          digest.update(chunk);
        }
        if (size !== file.bytes || digest.digest('hex') !== file.sha256) {
          throw new Error('bytes differ from verified artifact');
        }
      } catch {
        errors.push(`${file.path}: artifact HTTP verification failed`);
      }
    }
  }));
  return errors;
}

// A first upload receipt can precede edge asset availability. Readiness only
// waits for the authenticated entry bytes; the complete smoke below still owns
// every route, header and artifact. This runs inside the publisher's unchanged
// 600-second process timeout, not as an extension of that timeout.
export async function waitForArtifactReadiness(receipt, {
  fetchImpl = fetch, now = Date.now,
  delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  const entry = receipt.files.find((file) => file.path === 'index.html');
  if (!entry) throw new Error('Readiness requires verified index.html; reconcile the retained artifact before retry');
  const deadline = now() + 60_000;
  while (true) {
    const requestBudget = deadline - now();
    if (requestBudget <= 0) break;
    const signal = AbortSignal.timeout(Math.min(10_000, requestBudget));
    const errors = await verifyArtifactFiles({...receipt, files: [entry]}, fetchImpl, signal);
    if (!errors.length && now() <= deadline) return;
    const remaining = deadline - now();
    if (remaining > 0) await delay(Math.min(2_000, remaining));
  }
  throw new Error('Preview artifact did not become ready within 60000 ms; reconcile the retained version and exact artifact before retry');
}

export async function main(receipt) {
  if (!/^https:\/\/[0-9a-f]{8}-portal-preview\.lmdj\.workers\.dev$/.test(receipt.url)) {
    throw new Error('unexpected Preview origin');
  }
  await waitForArtifactReadiness(receipt);
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
