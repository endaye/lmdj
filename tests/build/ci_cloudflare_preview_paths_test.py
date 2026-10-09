"""Producer/consumer proof for the Cloudflare Preview paths filter.

Blind spot: the filter in cloudflare-preview-build.yml and the canonical
scripts/ci/cloudflare_preview_paths.json could agree on a set that silently
omits a real build input, skipping Previews that would have caught a site
defect. The independent oracle is the traced read inventory of
`npm --prefix apps/docs-site run check` (docs/plans/2026-10-09-cloudflare-preview-activation.md),
asserted here entry by entry, plus a fail-closed disposition of every tracked
top-level so a new tree cannot slip past unclassified.
"""
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/cloudflare-preview-build.yml'
CANONICAL = ROOT / 'scripts/ci/cloudflare_preview_paths.json'

# Independent oracle: every read that escapes apps/docs-site, traced 2026-10-09
# (repo-facts.mjs, host/release changelog projection, test-tier content asserts,
# executed shell entry points). Class (a) site content and (b) check-gate reads.
TRACED_INPUTS = [
    'products/lmdj/version.json',
    'products/lmdj/assembly.json',
    'products/lmdj/assembly.lock.json',
    'products/lmdj/CMakeLists.txt',
    'packages/foundation/module.json',
    'apps/creator-web/module.json',
    'apps/web-runtime-host/module.json',
    'apps/creator-web/CHANGELOG.md',
    'apps/web-runtime-host/CHANGELOG.md',
    'providers/local-proof-success/module.json',
    'contracts/assembly/lmdj.assembly.v1.schema.json',
    'docs/release-evidence/release-intents.json',
    'docs/release-evidence/changelog-publications.json',
    'docs/governance/version-management.md',
    'docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md',
    'docs/quality/2026-08-07-stage7-creator-editor-acceptance.md',
    'docs/quality/2026-08-12-stage7-creator-editor-review.md',
    'docs/plans/2026-08-07-lmdj-stage7-creator-editor.md',
    'docs/plans/2026-08-13-lmdj-stage7-review-remediation.md',
    'docs/design/2026-08-07-lmdj-stage7-creator-editor-design.md',
    'docs/design/2026-08-13-lmdj-stage7-review-remediation-design.md',
    'docs/release-evidence/2026-08-13-stage7-remediation-canary.md',
    'docs/release-evidence/2026-08-13-stage7-keyboard-mapping-canary-1.0.20.0.md',
    'tools/release/changelog_site.py',
    'tools/release/model.py',
    'tools/release/policy.json',
    'tools/canary/preparation.py',
    'tools/canary/records.py',
    'tests/build/release_changelog_site_test.py',
    'scripts/docs-site.sh',
    'scripts/architecture-portal.sh',
    '.github/workflows/cloudflare-preview-build.yml',
    '.github/workflows/cloudflare-preview-publish.yml',
    'scripts/ci/cloudflare_preview_publish.py',
    'scripts/ci/cloudflare_preview_artifact.py',
    'scripts/ci/cloudflare_preview_download.py',
]

# Paths that must never trigger a Preview build on their own.
NEGATIVES = [
    'packages/foundation/src/geometry.cpp',
    'packages/audio-runtime/include/audio/engine.hpp',
    'apps/core-cli/src/main.cpp',
    'apps/native-host/src/host.cpp',
    'tests/e2e/creator_journey.py',
    'tests/core/facade/application_test.cpp',
    'docs/prd/decisions/2026-10-08-pattern-length-and-copy.md',
    'docs/plans/2026-10-09-any-new-plan.md',
    'demos/lmdj-mark/index.html',
    '.github/workflows/ci.yml',
    '.github/workflows/deploy-cloudflare-portal.yml',
    'tools/project-bundle/bundle.py',
    'third_party/nlohmann-json/json.hpp',
]

