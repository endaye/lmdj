#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps/creator-web/tools"))
import deploy_orchestrator
import netlify_api


class DeployOrchestratorReleaseTest(unittest.TestCase):
    TAG = "lmdj-v1.0.15.2"
    TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
    ARCHIVE = "lmdj-creator-web-1.2.0-product-1.0.15.2.zip"

    def metadata(self, *, target: object = "main", assets: list[str] | None = None) -> str:
        runtime = "lmdj-web-runtime-host-2.1.1-product-1.0.15.2.zip"
        names = assets or [
            self.ARCHIVE,
            self.ARCHIVE + ".sha256",
            self.ARCHIVE + ".sha256.asc",
            runtime,
            runtime + ".sha256",
            runtime + ".sha256.asc",
        ]
        return json.dumps(
            {
                "assets": [{"name": name} for name in names],
                "isDraft": False,
                "isPrerelease": True,
                "tagName": self.TAG,
                "targetCommitish": target,
                "url": f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
            }
        )

    def parse(self, source: str):
        return deploy_orchestrator.parse_release_metadata(
            source,
            tag=self.TAG,
            tag_target=self.TARGET,
            product_build="1.0.15.2",
            host_version="1.2.0",
        )

    def test_common_main_target_metadata_is_auxiliary(self) -> None:
        self.assertEqual(
            self.parse(self.metadata(target="main")),
            (
                self.ARCHIVE,
                self.ARCHIVE + ".sha256",
                self.ARCHIVE + ".sha256.asc",
                f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
            ),
        )

    def test_requires_exact_six_canonical_release_assets(self) -> None:
        runtime = "lmdj-web-runtime-host-2.1.1-product-1.0.15.2.zip"
        complete = [
            self.ARCHIVE,
            self.ARCHIVE + ".sha256",
            self.ARCHIVE + ".sha256.asc",
            runtime,
            runtime + ".sha256",
            runtime + ".sha256.asc",
        ]
        for assets in (
            complete[:-1],
            [*complete, "extra"],
            [*complete[:-1], "wrong.asc"],
        ):
            with self.subTest(assets=assets):
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "asset identity"
                ):
                    self.parse(self.metadata(assets=assets))

    def test_selects_creator_assets_from_a_complete_dual_host_release(self) -> None:
        runtime = "lmdj-web-runtime-host-2.1.1-product-1.0.15.2.zip"
        assets = [
            self.ARCHIVE,
            self.ARCHIVE + ".sha256",
            self.ARCHIVE + ".sha256.asc",
            runtime,
            runtime + ".sha256",
            runtime + ".sha256.asc",
        ]
        self.assertEqual(
            self.parse(self.metadata(assets=assets)),
            (
                self.ARCHIVE,
                self.ARCHIVE + ".sha256",
                self.ARCHIVE + ".sha256.asc",
                f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
            ),
        )

    def test_rejects_invalid_target_metadata_without_using_it_as_attestation(self) -> None:
        for target in (None, "", "main\nother"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "target metadata"
                ):
                    self.parse(self.metadata(target=target))

    def test_legacy_v1_evidence_writer_is_not_exposed(self) -> None:
        self.assertFalse(hasattr(deploy_orchestrator, "write_evidence"))


