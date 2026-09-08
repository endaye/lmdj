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

`exit: none`, escalated at recurrence 2 to
https://github.com/endaye/lmdj/issues/980. The invariant is a research habit,
and no gate can read it: what went wrong was an inference from a correct
observation, not an artifact any check could inspect. A checker could flag
"`ApplicationConfig` gained a member without every construction site changing",
but that catches a missed call site, which is a different defect; it would not
have caught this one, and shipping it as this entry's exit would put a mechanism
in the ledger that does not enforce the rule it claims to. Revisit if a later
recurrence turns out to be mechanically decidable.
