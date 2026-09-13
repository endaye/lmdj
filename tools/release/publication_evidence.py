"""Prepare one reviewed publication evidence patch; never publish or deploy.

The exact published verifier supplies authority. This module produces a patch
against bounded, byte-checked local sources. Applying/committing the patch,
current-head review, merge and public-site verification are separate boundaries.
"""

from copy import deepcopy
from dataclasses import replace
from difflib import unified_diff
import json
from pathlib import Path
import re
import stat

from .changelog import ChangelogError
from .changelog_site import LEDGER, PUBLICATIONS, _pairs, project
from .model import Disposition, canonical_json, load_ledger_document
from .publication import collect_publication_state

PIN = "apps/docs-site/scripts/lib/snapshot-provenance.mjs"
PAGES = "apps/docs-site/docs/releases"
INDEX = PAGES + "/index.mdx"


def fail(why):
    raise ChangelogError(f"why: publication evidence {why}; remedy: reconcile the exact published Release and reviewed source before preparing its evidence PR")


def _read(root, relative):
    target = root / relative
    for parent in target.parents:
        if parent == root:
            break
        if parent.is_symlink() or not parent.is_dir():
            fail("source parent is unsafe")
    try:
        info = target.lstat()
    except OSError:
        fail("source is unavailable")
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_size > 8 * 1024 * 1024):
        fail("source is not a bounded single-link regular file")
    try:
        return target.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        fail("source bytes are unavailable or invalid UTF-8")


def _json(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError):
        fail("source JSON is invalid")


def _lf_lines(text):
    # Git patches frame only literal LF; Unicode line separators are content.
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _rewrite_entry(original, tag):
    # Retain all unrelated ledger bytes, including historical evidence. The
    # canonical ledger stores each entry on one line, as does promotion tooling.
    lines = _lf_lines(original)
    matches = []
    for index, line in enumerate(lines):
        candidate = line.strip().removesuffix(",")
        if not candidate.startswith("{"):
            continue
        try:
            entry = json.loads(candidate, object_pairs_hook=_pairs)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("tag") == tag and "kind" in entry:
            matches.append((index, entry))
    if len(matches) != 1:
        fail("ledger must contain exactly one one-line target entry")
    index, entry = matches[0]
    if entry["disposition"] == "published":
        return original
    if entry["disposition"] != "releasable":
        fail("intent is not releasable or published")
    entry["disposition"] = "published"
    old = lines[index]
    indent = old[:len(old) - len(old.lstrip())]
    comma = "," if old.strip().endswith(",") else ""
    ending = "\n" if old.endswith("\n") else ""
    lines[index] = indent + json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + comma + ending
    return "".join(lines)


def _diff(relative, before, after):
    if before == after:
        return ""
    if (before is not None and not before.endswith("\n")) or not after.endswith("\n"):
        fail("patch source lacks canonical final newline")
    header = f"diff --git a/{relative} b/{relative}\n"
    if before is None:
        header += "new file mode 100644\n"
    return header + "".join(unified_diff(
        _lf_lines(before or ""), _lf_lines(after),
        fromfile=f"a/{relative}" if before is not None else "/dev/null",
        tofile=f"b/{relative}"))


def plan_publication_patch(root, policy, intent, record):
    """Pure local planner. Caller must supply freshly verified intent/record.

    Compare both complete intent and frozen page bytes; a recorded digest alone
    cannot authorize rewriting another release or hiding a missing old page.
    """
    root = Path(root).resolve()
    ledger_text = _read(root, LEDGER)
    ledger_document = _json(ledger_text)
    ledger = load_ledger_document(ledger_document, policy)
    selected = ledger.intent_for_tag(intent.tag)
    if selected is None or selected.disposition not in (Disposition.RELEASABLE, Disposition.PUBLISHED):
        fail("local intent is missing or inadmissible")
    if replace(selected, disposition=intent.disposition) != intent:
        fail("local and freshly verified canonical intents differ")
    if record.get("tag") != intent.tag:
        fail("record belongs to another tag")
    publications_text = _read(root, PUBLICATIONS)
    publications = _json(publications_text)
    before_pages = {page["file"]: page["content"] for page in project(ledger, publications)}
    actual = {PAGES + "/" + entry.name for entry in (root / PAGES).iterdir()}
    if actual != set(before_pages):
        fail("historical page inventory differs from the reviewed records")
    for relative, content in before_pages.items():
        if _read(root, relative) != content:
            fail("existing page differs from its frozen projection")

    rewritten = _rewrite_entry(ledger_text, intent.tag)
    new_ledger = load_ledger_document(_json(rewritten), policy)
    expected_ledger = replace(ledger, entries=tuple(
        replace(entry, disposition=Disposition.PUBLISHED) if entry.tag == intent.tag else entry
        for entry in ledger.entries))
    if new_ledger != expected_ledger:
        fail("ledger rewrite changes facts other than disposition")
    updated = deepcopy(publications)
    existing = [entry for entry in updated["entries"] if entry["tag"] == intent.tag]
    if existing:
        if existing != [record]:
            fail("immutable publication record conflicts with the observed Release")
    else:
        updated["entries"].append(record)
    after_pages = {page["file"]: page["content"] for page in project(new_ledger, updated)}
    added = set(after_pages) - set(before_pages)
    if set(before_pages) - set(after_pages) or added not in (set(), {PAGES + f"/{intent.identity}.mdx"}):
        fail("generated page scope is not exactly the selected publication")
    for relative in set(before_pages) - {INDEX}:
        if before_pages[relative] != after_pages[relative]:
            fail("frozen historical content would change")

    pin_text = _read(root, PIN)
    pattern = r"^export const SOURCE_DOCUMENT_COUNT = ([1-9][0-9]*);$"
    matches = list(re.finditer(pattern, pin_text, re.MULTILINE))
    if len(matches) != 1:
        fail("independent source-document count pin is unavailable")
    match = matches[0]
    # Increment the independent reviewed pin by the declared added page count;
    # never derive it from observed files (which could already be missing).
    new_pin = pin_text[:match.start(1)] + str(int(match[1]) + len(added)) + pin_text[match.end(1):]
    changes = [(LEDGER, ledger_text, rewritten),
               (PUBLICATIONS, publications_text, publications_text if existing else canonical_json(updated).decode()),
               (PIN, pin_text, new_pin)]
    changes.extend((relative, before_pages.get(relative), content) for relative, content in after_pages.items())
    return "".join(_diff(relative, before, after) for relative, before, after in changes)


def collect_publication_patch(tag, release_id, plan_sha256, context):
    record, intent = collect_publication_state(tag, release_id, plan_sha256, context)
    return plan_publication_patch(context.repo_root, context.policy, intent, record)
