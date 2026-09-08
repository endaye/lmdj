import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {verifyArtifactFiles, waitForArtifactReadiness} from '../scripts/cloudflare-preview-smoke.mjs';

const origin = 'https://12345678-portal-preview.lmdj.workers.dev';
const bytes = Buffer.from('verified file');
const receipt = {url: origin, files: [{path: 'assets/example.js', bytes: bytes.length,
  sha256: createHash('sha256').update(bytes).digest('hex')}]};
const response = (body, url = `${origin}/assets/example.js`) => ({status: 200, url,
  body: (async function* () { yield body; })()});

test('Preview artifact bytes and digest match', async () => {
  assert.deepEqual(await verifyArtifactFiles(receipt, async () => response(bytes)), []);
});
test('changed asset fails even with successful HTTP', async () => {
  assert.equal((await verifyArtifactFiles(receipt, async () => response(Buffer.from('tampered')))).length, 1);
});
test('redirect to a foreign origin fails with identical bytes', async () => {
  assert.equal((await verifyArtifactFiles(receipt, async () => response(bytes, 'https://foreign.example/asset'))).length, 1);
});

test('oversized response stops consuming after the first excess chunk', async () => {
  let reads = 0;
  const result = await verifyArtifactFiles(receipt, async () => ({status: 200,
    url: `${origin}/assets/example.js`, body: (async function* () {
      reads += 1;
      yield Buffer.alloc(bytes.length + 1);
      reads += 1;
      yield Buffer.alloc(1024);
    })()}));
  assert.equal(result.length, 1);
  assert.equal(reads, 1);
});


const entryReceipt = {...receipt, files: [{...receipt.files[0], path: 'index.html'}]};
function readinessClock() {
  let elapsed = 0;
  return {now: () => elapsed, delay: async (ms) => { elapsed += ms; }};
}

test('first-version unavailable entry waits until its exact bytes are ready', async () => {
  let requests = 0;
  await waitForArtifactReadiness(entryReceipt, {...readinessClock(), fetchImpl: async () => {
    requests += 1;
    return requests === 1 ? {status: 404, url: origin} : response(bytes, origin);
  }});
  assert.equal(requests, 2);
});

test('permanently unavailable entry fails at the fixed readiness deadline', async () => {
  const clock = readinessClock();
  await assert.rejects(waitForArtifactReadiness(entryReceipt, {...clock,
    fetchImpl: async () => ({status: 404, url: origin})}), /did not become ready.*reconcile/i);
  assert.equal(clock.now(), 60_000);
});

test('HTTP success with wrong entry bytes never establishes readiness', async () => {
  await assert.rejects(waitForArtifactReadiness(entryReceipt, {...readinessClock(),
    fetchImpl: async () => response(Buffer.from('wrong'), origin)}), /did not become ready/);
});

test('missing verified entry cannot silently skip readiness', async () => {
  await assert.rejects(waitForArtifactReadiness(receipt, {...readinessClock(),
    fetchImpl: async () => { throw new Error('must not fetch'); }}), /verified index.html/);
});


test('entry returned after the readiness deadline is not accepted', async () => {
  const clock = readinessClock();
  await assert.rejects(waitForArtifactReadiness(entryReceipt, {...clock, fetchImpl: async () => {
    await clock.delay(60_001);
    return response(bytes, origin);
  }}), /did not become ready/);
});
