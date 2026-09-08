---
id: blind-search-reads-as-absence
area: core
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/918#issuecomment-5581492704
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/980
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/974
    observed_by: Claude Code (Opus 5)
exit: none
---

# Before reporting an absence, say how the search would have looked had the thing been present -- if the answer is "the same", the search is not evidence; and before accepting a reported presence, check it at the site where it would have to exist

## Why

An empty search result has two causes that look identical: the thing is not
there, or the search could never have found it. Only the first is a finding.
The second is a fact about the search, and reporting it as a fact about the
repository is how a healthy system gets reported as broken.

Nothing in the tooling distinguishes them. `grep` exits 1 either way, a filter
that matches no test prints the same "0 tests" as a suite that has none, and an
error payload compared against the wrong shape is as quiet as a payload that
says nothing is wrong. The check that would separate them has to be applied by
the person running the search, in the moment before they write the conclusion
down, because afterwards the empty result is all the evidence there is.

### The worked example

`facade::ApplicationConfig` is brace-initialised **positionally** at every
construction site in this repository -- the Hosts pass a bare list of values
and no member name ever appears. The struct itself says so:
`packages/application-facade/include/lmdj/facade/application.hpp:248-252`
requires new members to be appended rather than inserted, because "every brace
initialisation of this struct in the repository is positional" and an insertion
"would silently rebind Hosts' collaborators by type instead of failing to
compile".

So `grep -rn "soundset_store_limits"` finds the declaration in
`application.hpp` and the `.value_or` read in `application.cpp`, and nothing
else. That result is byte-identical whether the Host injects the value or omits
it, and the natural reading of it is that nothing assigns the member.

The Web Host injects it. `packages/web-runtime-platform/CMakeLists.txt:28-31`
reads the four `maximum_soundset_*` keys out of
`products/lmdj/generated/web-runtime-identity.json`, `:115-118` turns them into
`LMDJ_WEB_LIMIT_SOUNDSET_*`, `packages/web-runtime-platform/src/bridge.cpp:2870`
builds a `constexpr lmdj::facade::SoundSetStoreLimits` from them, and `:2899`
passes it as the last positional member. A comment at `:2867` says so in
words. None of that is reachable by the member's name.

This blindness is **permanent and structural, and it covers every
`ApplicationConfig` member, present and future**. It is not a property of
`soundset_store_limits`, and it will not be fixed by adding one: as long as the
struct is positionally initialised, no member name can appear at its own
assignment, and every name search for one will return the same empty result
whether the Host wires it or not. The same holds for every other positionally
brace-initialised aggregate here -- `RuntimePreparationLimits`,
`SoundSetStoreLimits`, `ProviderPolicy`.

### What it cost

The false conclusion -- that the Web Host silently ran on Facade defaults
instead of its manifest-declared limits -- was written into a merged Pull
Request body and was on its way to the maintainer as a **latent defect in a
shipped Product Build**, `1.0.44.0`. It would have bought an investigation of
correct code, and, worse, credible-looking evidence for that investigation: the
grep really was empty. That consequence is why this is a ledger entry and not a
note to self.

The shape has recurred at least six times in one Stage, across areas that have
nothing else in common: a `-t` filter matching the wrong test and reading as a
passing suite, a GraphQL error blob compared against `"0"`, an audit axis
pointed at a path that does not exist and therefore never firing, a survey grep
missing ``Core MCP `3.0.0` `` because of the backticks, an unregistered test
file reading as coverage, and this. The rule is not area-specific even though
this entry's example is.

### The same rule, from the other side

An unchecked report costs the same as an unchecked search, and arrives with more
authority because it reads like an observation. A Host operation surface is a
closed, enumerable list: `packages/web-runtime-platform/src/control_runtime.cpp`
dispatches on exact operation strings and each handler declares its exact
payload keys through `require(exact_keys(payload, {...}))`. So "the Host
answered X to operation Y with argument Z" is refutable in about a minute,
before a line of storage code is read.

