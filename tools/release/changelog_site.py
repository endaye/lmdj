"""Read-only projection of reviewed publication records and frozen changelogs.

No GitHub request or publication is performed here. The release driver must
produce publication records only after verify-published; reviewed source is not
a replacement for that far-side verification or the later public-site smoke.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re

from .batch_reference import thaw
from .changelog import ChangelogError, binding, render
from .model import Disposition, canonical_json, load_ledger_document, load_policy

PUBLICATIONS = "docs/release-evidence/changelog-publications.json"
LEDGER = "docs/release-evidence/release-intents.json"
SOURCE = "tools/release/changelog_site.py"


def fail(why):
    raise ChangelogError(f"why: release changelog projection {why}; remedy: reconcile reviewed publication evidence and frozen history")


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        fail("fields are missing or unknown")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("has duplicate JSON keys")
        result[key] = value
    return result


def _read(root, relative):
    selected = root / relative
    if selected.resolve() != selected or not selected.is_file() or selected.stat().st_size > 8 * 1024 * 1024:
        fail("source is not a bounded regular file")
    try:
        return json.loads(selected.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, ValueError):
        fail("source JSON is unavailable or invalid")


def _frontmatter(title, *, historical=False):
    return (f"---\ntitle: {title}\narea: {'history' if historical else 'operations'}\n"
            f"status: implemented\nowners: [release, docs]\nsource_paths: [{LEDGER}, {PUBLICATIONS}, {SOURCE}]\n"
            "---\n\n{/* Generated release projection; do not hand-edit frozen version pages. */}\n\n")


def project(ledger, publications):
    _closed(publications, ("schema", "entries"))
    if publications["schema"] != "lmdj.release-changelog-publications.v1" or type(publications["entries"]) is not list:
        fail("publication inventory is invalid")
    expected = {entry.tag: entry for entry in ledger.entries
                if entry.disposition is Disposition.PUBLISHED and entry.changelog is not None}
    seen = set()
    release_ids = set()
    rows = []
    for publication in publications["entries"]:
        _closed(publication, ("tag", "target_revision", "release_id", "published_at",
                              "plan_sha256", "changelog_sha256", "notes_sha256"))
        tag = publication["tag"]
        if type(tag) is not str or tag not in expected or tag in seen:
            fail("publication is duplicate, unpublished or missing a bound changelog")
        seen.add(tag)
        identifier = publication["release_id"]
        if type(identifier) is not int or identifier <= 0 or identifier in release_ids:
            fail("numeric Release identity is invalid or duplicated")
        release_ids.add(identifier)
        date = publication["published_at"]
        if type(date) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", date) is None:
            fail("publication date is invalid")
        try:
            datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            fail("publication date is invalid")
        for field in ("plan_sha256", "changelog_sha256", "notes_sha256"):
            if type(publication[field]) is not str or re.fullmatch(r"[0-9a-f]{64}", publication[field]) is None:
                fail("publication digest is invalid")
        intent = expected[tag]
        document = thaw(intent.changelog)
        digests = binding(document)
        if (publication["target_revision"] != intent.target_revision
                or publication["changelog_sha256"] != digests["sha256"]
                or publication["notes_sha256"] != digests["notes_sha256"]):
            fail("publication and frozen changelog identities differ")
        url = f"https://github.com/endaye/lmdj/releases/tag/{tag}"
        filename = f"apps/docs-site/docs/releases/{intent.identity}.mdx"
        content = (_frontmatter(f"LMDJ {intent.identity} release changelog", historical=True)
                   + f"Published: {date}. Release ID: {identifier}.\n\n"
                   + f"[GitHub Release]({url}) · [全部版本](./index.mdx)\n\n"
                   + "本页记录经审查的 Release 公开事实，不表示两个 Host 已部署或已晋级。\n\n"
                   + render(document)
                   + f"\nContent SHA-256: `{digests['sha256']}`\n\n"
                   + f"Notes SHA-256: `{digests['notes_sha256']}`\n\n"
                   + f"Plan SHA-256: `{publication['plan_sha256']}`\n\n"
                   + "[Creator Host 日志](../operations/creator-changelog.mdx) · "
                     "[Runtime Host 日志](../operations/runtime-changelog.mdx)\n")
        rows.append((date, intent.identity, {"file": filename, "content": content}))
    if seen != set(expected):
        fail("published bound changelog lacks a publication record")
    rows.sort(key=lambda row: (row[0], tuple(int(part) for part in row[1].split("."))), reverse=True)
    index = (_frontmatter("Product release changelogs") + "# Product release changelogs\n\n"
             "每个版本使用与 GitHub Release 相同的冻结日志。这里只列出已有冻结日志及经审查公开记录的版本；不补造历史日志。\n\n"
             "发布不等于 Runtime / Creator 已部署或 dev 已晋级。网站上线仍由正常 Git-triggered 构建完成。\n\n"
             "[发布流程](../operations/version-and-release.mdx) · "
             "[Creator Host 日志](../operations/creator-changelog.mdx) · "
             "[Runtime Host 日志](../operations/runtime-changelog.mdx)\n\n")
    if not rows:
        index += "暂无符合上述条件的 Product release changelog。\n"
    for date, identity, _ in rows:
        index += f"- [{identity}](./{identity}.mdx) — {date}\n"
    return [{"file": "apps/docs-site/docs/releases/index.mdx", "content": index}] + [row[2] for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    options = parser.parse_args()
    root = options.repo_root.resolve()
    policy = load_policy(root / "tools/release/policy.json")
    ledger = load_ledger_document(_read(root, LEDGER), policy)
    print(canonical_json({"pages": project(ledger, _read(root, PUBLICATIONS))}).decode(), end="")


if __name__ == "__main__":
    main()
