#!/usr/bin/env python3

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
FAILURE_ROOT = REPO_ROOT / "build/core/proof-failures"


before = set(FAILURE_ROOT.iterdir()) if FAILURE_ROOT.is_dir() else set()
with tempfile.TemporaryDirectory(prefix="lmdj-proof-failure-") as temporary:
    fake_bin = Path(temporary)
    fake_cmake = fake_bin / "cmake"
    fake_cmake.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'injected proof configure failure' >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    fake_cmake.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    completed = subprocess.run(
        ["scripts/core.sh", "proof"],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

after = set(FAILURE_ROOT.iterdir()) if FAILURE_ROOT.is_dir() else set()
created = after - before
assert len(created) == 1, (before, after, completed.stdout, completed.stderr)
failure_path = created.pop()
try:
    assert completed.returncode == 99, (completed.stdout, completed.stderr)
    proof_log = failure_path / "proof.log"
    assert proof_log.is_file(), failure_path
    log = proof_log.read_text(encoding="utf-8")
    assert "product version tests: PASS" in log
    assert "injected proof configure failure" in log
finally:
    shutil.rmtree(failure_path)

print("proof failure artifact preservation: PASS")

script = (REPO_ROOT / "scripts/core.sh").read_text(encoding="utf-8")
manifest_gate = script.index("python3 scripts/version.py manifest")
diff_gate = script.index("git diff --check", manifest_gate)
beat_publication = script.index(
    'copy_if_different "$proof_output_wav" "$published_output_wav"'
)
manifest_publication = script.index(
    'copy_if_different "$proof_manifest" "$published_manifest"'
)
assert manifest_gate < diff_gate < beat_publication < manifest_publication
