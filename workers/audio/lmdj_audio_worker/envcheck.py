"""parity 环境指纹校验（spec §3.2）：venv 的关键库版本必须与 constraints 完全一致。

指纹不符即中止，不得带病比较。stdlib only，可在任意 venv 中运行。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _norm(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def read_constraints(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, version = line.partition("==")
        if not sep or not version:
            raise ValueError(f"constraints 只允许 == 精确 pin：{line!r}")
        pins[_norm(name)] = version.strip()
    return pins


def check(pins: dict[str, str], installed: dict[str, str],
          label: str) -> list[str]:
    errors: list[str] = []
    for name, version in sorted(pins.items()):
        got = installed.get(name)
        if got is None:
            errors.append(f"{label}: 缺少 {name}=={version}")
        elif got != version:
            errors.append(f"{label}: {name}=={got}，constraints 要求 {version}")
    return errors


def freeze(venv: Path) -> dict[str, str]:
    proc = subprocess.run([str(venv / "bin" / "pip"), "freeze"],
                          capture_output=True, text=True, check=True)
    installed: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        name, sep, version = line.partition("==")
        if sep:
            installed[_norm(name)] = version.strip()
    return installed


def python_version(venv: Path) -> str:
    proc = subprocess.run(
        [str(venv / "bin" / "python"), "-c",
         "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("envcheck", description=__doc__)
    parser.add_argument("venvs", nargs="+", type=Path)
    parser.add_argument("--constraints", type=Path, required=True)
    args = parser.parse_args(argv)

    pins = read_constraints(args.constraints)
    failures: list[str] = []
    for venv in args.venvs:
        failures += check(pins, freeze(venv), str(venv))
    versions = {str(v): python_version(v) for v in args.venvs}
    if len(set(versions.values())) > 1:
        failures.append(f"python minor 版本不一致: {versions}")
    if failures:
        print("环境指纹校验失败：", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"环境指纹 OK: {', '.join(str(v) for v in args.venvs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
