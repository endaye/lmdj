"""One frozen, source-accounted Product changelog for Release and doc-site.

Git membership is mechanical evidence, not proof that editorial claims are true.
The candidate/evidence PR review owns semantic claims and exclusion reasons.
The caller must audit the selected published baseline's actual signed Release.
"""

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import subprocess

from .model import CANONICAL_REPOSITORY, Disposition, ReleaseKind, canonical_sha256


class ChangelogError(ValueError):
    pass


def _fail(why):
    raise ChangelogError(f"why: {why}; remedy: regenerate and review the exact candidate changelog")


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        _fail("invalid exact changelog revision")


def _tag(value):
    if type(value) is not str or re.fullmatch(r"lmdj-v(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}", value) is None:
        _fail("invalid Product tag")


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail("changelog fields are missing or unknown")


def _text(value):
    if (type(value) is not str or not 1 <= len(value) <= 1000 or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or any(char in value for char in "<>`{}[]\\")
            or re.search(r"(?i)(?:gh[pousra]_|github_pat_|sk-|bearer\s|private.key|password\s*[:=]|token\s*[:=])", value)):
        _fail("changelog text is unsafe or not a bounded plain-text line")


def _git(root, *arguments, allow_not_ancestor=False):
    # Do not let ambient GIT_DIR, injected -c config, replace objects or a user's
    # global config substitute another commit graph for the selected repository.
    environment = {key: value for key, value in os.environ.items()
                   if key in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                       GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", LC_ALL="C")
    try:
        result = subprocess.run(["git", "--no-pager", "-C", str(root), *arguments],
                                capture_output=True, text=True, env=environment, timeout=30)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        _fail("exact changelog Git graph is unavailable")
    if allow_not_ancestor and result.returncode == 1:
        return False
    if result.returncode != 0:
        _fail("exact changelog Git graph cannot be verified")
    return result.stdout.strip()


def _ancestor(root, before, after):
    _sha(before)
    _sha(after)
    return _git(root, "merge-base", "--is-ancestor", before, after,
                allow_not_ancestor=True) is not False


def _complete_graph(root):
    if _git(root, "rev-parse", "--is-shallow-repository") != "false":
        _fail("shallow history cannot prove the complete changelog range")


def select_baseline(root: Path, intent, ledger):
    """Select the unique nearest published same-profile Product ancestor.

    Never use floating latest, publication dates, numeric tag sorting, or a
    releasable-but-unpublished identity. Incomparable published ancestors fail.
    """
    _complete_graph(root)
    _sha(intent.target_revision)
    published = [item for item in ledger.entries
                  if item.kind is ReleaseKind.PRODUCT and item.profile == intent.profile
                  and item.disposition is Disposition.PUBLISHED and item.tag != intent.tag]
    candidates = [item for item in published
                  if _ancestor(root, item.target_revision, intent.target_revision)]
    nearest = [item for item in candidates if not any(
        other.tag != item.tag and _ancestor(root, item.target_revision, other.target_revision)
        for other in candidates)]
    if not candidates:
        if published:
            _fail("published history exists but no candidate baseline is provable")
        return None
    if len(nearest) != 1:
        _fail("published changelog baseline is ambiguous")
    return {"tag": nearest[0].tag, "target_revision": nearest[0].target_revision}


def source_inventory(root: Path, target: str, baseline: dict | None):
    _complete_graph(root)
    _sha(target)
    if _git(root, "cat-file", "-t", target) != "commit":
        _fail("changelog target is not a commit")
    revision_range = target
    if baseline is not None:
        _keys(baseline, ("tag", "target_revision"))
        _tag(baseline["tag"])
        _sha(baseline["target_revision"])
        if not _ancestor(root, baseline["target_revision"], target):
            _fail("changelog baseline is not a candidate ancestor")
        revision_range = baseline["target_revision"] + ".." + target
    commits = _git(root, "rev-list", "--reverse", "--topo-order", revision_range, "--").splitlines()
    if len(commits) > 10000:
        _fail("changelog range exceeds its reviewable inventory limit")
    for commit in commits:
        _sha(commit)
    return commits


def freeze(root, intent, ledger, changes, exclusions):
    """Bind reviewed editorial input to a freshly enumerated exact Git range."""
    if intent.kind is not ReleaseKind.PRODUCT or intent.profile != "web-hosts":
        _fail("unsupported changelog Product profile")
    _tag(intent.tag)
    if intent.identity != intent.tag.removeprefix("lmdj-v"):
        _fail("changelog Product identity differs from its tag")
    baseline = select_baseline(root, intent, ledger)
    document = {"schema": "lmdj.release-changelog.v1", "repository": CANONICAL_REPOSITORY,
                "tag": intent.tag, "product_build": intent.identity, "profile": intent.profile,
                "target_revision": intent.target_revision, "baseline": baseline,
                "commits": source_inventory(root, intent.target_revision, baseline),
                "changes": deepcopy(changes), "exclusions": deepcopy(exclusions)}
    validate(document)
    return document


def validate(document):
    _keys(document, ("schema", "repository", "tag", "product_build", "profile",
                     "target_revision", "baseline", "commits", "changes", "exclusions"))
    if (document["schema"] != "lmdj.release-changelog.v1"
            or document["repository"] != CANONICAL_REPOSITORY or document["profile"] != "web-hosts"):
        _fail("unsupported changelog authority or schema")
    _tag(document["tag"])
    _sha(document["target_revision"])
    if document["product_build"] != document["tag"].removeprefix("lmdj-v"):
        _fail("changelog Product identity differs")
    if document["baseline"] is not None:
        _keys(document["baseline"], ("tag", "target_revision"))
        _tag(document["baseline"]["tag"])
        _sha(document["baseline"]["target_revision"])
        if document["baseline"]["tag"] == document["tag"]:
            _fail("changelog baseline cannot be the current release")
    inventory = document["commits"]
    if type(inventory) is not list or len(inventory) > 10000:
        _fail("invalid changelog source inventory")
    for commit in inventory:
        _sha(commit)
    if len(set(inventory)) != len(inventory):
        _fail("duplicate changelog source commit")
    covered = []
    if type(document["changes"]) is not list or type(document["exclusions"]) is not list:
        _fail("invalid changelog editorial inventory")
    for change in document["changes"]:
        _keys(change, ("category", "area", "text", "commits"))
        if change["category"] not in ("feature", "fix", "compatibility", "known-issue"):
            _fail("unknown changelog category")
        if change["area"] not in ("creator", "runtime", "core", "release"):
            _fail("unknown changelog product area")
        _text(change["text"])
        if type(change["commits"]) is not list or not change["commits"]:
            _fail("changelog entry has no exact source")
        for commit in change["commits"]:
            _sha(commit)
            covered.append(commit)
    for excluded in document["exclusions"]:
        _keys(excluded, ("commit", "reason"))
        _sha(excluded["commit"])
        _text(excluded["reason"])
        covered.append(excluded["commit"])
    if len(covered) != len(set(covered)) or set(covered) != set(inventory):
        _fail("changelog omits, duplicates or invents source commits")


def verify_source(root, intent, ledger, document):
    validate(document)
    expected = freeze(root, intent, ledger, document["changes"], document["exclusions"])
    if expected != document:
        _fail("frozen changelog scope differs from the exact candidate and baseline")


def render(document):
    """Common Markdown payload; publication metadata belongs to each renderer."""
    validate(document)
    base = document["baseline"]
    lines = [f"# LMDJ {document['product_build']}", "",
             f"Tag: `{document['tag']}`", f"Target: `{document['target_revision']}`", "",
             (f"Changes since `{base['tag']}` (`{base['target_revision']}`)." if base else
              "First release: complete candidate history is explicitly accounted for."), ""]
    for category, heading in (("feature", "Features"), ("fix", "Fixes"),
                              ("compatibility", "Compatibility / migration"),
                              ("known-issue", "Known issues")):
        lines.extend(["## " + heading, ""])
        entries = [change for change in document["changes"] if change["category"] == category]
        if not entries:
            lines.extend(["No entries recorded in this category.", ""])
        for entry in entries:
            # Escape the few remaining Markdown metacharacters in plain text.
            text = re.sub(r"([*_!|~])", r"\\\1", entry["text"])
            sources = ", ".join(f"[{sha[:12]}](https://github.com/{CANONICAL_REPOSITORY}/commit/{sha})"
                                for sha in entry["commits"])
            lines.extend([f"- {entry['area']}: {text} ({sources})", ""])
    return "\n".join(lines)


def binding(document):
    validate(document)
    return {"schema": document["schema"], "sha256": canonical_sha256(document),
            "notes_sha256": hashlib.sha256(render(document).encode("utf-8")).hexdigest()}