A report filed as the blocker for Stage 11's Web half claimed
`project.import.begin`, `project.import.chunk` and `project.import.commit` all
returned `ok: true`, then `project.inspect` "on that exact id" returned
`NOT_FOUND` with the Project directory absent from OPFS beside a present
`imports/` and `catalog/`. `project.import.chunk` is not an operation -- the
chunked legs are `project.import.index` and `project.import.entry`.
`project.inspect` declares `exact_keys(payload, {})` and inspects the session's
retained path, so it cannot be addressed by a Project ID and answers
`state_error` with no session open; the id-addressed operation is
`project.open`. Neither `imports/` nor `catalog/` is a directory this product
creates: the staging root is `.lmdj-host/import-staging`, the Set Store root is
`soundsets`, and the OPFS mount drops the leading `lmdj-workspace` segment
(`pathParts` in `packages/project-io/src/web/library_opfs_storage.js`), so the
browser-visible tree is not the path Core names. Driving the real sequence
against the packaged Host in Chromium showed the whole journey working.

Reading the implementation first is what makes this expensive. Storage code read
in search of a defect that was never described will always yield something that
*could* go wrong, and that reading then becomes the report's corroboration.

The investigation of that report also reproduced the absence side within the
hour: a grep of `apps/creator-web/src` for
`importProjectBundle|projectImport|project.open` returned nothing and was
reported as "the Creator has no Project Bundle import UI". It has one --
`app.tsx` wires `onImport` to `importProjectJourney` in
`src/runtime/project_actions.ts`, and four tracked Creator specs drive it -- and
the grep would have printed the same nothing either way. Knowing the rule is not
applying it.

### Three more instruments, and the same rule already covered them

#974 produced three more instances in one Task, none of them a search:

- **A parity harness that could not express a crash.**
  `CatalogUpstreamParityTest` classified every value as accept-or-refuse, so an
  input that made one implementation raise `ValueError` was recorded as parity
  with an input the other side merely declined. The shared list therefore
  contained none of the crashing values. Fixed by giving it a third outcome.
- **A corpus that could not generate the class it was sampling for.** One
  reviewer's 531-input sweep reported zero divergences in the dangerous
  direction; another's fuzz, generated from the implementation's own grammar,
  hit that class at roughly 1.7 percent of hosts. Two adversarial reviewers
  disagreed about whether a whole class of defect existed, and the clean report
  was the one whose corpus could not produce the shape.
- **A diff filter that could not see prose.** A reviewer verifying a change
  that was partly comment used a delta check filtering comment lines out of the
  diff. The missing comment was invisible by construction, and the null result
  was read as confirmation.

**None of this is a new rule.** "How to apply" below already asks what the
check would have printed had the thing been present, and already says to prove
it can fire at all; the examples above already include a `-t` filter and a
misparsed payload, so the entry was never search-only. Both parties in that
review restated the entry's own rule to each other as though it were a finding,
which is worth recording only because of *why*: neither had read
`.agents/pitfalls/` before concluding, and the entry's own check — look at what
a search for this would return before claiming it is new — is the one that
would have caught it.

What the three instances do add is a phrasing that fits an instrument rather
than a search, and is answerable while the instrument is being built:

> For this check, name the class it cannot express. If you cannot name one,
> that is the finding.

The harness could not express `crash`, the corpus could not express `numeric
last label`, the filter could not express `comment`.

The eighth instance arrived while a reviewer was verifying the seventh. Asked
to confirm the cross-links added below, they grepped and got `0 referrers` for
all three -- true of the tree they were standing in, which was `main`, and
false of the commit under review, which was on a branch. What stopped them was
that `0, 0, 0` looked too clean for three files they had just read; had only
two of the three been linked, the wrong-tree grep and the real gap would have
printed the same number and nothing would have looked odd.

That instance is worth more than its size, because it is where the two shapes
in this entry turn out to be one. A stale pointer and a blind instrument are
usually distinguishable -- the first is a fact that went out of date, the
second a check that could not have reported otherwise -- but a grep against the
wrong tree is both at once, and the symptom is a number that is correct for
what was measured and wrong for what was asked. **Whoever verifies a commit is
the person most likely to be standing somewhere else**, so re-resolve the tree
before reading a zero, and prefer `git show <sha>:<path>` over reading the
working copy.

### The same defect has three entries and no cross-references

This is the part that is actually new, and it is a fact about the ledger rather
than about any instrument.

- [`audit-axis-cannot-fire`](audit-axis-cannot-fire.md) — `area: ci-release`.
  An occupancy axis reading a path that does not exist reports `clear` on every
  input, "indistinguishable from a clean audit".
