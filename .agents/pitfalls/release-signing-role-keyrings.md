---
id: release-signing-role-keyrings
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/pull/520
    observed_by: claude-fable-5-1
exit: gate:tests/build/release_prepare_test.py
---

# Release signing has two key roles but resolved both from one `GNUPGHOME`, so `prepare` failed at asset signing with no indication that the missing key was the checksum role's.

## Why

`tools/release/policy.json` pins two distinct fingerprints, `product` for the
annotated tag and `checksum` for the detached asset signatures. On an operator
machine those secrets legitimately live in separate keyrings: the product key
in the default `~/.gnupg`, the checksum key in the dedicated
`~/.gnupg-lmdj-release`. `cli.py` read one `GNUPGHOME` for both roles, so
whichever keyring was selected was missing the other role's secret and
`sign_detached` raised the role-agnostic `release detached signing failed`.

Two things made this expensive to diagnose during a live release. The error
names the operation, not the role or the fingerprint it looked for, so the
first hypothesis is a passphrase or agent problem rather than a keyring
mismatch. And `gpg` will sign non-interactively with a cached passphrase while
refusing to export the same secret key without a fresh one, so "signing works
but the key cannot be moved" looks like an agent fault instead of the
deliberate export policy it is. Moving key material is not the repair and was
never necessary.

A related trap sits next to it: this repository's operator config sets
`gpg.format=ssh` for commit signing, so `git tag --sign` would select SSH
signing and reject an OpenPGP fingerprint. Tag creation must pass
`-c gpg.format=openpgp` explicitly rather than inherit operator config.

## How to apply

Keep each signing role bound to its own keyring: the checksum role resolves
`~/.gnupg-lmdj-release`, and the product role continues to resolve the ambient
`GNUPGHOME`. Never relocate a secret key to satisfy a single-keyring lookup.
When `prepare` reports `release detached signing failed`, list the secret keys
in both keyrings against the two policy fingerprints before suspecting the
agent. `tests/build/release_prepare_test.py` asserts the checksum keyring stays
distinct from the product keyring, and `tests/build/release_transitions_test.py`
asserts tag creation forces the OpenPGP format.
