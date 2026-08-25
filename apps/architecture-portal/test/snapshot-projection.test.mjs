import assert from 'node:assert/strict';
import test from 'node:test';

import {checkSnapshotProjection} from '../scripts/check-snapshot-projection.mjs';

const METADATA = 'apps/architecture-portal/versioned_metadata/version-1.0.31.0.json';

function projection(files) {
  return {sha256: files.map((file) => file.sha256).join('-'), files};
}

const RECORDED = projection([
  {path: 'apps/architecture-portal/docs/hosts/native-host.mdx', bytes: 3, sha256: 'aaa'},
  {path: 'products/lmdj/assembly.json', bytes: 5, sha256: 'bbb'},
]);

function readMetadata(metadata) {
  return async () => metadata;
}

test('a change that introduces no snapshot metadata is not this gate\'s subject', async () => {
  const errors = await checkSnapshotProjection({
    addedFiles: ['scripts/core.sh', 'apps/architecture-portal/docs/hosts/native-host.mdx'],
    readMetadata: async () => assert.fail('no metadata should be read'),
    readProjection: async () => assert.fail('no projection should be computed'),
  });
  assert.deepEqual(errors, []);
});

test('a snapshot whose projection matches the merge target passes', async () => {
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async (paths) => {
      assert.deepEqual(paths, RECORDED.files.map((file) => file.path));
      return RECORDED;
    },
  });
  assert.deepEqual(errors, []);
});

test('a projected file changed after the snapshot was taken fails with its remedy', async () => {
  // The #282 shape: the snapshot is taken mid-branch, then the branch keeps
  // moving. On main the squash is the introducing commit, so the recorded
  // projection is compared against exactly this tree and no longer matches.
  const moved = projection([
    {...RECORDED.files[0], sha256: 'ccc'},
    RECORDED.files[1],
  ]);
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async () => moved,
  });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /does not match this change's own tree/);
  assert.match(errors[0], /scripts\/architecture-portal\.sh version 1\.0\.31\.0/);
});

test('a projected path renamed out of the tree fails with its remedy', async () => {
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async () => {
      throw new Error('path does not exist in revision');
    },
  });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /absent from this change's own tree/);
  assert.match(errors[0], /scripts\/architecture-portal\.sh version 1\.0\.31\.0/);
});

test('metadata without a usable projection fails closed instead of passing empty', async () => {
  for (const metadata of [{}, {source_projection: {}}, {source_projection: {files: [{}]}}]) {
    const errors = await checkSnapshotProjection({
      addedFiles: [METADATA],
      readMetadata: readMetadata(metadata),
      readProjection: async () => assert.fail('no projection should be computed'),
    });
    assert.equal(errors.length, 1);
    assert.match(errors[0], /carries no source projection/);
  }
});

test('an unreadable snapshot is reported, and a removed one is not this gate\'s subject', async () => {
  const unreadable = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: async () => {
      throw new Error('unexpected end of JSON input');
    },
    readProjection: async () => assert.fail('no projection should be computed'),
  });
  assert.equal(unreadable.length, 1);
  assert.match(unreadable[0], /cannot be read from the merge target/);

  const removed = await checkSnapshotProjection({
    addedFiles: [METADATA],
    readMetadata: async () => null,
    readProjection: async () => assert.fail('no projection should be computed'),
  });
  assert.deepEqual(removed, []);
});

test('every changed snapshot is reported once, in path order', async () => {
  const second = 'apps/architecture-portal/versioned_metadata/version-1.0.30.0.json';
  const errors = await checkSnapshotProjection({
    addedFiles: [METADATA, second, METADATA],
    readMetadata: readMetadata({source_projection: RECORDED}),
    readProjection: async () => projection([]),
  });
  assert.equal(errors.length, 2);
  assert.match(errors[0], /version-1\.0\.30\.0\.json/);
  assert.match(errors[1], /version-1\.0\.31\.0\.json/);
});