- [`gh-authorization-failure-reads-as-absence`](gh-authorization-failure-reads-as-absence.md)
  — `area: ci-release`. A failed authorization returning an empty list.
- this entry — `area: core`.

One defect, three entries, **zero cross-references in either direction**
(verified by grep, both ways), and this chain's instances belong to a fourth
surface again — Host test tooling. The ledger contract says to find prior art
by searching open entries by the Task's `area:*` labels, so a defect whose
instances are spread across four areas is precisely what that lookup cannot
reach. The discovery mechanism has a blind spot of the shape these three
entries warn about.

Cross-linked here in all three directions as the cheap half of the remedy;
whether they should be folded into one entry is
[#983](https://github.com/endaye/lmdj/issues/983). That is a finding about the
ledger's structure, not this entry's escalation — the escalation is #980, in the
closing paragraph, where the contract looks for it.

**This section's own evidence arrived while it was being written.** Two lanes
bumped this entry within seven minutes: one with the presence side above, from
a Web import report, and one with the instruments above. Each opened an
escalation Issue, so the entry briefly had two. The timestamps are the point --
#980 at 15:12:01Z, then #983 at 15:18:57Z by a lane that had been editing this
very file since 15:12:35Z. The second was opened against an entry that already
had an escalation, by someone with the file open, because an `area:core` search
does not surface an Issue and the contract's retrieval clause does not mention
open Issues at all. Neither agent was careless; the retrieval step could not
express the question.

## How to apply

- Before writing down that something is absent, answer one question: **what
  would this search have printed if the thing were present?** If the answer is
  "the same thing", stop -- you have measured the search, not the repository.
  Find a formulation whose positive and negative results differ, or verify at
  the site where the thing would have to exist.
- Prove the search can fire at all. Run it against a case you know is present:
  grep for a member you can see being assigned, point the filter at a test you
  know exists, feed the parser a payload you know is an error. A search that
  finds nothing and has never been shown to find anything is not a measurement.
- For `ApplicationConfig` specifically, never conclude from a name search. Read
  the construction sites and count positions against the member order in
  `packages/application-facade/include/lmdj/facade/application.hpp`:
  `packages/web-runtime-platform/src/bridge.cpp` for the Web Host, and the
  native Host's initialiser.
- Where a value is meant to flow from a manifest, trace the chain end to end
  rather than at one link -- generated identity JSON, `string(JSON ...)` in
  CMake, compile define, construction site. One link found empty says nothing
  about the others.
- Report absences with their method attached: "no call site assigns X, verified
  by reading both Hosts' initialiser lists" is a finding; "grep finds no
  assignment" is not.
- Before opening a lane from a report, check the report the same way. For every
  operation it names, `grep 'operation == "<name>"'` in `control_runtime.cpp`;
  for every argument it says it passed, read that handler's
  `require(exact_keys(payload, {...}))` line; for every path it says it
  inspected, find the literal in Core that writes it. Do this before reading the
  implementation. A report that fails the check has not observed a defect, and
  the honest outcome is a withdrawal pinned to an `origin/main` SHA.

- When the instrument is a **test harness, a sampling corpus or a review tool**
  rather than a search, name the class it cannot express before trusting a
  clean run from it. A harness with fewer outcomes than the question has
  answers, a corpus drawn from a space that cannot produce the failing shape,
  and a filter defined by excluding the thing under review are all the same
  defect, and all three reported clean.

`exit: none`, escalated at recurrence 2 to
https://github.com/endaye/lmdj/issues/980. The invariant is a research habit,
and no gate can read it: what went wrong was an inference from a correct
observation, not an artifact any check could inspect. A checker could flag
"`ApplicationConfig` gained a member without every construction site changing",
but that catches a missed call site, which is a different defect; it would not
have caught this one, and shipping it as this entry's exit would put a mechanism
in the ledger that does not enforce the rule it claims to. Revisit if a later
recurrence turns out to be mechanically decidable.

A sound search whose result later expired is a different failure and has its
own entry: [`stale-premise-gets-implemented`](stale-premise-gets-implemented.md).
This entry is about a search that could never have distinguished present from
absent; that one is about a finding that was correct when measured and was
re-used after the tree moved past it.
