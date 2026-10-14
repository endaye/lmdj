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

// Production JS in two independent realms over shared Wasm-shaped memory.
// These units isolate the JS custody boundary; the real pthread browser witness
// separately proves that C++ creates and retires these pins on production paths.
function sharedWriters({closeFails = false} = {}) {
  const heap = new Uint32Array(new SharedArrayBuffer(256));
  const block = 64;
  const base = block / 4;
  const generation = 17;
  const countPointer = 16;
  heap.set([1, 1, 0, 0, generation, 0, 0, countPointer], base);
  let locked = false;
  let acquisitions = 0;
  let closes = 0;
  let recoveries = 0;
  const freed = [];
  const file = {
    async createSyncAccessHandle() {
      acquisitions += 1;
      if (locked) throw new DOMException('', 'NoModificationAllowedError');
      locked = true;
      return {
        getSize() {return 32;},
        close() {
          if (closeFails) throw new DOMException('', 'InvalidStateError');
          assert.equal(locked, true, 'close must own the genuine physical lock');
          locked = false;
          closes += 1;
        },
      };
    },
    async getFile() {return new File([], 'lease.lock');},
  };
  function realm() {
    const library = {};
    const timers = new Map();
    let nextTimer = 1;
    runInNewContext(source, {
      LibraryManager: {library}, mergeInto: Object.assign,
      DOMException, crypto: webcrypto, TextEncoder,
      UTF8ToString: value => value, HEAPU32: heap,
      _free: pointer => freed.push(pointer),
      _lmdj_project_io_physical_writer_count: () => Atomics.load(heap, countPointer / 4),
      setTimeout(callback, delay) {
        assert.equal(delay, 2);
        const id = nextTimer++;
        timers.set(id, callback);
        return id;
      },
      clearTimeout: id => timers.delete(id),
    });
    const storage = library.$LmdjOpfs;
    storage.root = {async getDirectoryHandle() {return this;},
      async getFileHandle() {return file;}};
    storage.recoverIntents = async () => {recoveries += 1;};
    return {storage, timers, tick() {
      const [id, callback] = timers.entries().next().value ?? [];
      assert.ok(callback, 'a physical owner retry must remain scheduled');
      timers.delete(id);
      callback();
    }};
  }
  const owner = realm();
  const child = realm();
  function pin(remote) {
    if (remote) Atomics.add(heap, base + 2, 1);
    Atomics.add(heap, base + 1, 1);
  }
  function unpin(remote) {
    const gate = Atomics.load(heap, base + 1);
    const count = gate & 0x7fffffff;
    assert.ok(count > 0);
    Atomics.store(heap, base + 1,
        (gate & 0x80000000) | (count === 1 ? 0x80000000 : count - 1));
    if (remote) Atomics.sub(heap, base + 2, 1);
  }
  function retireCppMemory() {
    if (Atomics.sub(heap, base, 1) === 1) freed.push(block);
  }
  return {owner, child, realm, heap, block, base, generation, countPointer,
    pin, unpin, retireCppMemory, freed,
    setCloseFailure(value) {closeFails = value;},
    get acquired() {return acquisitions;}, get recovered() {return recoveries;},
    get locked() {return locked;}, get closed() {return closes;}};
}

async function acquireShared(fixture, realm, borrowed = 0) {
  return realm.storage.acquireWriter('project.lmdj', 12, 1,
      fixture.block, fixture.generation, borrowed);
}

function releaseShared(fixture, realm, token, remote) {
  assert.equal(realm.storage.releaseWriter(token, fixture.block, fixture.generation), true);
  fixture.unpin(remote);
  realm.storage.drainWriters();
}

