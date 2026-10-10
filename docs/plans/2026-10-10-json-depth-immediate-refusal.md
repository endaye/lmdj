# Immediate refusal at the existing JSON depth limit

## Premises at current main

Base: `d5554ed55f7ebc2d800285715cef79dcfed57c9a`.
This is a bounded prerequisite repair discovered while completing the Creator
follow-up Goal's required ASan acceptance. It is separate from the cutoff,
transport replay and monitoring Tasks and preserves their frozen proof trees.

The original complete ASan lane at `6ec71050e02cad41bac85e0c852ab80b1fd0b6e7`
failed `foundation.json` at its unchanged 30-second deadline. Its source and
five-case test are byte-identical on current main. Phase-only diagnostics finish
both 1,000-depth overloads, then spend the deadline in the 200,000-depth byte
parse; an original-binary stack sample is in nlohmann's lexer. The guard refuses
DOM containers at depth 64 but returns false to the parser, which continues
scanning the refused input. Source SHA-256:
`1c9d1b537e91dc2aff5cce5103c6d98ea707fa31c73d2e5bf94402da871c3858`.

PR #69 already delivered the exact depth limit and crash refusal, and #82 routed
disk JSON through this parser. Do not reimplement those deliveries or change
their accepted/rejected boundary. No successor in the refreshed JSON PR query
implements immediate refusal. A private prototype with the same GNU 13.3,
ASan/UBSan flags and original five cases passes in 0.0177 seconds; it is diagnostic
evidence, not the formal Task artifact or complete ASan acceptance.

## T1

Declared files:

- `packages/foundation/src/json.cpp`
- `packages/foundation/include/lmdj/foundation/json.hpp`
- `packages/foundation/CMakeLists.txt`
- `apps/docs-site/docs/core/modules/foundation.mdx`
- `docs/plans/2026-10-10-json-depth-immediate-refusal.md`

Throw a private depth-refusal signal from the existing container-start guard and
catch only that signal inside both public overloads, returning the existing
`std::nullopt`. This stops rejected-input scanning before deeper DOM construction.
Keep the exact limit, accepted values, malformed-input refusal and valid UTF-8
behavior. The signal must never escape the public parser. Failed stream reads
stop at the first excessive container; Project Store, Sequence Journal, Attempt
Store and Assembly loading already treat parser refusal as terminal.
Update the public processing comment and current Foundation page to describe
that early refusal and retained separate byte-size limits. Emscripten compiles
and links Foundation with the exception support needed to contain the private
signal; native compiler and sanitizer options remain unchanged. The existing
Project I/O exception settings apply to its consumers, not its upstream
Foundation compilation.

Lowest-tier verification uses the unchanged `foundation.json` CTest group on
fresh GNU dev and ASan builds, plus the staged new-file ownership suite. Preserve
all five cases, including both 200,000-depth overloads, and the original CTest
deadlines. Existing original-binary timeout evidence supplies the pre-fix RED;
the prototype does not substitute for rebuilding the tracked implementation.
Record exact source/test hashes and build statuses. No test, coverage floor,
compiler, kernel setting, sanitizer option or timeout change is part of T1.
Also cross-compile the same original five-case Foundation target with pinned
Emscripten and execute it through Node 26, then run the Portal check. This proves
the actual Wasm library contains the private signal, rather than relying on
native exception support. No new test or universal gate is introduced.
Complete selected batch lanes and current-head independent review remain merge
obligations. The other original ASan failures retain their own unresolved causes.

## Version Management

Version impact: Foundation compatible PATCH debt for the Goal's V1 settlement.
No manifest identity or Product Build allocation, tag, Release or deployment in
this Task. The public API and refusal result are unchanged.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/foundation/
Reason: documents immediate depth refusal, the rejected stream position and
Emscripten exception handling alongside the existing JSON boundary. No public
capability, Contract shape, source identity or architecture topology change.

## Pitfall Impact

Pitfall impact: none
Reason: this is product parser logic exercised by the existing strict depth
regression. Existing rebuilt-artifact and failure-classification guidance applies.

## Verification state

The first tracked-source GNU dev and ASan builds passed all original cases in
0.021 and 0.032 seconds respectively, preserving the actual CTest deadlines of
10 and 30 seconds. Ownership passed all 77 checks. Those frozen two-file results
remain retained. The public header still documented complete refused-input
scanning, so this Task now declares its processing comment and Portal update.
The private signal also needs Emscripten exception handling in Foundation itself.
Verify the final five-file input and real Wasm target before commit.

Fresh main `6ae1dff55b07c7882527941e144cd5874bf1d1d3` adds #1944's Portal preview
controls; all relevant parser/header/CMake/test/Foundation-page baselines remain
unchanged. Commit, push, review, complete selected batch verification and guarded
merge remain pending.

The final five-file tracked input passed fresh GNU dev and ASan builds and the
unchanged five-case group (0.059 and 0.041 seconds; original deadlines 10 and
30 seconds). The pinned Emscripten build of the same original target passed
through Node 26 in 0.097 seconds at its original 10-second deadline, including
both 200,000-depth overloads without an escaping refusal signal. Staged ownership
passed all 77 checks (7.99 seconds); the complete Portal check passed all 50
routes and internal links. The source, header, CMake and Portal page remain
byte-identical to those verified inputs; this results paragraph is the only
subsequent edit. Complete selected batch lanes, independent current-head review
and guarded merge remain pending. No other ASan failure is declared resolved.