class DeployOrchestratorSitePreflightTest(unittest.TestCase):
    SITE = "site-123"

    def site(self, deploy_id: str = "prior-123") -> netlify_api.PublishedSite:
        return netlify_api.PublishedSite(
            id=self.SITE,
            state="current",
            ssl_url="https://lmdj-creator.netlify.app",
            published_deploy=netlify_api.DraftDeploy(
                id=deploy_id,
                site_id=self.SITE,
                deploy_ssl_url=(
                    f"https://{deploy_id}--lmdj-creator.netlify.app"
                ),
                state="ready",
            ),
        )

    class Client:
        def __init__(
            self,
            *,
            sites: list[netlify_api.PublishedSite],
            file_count: int,
        ) -> None:
            self.sites = sites
            self.file_count = file_count
            self.calls: list[str] = []

        def get_site(self, *, site_id: str) -> netlify_api.PublishedSite:
            self.calls.append("site")
            return self.sites.pop(0)

        def get_site_file_count(self, *, site_id: str) -> int:
            self.calls.append("files")
            return self.file_count

    def test_current_site_preflight_binds_file_count_to_stable_site_identity(self) -> None:
        site = self.site()
        for file_count in (0, 12):
            with self.subTest(file_count=file_count):
                client = self.Client(sites=[site, site], file_count=file_count)
                result = deploy_orchestrator.current_site_preflight(
                    site_id=self.SITE, token="unused", client=client
                )
                self.assertEqual(result["file_count"], file_count)
                self.assertEqual(result["site"]["published_deploy"]["id"], "prior-123")
                self.assertEqual(client.calls, ["site", "files", "site"])

    def test_current_site_preflight_rejects_identity_change_during_inventory(self) -> None:
        client = self.Client(
            sites=[self.site("prior-123"), self.site("other-456")],
            file_count=0,
        )
        with self.assertRaisesRegex(
            deploy_orchestrator.DeployOrchestratorError,
            "changed during file inventory",
        ):
            deploy_orchestrator.current_site_preflight(
                site_id=self.SITE, token="unused", client=client
            )
        self.assertEqual(client.calls, ["site", "files", "site"])


class DeployOrchestratorPublishedProjectionTest(unittest.TestCase):
    def published(self, published_at: object) -> dict[str, object]:
        return {
            "deploy_ssl_url": "https://deploy-456--lmdj-creator.netlify.app",
            "id": "deploy-456",
            "published_at": published_at,
            "site_id": "site-123",
            "ssl_url": "https://lmdj-creator.netlify.app",
            "state": "ready",
        }

    def test_accepts_netlify_utc_timestamp_with_optional_fractional_seconds(self) -> None:
        for published_at in (
            "2026-08-09T00:00:00Z",
            "2026-08-09T00:00:00.740Z",
            "2026-08-09T00:00:00.123456789Z",
        ):
            with self.subTest(published_at=published_at):
                result = deploy_orchestrator.validate_published(
                    self.published(published_at),
                    site_id="site-123",
                    deploy_id="deploy-456",
                )
                self.assertEqual(result["published_at"], published_at)

    def test_rejects_non_utc_or_malformed_netlify_timestamp(self) -> None:
        for published_at in (
            "2026-08-09T00:00:00+00:00",
            "2026-08-09T00:00:00.Z",
            "2026-02-30T00:00:00.740Z",
        ):
            with self.subTest(published_at=published_at):
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError,
                    "timestamp is invalid",
                ):
                    deploy_orchestrator.validate_published(
                        self.published(published_at),
                        site_id="site-123",
                        deploy_id="deploy-456",
                    )


