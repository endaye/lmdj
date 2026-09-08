#!/usr/bin/env python3

"""Every Sound Set refusal belongs to the Facade; no Host may decide one.

#799 Task 4b, the cross-Host half. S11-D3 and the Locked Error Reasons table
put Set eligibility, content integrity and audio support in one place: the
Application Facade decides, and every Host repeats its answer. Four Hosts read
those operations -- the Web Host's `control_runtime` and `bridge`, the Native
Host, and core-mcp -- and each has its own test suite that would stay green if
that Host quietly started refusing on its own.

The defect this catches is one Host's refusal drifting from the Facade's. It is
invisible to any per-Host suite by construction, because each suite asserts
what its own Host does rather than what the Facade said.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]

# The Locked Error Reasons table of the Stage 11 plan. Naming one of these is
# how a Host would express a Sound Set refusal of its own; the vocabulary is
# frozen, so this list cannot drift without a design change that would also
# touch the plan.
LOCKED_REASONS = (
    "soundset_manifest_invalid",
    "soundset_slot_invalid",
    "soundset_occupied_conflict",
    "soundset_license_ineligible",
    "soundset_content_mismatch",
    "catalog_unavailable",
    "soundset_audio_unsupported",
)

# The Hosts' protocol and transport layer -- where a request is validated,
# dispatched and answered. Deliberately not `apps/creator-web/src/components`:
# a presentation layer names locked reasons to render guidance for them, which
# is recognising a refusal rather than deciding one, and the Creator surface
# does exactly that for four of the seven. That distinction is the boundary
# this gate defends and also the limit of what it can see -- see `emitted`.
HOST_SOURCES = (
    "packages/web-runtime-platform/src/control_runtime.cpp",
    "packages/web-runtime-platform/src/bridge.cpp",
    "packages/web-runtime-platform/web/protocol.mjs",
    "packages/web-runtime-platform/web/runtime_session.mjs",
    "apps/native-host/src/main.cpp",
    "apps/core-mcp/lmdj_core_mcp/server.py",
)

# Where the vocabulary is actually emitted. Read as a positive control, one
# reason at a time: a rule that cannot fire is not a rule, and a search finding
# nothing everywhere is indistinguishable from a broken search
# (`.agents/pitfalls/blind-search-reads-as-absence.md`).
#
# The first draft of this gate anchored the control on the Facade alone and
# found one reason of seven, which would have left six rules unexercised and
# silently unfalsifiable. The reasons are raised in Core, not in the Facade:
# manifest and slot faults and licence ineligibility in `foundation`, occupied
# collisions in `authoring-domain`, content mismatch and catalog unavailability
# in `project-io`, and whole-Set audio support in the Facade.
EMITTING_MODULES = (
    "packages/foundation/src",
    "packages/authoring-domain/src",
    "packages/project-io",
    "packages/application-facade/src",
)


def emitted(source: str, reason: str) -> bool:
    """True when `reason` appears as a string literal rather than as prose.

    A Host that decides a refusal has to put the token on the wire, which means
    a quoted literal. A Host that *documents* deferring to the Facade writes the
    same token in a comment -- `runtime_session.mjs` does exactly that, in a
    comment explaining that it forwards the user's policy and never substitutes
    a default, which is the opposite of deciding. Matching prose would have made
    this gate refuse the clearest example of the behaviour it wants.

    What this cannot express: a Host that decides a refusal while naming the
    token only in a comment, or one that refuses with a different message
    entirely. The first cannot reach the wire and so cannot matter; the second
    is real and out of reach of any textual rule -- it needs the behavioural
    parity table this gate is the cheap half of.
    """
    return re.search(rf'["\']{re.escape(reason)}["\']', source) is not None


def read(relative: str) -> str:
    path = REPO_ROOT / relative
    if not path.is_file():
        raise AssertionError(
            f"why: {relative} is missing, so this gate measured nothing for it; "
            "remedy: update HOST_SOURCES if the file moved, or restore the file"
        )
    return path.read_text(encoding="utf-8")


def main() -> int:
    problems: list[str] = []

    corpus = []
    for module in EMITTING_MODULES:
        root = REPO_ROOT / module
        if not root.is_dir():
            problems.append(
                f"why: {module} is missing, so the positive control below is "
                "weaker than it reads; remedy: update EMITTING_MODULES"
            )
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".cpp", ".hpp"}:
                corpus.append(path.read_text(encoding="utf-8", errors="ignore"))
    joined = "\n".join(corpus)

    # Per reason, not in aggregate. One findable token would otherwise let the
    # other six rules pass as unfalsifiable.
    unprovable = [r for r in LOCKED_REASONS if not emitted(joined, r)]
    if unprovable:
        problems.append(
            "why: these locked reasons are emitted nowhere this gate can see, "
            f"so their rules cannot fire and prove nothing: {unprovable}; "
            "remedy: confirm the Locked Error Reasons table still uses these "
            "tokens, and update LOCKED_REASONS or EMITTING_MODULES to match"
        )

    for relative in HOST_SOURCES:
        source = read(relative)
        for reason in LOCKED_REASONS:
            if emitted(source, reason):
                problems.append(
                    f"{relative}: host-decided-soundset-refusal -- why: this "
                    f"Host names the locked reason {reason!r}, which means it "
                    "is deciding a Sound Set refusal the Application Facade "
                    "owns; remedy: forward the operation and return the "
                    "Facade's answer unchanged -- S11-D3 puts eligibility, "
                    "content integrity and audio support in one place so the "
                    "Hosts cannot disagree about them"
                )

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(
        "Sound Set refusal ownership: PASS "
        f"({len(HOST_SOURCES)} Host sources, {len(LOCKED_REASONS)} reasons, "
        "each proven findable in the emitting modules)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
