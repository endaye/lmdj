from pathlib import Path
import json
import sys


FORBIDDEN = (
    "lmdj/project_io/",
    "project_store.hpp",
    "take_journal.hpp",
    "std::ifstream",
    "std::ofstream",
    "filesystem::directory_iterator",
)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: native_host_source_boundary_test.py SOURCE LINK_FILE")
    source_root = Path(sys.argv[1]).resolve(strict=True)
    link_file = Path(sys.argv[2]).resolve(strict=True)
    for path in source_root.rglob("*"):
        if path.suffix not in {".cpp", ".hpp"}:
            continue
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in source, (path, token)
    enqueue_sources = [
        path
        for path in source_root.rglob("*.cpp")
        if ".enqueue(" in path.read_text(encoding="utf-8")
    ]
    assert enqueue_sources == [source_root / "src" / "main.cpp"], enqueue_sources

    manifest = json.loads(
        (source_root / "module.json").read_text(encoding="utf-8")
    )
    assert manifest["dependencies"] == {
        "application-facade": "1.3.5",
        "audio-runtime": "0.4.1",
    }

    logical_dependencies = {
        value
        for value in link_file.read_text(encoding="utf-8").strip().split(";")
        if value.startswith("lmdj::")
    }
    expected = {"lmdj::application", "lmdj::audio_runtime"}
    if sys.platform == "darwin":
        expected.add("lmdj::audio_coreaudio")
    assert logical_dependencies == expected, logical_dependencies
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
