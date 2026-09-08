# LMDJ Architecture Portal Design

Status: Approved for specification review

Date: 2026-08-03

Audience: LMDJ product, design, Core, Host, Provider, platform, quality, and
release contributors

## 1. Decision

LMDJ will maintain a public-but-internal-facing product manual at
`https://lmdj.netlify.app/`. The manual covers the whole current product rather
than only Headless Core. It is a versioned, repository-owned Docusaurus static
site under `apps/architecture-portal/`.

The portal has four jobs:

1. explain the current product and its boundaries to internal team members;
2. give every product area and Core Module a stable page and architecture view;
3. freeze an immutable documentation snapshot for every formal Product Build;
4. make documentation impact, validation, and publication part of the normal
   implementation and release workflow.

The portal is not a marketing site and is not a replacement for authoritative
engineering decision records. `docs/architecture/`, governance documents,
Contracts, Module Manifests, Product Assembly, tests, and source code remain
their respective sources of truth. The portal curates and links those sources
into one readable product manual.

## 2. Context

The repository currently has individual Markdown decisions, SVG/Mermaid assets,
standalone research diagrams, and one manually deployed Headless Core diagram.
They do not form a navigable or automatically published manual.

`docs/architecture/current-product-architecture.md` describes the retired
Patch/Materials product chain. It cannot be presented as current architecture
because the active product is the clean-break Headless Core and must not read,
emit, wrap, or translate `lmdj.patch.v1` or `lmdj.materials.v1`.

The initial `lmdj.netlify.app` page was uploaded manually. Manual uploads do not
provide review, reproducibility, version snapshots, or a stable content-type and
route verification contract. The portal replaces that process with a Git-based
build and deploy pipeline.

## 3. Goals

- Provide a Chinese-first manual for the whole LMDJ product.
- Preserve English source identifiers for Modules, APIs, Contract IDs, typed
  states, errors, and commands.
- Give every implemented Core Module its own page and architecture diagram.
- Cover Product, Core, Hosts, Providers, Contracts, Assembly, Platform, and
  Operations with truthful implementation status.
- Derive current versions and composition from repository Manifests rather than
  duplicating them by hand.
- Publish the latest `main` documentation automatically to
  `lmdj.netlify.app`.
- Preserve formal Product Build snapshots at stable version routes.
- Block changes and releases when affected documentation is missing, stale, or
  structurally invalid.
- Keep generated diagrams reproducible from repository-owned inputs.

## 4. Non-goals

- Public marketing, SEO campaigns, lead capture, analytics, or user accounts.
- A general-purpose wiki or arbitrary file browser.
- Replacing Contract Schemas, source headers, Module Manifests, tests, ADRs, or
  approved product decisions.
- Publishing secrets, private credentials, internal incident data, personal
  information, or unreleased commercial terms.
- Claiming planned work is implemented.
- Restoring retired Patch/Materials architecture as a current compatibility
  layer.
- Requiring full Chinese/English duplicate page trees in the first version.

## 5. Product and repository boundary

The portal belongs under `apps/` because it is a buildable and deployable Host
for product documentation:

```text
apps/architecture-portal/
├── package.json
├── package-lock.json
├── docusaurus.config.ts
├── sidebars.ts
├── docs/
│   ├── overview/
│   ├── product/
│   ├── core/modules/
│   ├── hosts/
│   ├── providers/
│   ├── contracts/
│   ├── assembly/
│   ├── platform/
│   ├── operations/
│   └── history/
├── src/
│   ├── components/
│   ├── css/
│   └── theme/
├── static/
│   └── diagrams/
└── scripts/
```

The portal may read public repository facts at build time. It must not become a
runtime dependency of Core, Hosts, Providers, Product Assembly, or packaging.
No product runtime target may link to or import the portal.

`docs/architecture/` continues to own approved decisions. The portal summarizes
the current consequence of those decisions and links to the original documents.
Long rationale, review evidence, and superseded alternatives remain outside the
portal page body.

## 6. Information architecture

The documentation plugin owns the root route. The current overview is the home
page, so the site does not need a separate unversioned landing application.

### 6.1 Stable current routes