# Fail-closed disposition of tracked top-levels: anything not matched by the
# pattern set must be named here; a new top-level fails this test until its
# Preview relevance is decided.
IRRELEVANT_TOP_LEVELS = {
    '.agents', '.claude', '.codex', 'build', 'cmake', 'demos', 'packaging',
    'references', 'testdata', 'third_party', 'workers',
}
IRRELEVANT_ROOT_FILES = {
    '.gitattributes', '.gitignore', '.node-version', 'AGENTS.md', 'CMakeLists.txt',
    'CMakePresets.json', 'CLAUDE.md', 'LICENSE', 'README.md', 'wrangler.json',
}


def compile_pattern(pattern):
    """GitHub paths semantics: `*` stays inside one segment, `**` crosses them."""
    out = []
    for i, part in enumerate(pattern.split('/')):
        if part == '**':
            out.append('.*')
        else:
            out.append(re.escape(part).replace(r'\*', '[^/]*'))
    return re.compile('^' + '/'.join(out) + '$')


class PreviewPathsTest(unittest.TestCase):
    def setUp(self):
        canonical = json.loads(CANONICAL.read_text())
        self.assertEqual(canonical['schema'], 'lmdj.cloudflare-preview-paths.v1')
        self.patterns = [entry['value'] for entry in canonical['patterns']]
        self.assertTrue(all(entry.get('evidence') for entry in canonical['patterns']),
                        'why: a filter pattern without evidence is unauditable; '
                        'remedy: name the traced read each pattern covers')
        self.matchers = [(p, compile_pattern(p)) for p in self.patterns]
        tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.split()
        self.assertTrue(tracked)
        self.tracked = tracked

    def matches(self, path):
        return [p for p, rx in self.matchers if rx.match(path)]

    def test_workflow_paths_equal_canonical_set(self):
        block = re.search(r'(?m)^    paths:\n((?:      - [^\n]+\n)+)', WORKFLOW.read_text())
        self.assertIsNotNone(block, 'why: the pull_request paths filter is missing; '
                                    'remedy: restore it from scripts/ci/cloudflare_preview_paths.json')
        yaml = [line.strip()[2:] for line in block.group(1).splitlines()]
        self.assertEqual(sorted(yaml), sorted(self.patterns),
                         'why: workflow paths and the canonical set disagree; '
                         'remedy: edit scripts/ci/cloudflare_preview_paths.json and regenerate the block')

    def test_every_pattern_is_live(self):
        canonical = json.loads(CANONICAL.read_text())
        optional = {entry['value'] for entry in canonical['patterns'] if entry.get('optional')}
        for pattern, rx in self.matchers:
            if pattern in optional:
                continue
            self.assertTrue(any(rx.match(path) for path in self.tracked),
                            f'why: filter pattern {pattern} matches no tracked file; '
                            f'remedy: remove it or restore the input it covered')

    def test_traced_inputs_are_covered(self):
        for path in TRACED_INPUTS:
            self.assertTrue(self.matches(path),
                            f'why: traced build input {path} is not Preview-relevant; '
                            f'remedy: add a covering pattern to scripts/ci/cloudflare_preview_paths.json')

    def test_unrelated_paths_stay_out(self):
        for path in NEGATIVES:
            self.assertFalse(self.matches(path),
                             f'why: {path} cannot change the built site but triggers Previews; '
                             f'remedy: narrow the matching pattern')

    def test_every_top_level_is_dispositioned(self):
        top_levels = set()
        for path in self.tracked:
            first = path.split('/', 1)
            top_levels.add(first[0] if len(first) == 2 else path)
        for top in sorted(top_levels):
            if top in IRRELEVANT_TOP_LEVELS or top in IRRELEVANT_ROOT_FILES:
                continue
            covered = any(self.matches(path) for path in self.tracked
                          if path == top or path.startswith(top + '/'))
            self.assertTrue(covered,
                            f'why: tracked top-level {top} has no Preview-relevance disposition; '
                            f'remedy: cover it in cloudflare_preview_paths.json or declare it '
                            f'irrelevant in this test with the reason')


if __name__ == '__main__':
    unittest.main()
