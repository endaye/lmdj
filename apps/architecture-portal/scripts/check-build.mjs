import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {checkBuild} from './lib/build-check.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const facts = JSON.parse(await readFile(path.join(portalRoot, 'src/generated/site-facts.json'), 'utf8'));
const versionFacts = JSON.parse(await readFile(path.join(portalRoot, 'src/generated/version-facts.json'), 'utf8'));
const requiredRoutes = [
  '/', '/product/positioning/', '/product/capability-map/', '/product/workflows/',
  '/core/overview/', '/core/modules/foundation/', '/core/modules/authoring-domain/',
  '/core/modules/project-io/', '/core/modules/project-cooker/', '/core/modules/audio-runtime/',
  '/core/modules/provider-sdk/', '/core/modules/application-facade/', '/hosts/overview/',
  '/core/modules/web-runtime-platform/', '/hosts/core-cli/', '/hosts/core-mcp/',
  '/hosts/native-test-host/', '/hosts/web-runtime/', '/hosts/creator-web/',
  '/providers/overview/', '/providers/local-proof/', '/contracts/overview/',
  '/contracts/project/', '/contracts/project-bundle/', '/contracts/runtime-snapshot/', '/contracts/capability/',
  '/contracts/assembly/', '/contracts/error-module-version/', '/assembly/lmdj/',
  '/platform/native-audio/', '/platform/web-runtime/', '/platform/storage/', '/platform/input/',
  '/operations/testing-and-proof/', '/operations/version-and-release/',
  '/operations/documentation-governance/', '/history/legacy-patch-architecture/',
  '/diagrams/lmdj-product.html', '/diagrams/lmdj-product.svg', '/diagrams/lmdj-core.html',
  '/diagrams/web-runtime-platform.html', '/diagrams/web-runtime-platform.svg',
];
const errors = await checkBuild({
  buildRoot: path.join(portalRoot, 'build'),
  requiredRoutes,
  expectedIdentity: {productBuild: facts.product.version, revision: facts.revision.slice(0, 12)},
  versionSchemas: Object.fromEntries(
    Object.entries(versionFacts).map(([version, metadata]) => [version, metadata.schema_version]),
  ),
});

if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`portal build: ${requiredRoutes.length} routes and internal links valid`);
}