```text
/
/product/positioning
/product/capability-map
/product/workflows

/core/modules/foundation
/core/modules/authoring-domain
/core/modules/project-io
/core/modules/project-cooker
/core/modules/audio-runtime
/core/modules/provider-sdk
/core/modules/application-facade

/hosts/overview
/hosts/core-cli
/hosts/core-mcp
/hosts/native-test-host
/hosts/web-runtime

/providers/overview
/providers/local-proof

/contracts/overview
/contracts/project
/contracts/runtime-snapshot
/contracts/capability
/contracts/assembly
/contracts/error-module-version

/assembly/lmdj

/platform/native-audio
/platform/web-runtime
/platform/storage
/platform/input

/operations/testing-and-proof
/operations/version-and-release
/operations/documentation-governance

/history/legacy-patch-architecture
```

Routes whose capabilities are not implemented still contain a complete,
truthful boundary page with `designed` or `planned` status, the approved source
document, explicit non-capabilities, and the evidence required to change status.
They are not empty stubs.

### 6.2 Home page

The home page shows:

- Product Build, Channel, source revision, and documentation revision;
- an explicit current-status summary;
- the whole-product architecture diagram;
- navigation cards for Product, Core, Hosts, Providers, Contracts, Assembly,
  Platform, Operations, and History;
- implemented, partial, designed, planned, and retired status counts;
- the latest formal documentation snapshot and recent documentation changes;
- a warning when the viewed page is current `main` rather than a formal release
  snapshot.

## 7. Page contract

Every current page uses the same front matter contract:

```yaml
title: Audio Runtime
area: core
status: implemented
owners:
  - core
source_paths:
  - packages/audio-runtime
contracts:
  - lmdj.project.v1
decisions:
  - docs/architecture/2026-08-01-web-realtime-audio-threshold-decision.md
```

Allowed status values are:

- `implemented`: present in active product source and covered by current tests;
- `partial`: a bounded subset is implemented and the missing subset is stated;
- `designed`: approved design exists but product implementation is absent;
- `planned`: direction exists without an approved implementation contract;
- `retired`: historical material that active code must not use.

Module, Product Build, Contract version, Provider version, Host version, Channel,
and Git revision are derived fields. Authors do not enter them in front matter.
The build generates one facts file from:

- `products/lmdj/version.json`;
- `products/lmdj/assembly.json`;
- `products/lmdj/assembly.lock.json`;
- `packages/*/module.json`;
- `apps/*/module.json` where present;
- `providers/*/module.json`;
- `contracts/**/*.schema.json`.

Every component page contains these sections:

1. purpose and non-responsibilities;
2. current implementation status;
3. ownership and dependency boundary;
4. architecture diagram and primary data flow;
5. public API, Contract, and Artifact boundary;
6. state, typed errors, concurrency, and lifecycle where applicable;
7. use by Hosts, Providers, Assembly, or other product areas;
8. tests, Proof, and acceptance evidence;
9. current limitations and next approved gate;
10. version identity and recent relevant changes.

## 8. Diagram contract

Diagram inputs and generated artifacts are both repository-owned. A diagram is
not considered maintainable if it exists only under a user-local visualization
directory.

Each diagram has:

- a structured source file;
- a deterministic project-local render command;
- a generated standalone HTML or SVG artifact;
- a source digest recorded in the generated artifact;
- dark and light rendering;
- accessible text labels and a textual explanation on the parent page;
- a validation command covering malformed SVG, overlaps, off-canvas content,
  missing nodes, and stale generation.

The first implementation may vendor the minimum MIT-licensed renderer required
to reproduce the approved visual language, together with its license notice.
It must not depend on a contributor's `~/.codex`, `~/.agents`, browser profile,
or global npm installation.

The current standalone Headless Core diagram becomes the first whole-Core
overview. Its source is recreated inside the portal and its generated artifact
is no longer the authority once the portal is live.

## 9. Current truth and validation

The portal validator treats repository facts and prose differently:

- Manifest-derived identity is generated and compared mechanically.
- Prose explains responsibilities, reasons, workflows, and limitations.
- `source_paths` and `decisions` must resolve to tracked files or directories.
- Contract IDs must resolve to an active Contract Schema or be confined to a
  `retired` history page.
- Every Assembly Module, Host, Provider, and Contract must be represented by a
  current portal page or an explicit generated inventory entry.
- Every implemented Core Module must have a module page and diagram.
- Current pages must not contain `lmdj.patch.v1` or `lmdj.materials.v1`.
- A history page containing a retired Contract must carry a visible retired
  banner and may not link it as a current API.