class DeployOrchestratorEvidenceTest(unittest.TestCase):
    PRODUCT = "1.0.15.3"
    HOST = "1.2.0"
    SITE = "site-123"
    DEPLOY = "deploy-456"
    PRIOR = "prior-123"
    INDEX_SHA = "1" * 64
    MANIFEST_SHA = "2" * 64
    PRIOR_INDEX_SHA = "3" * 64
    PRIOR_MANIFEST_SHA = "4" * 64
    NOW = "2026-08-09T00:00:00Z"

    def http_result(
        self,
        *,
        product: str,
        host: str,
        index_sha: str,
        manifest_sha: str,
        deploy_id: str | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "asset_count": 5,
            "completed_at": self.NOW,
            "host_id": "creator-web",
            "host_version": host,
            "index_sha256": index_sha,
            "manifest_sha256": manifest_sha,
            "product_build": product,
            "started_at": self.NOW,
            "status": "passed",
            "url": (
                f"https://{deploy_id}--lmdj-creator.netlify.app/"
                if deploy_id is not None
                else "https://lmdj-creator.netlify.app/"
            ),
        }
        if deploy_id is not None:
            result["deploy_id"] = deploy_id
        return {
            "ended_at": self.NOW,
            "result": result,
            "started_at": self.NOW,
            "status": "passed",
        }

    def browser_result(
        self, *, url: str, product: str, host: str, deploy_id: str
    ) -> dict[str, object]:
        return {
            "base_url": url,
            "deploy_id": deploy_id,
            "ended_at": self.NOW,
            "host_version": host,
            "product_build": product,
            "started_at": self.NOW,
            "status": "passed",
        }

    def site(self, deploy_id: str, *, state: str = "current") -> dict[str, object]:
        return {
            "id": self.SITE,
            "published_deploy": {
                "deploy_ssl_url": (
                    f"https://{deploy_id}--lmdj-creator.netlify.app"
                ),
                "id": deploy_id,
                "site_id": self.SITE,
                "state": "ready",
            },
            "ssl_url": "https://lmdj-creator.netlify.app",
            "state": state,
        }

    def success_document(self) -> dict[str, object]:
        deploy_url = f"https://{self.DEPLOY}--lmdj-creator.netlify.app"
        prior_url = f"https://{self.PRIOR}--lmdj-creator.netlify.app"
        candidate_immutable_http = self.http_result(
            product=self.PRODUCT,
            host=self.HOST,
            index_sha=self.INDEX_SHA,
            manifest_sha=self.MANIFEST_SHA,
            deploy_id=self.DEPLOY,
        )
        candidate_production_http = self.http_result(
            product=self.PRODUCT,
            host=self.HOST,
            index_sha=self.INDEX_SHA,
            manifest_sha=self.MANIFEST_SHA,
        )
        prior_immutable_http = self.http_result(
            product="1.0.15.2",
            host=self.HOST,
            index_sha=self.PRIOR_INDEX_SHA,
            manifest_sha=self.PRIOR_MANIFEST_SHA,
            deploy_id=self.PRIOR,
        )
        prior_production_http = self.http_result(
            product="1.0.15.2",
            host=self.HOST,
            index_sha=self.PRIOR_INDEX_SHA,
            manifest_sha=self.PRIOR_MANIFEST_SHA,
        )
        return {
            "archive": {
                "filename": (
                    f"lmdj-creator-web-{self.HOST}-product-{self.PRODUCT}.zip"
                ),
                "sha256": "a" * 64,
            },
            "channel": "canary",
            "contract": "lmdj.creator-web.deployment-evidence.v1",
            "ended_at": self.NOW,
            "git_revision": "b" * 40,
            "github_actions": {
                "run_id": "123456789",
                "run_url": "https://github.com/endaye/lmdj/actions/runs/123456789",
            },
            "host_version": self.HOST,
            "immutable": {
                "browser": self.browser_result(
                    url=deploy_url,
                    product=self.PRODUCT,
                    host=self.HOST,
                    deploy_id=self.DEPLOY,
                ),
                "deploy_id": self.DEPLOY,
                "deploy_url": deploy_url,
                "http": candidate_immutable_http,
            },
            "prior_good": {
                "deploy_id": self.PRIOR,
                "deploy_url": prior_url,
                "host_version": self.HOST,
                "immutable": {
                    "browser": self.browser_result(
                        url=prior_url,
                        product="1.0.15.2",
                        host=self.HOST,
                        deploy_id=self.PRIOR,
                    ),
                    "http": prior_immutable_http,
                },
                "product_build": "1.0.15.2",
                "production": {
                    "browser": self.browser_result(
                        url="https://lmdj-creator.netlify.app",
                        product="1.0.15.2",
                        host=self.HOST,
                        deploy_id=self.PRIOR,
                    ),
                    "http": prior_production_http,
                },
                "site_response": self.site(self.PRIOR),
            },
            "product_build": self.PRODUCT,
            "production": {
                "browser": self.browser_result(
                    url="https://lmdj-creator.netlify.app",
                    product=self.PRODUCT,
                    host=self.HOST,
                    deploy_id=self.DEPLOY,
                ),
                "http": candidate_production_http,
                "url": "https://lmdj-creator.netlify.app",
            },
            "publication": {
                "response": {
                    "deploy_ssl_url": deploy_url,
                    "id": self.DEPLOY,
                    "published_at": self.NOW,
                    "site_id": self.SITE,
                    "ssl_url": "https://lmdj-creator.netlify.app",
                    "state": "ready",
                },
                "same_deploy_id": self.DEPLOY,
            },
            "release_files": {
                "index_sha256": self.INDEX_SHA,
                "manifest_sha256": self.MANIFEST_SHA,
            },
            "release_url": (
                "https://github.com/endaye/lmdj/releases/tag/lmdj-v1.0.15.3"
            ),
            "site_id": self.SITE,
            "started_at": self.NOW,
            "tag": "lmdj-v1.0.15.3",
        }

    def recovery_document(self) -> dict[str, object]:
        success = self.success_document()
        prior = success["prior_good"]
        return {
            "action": "prior-still-current",
            "attempted_deploy": {
                "id": self.DEPLOY,
                "url": f"https://{self.DEPLOY}--lmdj-creator.netlify.app",
            },
            "contract": "lmdj.creator-web.deployment-recovery-evidence.v1",
            "original_status": 2,
            "post_recovery_site": prior["site_response"],
            "prior_deploy": {
                "host_version": prior["host_version"],
                "id": prior["deploy_id"],
                "index_sha256": self.PRIOR_INDEX_SHA,
                "manifest_sha256": self.PRIOR_MANIFEST_SHA,
                "product_build": prior["product_build"],
                "url": prior["deploy_url"],
            },
            "reconcile": prior["site_response"],
            "recorded_at": self.NOW,
            "recovery_response": None,
            "status": "passed",
            "validation": {
                "immutable_browser": prior["immutable"]["browser"],
                "immutable_http": prior["immutable"]["http"],
                "production_browser": prior["production"]["browser"],
                "production_http": prior["production"]["http"],
                "status": "passed",
            },
        }

    def write(self, document: dict[str, object], contract: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            deploy_orchestrator.write_evidence_document(
                output=output,
                source=json.dumps(document),
                expected_contract=contract,
            )
            return output.read_text(encoding="utf-8")

    def test_success_evidence_cross_binds_release_and_live_byte_identity(self) -> None:
        document = self.success_document()
        self.assertEqual(
            self.write(document, document["contract"]),
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        )

    def test_read_only_validator_reuses_writer_schema_without_file_effects(self) -> None:
        for document in (self.success_document(), self.recovery_document()):
            with self.subTest(contract=document["contract"]):
                self.assertEqual(
                    deploy_orchestrator.validate_evidence_document(
                        source=json.dumps(document), expected_contract=document["contract"]),
                    document,
                )
                with tempfile.TemporaryDirectory() as directory:
                    result = subprocess.run(
                        [sys.executable, deploy_orchestrator.__file__,
                         "evidence-validate-document", document["contract"]],
                        input=json.dumps(document), text=True, capture_output=True,
                        cwd=directory, timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, self.write(document, document["contract"]))
                    self.assertEqual(list(Path(directory).iterdir()), [])

    def test_read_only_validator_refuses_one_fact_identity_drift(self) -> None:
        paths = [
            ("production", "url"),
            ("publication", "same_deploy_id"),
            ("publication", "response", "site_id"),
            ("immutable", "http", "result", "index_sha256"),
            ("production", "browser", "product_build"),
            ("prior_good", "site_response", "published_deploy", "id"),
            ("prior_good", "immutable", "http", "result", "manifest_sha256"),
        ]
        for path in paths:
            with self.subTest(path=path):
                document = self.success_document()
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = "wrong"
                with self.assertRaises(deploy_orchestrator.DeployOrchestratorError):
                    deploy_orchestrator.validate_evidence_document(
                        source=json.dumps(document), expected_contract=document["contract"])
                with tempfile.TemporaryDirectory() as directory:
                    result = subprocess.run(
                        [sys.executable, deploy_orchestrator.__file__,
                         "evidence-validate-document", document["contract"]],
                        input=json.dumps(document), text=True, capture_output=True,
                        cwd=directory, timeout=10,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(list(Path(directory).iterdir()), [])

    def test_success_evidence_accepts_manifest_verified_asset_count(self) -> None:
        document = self.success_document()
        document["immutable"]["http"]["result"]["asset_count"] = 13
        document["production"]["http"]["result"]["asset_count"] = 13
        self.assertIn(
            '"asset_count":13', self.write(document, document["contract"])
        )

    def test_success_evidence_rejects_invalid_asset_count(self) -> None:
        for asset_count in (0, -1, True):
            with self.subTest(asset_count=asset_count):
                document = self.success_document()
                document["production"]["http"]["result"][
                    "asset_count"
                ] = asset_count
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "schema"
                ):
                    self.write(document, document["contract"])

    def test_success_evidence_accepts_exact_creator_url(self) -> None:
        document = self.success_document()
        result = document["production"]["http"]["result"]
        self.assertIn('"url":"https://lmdj-creator.netlify.app/"', self.write(
            document, document["contract"]
        ))

    def test_recovery_evidence_accepts_exact_creator_url(self) -> None:
        document = self.recovery_document()
        result = document["validation"]["production_http"]["result"]
        self.assertIn('"url":"https://lmdj-creator.netlify.app/"', self.write(
            document, document["contract"]
        ))

    def test_rejects_mismatched_creator_url_evidence(self) -> None:
        for url in (
            "https://other.example/",
            "https://lmdj-creator.netlify.app/path",
            "http://lmdj-creator.netlify.app/",
        ):
            with self.subTest(url=url):
                document = self.success_document()
                result = document["production"]["http"]["result"]
                result["url"] = url
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "schema"
                ):
                    self.write(document, document["contract"])

    def test_rejects_impossible_utc_timestamps_and_empty_http_results(self) -> None:
        for mutate in (
            lambda value: value.__setitem__("started_at", "9999-99-99T99:99:99Z"),
            lambda value: value["immutable"]["http"].__setitem__("result", {}),
        ):
            with self.subTest(mutate=mutate):
                document = self.success_document()
                mutate(document)
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "schema"
                ):
                    self.write(document, document["contract"])

    def test_rejects_http_identity_or_byte_mismatch(self) -> None:
        for key, value in (
            ("product_build", "1.0.99.0"),
            ("manifest_sha256", "f" * 64),
        ):
            with self.subTest(key=key):
                document = self.success_document()
                document["production"]["http"]["result"][key] = value
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "schema"
                ):
                    self.write(document, document["contract"])

    def test_rejects_legacy_alias_not_new_recovery_claim(self) -> None:
        document = {
            "action": "alias-not-new",
            "attempted_deploy": {
                "id": self.DEPLOY,
                "url": f"https://{self.DEPLOY}--lmdj-creator.netlify.app",
            },
            "contract": "lmdj.creator-web.deployment-recovery-evidence.v1",
            "original_status": 2,
            "prior_deploy": {"id": self.PRIOR, "url": f"https://{self.PRIOR}--lmdj-creator.netlify.app"},
            "reconcile": self.site("third-789"),
            "recorded_at": self.NOW,
            "recovery_response": None,
            "validation": {
                "immutable_browser": {},
                "immutable_http": {},
                "production_browser": {},
                "production_http": {},
                "status": "passed",
            },
        }
        with self.assertRaisesRegex(
            deploy_orchestrator.DeployOrchestratorError, "recovery evidence schema"
        ):
            self.write(document, document["contract"])


if __name__ == "__main__":
    unittest.main()
