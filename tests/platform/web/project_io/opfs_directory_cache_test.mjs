import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {runInNewContext} from 'node:vm';

const source = await readFile(new URL('../../../../packages/project-io/src/web/library_opfs_storage.js', import.meta.url), 'utf8');

// An in-memory OPFS whose handles name an entry, not a path: a handle to a
// removed directory fails every later lookup, even after a directory of the
// same name is created again. That is the stricter of the browser semantics
// (a path-addressed handle would follow the new directory), so a cache that
// is correct here is correct for both.
class Directory {
  constructor() { this.entries = new Map(); this.removed = false; }
  remove() {
    this.removed = true;
    for (const entry of this.entries.values()) if (entry instanceof Directory) entry.remove();
  }
}

function storage() {
  const root = new Directory();
  const counts = {lookups: 0};
  const handle = (node) => ({
    kind: 'directory',
    async getDirectoryHandle(name, {create} = {}) {
      counts.lookups += 1;
      if (node.removed) throw new DOMException('', 'NotFoundError');
      let child = node.entries.get(name);
      if (!child && create) node.entries.set(name, child = new Directory());
      if (!child) throw new DOMException('', 'NotFoundError');
      if (!(child instanceof Directory)) throw new DOMException('', 'TypeMismatchError');
      return handle(child);
    },
    async getFileHandle(name) {
      if (node.removed) throw new DOMException('', 'NotFoundError');
      const file = node.entries.get(name);
      if (!(file instanceof File)) throw new DOMException('', 'NotFoundError');
      return {getFile: async () => file};
    },
    async removeEntry(name) {
      if (node.removed || !node.entries.has(name)) throw new DOMException('', 'NotFoundError');
      const removed = node.entries.get(name);
      if (removed instanceof Directory) removed.remove();
      node.entries.delete(name);
    },
  });
  // Another realm's view of the same origin storage: it never touches the
  // library's cache.
  const external = {
    node(parts) { return parts.reduce((node, part) => node.entries.get(part), root); },
    mkdir(parts) {
      let node = root;
      for (const part of parts) {
        if (!node.entries.has(part)) node.entries.set(part, new Directory());
        node = node.entries.get(part);
      }
      return node;
    },
    remove(parts) {
      const parent = this.node(parts.slice(0, -1));
      parent.entries.get(parts.at(-1)).remove();
      parent.entries.delete(parts.at(-1));
    },
  };
  const library = {};
  const context = {LibraryManager: {library}, mergeInto: Object.assign, DOMException,
    UTF8ToString: value => value,
    Asyncify: {State: {Normal: 0}, state: 0, currData: 0, handleAsync(work) { return work(); }}};
  runInNewContext(source, context);
  context.LmdjOpfs = library.$LmdjOpfs;
  context.LmdjOpfs.root = handle(root);
  const call = (name, path) => library[name](path, path.length);
  return {counts, external, call,
    exists: (path) => call('lmdj_opfs_directory_exists', path),
    size: (path) => call('lmdj_opfs_byte_length', path)};
}

const bundle = ['projects', 'p1', 'bundle.lmdj', 'history', 'transactions'];
const path = (parts) => `/lmdj-workspace/${parts.join('/')}`;

test('a repeated lookup asks the browser only for the last level', async () => {
  const fixture = storage();
  fixture.external.mkdir(bundle);
  assert.equal(await fixture.exists(path(bundle)), 1);
  assert.equal(fixture.counts.lookups, bundle.length);
  fixture.counts.lookups = 0;
  assert.equal(await fixture.exists(path(bundle)), 1);
  assert.equal(fixture.counts.lookups, 1);
  // Absence below a cached ancestor is confirmed again from the root.
  fixture.counts.lookups = 0;
  assert.equal(await fixture.exists(path([...bundle.slice(0, 3), 'assets'])), 0);
  assert.equal(fixture.counts.lookups, 1 + 4);
});

test('a directory another realm removed is never reported from memory', async () => {
  const fixture = storage();
  fixture.external.mkdir(bundle);
  assert.equal(await fixture.exists(path(bundle)), 1);
  fixture.external.remove(bundle);
  assert.equal(await fixture.exists(path(bundle)), 0);
  fixture.external.remove(bundle.slice(0, 3));
  assert.equal(await fixture.exists(path(bundle.slice(0, 4))), 0);
  assert.equal(await fixture.exists(path(bundle.slice(0, 3))), 0);
});

test('an ancestor another realm replaced is resolved again from the root', async () => {
  const fixture = storage();
  fixture.external.mkdir(bundle);
  assert.equal(await fixture.exists(path(bundle)), 1);
  fixture.external.remove(bundle.slice(0, 2));
  fixture.external.mkdir(bundle).entries.set('t1.json', new File(['abc'], 't1.json'));
  assert.equal(await fixture.exists(path(bundle)), 1);
  assert.equal(await fixture.size(path([...bundle, 't1.json'])), 3);
});

test('the library forgets a tree it removes and creates it again', async () => {
  const fixture = storage();
  fixture.external.mkdir(bundle);
  assert.equal(await fixture.exists(path(bundle)), 1);
  assert.equal(await fixture.call('lmdj_opfs_remove_tree', path(bundle.slice(0, 3))), 0);
  assert.equal(await fixture.exists(path(bundle)), 0);
  assert.equal(await fixture.call('lmdj_opfs_ensure_directory', path(bundle)), 0);
  assert.equal(await fixture.exists(path(bundle)), 1);
});
