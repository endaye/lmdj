# LMDJ Architecture Portal Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, govern, version, validate, and automatically publish the complete LMDJ internal product manual at `lmdj.netlify.app`.

**Architecture:** An isolated Docusaurus application under `apps/architecture-portal/` owns current and versioned Markdown/MDX pages. Project-local Node scripts derive display facts from Product/Module/Host/Provider/Contract manifests, render deterministic diagrams, validate documentation contracts, and smoke-test generated or deployed routes; repository wrappers, CI, governance, and Netlify configuration make those checks part of normal implementation and release flow.

**Tech Stack:** Node.js `>=22.13.0`; npm lockfile; Docusaurus `3.10.2`; React/React DOM `19.2.8`; TypeScript `6.0.2`; Node test runner; `gray-matter` `4.0.3`; `yaml` `2.9.0`; `glob` `13.0.6`; `cheerio` `1.2.0`; Netlify CLI `27.0.2`; Bash; GitHub Actions; Netlify static hosting.

## Global Constraints

- Work only in the isolated `feat/architecture-portal` worktree; never edit or commit on `main`.
- Every Task is one reviewable Conventional Commit and stages only its declared files.
- The portal is Chinese-first; source identifiers, Module IDs, Contract IDs, APIs, commands, typed errors, and states remain exact English identifiers.
- Current pages must not present `lmdj.patch.v1` or `lmdj.materials.v1` as active. Those strings are allowed only under `history/` with `status: retired`.
- Current Product/Module/Host/Provider/Contract versions are generated from repository manifests and never hand-maintained in page front matter.
- Every current Assembly Module, Host, Provider, and Contract must resolve to a portal page or generated inventory entry.
- Every implemented Core Module must have a dedicated page and deterministic diagram.
- `apps/architecture-portal/` has its own `package.json` and lockfile; do not add a root `package.json` or global package requirement.
- Build output and generated current facts are untracked; diagram sources and diagram HTML/SVG outputs are tracked and freshness-checked.
- Documentation snapshots use four-part Product Build identity, not SemVer, and live at `/versions/PRODUCT_BUILD/`.
- A formal snapshot never mutates an existing version or guesses product identity.
- Local build, CI, Netlify Deploy Preview, production deploy, and public smoke are separate evidence states.
- Push, Pull Request, merge, tag, release, publication, deployment, and Channel promotion remain separately authorized.

## File map

| Path | Responsibility |
| --- | --- |
| `apps/architecture-portal/package.json` | pinned portal toolchain and stable npm commands |
| `apps/architecture-portal/docusaurus.config.ts` | root docs routing, versions, navbar, metadata, broken-link policy |
| `apps/architecture-portal/sidebars.ts` | explicit whole-product navigation order |
| `apps/architecture-portal/docs/**` | current manual content |
| `apps/architecture-portal/versioned_docs/**` | immutable formal Product Build snapshots |
| `apps/architecture-portal/versioned_sidebars/**` | frozen snapshot navigation |
| `apps/architecture-portal/versioned_metadata/**` | frozen Product Build, revision, and Assembly lock facts |
| `apps/architecture-portal/src/components/**` | identity, status, navigation, and diagram presentation |
| `apps/architecture-portal/src/css/custom.css` | portal visual system and responsive behavior |
| `apps/architecture-portal/diagrams/*.architecture.json` | tracked diagram topology and labels |
| `apps/architecture-portal/static/diagrams/**` | tracked generated standalone SVG/HTML artifacts |
| `apps/architecture-portal/scripts/lib/**` | reusable facts, metadata, diagram, route, and smoke libraries |
| `apps/architecture-portal/scripts/*.mjs` | command entry points |
| `apps/architecture-portal/test/*.test.mjs` | Node unit and fixture tests |
| `scripts/architecture-portal.sh` | repository-stable install/dev/build/check/version/smoke interface |
| `docs/governance/architecture-portal.md` | canonical documentation-impact and publication policy |
| `.github/workflows/architecture-portal.yml` | PR and `main` portal gate |
| `.github/workflows/architecture-portal-smoke.yml` | post-deployment public verification |
| `netlify.toml` | repository-owned production build and publish contract |

---

### Task 1: Scaffold the isolated Docusaurus portal and stable command

**Files:**
- Create: `apps/architecture-portal/package.json`
- Create: `apps/architecture-portal/package-lock.json`
- Create: `apps/architecture-portal/tsconfig.json`
- Create: `apps/architecture-portal/docusaurus.config.ts`
- Create: `apps/architecture-portal/sidebars.ts`
- Create: `apps/architecture-portal/src/css/custom.css`
- Create: `apps/architecture-portal/docs/overview/index.mdx`
- Create: `apps/architecture-portal/static/img/logo.svg`
- Create: `apps/architecture-portal/test/entrypoint.test.mjs`
- Create: `scripts/architecture-portal.sh`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Node.js 22 and npm.
- Produces: `scripts/architecture-portal.sh install|dev|build|check|version|smoke`; Docusaurus build output at `apps/architecture-portal/build/`.

- [ ] **Step 1: Write the failing stable-entrypoint test**

```js
// apps/architecture-portal/test/entrypoint.test.mjs
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');
const wrapper = path.join(repoRoot, 'scripts/architecture-portal.sh');

test('wrapper rejects an unsupported command with usage status', () => {
  const result = spawnSync(wrapper, ['unknown'], {encoding: 'utf8'});
  assert.equal(result.status, 64);
  assert.match(result.stderr, /usage:/);
});

test('portal package is private and pins Node 22', async () => {
  const manifest = (await import('../package.json', {with: {type: 'json'}})).default;
  assert.equal(manifest.private, true);
  assert.equal(manifest.engines.node, '>=22.13.0');
});
```