- Internal links and route slugs are checked in the production build output.

The portal displays the build revision supplied by CI or Netlify. Local builds
display `dev` plus the current short Git SHA. Formal snapshots display the exact
Product Build and Git revision from the snapshot operation.

## 10. Documentation impact governance

Every implementation plan must contain a `## Documentation Impact` section.
The allowed conclusions are:

```text
Documentation impact: required
Affected portal pages: stable routes changed by the Task
Reason: concrete architecture, API, Contract, behavior, status, version, or release change
```

or:

```text
Documentation impact: none
Reason: concrete explanation of why the observable product manual remains accurate
```

Documentation impact is required when a change affects any of:

- product behavior, capability, workflow, or status;
- Module responsibility, dependency, public API, state, or concurrency;
- Project, Runtime Snapshot, Capability, Assembly, Error, Module, or Version
  Contract;
- Host, Provider, Platform, Product Assembly, build, Proof, package, release, or
  deployment behavior;
- a version or source path displayed by the portal.

An affected implementation Task is incomplete until its portal changes and
checks pass. A separate empty documentation-only commit is not required when
the page update belongs to the same Task boundary.

The canonical rule is recorded in:

- repository `AGENTS.md` and its mirrored contributor guidance;
- `docs/governance/architecture-portal.md`;
- the Pull Request template;
- version and release governance where formal snapshots are gated.

## 11. Version model

The current site always represents the documentation on `main`. Formal Product
Builds receive immutable documentation snapshots.

```text
current main                 → /
formal Product Build 1.0.13.0 → /versions/1.0.13.0/
```

The snapshot command is:

```bash
scripts/architecture-portal.sh version 1.0.13.0
```

It must:

1. validate the four-part Product Build syntax;
2. require an exact match with `products/lmdj/version.json`;
3. require a clean worktree;
4. run the complete portal check before freezing;
5. copy the current page set and versioned assets using Docusaurus versioning;
6. record the exact Git revision and Assembly Lock digest;
7. update version navigation and a concise documentation change summary;
8. reject an existing version instead of overwriting or silently regenerating
   it;
9. run the complete portal check again after freezing.

Only Product Builds that reach the repository's formal release flow require a
snapshot. Ordinary commits update current documentation without copying the
whole site. Historical snapshot corrections require an explicit documentation
fix and may correct explanation or broken links, but may not rewrite the
recorded product composition.

## 12. Build and developer interface

The stable repository entry point is:

```bash
scripts/architecture-portal.sh install
scripts/architecture-portal.sh dev
scripts/architecture-portal.sh build
scripts/architecture-portal.sh check
scripts/architecture-portal.sh version PRODUCT_BUILD
scripts/architecture-portal.sh smoke BASE_URL
```

The wrapper owns working-directory selection and refuses unsupported commands.
The portal pins its Node engine, npm dependencies, and lockfile inside
`apps/architecture-portal/`; it does not add a root `package.json`.

`check` runs, at minimum:

- formatting and type checks for portal source;
- front matter schema validation;
- repository fact generation and consistency checks;
- page inventory and status validation;
- retired Contract isolation checks;
- diagram source/artifact freshness validation;
- Docusaurus production build;
- generated route and internal-link checks;
- current and frozen-version navigation checks.

## 13. CI and Netlify publication

### 13.1 Pull Request gate

`.github/workflows/architecture-portal.yml` runs when portal source, displayed
Manifests, Contracts, Assembly, version identity, governance, or portal scripts
change. It executes the stable `check` command from a clean checkout.

The Pull Request template requires the author to declare documentation impact
and list affected routes. A missing declaration fails the governance check for
implementation Pull Requests.

Netlify creates a Deploy Preview for Pull Requests. A preview is review evidence,
not production publication and not proof of a formal Product Build snapshot.

### 13.2 Production publication

The `lmdj` Netlify site remains connected to this repository and tracks only
`main`. Repository-owned `netlify.toml` defines:

- base directory `apps/architecture-portal`;
- locked dependency installation;
- the production build command;
- publish directory;
- redirects or headers required by the static site.

A green merge to `main` triggers one atomic Netlify production deploy. The
workflow never commits generated build output back to `main`. Manual drag/drop,
manual ZIP upload, and direct production API upload are not part of the normal
workflow.

### 13.3 Public smoke verification

The post-deploy gate checks the immutable Deploy URL first, then the production
domain. It requires:

