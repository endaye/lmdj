import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../docs');
const requiredRoutes = [
  'overview/index', 'product/positioning', 'product/capability-map', 'product/workflows',
  'core/modules/foundation', 'core/modules/authoring-domain', 'core/modules/project-io',
  'core/modules/project-cooker', 'core/modules/audio-runtime', 'core/modules/provider-sdk',
  'core/modules/application-facade', 'hosts/overview', 'hosts/core-cli', 'hosts/core-mcp',
  'hosts/native-test-host', 'hosts/web-runtime', 'providers/overview', 'providers/local-proof',
  'contracts/overview', 'contracts/project', 'contracts/runtime-snapshot',
  'contracts/capability', 'contracts/assembly', 'contracts/error-module-version',
  'assembly/lmdj', 'platform/native-audio', 'platform/web-runtime', 'platform/storage',
  'platform/input', 'operations/testing-and-proof', 'operations/version-and-release',
  'operations/documentation-governance', 'history/legacy-patch-architecture',
];

test('every approved route has a non-placeholder page', async () => {
  for (const route of requiredRoutes) {
    const body = await readFile(path.join(docsRoot, `${route}.mdx`), 'utf8');
    assert.doesNotMatch(body, /\b(TBD|TODO|FIXME)\b/);
    assert.match(body, /## /);
  }
});