test('a delegated realm uses the acquired lock without reacquisition or recovery', async () => {
  const f = sharedWriters();
  const rootToken = await acquireShared(f, f.owner);
  f.pin(true);
  const childToken = await acquireShared(f, f.child, 1);
  assert.equal(f.acquired, 1);
  assert.equal(f.recovered, 1);
  assert.equal(f.child.storage.activeLease('/lmdj-workspace/project.lmdj/data', 1).delegated, true);
  assert.throws(() => f.child.storage.activeLease('/lmdj-workspace/project.lmdj/data', 2),
      error => error.name === 'NoModificationAllowedError');
  releaseShared(f, f.child, childToken, true);
  assert.equal(f.child.storage.leaseTokens.size, 0);
  assert.equal(f.child.storage.leasesByPath.size, 0);
  assert.equal(f.locked, true);
  releaseShared(f, f.owner, rootToken, false);
  assert.equal(f.closed, 1);
  f.retireCppMemory();
  assert.deepEqual(f.freed, [f.block]);
});

test('parent release retains physical custody and allows same-platform renewal while a child lives', async () => {
  const f = sharedWriters();
  const rootToken = await acquireShared(f, f.owner);
  f.pin(true);
  const childToken = await acquireShared(f, f.child, 1);
  releaseShared(f, f.owner, rootToken, false);
  assert.equal(f.locked, true);
  assert.throws(() => f.owner.storage.activeLease('/lmdj-workspace/project.lmdj/data', 1),
      error => error.name === 'InvalidStateError');
  await assert.rejects(f.realm().storage.acquireWriter('project.lmdj', 12, 99),
      error => error.name === 'NoModificationAllowedError');
  f.pin(false);
  const renewed = await acquireShared(f, f.owner, 1);
  assert.equal(f.owner.storage.activeLease('/lmdj-workspace/project.lmdj/data', 1).delegated, false);
  releaseShared(f, f.owner, renewed, false);
  releaseShared(f, f.child, childToken, true);
  assert.equal(f.locked, true, 'remote release does not impersonate the owner');
  f.retireCppMemory();
  assert.deepEqual(f.freed, [], 'JS physical owner still holds the shared words');
  f.owner.tick();
  assert.equal(f.closed, 1);
  assert.deepEqual(f.freed, [f.block]);
  assert.equal(f.owner.timers.size, 0);
  const foreign = f.realm().storage;
  const fresh = await foreign.acquireWriter('project.lmdj', 12, 99);
  assert.equal(f.locked, true);
  assert.equal(foreign.releaseWriter(fresh), true);
  assert.equal(f.closed, 2);
});

test('a wrong generation or block cannot erase a same-numbered local lease', async () => {
  const f = sharedWriters();
  const token = await acquireShared(f, f.owner);
  assert.equal(f.owner.storage.releaseWriter(token, f.block, f.generation + 1), false);
  assert.equal(f.owner.storage.releaseWriter(token, f.block + 4, f.generation), false);
  assert.equal(f.owner.storage.leaseTokens.size, 1);
  assert.equal(f.locked, true);
  assert.equal(Atomics.load(f.heap, f.base + 1), 1);
  releaseShared(f, f.owner, token, false);
  f.retireCppMemory();
});

test('terminal release seals admission but cannot acknowledge a genuine remote pin', async () => {
  const f = sharedWriters();
  const rootToken = await acquireShared(f, f.owner);
  f.pin(true);
  const childToken = await acquireShared(f, f.child, 1);
  assert.equal(f.owner.storage.releaseAllWriters(), false);
  assert.equal(f.locked, true);
  assert.equal(f.closed, 0);
  assert.equal(Atomics.load(f.heap, f.base + 1) & 0x7fffffff, 2,
      'terminal authorization must not fabricate C++ releases');
  await assert.rejects(acquireShared(f, f.realm(), 1),
      error => error.name === 'InvalidStateError');
  releaseShared(f, f.child, childToken, true);
  assert.equal(f.owner.storage.releaseAllWriters(), true);
  assert.equal(f.closed, 1);
  assert.equal(f.owner.storage.leaseTokens.has(rootToken), false);
  assert.equal(Atomics.load(f.heap, f.base + 6), 1);
  f.unpin(false); // Later C++ destruction observes the actual physical receipt.
  f.retireCppMemory();
  assert.deepEqual(f.freed, [f.block]);
});

