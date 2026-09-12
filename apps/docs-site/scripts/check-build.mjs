import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {checkBuild} from './lib/build-check.mjs';
import {projectReleaseChangelogs} from './lib/release-changelogs.mjs';
import {smokeReleaseChangelogs} from './lib/release-site-smoke.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const facts = JSON.parse(await readFile(path.join(portalRoot, 'src/generated/site-facts.json'), 'utf8'));
const versionFacts = JSON.parse(await readFile(path.join(portalRoot, 'src/generated/version-facts.json'), 'utf8'));
const releasePages = await projectReleaseChangelogs(path.resolve(portalRoot, '../..'));
const requiredRoutes = [
  '/', '/product/positioning/', '/product/capability-map/', '/product/workflows/',
  '/core/overview/', '/core/modules/foundation/', '/core/modules/authoring-domain/',
  '/core/modules/project-io/', '/core/modules/project-cooker/', '/core/modules/audio-runtime/',
  '/core/modules/provider-sdk/', '/core/modules/application-facade/', '/hosts/overview/',
  '/core/modules/web-runtime-platform/', '/hosts/core-cli/', '/hosts/core-mcp/',
  '/hosts/native-host/', '/hosts/cardputer-host/', '/hosts/web-runtime/', '/hosts/creator-web/',
  '/providers/overview/', '/providers/local-proof/', '/contracts/overview/', '/contracts/cardputer-transfer/',
  '/contracts/project/', '/contracts/project-bundle/', '/contracts/runtime-snapshot/', '/contracts/capability/',
  '/contracts/assembly/', '/contracts/error-module-version/', '/assembly/lmdj/',
  '/platform/native-audio/', '/platform/web-runtime/', '/platform/storage/', '/platform/input/',
  '/operations/testing-and-proof/', '/operations/version-and-release/',
  '/operations/creator-changelog/', '/operations/runtime-changelog/',
  '/operations/documentation-governance/', '/history/legacy-patch-architecture/',
  '/diagrams/lmdj-product.html', '/diagrams/lmdj-product.svg', '/diagrams/lmdj-core.html',
  '/diagrams/web-runtime-platform.html', '/diagrams/web-runtime-platform.svg',
  ...releasePages.map(({file}) => {
    const identity = path.basename(file, '.mdx');
    return identity === 'index' ? '/releases/' : `/releases/${identity}/`;
  }),
];
const errors = await checkBuild({
  buildRoot: path.join(portalRoot, 'build'),
  requiredRoutes,
  expectedIdentity: {productBuild: facts.product.version, revision: facts.revision.slice(0, 12)},
  versionSchemas: Object.fromEntries(
    Object.entries(versionFacts).map(([version, metadata]) => [version, metadata.schema_version]),
  ),
});
// Exercise the same source-content verifier against built HTML before upload.
// Production/Preview still require separate HTTP observations via smoke.mjs.
const releaseContent = await smokeReleaseChangelogs({
  baseUrl: 'https://docs.lmdj.workers.dev', pages: releasePages,
  fetchImpl: async (url) => new Response(await readFile(
    path.join(portalRoot, 'build', new URL(url).pathname, 'index.html')),
  {headers: {'Content-Type': 'text/html'}}),
});
errors.push(...releaseContent.errors);

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`portal build: ${requiredRoutes.length} routes and internal links valid`);
}
