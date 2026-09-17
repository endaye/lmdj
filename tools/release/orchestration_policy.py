"""Closed defaults for release orchestration, subordinate to release policy.

Parsing configuration performs no release operation and grants no authorization.
The request journal must bind the digest before any external effect.
"""

from dataclasses import dataclass
import json
from pathlib import Path

from .model import ReleasePolicy, canonical_sha256, channel_rank


class OrchestrationPolicyError(ValueError):
    pass


def _fail(reason: str) -> None:
    raise OrchestrationPolicyError(
        f"why: {reason}; remedy: restore a reviewed, closed orchestration policy"
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate orchestration policy key")
        result[key] = value
    return result


def _keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail("unknown or missing orchestration policy fields")


@dataclass(frozen=True)
class OrchestrationPolicy:
    digest: str
    default_profile: str
    release_profile: str
    publication_channel: str
    target_channel: str
    hosts: tuple[str, ...]
    changelog_destinations: tuple[str, ...]
    read_attempts: int
    read_backoff_seconds: int
    poll_interval_seconds: int
    candidate_test_requests: int

    def select(self, name: str | None = None) -> "OrchestrationPolicy":
        if name is not None and name != self.default_profile:
            _fail("unknown release orchestration profile")
        return self


def load_orchestration_policy(path: Path, release: ReleasePolicy) -> OrchestrationPolicy:
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object)
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("orchestration policy is unavailable or malformed")
    _keys(document, ("schema", "default_profile", "profiles", "recovery"))
    if document["schema"] != "lmdj.release-orchestration-policy.v1":
        _fail("unsupported orchestration policy schema")
    if document["default_profile"] != "web-hosts-dev":
        _fail("unsupported default release scope")
    _keys(document["profiles"], ("web-hosts-dev",))
    profile = document["profiles"]["web-hosts-dev"]
    _keys(profile, ("release_profile", "publication_channel", "target_channel", "hosts",
                    "changelog_destinations"))
    if profile["release_profile"] != "web-hosts" or "web-hosts" not in release.product_profiles:
        _fail("release profile does not admit the Web Host product")
    if (profile["publication_channel"], profile["target_channel"]) != ("canary", "dev"):
        _fail("orchestration cannot expand publication or promotion Channel")
    if (channel_rank(release.promotion.max_channel) < channel_rank("dev")
            or release.channel_release("canary") != (True, False)):
        _fail("release policy does not admit canary to dev")
    if (profile["hosts"] != ["runtime", "creator"]
            or release.promotion.required_hosts("web-hosts") != ("runtime", "creator")):
        _fail("orchestration must include both required Hosts in the declared order")
    if profile["changelog_destinations"] != ["github-release", "doc-site"]:
        _fail("orchestration must publish both changelog destinations")
    recovery = document["recovery"]
    bounds = {"read_attempts": (1, 5), "read_backoff_seconds": (1, 60),
              "poll_interval_seconds": (10, 60), "candidate_test_requests": (1, 1)}
    _keys(recovery, bounds)
    for name, (lower, upper) in bounds.items():
        value = recovery[name]
        if type(value) is not int or not lower <= value <= upper:
            _fail("orchestration recovery exceeds its bounded budget")
    return OrchestrationPolicy(
        canonical_sha256(document), document["default_profile"], profile["release_profile"],
        profile["publication_channel"], profile["target_channel"], tuple(profile["hosts"]),
        tuple(profile["changelog_destinations"]), **recovery,
    )
