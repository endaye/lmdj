# Pitfall Ledger

The Pitfall Ledger retains process and invariant knowledge that cannot be derived
from the product code or fully captured by a product regression test. It is
repository-resident and agent-neutral so every human and coding agent encounters
the same operational memory.

## Directory contract

- Entries live in `.agents/pitfalls/`, one Markdown file per pitfall.
- The directory listing is the index. Do not add a shared hand-maintained index
  or a `docs/lessons/` collection; parallel branches must not share an append
  point.
- Use a stable lowercase kebab-case `id` as the filename, for example
  `.agents/pitfalls/release-intent-binding.md`.
- Before adding an entry, grep existing `id` and `area` values. A near match is
  another recurrence of the existing pitfall, not a sibling entry.
- Product-logic defects whose regression test fully expresses the invariant do
  not belong here. The regression test is their exit.

## Entry contract

Copy `.agents/pitfalls/TEMPLATE`. The template deliberately has no `.md`
suffix so a future `*.md` entry lint does not mistake placeholders for a live
entry. Every entry has YAML frontmatter with:

- `id`: stable lowercase kebab-case identifier matching the filename;
- `area`: one existing GitHub `area:*` label namespace without the `area:`
  prefix;
- `status`: `open` or `absorbed`;
- `recurrences`: a YAML list where every occurrence contains an ISO date, a
  GitHub PR or commit link, and `observed_by` naming the agent/model that hit it
  (use `unknown` only when surviving evidence cannot attribute it);
- `exit`: `none`, `skill:<path>`, or `gate:<test path>`.

The body contains one sentence naming the pitfall, a **Why** section explaining
the root cause, and a **How to apply** section with imperative guidance any
agent can follow. An open entry with `exit: none` states why no mechanism exists
yet. Absorbed entries remain as concise pointers to their enforcing mechanism,
not a growing alternative governance narrative.

## Recurrence and escalation

When an entry's recurrence count reaches 2, the Task handling that recurrence
must do one of the following in the same shipping cycle:

1. land an eligible mechanism, record it in `exit`, and set `status: absorbed`;
2. open an escalation Issue, link it from the entry, and keep the entry open
   until the mechanism lands.

Later occurrences remain in the recurrence list even after absorption. If an
absorbed mechanism fails, record the occurrence and repair or replace the exit;
do not fork the history into a new entry.

## Gate admission criteria

A pitfall may graduate to a CI or audit gate only when all three criteria hold:

1. the invariant is settled and is not an open question in
   `docs/prd/questions/`;
2. violation of the invariant is mechanically decidable;
3. the check is deterministic.

If any criterion fails, the entry exits to a `skill:<path>` section instead of
a gate. Do not turn product judgment, fuzzy duplicate detection, or an open
Contract/concurrency question into a mechanical gate.

## Gate failure messages

Every gate admitted under this contract must fail with a message containing
both:

- `why`: the violated invariant and why the observed state violates it;
- `remedy`: the concrete action or command that corrects the state.

A bare assertion, generic invalid-state message, or file-only diagnostic does
not satisfy this rule.

## Retrieval and updates

At a skill trigger point, search open entries by the Task's `area:*` labels and
read each matching entry before acting. The shipping flow in
`.agents/skills/issue-done/SKILL.md` owns record-or-bump, recurrence counting,
and the Pull Request declaration. Release-specific retrieval belongs in
`.agents/skills/lmdj-release/SKILL.md`.
