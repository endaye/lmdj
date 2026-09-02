"""Channel promotion: a reviewed ledger mutation that never touches the GitHub Release.

`plan_promotion` decides whether one published Product intent may move to a
higher Channel and gathers the evidence the policy requires. `apply_promotion`
writes exactly two things into the working tree: one promotion evidence
document and one `promotions` record on the intent's ledger line. Committing
and reviewing that change is the operator's next, separately authorized step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Mapping, Sequence

from tools.release.deployment_evidence import verify_deployment_run
from tools.release.model import (
    CHANNEL_ORDER,
    PROMOTION_ATTESTATIONS,
    STABLE_PROMOTION_QUESTION,
    DeploymentRunRecord,
    Disposition,
    ReleaseIntent,
    ReleaseKind,
    channel_rank,
    load_ledger,
)

LEDGER_PATH = "docs/release-evidence/release-intents.json"
EVIDENCE_ROOTS: tuple[str, ...] = ("docs/release-evidence/", "docs/quality/")
_RUN_ARGUMENT = re.compile(r"(?P<host>[a-z][a-z0-9-]*)=(?P<run_id>[1-9][0-9]*)\Z")


class PromotionError(RuntimeError):
    """A promotion request violates policy, its gates, or the ledger it would edit."""


@dataclass(frozen=True)
class PromotionPlan:
    tag: str
    identity: str
    target_revision: str
    profile: str
    from_channel: str
    to_channel: str
    promoted_at: str
    attestation: str
    deployment_runs: tuple[DeploymentRunRecord, ...]
    evidence_paths: tuple[str, ...]
    evidence_document: str


@dataclass(frozen=True)
class PromotionResult:
    ledger_path: str
    evidence_document: str
    to_channel: str


def parse_deployment_run_arguments(values: Sequence[str]) -> Mapping[str, int]:
    """Parse repeated `HOST=RUN_ID` arguments into one host->run mapping."""
    runs: dict[str, int] = {}
    for value in values:
        match = _RUN_ARGUMENT.fullmatch(value)
        if match is None:
            raise PromotionError(f"deployment run must be HOST=RUN_ID, got: {value}")
        host = match.group("host")
        if host in runs:
            raise PromotionError(f"deployment run for host {host} was given more than once")
        runs[host] = int(match.group("run_id"))
    return runs


def plan_promotion(
    context: object,
    *,
    tag: str,
    channel: str,
    deployment_runs: Mapping[str, int],
    evidence_paths: Sequence[str],
    now: datetime | None = None,
) -> PromotionPlan:
    """Validate the transition and its gates without writing anything."""
    policy = context.policy
    intent = context.ledger.intent_for_tag(tag)
    if intent is None:
        raise PromotionError("tag is not authorized by the intent ledger")
    if intent.kind is not ReleaseKind.PRODUCT or intent.channel is None:
        raise PromotionError("only Product intents carry a Channel")
    if intent.disposition is not Disposition.PUBLISHED:
        raise PromotionError(
            f"only a published Product may be promoted; {tag} is {intent.disposition.value}"
        )
    if channel not in CHANNEL_ORDER:
        raise PromotionError(f"unknown channel: {channel}")
    if channel == "stable":
        raise PromotionError(
            "stable promotion is not implemented: publication pins prerelease and D8 forbids "
            f"flipping it on a published Release; see {STABLE_PROMOTION_QUESTION}"
        )
    current = intent.current_channel
    assert current is not None
    if channel_rank(channel) <= channel_rank(current):
        raise PromotionError(f"{tag} is already {current}; promotion must move strictly forward")
    if channel_rank(channel) > channel_rank(policy.promotion.max_channel):
        raise PromotionError(
            f"policy max_channel is {policy.promotion.max_channel}; {channel} is not permitted"
        )

    required_hosts = policy.promotion.required_hosts(intent.profile)
    missing = [host for host in required_hosts if host not in deployment_runs]
    extra = sorted(set(deployment_runs) - set(required_hosts))
    if missing:
        raise PromotionError(
            f"profile {intent.profile} requires deployment evidence for: {', '.join(missing)}"
        )
    if extra:
        raise PromotionError(
            f"profile {intent.profile} has no deployment host named: {', '.join(extra)}"
        )
    records: list[DeploymentRunRecord] = []
    for host in required_hosts:
        run_id = deployment_runs[host]
        result = verify_deployment_run(
            context.github,
            repository=policy.repository,
            branch=policy.branch,
            host=host,
            host_policy=policy.promotion.hosts[host],
            tag=tag,
            target_revision=intent.target_revision,
            identity=intent.identity,
            run_id=run_id,
        )
        if result.code != "ok":
            raise PromotionError(f"[{result.code}] {result.message}")
        assert result.evidence_sha256 is not None
        records.append(DeploymentRunRecord(host, run_id, result.evidence_sha256))

    root = Path(context.repo_root)
    attested: list[str] = []
    for relative in evidence_paths:
        if not any(relative.startswith(prefix) for prefix in EVIDENCE_ROOTS):
            raise PromotionError(
                f"promotion evidence must live under {' or '.join(EVIDENCE_ROOTS)}: {relative}"
            )
        if not _tracked(root, relative):
            raise PromotionError(f"promotion evidence is not a tracked file: {relative}")
        if relative in attested:
            raise PromotionError(f"promotion evidence repeats a path: {relative}")
        attested.append(relative)
    if channel == "beta" and not attested:
        raise PromotionError(
            "beta promotion requires at least one tracked acceptance document under "
            + " or ".join(EVIDENCE_ROOTS)
        )

    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    promoted_at = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    document = (
        f"docs/release-evidence/{moment.strftime('%Y-%m-%d')}-lmdj-{intent.identity}"
        f"-promotion-{channel}.md"
    )
    if (root / document).exists():
        raise PromotionError(f"promotion evidence document already exists: {document}")
    return PromotionPlan(
        tag=tag,
        identity=intent.identity,
        target_revision=intent.target_revision,
        profile=intent.profile,
        from_channel=current,
        to_channel=channel,
        promoted_at=promoted_at,
        attestation=PROMOTION_ATTESTATIONS[channel],
        deployment_runs=tuple(records),
        evidence_paths=(document, *attested),
        evidence_document=document,
    )


def apply_promotion(root: Path, plan: PromotionPlan, policy: object) -> PromotionResult:
    """Write the evidence document and the ledger record, validating the result."""
    root = Path(root)
    ledger_path = root / LEDGER_PATH
    original = ledger_path.read_text(encoding="utf-8")
    rewritten = _append_promotion(original, plan)
    document_path = root / plan.evidence_document
    if document_path.exists():
        raise PromotionError(f"promotion evidence document already exists: {plan.evidence_document}")
    document_path.parent.mkdir(parents=True, exist_ok=True)
    document_path.write_text(render_evidence_document(plan), encoding="utf-8")
    ledger_path.write_text(rewritten, encoding="utf-8")
    try:
        ledger = load_ledger(ledger_path, policy)
        intent = ledger.intent_for_tag(plan.tag)
        if intent is None or intent.current_channel != plan.to_channel:
            raise PromotionError("rewritten ledger does not record the promotion")
    except Exception:
        ledger_path.write_text(original, encoding="utf-8")
        document_path.unlink(missing_ok=True)
        raise
    return PromotionResult(LEDGER_PATH, plan.evidence_document, plan.to_channel)


def render_evidence_document(plan: PromotionPlan) -> str:
    runs = "\n".join(
        f"| `{run.host}` | [`{run.run_id}`](https://github.com/endaye/lmdj/actions/runs/{run.run_id}) | `{run.evidence_sha256}` |"
        for run in plan.deployment_runs
    ) or "| none | this profile has no deployment host | |"
    extra = "\n".join(f"- `{path}`" for path in plan.evidence_paths[1:]) or "- none beyond this record"
    gate = {
        "dev": (
            "`dev` requires the canary conditions plus the matching E2E and team-integration "
            "evidence. Each Host deployment run above completed a manual exact-tag "
            "`workflow_dispatch`, and its retained `evidence.json` names this tag, this "
            "target revision and this Product Build, and passed the immutable and production "
            "HTTP and browser checks. That evidence is the decidable form of the gate."
        ),
        "beta": (
            "`beta` requires the dev conditions plus approved user-flow, recovery and "
            "platform/device acceptance. The tool verified that the acceptance documents "
            "listed below are tracked; their content is a human judgement this record "
            "attests to rather than decides."
        ),
    }[plan.to_channel]
    return f"""# LMDJ `{plan.identity}` Channel Promotion — `{plan.from_channel}` to `{plan.to_channel}`