- [ ] **Step 2: Run the test and verify the missing scaffold fails**

Run: `node --test apps/architecture-portal/test/entrypoint.test.mjs`

Expected: FAIL because `apps/architecture-portal/package.json` and `scripts/architecture-portal.sh` do not exist.

- [ ] **Step 3: Create the pinned package and TypeScript configuration**

```json
{
  "name": "@lmdj/architecture-portal",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "engines": {"node": ">=22.13.0"},
  "scripts": {
    "docusaurus": "docusaurus",
    "start": "docusaurus start",
    "build": "docusaurus build",
    "serve": "docusaurus serve",
    "clear": "docusaurus clear",
    "typecheck": "tsc --noEmit",
    "test": "node --test test/*.test.mjs",
    "check": "npm test && npm run typecheck && npm run build"
  },
  "dependencies": {
    "@docusaurus/core": "3.10.2",
    "@docusaurus/faster": "3.10.2",
    "@docusaurus/preset-classic": "3.10.2",
    "@mdx-js/react": "3.1.1",
    "clsx": "2.1.1",
    "prism-react-renderer": "2.4.1",
    "react": "19.2.8",
    "react-dom": "19.2.8"
  },
  "devDependencies": {
    "@docusaurus/module-type-aliases": "3.10.2",
    "@docusaurus/tsconfig": "3.10.2",
    "@docusaurus/types": "3.10.2",
    "@types/react": "19.2.18",
    "typescript": "6.0.2"
  }
}
```

```json
{
  "extends": "@docusaurus/tsconfig",
  "compilerOptions": {
    "baseUrl": ".",
    "ignoreDeprecations": "6.0",
    "resolveJsonModule": true,
    "strict": true
  },
  "exclude": [".docusaurus", "build"]
}
```

Run: `cd apps/architecture-portal && npm install --package-lock-only`

Expected: `package-lock.json` records only the pinned application dependency graph.

- [ ] **Step 4: Create root-route Docusaurus configuration and sidebar**

Use `routeBasePath: '/'`, `includeCurrentVersion: true`, `lastVersion: 'current'`, `onBrokenLinks: 'throw'`, `defaultLocale: 'zh-Hans'`, no blog, no edit URL, and a current-version label `当前 main`. Configure the docs plugin so `overview/index` owns `/` and frozen docs use `versions/PRODUCT_BUILD` paths.

```ts
// apps/architecture-portal/docusaurus.config.ts
import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'LMDJ Product Manual',
  tagline: 'LMDJ 产品、架构与交付说明书',
  url: 'https://lmdj.netlify.app',
  baseUrl: '/',
  future: {v4: true},
  onBrokenLinks: 'throw',
  i18n: {defaultLocale: 'zh-Hans', locales: ['zh-Hans']},
  presets: [[
    'classic',
    {
      docs: {
        routeBasePath: '/',
        sidebarPath: './sidebars.ts',
        includeCurrentVersion: true,
        lastVersion: 'current',
        versions: {current: {label: '当前 main', path: ''}},
      },
      blog: false,
      theme: {customCss: './src/css/custom.css'},
    } satisfies Preset.Options,
  ]],
  themeConfig: {
    colorMode: {respectPrefersColorScheme: true},
    navbar: {
      title: 'LMDJ Manual',
      items: [
        {type: 'docSidebar', sidebarId: 'manual', label: '产品说明书', position: 'left'},
        {type: 'docsVersionDropdown', position: 'right'},
        {href: 'https://github.com/endaye/lmdj', label: 'Repository', position: 'right'},
      ],
    },
    footer: {style: 'dark', copyright: 'LMDJ internal product manual · publicly readable'},
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;
```

```ts
// apps/architecture-portal/sidebars.ts
import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  manual: [
    'overview/index',
    {type: 'autogenerated', dirName: 'product'},
    {type: 'autogenerated', dirName: 'core'},
    {type: 'autogenerated', dirName: 'hosts'},
    {type: 'autogenerated', dirName: 'providers'},
    {type: 'autogenerated', dirName: 'contracts'},
    {type: 'autogenerated', dirName: 'assembly'},
    {type: 'autogenerated', dirName: 'platform'},
    {type: 'autogenerated', dirName: 'operations'},
    {type: 'autogenerated', dirName: 'history'},
  ],
};

export default sidebars;
```

- [ ] **Step 5: Create the repository wrapper**

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
portal_root="$repo_root/apps/architecture-portal"

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/architecture-portal.sh install
  scripts/architecture-portal.sh dev
  scripts/architecture-portal.sh build
  scripts/architecture-portal.sh check
  scripts/architecture-portal.sh version PRODUCT_BUILD
  scripts/architecture-portal.sh smoke BASE_URL
EOF
}

