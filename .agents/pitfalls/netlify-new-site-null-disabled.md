---
id: netlify-new-site-null-disabled
area: web-host
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/actions/runs/33630866285
    observed_by: claude-fable-5-1
exit: gate:apps/web-runtime-host/test/netlify_api_test.py
---

# Netlify reports a never-deployed site's `disabled` flag as null, and requiring a boolean rejected the first deployment to every newly provisioned site.

## Why

`NetlifyClient.get_site` validated site identity with
`isinstance(disabled, bool)`. A site that has never been deployed returns
`"disabled": null`; the field only becomes `false` once a deploy sets it. The
first Creator deployment to the freshly provisioned `lmdj-creator` therefore
failed preflight with `Netlify site identity is invalid`, while
`lmdj-runtime` passed because months of deploys had populated its flag.

The check was stricter than the invariant it protects. `disabled` feeds only
`serving_state = "disabled" if disabled or state == "disabled" else state`,
where a null flag is already correctly falsy. Rejecting null bought nothing and
cost the entire first-deployment path.

The message named the site identity, which invites suspicion of the configured
Site ID or the production URL, and both were correct. The site's own JSON held
the answer: the new site read `"disabled": null` where the working site read
`"disabled": false`.

This is the same never-exercised-path family as
[[operator-only-deploy-script-faults]] and
[[github-release-asset-url-rewrite]]: every existing test supplied a boolean,
so no fixture ever modelled a site that had not been deployed yet.

## How to apply

When validating a third-party API document, reject a value only when it would
make a decision unsafe. An optional flag whose absence has a well-defined
meaning must accept null and let the downstream expression handle it. Any
fixture for a resource with a first-use state must model that first use: a
never-deployed site, an empty inventory, an unset optional flag. When a Netlify
identity error names a field you configured correctly, diff the new resource's
JSON against a working one before re-checking the configuration.