This record promotes one published Product Build to a higher Channel. It changes
the release record only. The source tag, the GitHub Release, its `prerelease`
flag and its assets are unchanged, per pipeline decision D8. Promotion does not
authorize deployment, and deployment did not authorize this promotion.

## Exact identity

| Field | Value |
| --- | --- |
| Tag | `{plan.tag}` |
| Identity | `{plan.identity}` |
| Profile | `{plan.profile}` |
| Target revision | `{plan.target_revision}` |
| Channel before | `{plan.from_channel}` |
| Promoted to | `{plan.to_channel}` |
| Promoted at | `{plan.promoted_at}` |
| Attestation | `{plan.attestation}` |

## Gate

{gate}

## Deployment evidence

| Host | Run | `evidence.json` sha256 |
| --- | --- | --- |
{runs}

## Additional evidence

{extra}

## What this record does not do

It does not move the tag, edit the Release, change `prerelease` or `latest`,
deploy either Host, or authorize any later Channel. `stable` promotion is not
implemented; see `{STABLE_PROMOTION_QUESTION}`.
"""


def _append_promotion(ledger_text: str, plan: PromotionPlan) -> str:
    lines = ledger_text.split("\n")
    needle_tag = f'"tag":"{plan.tag}"'
    matches = [
        index for index, line in enumerate(lines)
        if needle_tag in line and '"kind":"product"' in line
    ]
    if len(matches) != 1:
        raise PromotionError("ledger does not hold exactly one one-line Product entry for the tag")
    index = matches[0]
    line = lines[index]
    stripped = line.strip()
    trailing_comma = stripped.endswith(",")
    body = stripped[:-1] if trailing_comma else stripped
    indent = line[: len(line) - len(line.lstrip())]
    try:
        entry = json.loads(body)
    except json.JSONDecodeError as error:
        raise PromotionError("ledger entry line is not a single JSON object") from error
    if not isinstance(entry, dict):
        raise PromotionError("ledger entry line is not a JSON object")
    record = {
        "channel": plan.to_channel,
        "promoted_at": plan.promoted_at,
        "evidence_paths": list(plan.evidence_paths),
        "deployment_runs": [
            {"host": run.host, "run_id": run.run_id, "evidence_sha256": run.evidence_sha256}
            for run in plan.deployment_runs
        ],
        "attestation": plan.attestation,
    }
    promotions = entry.get("promotions", [])
    if not isinstance(promotions, list):
        raise PromotionError("ledger entry promotions is not a list")
    entry["promotions"] = [*promotions, record]
    rendered = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
    lines[index] = f"{indent}{rendered}{',' if trailing_comma else ''}"
    return "\n".join(lines)


def _tracked(root: Path, relative: str) -> bool:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        return False
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0
