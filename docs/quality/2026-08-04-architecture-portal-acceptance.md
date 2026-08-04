# Architecture Portal Local Acceptance — 2026-08-04

## Scope and identity

- Portal: LMDJ Product Manual
- Product Build: `1.0.13.0`
- Browser-tested implementation revision: `122e51a78e8dfb63b27451bf5165290be13b7e4f`
- Formal snapshot revision: `1d4da9322178d4078e548b5e03a0878c03215fc5`
- Assembly Lock SHA-256: `3371ddfe29d01e544ac11c7b0a5a3c456583e1b74a2579851b9c8e86b3c4f0bd`
- Current pages: 34
- Diagram sources: 9
- Tracked diagram outputs: 18 HTML/SVG files
- Production-build routes checked: 37

This document records local implementation and acceptance only. Push, Pull
Request, merge, Netlify Deploy Preview, production publication, Deploy ID, and
public smoke verification were not performed.

## Automated evidence

The following commands exited `0`:

```bash
scripts/architecture-portal.sh install
scripts/architecture-portal.sh check
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
git diff --check
```

Portal output reported 21 passing tests, 34 valid pages, 9 valid diagram
sources, 18 valid diagram outputs, and 37 valid production routes/internal
links. Core dependency verification, active-tree verification, product version
tests, and Product Build verification also passed.

The portal's Netlify build contract was separately exercised with:

```bash
npm run netlify:build
```

It completed the offline Netlify production build successfully. The final
clean-branch portal gate was rerun after committing this evidence.

## Browser evidence

The production build was served through Netlify CLI `27.0.2` in offline mode
and inspected with Chromium at `1440x1000` and `390x844`.

- Home navigation opened a Core Module page through the visible section card.
- Current and Product Build `1.0.13.0` version switching rendered the expected
  current revision and immutable snapshot revision.
- All seven Core Module routes returned `200` with their expected H1.
- Product, Core, Hosts, Providers, Contracts, Assembly, Platform, Operations,
  and History representative routes returned `200`.
- Whole-product HTML and SVG diagrams returned `200` with `text/html` and
  `image/svg+xml`; embedded whole-product and Module diagrams rendered.
- Light and dark modes rendered correctly after iframe theme synchronization.
- History visibly labels `lmdj.patch.v1` and `lmdj.materials.v1` as retired.
- Browser traversal recorded zero console errors and zero failed requests.
- At 390 px, document width equalled viewport width and the mobile navigation
  exposed every section plus the version selector. Wide diagrams remain
  horizontally scrollable inside their iframe without widening the document.

Retained screenshots:

- [`output/playwright/architecture-portal-desktop.png`](../../output/playwright/architecture-portal-desktop.png)
- [`output/playwright/architecture-portal-dark.png`](../../output/playwright/architecture-portal-dark.png)
- [`output/playwright/architecture-portal-mobile.png`](../../output/playwright/architecture-portal-mobile.png)

The Docusaurus development preview treats the dotted version directory as a
file-like path and returns `404` on a direct snapshot refresh. This is not the
deployment runtime: Netlify's local static runtime returned `200 text/html` for
`/`, `/versions/1.0.13.0/`, and `/core/modules/foundation/`.

## Design acceptance

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Every approved route has truthful, non-placeholder content | PASS | 34 page sources validated; 37 production routes and internal links checked |
| 2 | Seven implemented Core Modules have dedicated diagrams | PASS | Seven Module pages and their diagram outputs were browser-tested |
| 3 | Product/Core diagrams distinguish delivery states | PASS | Current pages and diagrams expose implemented, partial, designed/planned, and retired states |
| 4 | Displayed identities match Manifests and Assembly Lock | PASS | Generated facts, metadata validator, identity build check, and Assembly digest passed |
| 5 | Legacy Patch/Materials content is visibly retired and isolated to History | PASS | Metadata test and History browser acceptance passed |
| 6 | `scripts/architecture-portal.sh check` passes from a clean checkout | PASS | Final clean-branch rerun passed after the evidence commit |
| 7 | Pull Request workflow passes | PENDING | No push or Pull Request was authorized |
| 8 | Deploy Preview is reviewed | PENDING | No Netlify Deploy Preview was authorized |
| 9 | `main` automatically publishes to `lmdj.netlify.app` | PENDING | No merge or production publication was authorized |
| 10 | Public smoke passes and records Deploy ID | PENDING | No production Deploy ID exists for this revision |
| 11 | Approved documentation-impact governance exists | PASS | Governance guide, PR declaration, validator, CI gate, and deployment runbook are tracked |
| 12 | Current formal Product Build has a valid snapshot | PASS | `/versions/1.0.13.0/` renders fixed revision `1d4da9322178...` and is labelled as a formal snapshot |

## External boundary

The local branch is ready for review. Items 7–10 remain deliberately PENDING
until separately authorized remote actions produce their own evidence. A local
build or Netlify-ready configuration must not be reported as an updated
`lmdj.netlify.app` production deployment.