- HTTPS success;
- `Content-Type: text/html` for HTML routes;
- the expected Product Build and Git revision;
- home page, every top-level section, all seven Core Module routes, and the
  latest formal version route;
- no raw-source rendering;
- no broken internal asset or navigation request.

The smoke command records the Netlify Deploy ID and checked revision as release
evidence. A failed deploy or smoke does not become release-verified.

## 14. Failure and rollback behavior

- Content validation failure blocks the Pull Request.
- A portal build failure blocks Netlify publication.
- Netlify keeps the prior production deploy active until a new atomic deploy is
  ready.
- A post-deploy smoke failure is reported against the exact Deploy ID; rollback
  restores the last verified deploy rather than rebuilding unknown source.
- A documentation snapshot mismatch blocks the Product release workflow before
  tag or publication.
- Missing display data fails closed with a clear build error. The portal does
  not substitute guessed versions or statuses.
- A diagram render failure leaves the last committed artifact unchanged and
  fails the Task.

Rollback does not authorize moving or recreating immutable product tags. Portal
rollback and product release rollback remain separate operations.

## 15. Public access and security

The portal may remain publicly readable. Public access does not weaken content
review:

- only tracked, reviewed content is published;
- secrets and environment values are never rendered;
- source links point only to intended repository paths;
- provider credentials, private Artifact data, Project contents, and user data
  are excluded;
- no edit, comment, upload, authentication, analytics, or form backend is added
  in the first version;
- external links use safe browser behavior and are validated separately from
  internal routes.

## 16. Initial content acceptance

The first production portal is complete only when:

1. every route in §6 exists and contains non-placeholder truthful content;
2. all seven implemented Core Modules have a dedicated architecture diagram;
3. the whole-product and whole-Core diagrams distinguish implemented, partial,
   designed, planned, and retired content;
4. displayed versions match current Manifests and Assembly Lock;
5. the legacy Patch/Materials page is visibly retired and absent from current
   navigation paths except History;
6. `scripts/architecture-portal.sh check` passes from a clean checkout;
7. the Pull Request workflow passes;
8. a Deploy Preview is reviewed;
9. `main` publishes automatically to `lmdj.netlify.app`;
10. public smoke verification passes with `text/html` and records the Deploy ID;
11. the repository contains the approved documentation-impact governance;
12. the current formal Product Build has a valid version snapshot.

Local build success, a Netlify `ready` status, and public smoke verification are
reported as separate evidence.

## 17. Testing strategy

Tests are layered:

- unit tests cover metadata parsing, facts generation, status rules, and
  Product Build validation;
- fixture tests cover missing paths, mismatched versions, retired Contract
  leakage, incomplete Module inventory, and stale diagrams;
- build tests cover Docusaurus output, route inventory, version navigation, and
  internal links;
- browser smoke covers home navigation, representative responsive layout,
  diagram rendering, dark/light appearance, and version switching;
- deployment smoke covers immutable preview and production HTTP behavior.

The complete portal check must run without changing tracked files. A second run
of fact generation and version validation must be idempotent.

## 18. Delivery sequence

Implementation is divided into reviewable Tasks:

1. scaffold the isolated Docusaurus portal and stable repository command;
2. implement repository facts, front matter, inventory, and validation;
3. implement the shared theme, home page, navigation, and page components;
4. create whole-product, whole-Core, and seven Module diagrams;
5. author every initial route with current repository evidence;
6. add formal version freezing and the current Product Build snapshot;
7. add documentation-impact governance and Pull Request checks;
8. add repository-owned Netlify configuration and preview/production smoke;
9. verify preview, publish production after authorized merge, and record the
   exact Deploy ID and public acceptance evidence.

Push, Pull Request creation, merge, tag, release, and deployment remain separate
authorizations. The approved design authorizes local implementation commits but
does not itself authorize those external transitions.

## 19. Version Management

Version impact: none.

Reason: this design establishes a documentation product, governance, and future
snapshot contract without changing the current Product Build, any Core Module
SemVer, Provider SemVer, Host SemVer, or Contract SemVer. The first portal
implementation will display and freeze the existing Product Build identity; it
must not bump product or runtime versions merely because documentation is added.

Docusaurus and portal package dependencies will be pinned in the isolated portal
lockfile. Their package version is implementation tooling identity, not LMDJ
Product Build identity.
