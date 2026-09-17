import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {runInNewContext} from 'node:vm';
import {webcrypto} from 'node:crypto';

const source = await readFile(new URL('../../../../packages/project-io/src/web/library_opfs_storage.js', import.meta.url), 'utf8');

// Only the browser file boundary is injected. Exercise the production writer
// acquisition and public status mapping, including failure before token creation.
function platform(file) {
  const library = {};
  runInNewContext(source, {LibraryManager: {library}, mergeInto: Object.assign,
    DOMException, crypto: webcrypto, TextEncoder, UTF8ToString: value => value});
  const storage = library.$LmdjOpfs;
  storage.root = {async getDirectoryHandle() {return this;}, async getFileHandle() {return file;}};
  return storage;
}

test('writer lock contention on a valid WebKit file reports busy without creating a lease', async () => {
  const storage = platform({
    async createSyncAccessHandle() {throw new DOMException('', 'InvalidStateError');},
    async getFile() {return new File([], 'lease.lock');},
  });
  await assert.rejects(storage.acquireWriter('project.lmdj', 12, 1), error => storage.status(error) === -3);
  assert.equal(storage.leaseTokens.size, 0);
  assert.equal(storage.leasesByPath.size, 0);
});

test('an invalid file handle is not mislabeled as writer contention', async () => {
  const invalid = new DOMException('', 'InvalidStateError');
  const storage = platform({
    async createSyncAccessHandle() {throw invalid;},
    async getFile() {throw new DOMException('', 'InvalidStateError');},
  });
  await assert.rejects(storage.acquireWriter('project.lmdj', 12, 1), error => error === invalid && storage.status(error) === -5);
});

test('quota failure during writer acquisition retains its original condition', async () => {
  const quota = new DOMException('', 'QuotaExceededError');
  const storage = platform({async createSyncAccessHandle() {throw quota;}});
  await assert.rejects(storage.acquireWriter('project.lmdj', 12, 1), error => error === quota && storage.status(error) === -6);
});

test('invalid state outside writer acquisition retains its original condition', () => {
  assert.equal(platform({}).status(new DOMException('', 'InvalidStateError')), -5);
});

test('invalid state after acquiring a writer closes the access handle without relabeling', async () => {
  const invalid = new DOMException('', 'InvalidStateError');
  let closed = false;
  const storage = platform({async createSyncAccessHandle() {return {
    getSize() {throw invalid;}, close() {closed = true;},
  };}});
  await assert.rejects(storage.acquireWriter('project.lmdj', 12, 1), error => error === invalid && storage.status(error) === -5);
  assert.equal(closed, true);
  assert.equal(storage.leaseTokens.size, 0);
});
