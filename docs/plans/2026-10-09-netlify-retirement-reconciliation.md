# Netlify retirement reconciliation — stale production identity fixes

Relates to #927, #873.

## Background

The #927 retirement audit (2026-10-09, main `502932e34`) confirmed no live
Netlify consumer remains: no `netlify.toml`, no workflow reference, both Host
deploy workflows run the Cloudflare adapter, the legacy scripts' `deploy` verb
hard-refuses without `LMDJ_ALLOW_RETIRED_NETLIFY_DEPLOY=1`, and the deleted
sites return authenticated 404. Three stale spots remain inside current
source/docs and are reconciled here.

## Declared files

- `docs/governance/version-management.md` — the Web Host section still named
  the deleted `lmdj-creator.netlify.app` / `lmdj-runtime.netlify.app` as the
  fixed deployment targets; now records the `creator.lmdj.workers.dev` /
  `lab.lmdj.workers.dev` targets and the 2026-09-08 authorized deletion.
- `apps/docs-site/scripts/lib/build-check.mjs` — the internal-link checker
  still treated `https://lmdj.netlify.app` as the site origin, so absolute
  links to the real origin `https://docs.lmdj.workers.dev` were misclassified
  external and skipped. Now the current origin is internal and checked.
- `apps/docs-site/test/build-check.test.mjs` — regression: an absolute link to
  the current origin is internal (broken when missing); a foreign origin stays
  external.

## Explicitly not changed

- `scripts/ci/scope_policy.json` `netlify.toml` entries: retained as deletion
  guards, matching the repo convention of keeping ownership for the old side of
  deletion ranges (same as `apps/web-runtime-lab/` etc.); zero cost, trips the
  ownership gate if the file ever reappears.
- `apps/docs-site/test/smoke.test.mjs` `example.netlify.app` fixtures and the
  `before mutating Netlify` assertion text in the Host deploy workflow tests:
  arbitrary fixture names / historically accurate text for the retired path;
  no behavioral content.
- Versioned portal snapshots and dated historical docs: frozen.

## Verification

- `node --test apps/docs-site/test/build-check.test.mjs`
- `scripts/docs-site.sh check` — full pipeline; the origin change makes the
  checker classify every canonical/OG absolute link as internal, so the
  complete build is the far-side proof.

## Version Management

Version impact: none — governance text and a portal check tool; no Product,
Module, Provider or Contract identity changes.

## Documentation impact

Documentation impact: none. The build-check origin is internal tooling
behavior with no portal page describing the old constant; the
`version-management.md` fix corrects a governance doc, not a portal page
(`/operations/*` routes already name the Cloudflare targets). Portal check runs
as proof.