test('an empty local map is not a terminal receipt for a different physical owner realm', async () => {
  const f = sharedWriters();
  const token = await acquireShared(f, f.owner);
  assert.equal(f.child.storage.releaseAllWriters(), false);
  assert.equal(f.locked, true);
  releaseShared(f, f.owner, token, false);
  assert.equal(f.child.storage.releaseAllWriters(), true);
  f.retireCppMemory();
});

test('a failed physical close retains all custody and never reports terminal success', async () => {
  const f = sharedWriters({closeFails: true});
  await acquireShared(f, f.owner);
  assert.equal(f.owner.storage.releaseAllWriters(), false);
  assert.equal(f.locked, true);
  assert.equal(f.owner.storage.leaseTokens.size, 1);
  assert.equal(Atomics.load(f.heap, f.base), 2);
  assert.equal(Atomics.load(f.heap, f.base + 6), 0);
  assert.equal(Atomics.load(f.heap, f.countPointer / 4), 1);
  assert.deepEqual(f.freed, []);
  f.setCloseFailure(false);
  assert.equal(f.owner.storage.releaseAllWriters(), true);
  assert.equal(f.closed, 1);
  f.unpin(false);
  f.retireCppMemory();
  assert.deepEqual(f.freed, [f.block]);
});

test('ordinary inline close failure propagates and preserves the physical owner for a real retry', async () => {
  const f = sharedWriters({closeFails: true});
  const token = await acquireShared(f, f.owner);
  assert.equal(f.owner.storage.releaseWriter(token, f.block, f.generation), true);
  f.unpin(false);
  assert.throws(() => f.owner.storage.drainWriters(), error => error.name === 'InvalidStateError');
  assert.equal(f.locked, true);
  assert.equal(Atomics.load(f.heap, f.countPointer / 4), 1);
  f.retireCppMemory();
  assert.deepEqual(f.freed, []);
  f.setCloseFailure(false);
  f.owner.tick();
  assert.equal(f.closed, 1);
  assert.deepEqual(f.freed, [f.block]);
});

test('initialization failure plus failed close retains unpublished physical custody', async () => {
  const f = sharedWriters({closeFails: true});
  const original = new DOMException('', 'QuotaExceededError');
  f.owner.storage.recoverIntents = async () => {throw original;};
  await assert.rejects(acquireShared(f, f.owner),
      error => error.name === 'InvalidStateError');
  assert.equal(f.owner.storage.leaseTokens.size, 0);
  assert.equal(f.owner.storage.leasesByPath.size, 1);
  assert.equal(f.locked, true);
  assert.equal(Atomics.load(f.heap, f.base), 2);
  assert.equal(Atomics.load(f.heap, f.countPointer / 4), 1);
  assert.throws(() => f.owner.storage.activeLease('/lmdj-workspace/project.lmdj/data', 1),
      error => error.name === 'InvalidStateError');
  assert.equal(f.child.storage.releaseAllWriters(), false);
  assert.equal(f.owner.storage.releaseAllWriters(), false);
  f.setCloseFailure(false);
  assert.equal(f.owner.storage.releaseAllWriters(), true);
  assert.equal(f.closed, 1);
  f.unpin(false);
  f.retireCppMemory();
  assert.deepEqual(f.freed, [f.block]);
});

test('successful cleanup preserves the original recovery error and actual physical receipt', async () => {
  const f = sharedWriters();
  const original = new DOMException('', 'QuotaExceededError');
  f.owner.storage.recoverIntents = async () => {throw original;};
  await assert.rejects(acquireShared(f, f.owner), error => error === original);
  assert.equal(f.owner.storage.leasesByPath.size, 0);
  assert.equal(f.locked, false);
  assert.equal(f.closed, 1);
  assert.equal(Atomics.load(f.heap, f.base + 6), 1);
  assert.equal(Atomics.load(f.heap, f.countPointer / 4), 0);
  f.unpin(false);
  f.retireCppMemory();
  assert.deepEqual(f.freed, [f.block]);
});