[[ $# -ge 1 ]] || { usage; exit 64; }
command_name="$1"
shift
cd "$portal_root"

case "$command_name" in
  install) [[ $# -eq 0 ]] || { usage; exit 64; }; exec npm ci ;;
  dev) [[ $# -eq 0 ]] || { usage; exit 64; }; exec npm run start ;;
  build) [[ $# -eq 0 ]] || { usage; exit 64; }; exec npm run build ;;
  check) [[ $# -eq 0 ]] || { usage; exit 64; }; exec npm run check ;;
  version) [[ $# -eq 1 ]] || { usage; exit 64; }; exec node scripts/version-docs.mjs "$1" ;;
  smoke) [[ $# -eq 1 ]] || { usage; exit 64; }; exec node scripts/smoke.mjs "$1" ;;
  *) usage; exit 64 ;;
esac
```

Mark the wrapper executable. Add `.docusaurus/`, `apps/architecture-portal/build/`, `apps/architecture-portal/node_modules/`, and `apps/architecture-portal/src/generated/` to `.gitignore`.

- [ ] **Step 6: Install and prove the scaffold**

Run:

```bash
scripts/architecture-portal.sh install
node --test apps/architecture-portal/test/entrypoint.test.mjs
scripts/architecture-portal.sh build
```

Expected: two Node tests PASS and Docusaurus writes `apps/architecture-portal/build/index.html`.

- [ ] **Step 7: Commit the scaffold**

```bash
git add .gitignore scripts/architecture-portal.sh apps/architecture-portal
git diff --cached --check
git commit -m "feat(docs): scaffold architecture portal"
```

### Task 2: Generate repository facts and validate page metadata

**Files:**
- Modify: `apps/architecture-portal/package.json`
- Modify: `apps/architecture-portal/package-lock.json`
- Create: `apps/architecture-portal/scripts/lib/repo-facts.mjs`
- Create: `apps/architecture-portal/scripts/lib/page-metadata.mjs`
- Create: `apps/architecture-portal/scripts/generate-facts.mjs`
- Create: `apps/architecture-portal/scripts/validate-docs.mjs`
- Create: `apps/architecture-portal/test/repo-facts.test.mjs`
- Create: `apps/architecture-portal/test/page-metadata.test.mjs`
- Create: `apps/architecture-portal/test/fixtures/valid-page.md`
- Create: `apps/architecture-portal/test/fixtures/retired-page.md`

**Interfaces:**
- Consumes: repository root JSON manifests and Markdown/MDX front matter.
- Produces: `readRepoFacts({repoRoot, revision, channel})`; `validatePageMetadata({file, data, repoRoot, activeContractIds})`; ignored `src/generated/site-facts.json`.

- [ ] **Step 1: Add parser dependencies and failing facts tests**

Add exact development dependencies `gray-matter: 4.0.3`, `yaml: 2.9.0`, and `glob: 13.0.6`; refresh the lockfile.

```js
// apps/architecture-portal/test/repo-facts.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readRepoFacts} from '../scripts/lib/repo-facts.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

test('facts match the current locked product composition', async () => {
  const facts = await readRepoFacts({repoRoot, revision: 'abcdef123456', channel: 'canary'});
  assert.equal(facts.product.version, '1.0.13.0');
  assert.equal(facts.revision, 'abcdef123456');
  assert.equal(facts.channel, 'canary');
  assert.deepEqual(facts.modules.map(({id}) => id), [
    'application-facade', 'audio-runtime', 'authoring-domain', 'foundation',
    'project-cooker', 'project-io', 'provider-sdk',
  ]);
  assert.equal(facts.hosts.length, 3);
  assert.equal(facts.providers.length, 2);
  assert.equal(facts.contracts.length, 6);
});
```

- [ ] **Step 2: Run tests and verify missing libraries fail**

Run: `cd apps/architecture-portal && npm test`

Expected: FAIL with module-not-found for `repo-facts.mjs` and `page-metadata.mjs`.

- [ ] **Step 3: Implement exact fact derivation**

`readRepoFacts` must parse the four-part version, sort all identities by ID, compare every Assembly Lock entry with the corresponding manifest, compute the SHA-256 of `assembly.lock.json`, and reject mismatch with messages prefixed `portal facts error:`.

```js
export async function readRepoFacts({repoRoot, revision, channel}) {
  const version = await readJson(path.join(repoRoot, 'products/lmdj/version.json'));
  const assembly = await readJson(path.join(repoRoot, 'products/lmdj/assembly.json'));
  const lockPath = path.join(repoRoot, 'products/lmdj/assembly.lock.json');
  const lockBytes = await readFile(lockPath);
  const lock = JSON.parse(lockBytes);
  const productVersion = [version.milestone, version.minor, version.build, version.patch].join('.');
  if (assembly.product.version !== productVersion || lock.product.version !== productVersion) {
    throw new Error(`portal facts error: product version mismatch for ${productVersion}`);
  }
  return {
    schema_version: 1,
    product: {id: 'lmdj', version: productVersion},
    channel,
    revision,
    assembly_lock_sha256: createHash('sha256').update(lockBytes).digest('hex'),
    modules: sortIdentities(lock.modules),
    hosts: sortIdentities(lock.hosts),
    providers: sortIdentities(lock.providers),
    contracts: sortIdentities(lock.contracts),
  };
}
```

- [ ] **Step 4: Implement the front matter contract**

Require `title`, `area`, `status`, `owners`, and `source_paths`; allow only areas `overview`, `product`, `core`, `hosts`, `providers`, `contracts`, `assembly`, `platform`, `operations`, `history`; allow only statuses `implemented`, `partial`, `designed`, `planned`, `retired`. Resolve every source and decision path against `repoRoot`. Reject retired Contract IDs outside `history` and reject `lmdj.patch.v1` or `lmdj.materials.v1` in non-retired current content.

```js
export function validatePageMetadata({file, data, body, repoRoot, activeContractIds}) {
  const errors = [];
  for (const key of ['title', 'area', 'status', 'owners', 'source_paths']) {
    if (data[key] == null) errors.push(`${file}: missing ${key}`);
  }
  if (data.status === 'retired' && data.area !== 'history') {
    errors.push(`${file}: retired pages must be under history`);
  }
  for (const sourcePath of data.source_paths ?? []) {
    if (!existsSync(path.join(repoRoot, sourcePath))) errors.push(`${file}: missing source path ${sourcePath}`);
  }
  if (data.area !== 'history' && /lmdj\.(patch|materials)\.v1/.test(body)) {
    errors.push(`${file}: retired Contract leaked into current documentation`);
  }
  return errors;
}
```

- [ ] **Step 5: Generate ignored current facts before build**

`generate-facts.mjs` obtains `PORTAL_REVISION` or `git rev-parse HEAD`, obtains `PORTAL_CHANNEL` or defaults to `canary`, writes formatted deterministic JSON to `src/generated/site-facts.json`, and prints `portal facts: PRODUCT_BUILD REVISION`.

Update scripts so `build` and `check` run generation first:

```json
{
  "facts": "node scripts/generate-facts.mjs",
  "validate:docs": "node scripts/validate-docs.mjs",
  "build": "npm run facts && docusaurus build",
  "check": "npm test && npm run validate:docs && npm run typecheck && npm run build"
}
```

- [ ] **Step 6: Run tests and current metadata validation**

Run:

```bash
cd apps/architecture-portal
npm test
npm run facts
npm run validate:docs
```

Expected: all tests PASS and facts report `1.0.13.0` with the current revision.

- [ ] **Step 7: Commit fact generation**

```bash
git add apps/architecture-portal/package.json apps/architecture-portal/package-lock.json \
  apps/architecture-portal/scripts apps/architecture-portal/test
git diff --cached --check
git commit -m "feat(docs): derive portal facts from manifests"
```

### Task 3: Build the shared product-manual experience and all initial pages

**Files:**
- Modify: `apps/architecture-portal/docusaurus.config.ts`
- Modify: `apps/architecture-portal/sidebars.ts`
- Modify: `apps/architecture-portal/src/css/custom.css`
- Create: `apps/architecture-portal/src/components/BuildIdentity.tsx`
- Create: `apps/architecture-portal/src/components/StatusBadge.tsx`
- Create: `apps/architecture-portal/src/components/SectionCards.tsx`
- Create: `apps/architecture-portal/src/components/DiagramFrame.tsx`
- Create: every route listed in design §6 under `apps/architecture-portal/docs/`
- Create: `apps/architecture-portal/test/content-inventory.test.mjs`

**Interfaces:**
- Consumes: `src/generated/site-facts.json`, front matter contract, static diagram URLs.
- Produces: root home page, explicit whole-product navigation, truthful current/manual pages, shared identity/status/diagram components.

- [ ] **Step 1: Write the failing route inventory test**

```js
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
```

- [ ] **Step 2: Run the inventory test and verify missing routes fail**

Run: `cd apps/architecture-portal && npm test`

Expected: FAIL on the first missing route after `overview/index`.

- [ ] **Step 3: Implement shared components**

`BuildIdentity` reads generated facts and, when inside a versioned doc, selects matching `versioned_metadata/version-PRODUCT_BUILD.json`; `StatusBadge` maps the five statuses to fixed Chinese labels; `SectionCards` accepts exact `{title, description, to, status}` items; `DiagramFrame` renders an accessible iframe plus direct HTML/SVG links.

```tsx
export type PortalStatus = 'implemented' | 'partial' | 'designed' | 'planned' | 'retired';

const labels: Record<PortalStatus, string> = {
  implemented: '已实现', partial: '部分实现', designed: '已设计', planned: '规划中', retired: '已退役',
};

export function StatusBadge({status}: {status: PortalStatus}) {
  return <span className={`status-badge status-${status}`}>{labels[status]}</span>;
}
```

- [ ] **Step 4: Author the home page and current product pages**

The home page must use `BuildIdentity`, display current-versus-snapshot status, embed `/diagrams/lmdj-product.html`, and link every top-level section. Product pages must state the 64-Pad Playable Beat Instrument direction, Project/Runtime/Provider/Assembly boundaries, current implemented Proof scope, and planned product UI scope without reviving Patch/Materials.

- [ ] **Step 5: Author seven complete Core Module pages**

Each module page must contain the ten sections from design §7 and exact source paths from its `module.json`. Use current Module dependencies and versions only through generated `BuildIdentity`/inventory components. Link tests by their actual `tests/core/**` locations and label unproven device/product acceptance separately from automated Proof.

- [ ] **Step 6: Author Hosts, Providers, Contracts, Assembly, Platform, Operations, and History pages**

Required status truth:

- CLI, MCP, and Native Test Host: implemented;
- formal Web Runtime Host: designed/partial according to current merged source evidence;
- local proof Providers: implemented Proof-only;
- production/cloud Providers: planned and absent;
- Project, Capability v2, Assembly v2, Error, Module, Product Version Contracts: implemented;
- Runtime Snapshot: immutable derived boundary, not Project Truth;
- Native audio: implemented Proof scope with physical acceptance reported separately;
- input adapters and product GUI: planned unless current source proves otherwise;
- legacy Patch/Materials: retired history only.

- [ ] **Step 7: Run content, type, and production build checks**

Run: `scripts/architecture-portal.sh check`

Expected: all Node tests, metadata validation, typecheck, and Docusaurus build PASS; `build/index.html` exists.

- [ ] **Step 8: Commit the manual content shell**

```bash
git add apps/architecture-portal
git diff --cached --check
git commit -m "feat(docs): author LMDJ product manual"
```

### Task 4: Add deterministic whole-product and Module diagrams

**Files:**
- Modify: `apps/architecture-portal/package.json`
- Create: `apps/architecture-portal/diagrams/*.architecture.json`
- Create: `apps/architecture-portal/scripts/lib/diagram.mjs`
- Create: `apps/architecture-portal/scripts/render-diagrams.mjs`
- Create: `apps/architecture-portal/scripts/validate-diagrams.mjs`
- Create: `apps/architecture-portal/test/diagram.test.mjs`
- Create: `apps/architecture-portal/static/diagrams/*.svg`
- Create: `apps/architecture-portal/static/diagrams/*.html`
- Modify: relevant `apps/architecture-portal/docs/**/*.mdx`

**Interfaces:**
- Consumes: schema-version-1 diagram JSON with components, boundaries, connections, and cards.
- Produces: `renderDiagram(source): {svg, html, sourceSha256}`; tracked dual-theme SVG and standalone HTML for whole product, whole Core, and seven Modules.

- [ ] **Step 1: Write failing renderer and validation tests**

```js
test('renderer is deterministic and records the source digest', () => {
  const source = fixtureDiagram();
  const first = renderDiagram(source);
  const second = renderDiagram(source);
  assert.equal(first.svg, second.svg);
  assert.equal(first.sourceSha256, second.sourceSha256);
  assert.match(first.svg, new RegExp(`data-source-sha256="${first.sourceSha256}"`));
});

test('validator rejects overlaps and missing edge endpoints', () => {
  assert.deepEqual(validateDiagram(invalidFixture()), [
    'components a and b overlap',
    'connection a -> missing references unknown component missing',
  ]);
});
```

- [ ] **Step 2: Implement the renderer contract**

Use a fixed `1560 × 820` viewBox, semantic CSS variables, opaque masks before component fills, arrows before components, orthogonal connection paths, CJK-aware label width checks, and cards below the main graph. Validate unique IDs, finite coordinates, bounds, component overlap, endpoint existence, label length, and legend clearance before rendering.

```js
function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

export function renderDiagram(source) {
  const errors = validateDiagram(source);
  if (errors.length) throw new Error(`diagram validation failed:\n- ${errors.join('\n- ')}`);
  const canonical = `${canonicalJson(source)}\n`;
  const sourceSha256 = createHash('sha256').update(canonical).digest('hex');
  const svg = renderSvg(source, sourceSha256);
  return {sourceSha256, svg, html: wrapStandaloneHtml(source.meta.title, svg)};
}
```

- [ ] **Step 3: Create exact diagram inventory**

Create sources and outputs for:

```text
lmdj-product
lmdj-core
foundation
authoring-domain
project-io
project-cooker
audio-runtime
provider-sdk
application-facade
```

The whole-Core topology must show `Hosts → Application Facade → Authoring Domain → Project Cooker → Immutable Runtime Snapshot → Audio Runtime`, the Project I/O side path, Provider SDK/Provider isolation, Foundation, Contracts, and Product Assembly. Module diagrams must show public inputs/outputs, direct dependencies, owned state, and forbidden boundaries rather than repeating the whole-Core graph.

- [ ] **Step 4: Generate and validate tracked artifacts**

Add scripts:

```json
{
  "diagrams": "node scripts/render-diagrams.mjs",
  "validate:diagrams": "node scripts/validate-diagrams.mjs",
  "check": "npm test && npm run validate:docs && npm run validate:diagrams && npm run typecheck && npm run build"
}
```

Run twice:

```bash
cd apps/architecture-portal
npm run diagrams
git diff -- static/diagrams > /tmp/portal-diagram-first.diff
npm run diagrams
npm run validate:diagrams
```

Expected: second generation produces no additional diff; nine sources and eighteen outputs pass.

- [ ] **Step 5: Embed diagrams and run the full portal check**

Every Core Module page embeds its named standalone HTML and links its SVG. The home page embeds `lmdj-product`; Core overview embeds `lmdj-core`. Run `scripts/architecture-portal.sh check` and expect PASS.

- [ ] **Step 6: Commit diagrams**

```bash
git add apps/architecture-portal
git diff --cached --check
git commit -m "feat(docs): visualize product and Core modules"
```

### Task 5: Enforce build-output routes, links, and current-truth coverage

**Files:**
- Modify: `apps/architecture-portal/package.json`
- Create: `apps/architecture-portal/scripts/lib/build-check.mjs`
- Create: `apps/architecture-portal/scripts/check-build.mjs`
- Create: `apps/architecture-portal/test/build-check.test.mjs`
- Create: `apps/architecture-portal/test/fixtures/build-valid/**`
- Create: `apps/architecture-portal/test/fixtures/build-invalid/**`

**Interfaces:**
- Consumes: Docusaurus `build/`, approved route list, generated facts, and page inventory.
- Produces: `checkBuild({buildRoot, requiredRoutes, expectedIdentity}): string[]` and a fail-closed `check-build.mjs` entry point.

- [ ] **Step 1: Write failing route/link tests**

```js
test('build checker reports missing routes, broken internal links, and identity drift', async () => {
  const errors = await checkBuild({
    buildRoot: invalidRoot,
    requiredRoutes: ['/', '/core/modules/foundation/'],
    expectedIdentity: {productBuild: '1.0.13.0', revision: 'abcdef1'},
  });
  assert.deepEqual(errors, [
    'missing route /core/modules/foundation/',
    'broken internal link /missing/ from /index.html',
    'index identity does not contain Product Build 1.0.13.0',
  ]);
});
```

- [ ] **Step 2: Implement bounded HTML output inspection**

Add exact `cheerio: 1.2.0`. Enumerate built `.html` files once, map pretty routes to files, collect same-origin `href`/`src` values, ignore fragments and `mailto:`, reject missing targets, and verify the expected Product Build/revision in the home page. Do not fetch the network during build checks.

- [ ] **Step 3: Add Assembly/current-page completeness checks**

Extend `validate-docs.mjs` so every lock entry maps to declared `module`, `host`, `provider`, or `contracts` front matter. Require every package Module ID to have one page and diagram. Print errors sorted by path and exit `1`.

- [ ] **Step 4: Add build check to the stable gate**

```json
{
  "check:build": "node scripts/check-build.mjs",
  "check": "npm test && npm run validate:docs && npm run validate:diagrams && npm run typecheck && npm run build && npm run check:build"
}
```

Run: `scripts/architecture-portal.sh check`

Expected: PASS with all approved current routes and assets present.

- [ ] **Step 5: Commit current-truth gates**

```bash
git add apps/architecture-portal
git diff --cached --check
git commit -m "test(docs): enforce portal current truth"
```

### Task 6: Implement formal Product Build documentation versioning

**Files:**
- Modify: `apps/architecture-portal/docusaurus.config.ts`
- Modify: `apps/architecture-portal/package.json`
- Create: `apps/architecture-portal/scripts/lib/version-docs.mjs`
- Create: `apps/architecture-portal/scripts/version-docs.mjs`
- Create: `apps/architecture-portal/test/version-docs.test.mjs`
- Create: `apps/architecture-portal/versioned_metadata/.gitkeep`

**Interfaces:**
- Consumes: exact Product Build, clean Git state, current facts, Docusaurus version command.
- Produces: `freezeVersion({portalRoot, repoRoot, requestedVersion, revision})`; fail-closed versioning command ready to create immutable snapshots.

- [ ] **Step 1: Write failing version contract tests**

```js
test('freeze rejects syntax mismatch, dirty worktree, and existing version', async () => {
  await assert.rejects(() => freezeVersion(fixture({requestedVersion: '1.0.13'})), /four-part Product Build/);
  await assert.rejects(() => freezeVersion(fixture({requestedVersion: '1.0.12.0'})), /does not match 1.0.13.0/);
  await assert.rejects(() => freezeVersion(fixture({dirty: true})), /clean worktree/);
  await assert.rejects(() => freezeVersion(fixture({existing: ['1.0.13.0']})), /already exists/);
});
```

- [ ] **Step 2: Implement fail-closed version freezing**

The command validates `^\d+\.\d+\.\d+\.\d+$`, compares current facts, checks `git status --porcelain`, runs `npm run check`, invokes `docusaurus docs:version PRODUCT_BUILD`, writes metadata with exact `product_build`, `revision`, `assembly_lock_sha256`, and `frozen_at_utc`, updates Docusaurus version config to path `versions/PRODUCT_BUILD`, then runs `npm run check` again. Existing versions are rejected before any write.

- [ ] **Step 3: Make version tests use isolated fixtures**

Inject command execution and file-system adapters into `freezeVersion` so unit tests never modify real `docs/` or Git state. Assert exact command order:

```js
assert.deepEqual(commands, [
  ['npm', ['run', 'check']],
  ['npm', ['run', 'docusaurus', '--', 'docs:version', '1.0.13.0']],
  ['npm', ['run', 'check']],
]);
```

- [ ] **Step 4: Prove versioning implementation without modifying current docs**

Run:

```bash
cd apps/architecture-portal
npm test
npm run check
```

Expected: version unit tests pass against isolated fixtures and the real current docs remain unchanged.

- [ ] **Step 5: Commit the versioning engine**

```bash
git add apps/architecture-portal
git diff --cached --check
git commit -m "feat(docs): freeze product manual versions"
```

### Task 7: Freeze the Product Build 1.0.13.0 documentation snapshot

**Files:**
- Generate: `apps/architecture-portal/versioned_docs/version-1.0.13.0/**`
- Generate: `apps/architecture-portal/versioned_sidebars/version-1.0.13.0-sidebars.json`
- Generate: `apps/architecture-portal/versioned_metadata/version-1.0.13.0.json`
- Generate: `apps/architecture-portal/versions.json`

**Interfaces:**
- Consumes: clean Task 6 commit and Product Build `1.0.13.0` facts.
- Produces: immutable `/versions/1.0.13.0/` documentation snapshot.

- [ ] **Step 1: Verify the Task 6 worktree is clean**

Run: `git status --porcelain`

Expected: no output.

- [ ] **Step 2: Freeze the exact current Product Build**

Run: `scripts/architecture-portal.sh version 1.0.13.0`

Expected: versioned docs, sidebar, metadata, and `versions.json` are created; current and `/versions/1.0.13.0/` checks pass.

- [ ] **Step 3: Inspect frozen identity**

Run:

```bash
jq '{product_build,revision,assembly_lock_sha256}' \
  apps/architecture-portal/versioned_metadata/version-1.0.13.0.json
git diff --check
```

Expected: Product Build is exactly `1.0.13.0`, revision is the Task 6 commit, and Assembly lock digest is 64 lowercase hexadecimal characters.

- [ ] **Step 4: Commit the immutable snapshot**

```bash
git add apps/architecture-portal/versioned_docs \
  apps/architecture-portal/versioned_sidebars \
  apps/architecture-portal/versioned_metadata \
  apps/architecture-portal/versions.json
git diff --cached --check
git commit -m "docs(portal): freeze product build 1.0.13.0"
```

### Task 8: Make documentation impact a repository rule and CI gate

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/governance/version-management.md`
- Create: `docs/governance/architecture-portal.md`
- Create: `.github/pull_request_template.md`
- Create: `.github/workflows/architecture-portal.yml`
- Create: `apps/architecture-portal/scripts/check-doc-impact.mjs`
- Create: `apps/architecture-portal/test/doc-impact.test.mjs`

**Interfaces:**
- Consumes: PR body from `PORTAL_PR_BODY`, changed files from `PORTAL_CHANGED_FILES` or Git diff.
- Produces: `checkDocumentationImpact({body, changedFiles}): string[]`; mandatory plan/PR governance and CI job.

- [ ] **Step 1: Write failing documentation-impact tests**

```js
test('implementation change requires a concrete impact declaration', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: ',
    changedFiles: ['packages/audio-runtime/src/engine.cpp'],
  }), ['documentation impact reason is empty']);
});

test('affected implementation accepts required routes', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: required\nAffected portal pages: /core/modules/audio-runtime/\nReason: trigger state changed',
    changedFiles: ['packages/audio-runtime/src/engine.cpp', 'apps/architecture-portal/docs/core/modules/audio-runtime.mdx'],
  }), []);
});
```

- [ ] **Step 2: Add the canonical governance document**

Record exact required/none syntax, affected file categories, stable commands, Task ownership, formal snapshot gate, state distinctions, public content exclusions, deploy/rollback evidence, and the rule that no-impact does not create empty portal churn.

- [ ] **Step 3: Mirror the concise project rule in AGENTS and CLAUDE**

Insert the same `## Architecture portal and documentation impact` section in both files. Require every plan to declare impact, require affected portal routes in the same Task, prohibit guessed identities and manual production uploads, and point to `docs/governance/architecture-portal.md`.

- [ ] **Step 4: Extend version governance**

Add the formal portal snapshot as a pre-release gate without changing Product/Module/Contract version semantics. Replace the placeholder angle-bracket example in the existing no-impact block with concrete prose while preserving its meaning.

- [ ] **Step 5: Add PR template and CI workflow**

The workflow uses checkout v6, Node 22, `npm ci`, and `scripts/architecture-portal.sh check`. It triggers on Pull Requests and `main` pushes when portal source, Module/Host/Provider manifests, Contracts, Product Assembly/version, governance, workflow, or wrapper paths change. A PR-only step passes the Pull Request body and changed-file list into `check-doc-impact.mjs`.

- [ ] **Step 6: Verify governance and CI syntax**

Run:

```bash
cmp <(sed -n '/^## Architecture portal/,/^## /p' AGENTS.md) \
    <(sed -n '/^## Architecture portal/,/^## /p' CLAUDE.md)
scripts/architecture-portal.sh check
cd apps/architecture-portal
node -e 'import("yaml").then(async ({parse}) => parse(await (await import("node:fs/promises")).readFile("../../.github/workflows/architecture-portal.yml", "utf8")))'
```

Expected: mirrored sections match, portal check passes, workflow YAML parses.

- [ ] **Step 7: Commit project governance**

```bash
git add AGENTS.md CLAUDE.md docs/governance .github/pull_request_template.md \
  .github/workflows/architecture-portal.yml apps/architecture-portal
git diff --cached --check
git commit -m "docs(governance): require portal impact review"
```

### Task 9: Define Netlify production and post-deploy smoke verification

**Files:**
- Create: `netlify.toml`
- Create: `apps/architecture-portal/scripts/lib/smoke.mjs`
- Create: `apps/architecture-portal/scripts/smoke.mjs`
- Create: `apps/architecture-portal/test/smoke.test.mjs`
- Create: `.github/workflows/architecture-portal-smoke.yml`
- Create: `docs/deploy/architecture-portal.md`

**Interfaces:**
- Consumes: `BASE_URL`, expected Product Build/revision, public HTTPS responses.
- Produces: `smokePortal({baseUrl, productBuild, revision, fetchImpl}): Promise<string[]>`; source-controlled Netlify build; immutable Deploy and production verification.

- [ ] **Step 1: Write failing smoke tests with a fake fetch**

```js
test('smoke rejects raw source and wrong identity', async () => {
  const errors = await smokePortal({
    baseUrl: 'https://example.netlify.app',
    productBuild: '1.0.13.0',
    revision: 'abcdef1',
    fetchImpl: fakeResponses({
      '/': {status: 200, type: 'text/plain', body: '<!DOCTYPE html>'},
    }),
  });
  assert.deepEqual(errors, [
    '/ returned content-type text/plain; charset=UTF-8',
    '/ did not render Product Build 1.0.13.0',
    '/ did not render revision abcdef1',
  ]);
});
```

- [ ] **Step 2: Implement bounded production smoke**

Check `/`, every top-level section, seven Core Module routes, `/versions/1.0.13.0/`, and referenced same-origin static assets. Require HTTPS, 2xx, HTML MIME for routes, expected identity on home/version pages, and reject bodies beginning with escaped or visible source text. Limit concurrent requests to four and print sorted errors prefixed `portal smoke error:`.

- [ ] **Step 3: Add repository-owned Netlify configuration**

Add exact development dependency `netlify-cli: 27.0.2`, refresh the lockfile, and add `"netlify:build": "netlify build"` to package scripts.

```toml
[build]
base = "apps/architecture-portal"
command = "npm ci && npm run check"
publish = "build"

[build.environment]
NODE_VERSION = "22"
NPM_FLAGS = "--no-audit --no-fund"

[[headers]]
for = "/*"
[headers.values]
X-Content-Type-Options = "nosniff"
Referrer-Policy = "strict-origin-when-cross-origin"
```

Do not force a global `Content-Type`; Netlify must infer `.html` as `text/html`, and smoke must catch regression.

- [ ] **Step 4: Add deployment-status smoke workflow**

Trigger on `deployment_status`. Run only for successful Netlify deployments whose environment URL host ends in `netlify.app`. Checkout the deployment SHA, install Node 22 and portal dependencies, then run `scripts/architecture-portal.sh smoke "$DEPLOYMENT_URL"`. Upload the smoke log on failure.

- [ ] **Step 5: Document deployment and rollback evidence**

`docs/deploy/architecture-portal.md` must separate local check, CI, Deploy Preview, production deploy, and release verification; record how to obtain Deploy ID; forbid normal manual API/ZIP uploads; explain restoring the last verified Deploy without moving product tags.

- [ ] **Step 6: Run local Netlify-equivalent checks**

Run:

```bash
scripts/architecture-portal.sh check
cd apps/architecture-portal
npm run netlify:build
```

Expected: both builds pass and publish `apps/architecture-portal/build`.

- [ ] **Step 7: Commit deployment contracts**

```bash
git add netlify.toml .github/workflows/architecture-portal-smoke.yml \
  apps/architecture-portal docs/deploy/architecture-portal.md
git diff --cached --check
git commit -m "ci(docs): automate Netlify portal verification"
```

### Task 10: Complete local acceptance and prepare external review

**Files:**
- Create: `docs/quality/2026-08-04-architecture-portal-acceptance.md`

**Interfaces:**
- Consumes: approved design, Tasks 1–9 artifacts, clean checkout, local browser.
- Produces: requirement-by-requirement acceptance evidence and a reviewable clean branch.

- [ ] **Step 1: Run the complete automated acceptance matrix**

```bash
scripts/architecture-portal.sh install
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
git diff --check
```

Expected: every command exits `0`; portal output contains current and `1.0.13.0` routes.

- [ ] **Step 2: Run local browser acceptance**

Serve the production build on loopback. Verify desktop and mobile widths, home navigation, all seven Module pages, whole-product/Core/module diagrams, dark/light mode, direct SVG/HTML diagram links, version switching, History retired banner, no browser console errors, and no failed same-origin requests.

If any defect appears, stop this Task, return to the owning Task's exact files, add a failing regression test, implement the bounded fix, and create a separate Conventional Commit before restarting acceptance.

- [ ] **Step 3: Write evidence against all twelve design acceptance items**

The quality document records exact command results, route counts, page/diagram counts, current Product Build, Git revision, Assembly lock digest, screenshot paths, and external states that remain unperformed. Any unproven item remains FAIL or PENDING rather than being inferred.

- [ ] **Step 4: Commit acceptance evidence**

```bash
git add docs/quality/2026-08-04-architecture-portal-acceptance.md
git diff --cached --check
git commit -m "test(docs): verify architecture portal acceptance"
```

- [ ] **Step 5: Inspect final branch state**

```bash
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git status --short --branch
```

Expected: Task commits are reviewable, no unrelated files are included, and the worktree is clean.

- [ ] **Step 6: Stop at the external-action boundary**

Report local implementation and acceptance separately. Push, PR, merge, Netlify Deploy Preview, production publication, and public smoke require their own authorization and evidence. Do not describe `lmdj.netlify.app` as updated until the merged revision is actually deployed and smoke-verified.

## Version Management

Version impact: none.

Reason: the portal documents and snapshots the existing Product Build `1.0.13.0` and current Module/Host/Provider/Contract identities. It does not change product runtime behavior, public Core APIs, Contract shapes, Provider behavior, packaging, or Assembly composition. Docusaurus package identity `0.0.0` remains private implementation tooling and is not an LMDJ Product or Module version.

The plan creates a documentation snapshot named `1.0.13.0`; that snapshot records existing identity and does not mint, move, or publish an `lmdj-v1.0.13.0` tag. No tag, push, GitHub Release, Channel promotion, merge, or deployment is authorized by this plan.

Rollback reuses the last verified Netlify Deploy ID for the portal and never rewrites an immutable Product Build snapshot or product tag.

## Documentation Impact

Documentation impact: required.

Affected portal pages: every route in design §6, plus `docs/governance/architecture-portal.md`, `docs/governance/version-management.md`, and `docs/deploy/architecture-portal.md`.

Reason: this plan creates the portal, converts current architecture and product facts into the maintained manual, freezes the first Product Build documentation snapshot, and establishes the documentation-impact and publication rules requested by the product owner.
