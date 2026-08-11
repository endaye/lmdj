import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {readRepoFacts} from '../scripts/lib/repo-facts.mjs';

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../docs');
const versionedDocsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../versioned_docs');
const repoRoot = path.resolve(docsRoot, '../../..');
const transientSnapshotClaim =
  /(?:快照[^。\n]*(?:尚未生成|尚未建立|由下一[^。\n]*Task)|尚未建立[^。\n]*快照|当前缺少[^。\n]*快照|尚无[^。\n]*快照|下一(?:文档)?门禁[^。\n]*建立[^。\n]*快照)/;
const requiredRoutes = [
  'overview/index', 'product/positioning', 'product/capability-map', 'product/workflows',
  'core/overview', 'core/modules/foundation', 'core/modules/authoring-domain', 'core/modules/project-io',
  'core/modules/project-cooker', 'core/modules/audio-runtime', 'core/modules/provider-sdk',
  'core/modules/application-facade', 'core/modules/web-runtime-platform', 'hosts/overview',
  'hosts/core-cli', 'hosts/core-mcp', 'hosts/native-test-host', 'hosts/web-runtime',
  'hosts/creator-web', 'providers/overview', 'providers/local-proof',
  'contracts/overview', 'contracts/project', 'contracts/project-bundle', 'contracts/runtime-snapshot',
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

test('formal snapshot does not describe itself as current main documentation', async () => {
  const body = await readFile(path.join(versionedDocsRoot, 'version-1.0.13.0/overview/index.mdx'), 'utf8');
  assert.doesNotMatch(body, /(?:随 `main` 演进|current 文档|当前文档)/);
  assert.match(body, /正式快照/);
});

test('current overview uses stable doc IDs and all ten diagram callers use validated IDs', async () => {
  const overview = await readFile(path.join(docsRoot, 'overview/index.mdx'), 'utf8');
  const docIds = [...overview.matchAll(/docId:\s*['"]([^'"]+)['"]/g)].map((match) => match[1]);
  assert.equal(docIds.length, 9);
  assert.equal(new Set(docIds).size, 9);
  assert.doesNotMatch(overview, /\bto:\s*['"]/);

  const callers = [
    ['overview/index.mdx', 'lmdj-product'],
    ['core/overview.mdx', 'lmdj-core'],
    ['core/modules/foundation.mdx', 'foundation'],
    ['core/modules/authoring-domain.mdx', 'authoring-domain'],
    ['core/modules/project-io.mdx', 'project-io'],
    ['core/modules/project-cooker.mdx', 'project-cooker'],
    ['core/modules/audio-runtime.mdx', 'audio-runtime'],
    ['core/modules/provider-sdk.mdx', 'provider-sdk'],
    ['core/modules/application-facade.mdx', 'application-facade'],
    ['core/modules/web-runtime-platform.mdx', 'web-runtime-platform'],
  ];
  for (const [relative, diagramId] of callers) {
    const body = await readFile(path.join(docsRoot, relative), 'utf8');
    assert.match(body, new RegExp(`<DiagramFrame[^>]+diagramId=["']${diagramId}["']`));
    assert.doesNotMatch(body, /<DiagramFrame[^>]+(?:html|svg)=/);
  }
});

test('current truth is version-neutral about the formal Web Host, snapshot lifecycle, and evidence', async () => {
  assert.ok(
    requiredRoutes.includes('core/overview'),
    'current truth inventory includes the Core overview',
  );
  const currentPages = await Promise.all(requiredRoutes.map(async (route) => ({
    route,
    body: await readFile(path.join(docsRoot, `${route}.mdx`), 'utf8'),
  })));
  for (const {route, body} of currentPages) {
    assert.doesNotMatch(body, /Task 12[AB]/, `${route} contains task-phase wording`);
    assert.doesNotMatch(
      body,
      transientSnapshotClaim,
      `${route} claims a transient missing snapshot`,
    );
    assert.doesNotMatch(body, /Web Runtime (?:目前是|仍是) Lab\/设计边界/, `${route} describes the formal Host as Lab-only`);
    assert.doesNotMatch(body, /未来正式 Host/, `${route} describes an assembled Host as future`);
  }

  const capability = await readFile(path.join(docsRoot, 'product/capability-map.mdx'), 'utf8');
  const facts = await readRepoFacts({repoRoot, revision: 'current', channel: 'canary'});
  const creatorWeb = facts.hosts.find(({id}) => id === 'creator-web');
  const webRuntime = facts.hosts.find(({id}) => id === 'web-runtime-host');
  assert.ok(creatorWeb, 'current assembly includes Creator Web Host');
  assert.ok(webRuntime, 'current assembly includes Formal Web Runtime Host');
  assert.ok(
    capability.includes(
      `Creator Web Host \`${creatorWeb.version}\` 与 Formal Web Runtime Host \`${webRuntime.version}\` 已装配`,
    ),
    'capability map uses current generated Host identities',
  );
  assert.match(capability, /Web Runtime Lab[^。]+独立实验工具/);

  const proof = await readFile(path.join(docsRoot, 'operations/testing-and-proof.mdx'), 'utf8');
  assert.match(proof, /Product Build `1\.0\.16\.6`/);
  assert.match(proof, /scripts\/creator-web\.sh/);
  assert.match(proof, /不继承历史 Build 的 PR、CI 或 merge 结论/);
  assert.doesNotMatch(proof, /Pull Request CI[^。]+pending/);
  assert.equal((proof.match(/deferred \/ unverified/g) ?? []).length, 5);

  const overview = await readFile(path.join(docsRoot, 'overview/index.mdx'), 'utf8');
  assert.match(overview, /Build Identity[^。]+current[^。]+不可变正式快照/);

  const acceptance = await readFile(
    path.join(repoRoot, 'docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md'),
    'utf8',
  );
  const currentAcceptance = acceptance.split('\n## Task 12A historical outcome')[0];
  assert.doesNotMatch(
    currentAcceptance,
    /(?:1\.0\.15\.0[^\n]*(?:missing|absent)|(?:does not claim|no)[^\n]*1\.0\.15\.0[^\n]*snapshot|Task 4[^\n]*snapshot)/i,
    'current acceptance claims a transient missing snapshot',
  );
});
