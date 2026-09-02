"""Pure, fail-closed release policy and intent-ledger model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping
from urllib.parse import quote
from types import MappingProxyType


class ReleaseModelError(ValueError):
    """Raised when a release policy or ledger violates its closed schema."""


class ReleaseKind(StrEnum):
    PRODUCT = "product"
    MODULE = "module"
    CONTRACT = "contract"
    PROVIDER = "provider"


class Disposition(StrEnum):
    ALLOCATED = "allocated"
    RELEASABLE = "releasable"
    PUBLISHED = "published"
    ABANDONED = "abandoned"
    SUPERSEDED_UNRELEASED = "superseded-unreleased"


@dataclass(frozen=True)
class TagIdentity:
    tag: str
    kind: ReleaseKind
    identity: tuple[str, ...]

    @property
    def output_name(self) -> str:
        """Return a single path component for a tag, including slash-bearing tags."""
        return quote(self.tag, safe="")


@dataclass(frozen=True)
class AssetRecord:
    name: str
    bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or "/" in self.name or "\\" in self.name:
            raise ReleaseModelError("asset name must be a non-path filename")
        if not _is_positive_int(self.bytes):
            raise ReleaseModelError("asset bytes must be a non-negative integer")
        _require_digest(self.sha256, "asset sha256")


CHANNEL_ORDER: tuple[str, ...] = ("canary", "dev", "beta", "stable")
STABLE_PROMOTION_QUESTION = "docs/prd/questions/stable-channel-prerelease-flip.md"
PROMOTION_ATTESTATIONS: Mapping[str, str] = MappingProxyType({
    # dev is decided from retained deployment evidence; beta additionally
    # rests on a human acceptance record the tool can only locate, not judge.
    "dev": "verified",
    "beta": "manual-attested",
})


def channel_rank(channel: str) -> int:
    if channel not in CHANNEL_ORDER:
        raise ReleaseModelError(f"unknown channel: {channel}")
    return CHANNEL_ORDER.index(channel)


@dataclass(frozen=True)
class DeploymentRunRecord:
    host: str
    run_id: int
    evidence_sha256: str


@dataclass(frozen=True)
class PromotionRecord:
    channel: str
    promoted_at: str
    evidence_paths: tuple[str, ...]
    deployment_runs: tuple[DeploymentRunRecord, ...]
    attestation: str


@dataclass(frozen=True)
class HostDeploymentPolicy:
    workflow_path: str
    artifact: str
    contract_prefix: str


@dataclass(frozen=True)
class PromotionPolicy:
    max_channel: str
    deployment_evidence: Mapping[str, tuple[str, ...]]
    hosts: Mapping[str, HostDeploymentPolicy]

    def required_hosts(self, profile: str) -> tuple[str, ...]:
        if profile not in self.deployment_evidence:
            raise ReleaseModelError(f"promotion policy has no deployment evidence rule for profile: {profile}")
        return self.deployment_evidence[profile]


@dataclass(frozen=True)
class ReleaseIntent:
    tag: str
    kind: ReleaseKind
    identity: str
    target_revision: str
    disposition: Disposition
    profile: str
    evidence_paths: tuple[str, ...]
    channel: str | None = None
    snapshot: str | None = None
    merged_main_run_id: int | None = None
    make_latest: bool = False
    promotions: tuple[PromotionRecord, ...] = ()

    @property
    def current_channel(self) -> str | None:
        """The Channel after promotions; `channel` stays the publication Channel."""
        if self.channel is None:
            return None
        return self.promotions[-1].channel if self.promotions else self.channel


@dataclass(frozen=True)
class HistoricalException:
    tag: str
    target_revision: str
    observed_before: str
    code: str
    reason: str
    evidence_paths: tuple[str, ...]
    release_id: int | None = None


@dataclass(frozen=True)
class ReleasePlan:
    schema: str
    repository: str
    tag: str
    tag_object: str
    target_revision: str
    kind: ReleaseKind
    identity: str
    channel: str | None
    profile: str
    assets: tuple[AssetRecord, ...]

    @property
    def output_name(self) -> str:
        return quote(self.tag, safe="")


@dataclass(frozen=True)
class ReleasePolicy:
    repository: str
    branch: str
    blocking_workflow: str
    product_fingerprint: str
    checksum_fingerprint: str
    tag_patterns: Mapping[ReleaseKind, str]
    product_profiles: frozenset[str]
    source_profiles: frozenset[str]
    channels: Mapping[str, Mapping[str, object]]
    release_environment: str
    runtime_canary_environment: str
    creator_canary_environment: str
    historical_cutoff: str
    promotion: PromotionPolicy

    def channel_release(self, channel: str, make_latest: bool = False) -> tuple[bool, bool]:
        if channel not in self.channels:
            raise ReleaseModelError(f"unknown channel: {channel}")
        if not isinstance(make_latest, bool):
            raise ReleaseModelError("make_latest must be a boolean")
        policy = self.channels[channel]
        if channel != "stable" and make_latest:
            raise ReleaseModelError("only stable Product Releases may be latest")
        return (_require_bool(policy["prerelease"], "channel prerelease"), make_latest if channel == "stable" else False)


@dataclass(frozen=True)
class ReleaseLedger:
    entries: tuple[ReleaseIntent, ...]
    historical_exceptions: tuple[HistoricalException, ...]

    def intent_for_tag(self, tag: str) -> ReleaseIntent | None:
        return next((entry for entry in self.entries if entry.tag == tag), None)


_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FINGERPRINT = re.compile(r"[0-9A-F]{40}\Z")
_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_LEDGER_SCHEMA = "lmdj.release-intents.v1"
_POLICY_SCHEMA = "lmdj.release-policy.v1"
_EXCEPTION_CODES = frozenset(("pre-governance-tag-scheme", "pre-pipeline-ci-evidence"))
_CANONICAL_REPOSITORY = "endaye/lmdj"
_CANONICAL_BRANCH = "main"
_PRODUCT_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
_CHECKSUM_FINGERPRINT = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"
_HISTORICAL_CUTOFF = "2026-08-13T00:00:00Z"

# Bootstrap anchors for a local command before it can load canonical policy.
CANONICAL_REPOSITORY = _CANONICAL_REPOSITORY
CANONICAL_BRANCH = _CANONICAL_BRANCH
CANONICAL_BLOCKING_WORKFLOW = "Core CI"
CANONICAL_PRODUCT_FINGERPRINT = _PRODUCT_FINGERPRINT


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def load_policy(path: Path | str) -> ReleasePolicy:
    document = _load_json(path, "policy")
    _require_exact_keys(document, {
        "schema", "repository", "branch", "blocking_workflow", "fingerprints", "tag_patterns", "profiles",
        "channels", "environments", "historical_cutoff", "promotion",
    }, "policy")
    if document["schema"] != _POLICY_SCHEMA:
        raise ReleaseModelError("unsupported policy schema")
    repository = _require_string(document["repository"], "policy repository")
    branch = _require_string(document["branch"], "policy branch")
    blocking_workflow = _require_string(document["blocking_workflow"], "policy blocking workflow")
    if repository != _CANONICAL_REPOSITORY or branch != _CANONICAL_BRANCH:
        raise ReleaseModelError("policy repository and branch must be canonical")
    if blocking_workflow != CANONICAL_BLOCKING_WORKFLOW:
        raise ReleaseModelError("policy blocking workflow must be canonical")
    fingerprints = _require_mapping(document["fingerprints"], "fingerprints")
    _require_exact_keys(fingerprints, {"product", "checksum"}, "fingerprints")
    product_fingerprint = _require_fingerprint(fingerprints["product"], "product fingerprint")
    checksum_fingerprint = _require_fingerprint(fingerprints["checksum"], "checksum fingerprint")
    if product_fingerprint == checksum_fingerprint:
        raise ReleaseModelError("product and checksum fingerprints must differ")
    if (product_fingerprint, checksum_fingerprint) != (_PRODUCT_FINGERPRINT, _CHECKSUM_FINGERPRINT):
        raise ReleaseModelError("policy fingerprints must be the canonical role anchors")
    tag_patterns_document = _require_mapping(document["tag_patterns"], "tag_patterns")
    _require_exact_keys(tag_patterns_document, {kind.value for kind in ReleaseKind}, "tag_patterns")
    tag_patterns: dict[ReleaseKind, str] = {}
    for kind in ReleaseKind:
        pattern = _require_string(tag_patterns_document[kind.value], f"{kind.value} tag pattern")
        if not pattern.startswith("^") or not pattern.endswith("$"):
            raise ReleaseModelError(f"{kind.value} tag pattern must be anchored")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ReleaseModelError(f"invalid {kind.value} tag pattern") from error
        tag_patterns[kind] = pattern
    profiles = _require_mapping(document["profiles"], "profiles")
    _require_exact_keys(profiles, {"product", "source"}, "profiles")
    product_profiles = _string_set(profiles["product"], "product profiles")
    source_profiles = _string_set(profiles["source"], "source profiles")
    if product_profiles != {"core-package", "web-runtime-host", "web-hosts"} or source_profiles != {"source-only"}:
        raise ReleaseModelError("profiles do not satisfy the closed release policy")
    channels_document = _require_mapping(document["channels"], "channels")
    _require_exact_keys(channels_document, {"canary", "dev", "beta", "stable"}, "channels")
    channels: dict[str, Mapping[str, object]] = {}
    for name, prerelease in (("canary", True), ("dev", True), ("beta", True), ("stable", False)):
        item = _require_mapping(channels_document[name], f"{name} channel")
        _require_exact_keys(item, {"prerelease"}, f"{name} channel")
        if _require_bool(item["prerelease"], f"{name} prerelease") is not prerelease:
            raise ReleaseModelError(f"{name} channel prerelease policy is invalid")
        channels[name] = dict(item)
    environments = _require_mapping(document["environments"], "environments")
    _require_exact_keys(
        environments,
        {"release", "runtime_canary", "creator_canary"},
        "environments",
    )
    cutoff = _require_utc(document["historical_cutoff"], "historical_cutoff")
    release_environment = _require_string(environments["release"], "release environment")
    runtime_canary_environment = _require_string(environments["runtime_canary"], "runtime-canary environment")
    creator_canary_environment = _require_string(
        environments["creator_canary"],
        "creator-canary environment",
    )
    if (
        release_environment,
        runtime_canary_environment,
        creator_canary_environment,
        cutoff,
    ) != (
        "release",
        "runtime-canary",
        "creator-canary",
        _HISTORICAL_CUTOFF,
    ):
        raise ReleaseModelError("policy environments or historical cutoff are not canonical")
    promotion = _parse_promotion_policy(document["promotion"], frozenset(product_profiles))
    return ReleasePolicy(
        repository=repository, branch=branch, blocking_workflow=blocking_workflow,
        product_fingerprint=product_fingerprint,
        checksum_fingerprint=checksum_fingerprint, tag_patterns=MappingProxyType(tag_patterns),
        product_profiles=frozenset(product_profiles), source_profiles=frozenset(source_profiles),
        channels=MappingProxyType({name: MappingProxyType(dict(item)) for name, item in channels.items()}),
        release_environment=release_environment,
        runtime_canary_environment=runtime_canary_environment,
        creator_canary_environment=creator_canary_environment,
        historical_cutoff=cutoff,
        promotion=promotion,
    )


def _parse_promotion_policy(value: object, product_profiles: frozenset[str]) -> PromotionPolicy:
    document = _require_mapping(value, "promotion policy")
    _require_exact_keys(document, {"max_channel", "deployment_evidence", "hosts"}, "promotion policy")
    max_channel = _require_string(document["max_channel"], "promotion max_channel")
    if max_channel not in CHANNEL_ORDER:
        raise ReleaseModelError("promotion max_channel is not a known channel")
    hosts_document = _require_mapping(document["hosts"], "promotion hosts")
    hosts: dict[str, HostDeploymentPolicy] = {}
    for name in sorted(hosts_document):
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9-]*", name) is None:
            raise ReleaseModelError("promotion host names must be lowercase identifiers")
        item = _require_mapping(hosts_document[name], f"promotion host {name}")
        _require_exact_keys(item, {"workflow_path", "artifact", "contract_prefix"}, f"promotion host {name}")
        workflow_path = _require_string(item["workflow_path"], f"{name} workflow_path")
        if not workflow_path.startswith(".github/workflows/") or not workflow_path.endswith(".yml"):
            raise ReleaseModelError(f"{name} workflow_path must name a repository workflow")
        hosts[name] = HostDeploymentPolicy(
            workflow_path,
            _require_string(item["artifact"], f"{name} artifact"),
            _require_string(item["contract_prefix"], f"{name} contract_prefix"),
        )
    evidence_document = _require_mapping(document["deployment_evidence"], "promotion deployment_evidence")
    _require_exact_keys(evidence_document, set(product_profiles), "promotion deployment_evidence")
    deployment_evidence: dict[str, tuple[str, ...]] = {}
    for profile in sorted(evidence_document):
        names = _require_list(evidence_document[profile], f"{profile} deployment evidence hosts")
        resolved: list[str] = []
        for host in names:
            host = _require_string(host, f"{profile} deployment evidence host")
            if host not in hosts:
                raise ReleaseModelError(f"{profile} deployment evidence names an unknown host: {host}")
            resolved.append(host)
        if len(set(resolved)) != len(resolved):
            raise ReleaseModelError(f"{profile} deployment evidence hosts must not repeat")
        deployment_evidence[profile] = tuple(resolved)
    return PromotionPolicy(
        max_channel=max_channel,
        deployment_evidence=MappingProxyType(deployment_evidence),
        hosts=MappingProxyType(hosts),
    )


def _parse_promotions(
    value: object,
    policy: ReleasePolicy,
    *,
    publication_channel: str,
    disposition: Disposition,
    profile: str,
) -> tuple[PromotionRecord, ...]:
    items = _require_list(value, "promotions")
    if not items:
        raise ReleaseModelError("promotions must not be empty when present")
    if disposition is not Disposition.PUBLISHED:
        raise ReleaseModelError("only a published Product intent may carry promotions")
    previous_rank = channel_rank(publication_channel)
    max_rank = channel_rank(policy.promotion.max_channel)
    required_hosts = policy.promotion.required_hosts(profile)
    records: list[PromotionRecord] = []
    for index, raw in enumerate(items):
        item = _require_mapping(raw, f"promotion {index}")
        _require_exact_keys(
            item, {"channel", "promoted_at", "evidence_paths", "deployment_runs", "attestation"},
            f"promotion {index}",
        )
        channel = _require_string(item["channel"], f"promotion {index} channel")
        if channel == "stable":
            raise ReleaseModelError(
                "stable promotion is not implemented: publication pins prerelease and D8 forbids "
                f"flipping it on a published Release; see {STABLE_PROMOTION_QUESTION}"
            )
        rank = channel_rank(channel)
        if rank <= previous_rank:
            raise ReleaseModelError(f"promotion {index} must move strictly forward from {CHANNEL_ORDER[previous_rank]}")
        if rank > max_rank:
            raise ReleaseModelError(
                f"promotion {index} exceeds the policy max_channel {policy.promotion.max_channel}"
            )
        promoted_at = _require_utc(item["promoted_at"], f"promotion {index} promoted_at")
        evidence_paths = _paths(item["evidence_paths"], f"promotion {index} evidence_paths")
        attestation = _require_string(item["attestation"], f"promotion {index} attestation")
        if attestation != PROMOTION_ATTESTATIONS[channel]:
            raise ReleaseModelError(
                f"promotion {index} to {channel} must be attested as {PROMOTION_ATTESTATIONS[channel]}"
            )
        runs_document = _require_list(item["deployment_runs"], f"promotion {index} deployment_runs")
        runs: list[DeploymentRunRecord] = []
        for run_index, raw_run in enumerate(runs_document):
            run_item = _require_mapping(raw_run, f"promotion {index} deployment run {run_index}")
            _require_exact_keys(
                run_item, {"host", "run_id", "evidence_sha256"},
                f"promotion {index} deployment run {run_index}",
            )
            host = _require_string(run_item["host"], "deployment run host")
            if host not in policy.promotion.hosts:
                raise ReleaseModelError(f"promotion {index} names an unknown deployment host: {host}")
            run_id = run_item["run_id"]
            if type(run_id) is not int or run_id <= 0:
                raise ReleaseModelError("deployment run_id must be a positive integer")
            digest = _require_string(run_item["evidence_sha256"], "deployment evidence_sha256")
            if _SHA256.fullmatch(digest) is None:
                raise ReleaseModelError("deployment evidence_sha256 must be a lowercase SHA-256")
            runs.append(DeploymentRunRecord(host, run_id, digest))
        if tuple(run.host for run in runs) != tuple(required_hosts):
            raise ReleaseModelError(
                f"promotion {index} deployment runs must cover exactly the profile hosts in order: "
                + (", ".join(required_hosts) or "none")
            )
        records.append(PromotionRecord(channel, promoted_at, evidence_paths, tuple(runs), attestation))
        previous_rank = rank
    return tuple(records)


def classify_tag(tag: str, policy: ReleasePolicy) -> TagIdentity:
    if not isinstance(tag, str) or not tag:
        raise ReleaseModelError("tag must be a non-empty string")
    for kind, pattern in policy.tag_patterns.items():
        match = re.fullmatch(pattern, tag)
        if match is None:
            continue
        groups = match.groupdict()
        if kind is ReleaseKind.PRODUCT:
            return TagIdentity(tag, kind, (groups["version"],))
        return TagIdentity(tag, kind, (groups["id"], groups["version"]))
    raise ReleaseModelError(f"tag is not a current-policy formal release tag: {tag}")


def load_ledger(path: Path | str, policy: ReleasePolicy) -> ReleaseLedger:
    return load_ledger_document(_load_json(path, "ledger"), policy)


def load_ledger_document(document: object, policy: ReleasePolicy) -> ReleaseLedger:
    top = _require_mapping(document, "ledger")
    _require_exact_keys(top, {"schema", "entries", "historical_exceptions"}, "ledger")
    if top["schema"] != _LEDGER_SCHEMA:
        raise ReleaseModelError("unsupported ledger schema")
    entries_document = _require_list(top["entries"], "ledger entries")
    entries = tuple(_parse_entry(item, policy) for item in entries_document)
    tags = [entry.tag for entry in entries]
    identities = [(entry.kind, entry.identity) for entry in entries]
    if len(tags) != len(set(tags)):
        raise ReleaseModelError("duplicate ledger tag")
    if len(identities) != len(set(identities)):
        raise ReleaseModelError("duplicate ledger identity")
    exceptions = tuple(_parse_exception(item, policy) for item in _require_list(top["historical_exceptions"], "historical_exceptions"))
    if len({exception.tag for exception in exceptions}) != len(exceptions):
        raise ReleaseModelError("duplicate historical exception tag")
    entries_by_tag = {entry.tag: entry for entry in entries}
    for exception in exceptions:
        entry = entries_by_tag.get(exception.tag)
        if entry is not None:
            if entry.target_revision != exception.target_revision:
                raise ReleaseModelError("historical exception target_revision must match its ledger entry")
            if entry.disposition in {Disposition.ALLOCATED, Disposition.RELEASABLE}:
                raise ReleaseModelError("historical exception cannot authorize allocated or releasable intent")
            if exception.code == "pre-governance-tag-scheme":
                raise ReleaseModelError("pre-governance historical exception cannot name a formal ledger tag")
        else:
            try:
                classify_tag(exception.tag, policy)
            except ReleaseModelError:
                if exception.code != "pre-governance-tag-scheme":
                    raise ReleaseModelError("non-formal historical tag requires pre-governance-tag-scheme") from None
            else:
                raise ReleaseModelError("historical exception for a formal tag requires a ledger entry")
    return ReleaseLedger(entries, exceptions)


def _parse_entry(value: object, policy: ReleasePolicy) -> ReleaseIntent:
    item = _require_mapping(value, "ledger entry")
    common = {"tag", "kind", "identity", "target_revision", "disposition", "profile", "evidence_paths"}
    kind = _enum(ReleaseKind, item.get("kind"), "kind")
    required = set(common)
    if kind is ReleaseKind.PRODUCT:
        required.add("channel")
    _require_exact_keys(
        item, required, "ledger entry",
        optional={"snapshot", "merged_main_run_id", "make_latest", "promotions"},
    )
    tag = _require_string(item["tag"], "tag")
    tag_identity = classify_tag(tag, policy)
    if tag_identity.kind is not kind:
        raise ReleaseModelError("ledger kind does not match tag")
    identity = _require_string(item["identity"], "identity")
    expected_identity = tag_identity.identity[0] if kind is ReleaseKind.PRODUCT else "@".join(tag_identity.identity)
    if identity != expected_identity:
        raise ReleaseModelError("ledger identity does not match tag")
    target_revision = _require_sha(item["target_revision"], "target_revision")
    disposition = _enum(Disposition, item["disposition"], "disposition")
    profile = _require_string(item["profile"], "profile")
    if kind is ReleaseKind.PRODUCT:
        if profile not in policy.product_profiles:
            raise ReleaseModelError("Product profile is not allowed")
        channel = _require_string(item["channel"], "channel")
        if channel not in policy.channels:
            raise ReleaseModelError("Product channel is not allowed")
        if "make_latest" in item:
            make_latest = _require_bool(item["make_latest"], "make_latest")
            if channel != "stable":
                raise ReleaseModelError("make_latest is only permitted for stable Product Releases")
        elif channel == "stable":
            raise ReleaseModelError("stable Product Releases require explicit make_latest")
        else:
            make_latest = False
        policy.channel_release(channel, make_latest)
        snapshot = _optional_string(item, "snapshot")
        promotions = (
            _parse_promotions(
                item["promotions"], policy,
                publication_channel=channel, disposition=disposition, profile=profile,
            )
            if "promotions" in item else ()
        )
    else:
        if profile not in policy.source_profiles:
            raise ReleaseModelError("non-Product profile must be source-only")
        if "channel" in item or "snapshot" in item or "make_latest" in item or "promotions" in item:
            raise ReleaseModelError(
                "non-Product ledger entry may not contain channel, snapshot, make_latest, or promotions"
            )
        channel, snapshot, make_latest, promotions = None, None, False, ()
    run_id = _optional_positive_int(item, "merged_main_run_id")
    evidence_paths = _paths(item["evidence_paths"], "evidence_paths")
    return ReleaseIntent(
        tag, kind, identity, target_revision, disposition, profile, evidence_paths,
        channel, snapshot, run_id, make_latest, promotions,
    )


def _parse_exception(value: object, policy: ReleasePolicy) -> HistoricalException:
    item = _require_mapping(value, "historical exception")
    _require_exact_keys(
        item, {"tag", "target_revision", "observed_before", "code", "reason", "evidence_paths"},
        "historical exception", optional={"release_id"},
    )
    code = _require_string(item["code"], "historical exception code")
    if code not in _EXCEPTION_CODES:
        raise ReleaseModelError("historical exception code is not allowed")
    observed_before = _require_utc(item["observed_before"], "historical exception observed_before")
    if _parse_utc(observed_before) >= _parse_utc(policy.historical_cutoff):
        raise ReleaseModelError("historical exception observed_before must precede historical_cutoff")
    release_id = _optional_positive_int(item, "release_id")
    return HistoricalException(
        _require_string(item["tag"], "historical exception tag"),
        _require_sha(item["target_revision"], "historical exception target_revision"),
        observed_before, code, _require_string(item["reason"], "historical exception reason"),
        _paths(item["evidence_paths"], "historical exception evidence_paths"), release_id,
    )


def _load_json(path: Path | str, label: str) -> object:
    try:
        with Path(path).open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseModelError(f"cannot load {label}") from error


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ReleaseModelError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ReleaseModelError(f"{label} must be an array")
    return value


def _require_exact_keys(item: Mapping[str, object], required: set[str], label: str, *, optional: set[str] | None = None) -> None:
    allowed = required if optional is None else required | optional
    unexpected = set(item) - allowed
    missing = required - set(item)
    if unexpected:
        raise ReleaseModelError(f"{label} has unexpected fields: {', '.join(sorted(unexpected))}")
    if missing:
        raise ReleaseModelError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseModelError(f"{label} must be a non-empty string")
    return value


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ReleaseModelError(f"{label} must be a boolean")
    return value


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _optional_positive_int(item: Mapping[str, object], key: str) -> int | None:
    if key not in item:
        return None
    value = item[key]
    if not _is_positive_int(value) or value == 0:
        raise ReleaseModelError(f"{key} must be a positive integer")
    return value


def _optional_string(item: Mapping[str, object], key: str) -> str | None:
    return _require_string(item[key], key) if key in item else None


def _enum(enum_type: type[StrEnum], value: object, label: str):
    if not isinstance(value, str):
        raise ReleaseModelError(f"{label} is not allowed")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ReleaseModelError(f"{label} is not allowed") from error


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA40.fullmatch(value) is None:
        raise ReleaseModelError(f"{label} must be lowercase 40-hex")
    return value


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ReleaseModelError(f"{label} must be lowercase 64-hex")
    return value


def _require_fingerprint(value: object, label: str) -> str:
    if not isinstance(value, str) or _FINGERPRINT.fullmatch(value) is None:
        raise ReleaseModelError(f"{label} must be uppercase 40-hex")
    return value


def _string_set(value: object, label: str) -> set[str]:
    values = _require_list(value, label)
    result = {_require_string(item, label) for item in values}
    if len(result) != len(values):
        raise ReleaseModelError(f"{label} must not contain duplicates")
    return result


def _paths(value: object, label: str) -> tuple[str, ...]:
    paths = _require_list(value, label)
    if not paths:
        raise ReleaseModelError(f"{label} must not be empty")
    result: list[str] = []
    for path in paths:
        path = _require_string(path, label)
        if _PATH.fullmatch(path) is None or path.startswith("/") or "//" in path or any(part in {".", ".."} for part in path.split("/")):
            raise ReleaseModelError(f"{label} must contain canonical repo-relative paths")
        result.append(path)
    if len(set(result)) != len(result):
        raise ReleaseModelError(f"{label} must not contain duplicates")
    return tuple(result)


def _require_utc(value: object, label: str) -> str:
    value = _require_string(value, label)
    if _UTC.fullmatch(value) is None:
        raise ReleaseModelError(f"{label} must be an exact UTC timestamp")
    try:
        _parse_utc(value)
    except ValueError as error:
        raise ReleaseModelError(f"{label} must be an exact UTC timestamp") from error
    return value


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
