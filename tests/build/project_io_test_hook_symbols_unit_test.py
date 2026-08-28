#!/usr/bin/env python3

import importlib.util
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parent
    / "project_io_test_hook_symbols_test.py"
)
SPEC = importlib.util.spec_from_file_location(
    "project_io_test_hook_symbols_test", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidateSymbolsTest(unittest.TestCase):
    def test_clean_global_symbols_pass(self) -> None:
        self.assertEqual(
            [],
            MODULE.validate_symbols(
                "0000000000000000 T lmdj::project_io::ProjectStore::load\n"
            ),
        )

    def test_each_forbidden_test_hook_symbol_is_reported_once(self) -> None:
        forbidden = (
            "FaultPoint",
            "set_fault_hook",
            "set_active_directory_sync_hook",
            "set_pattern_claim_hook",
            "invoke_pattern_claim_hook",
            "fail_next_pattern_publication",
        )
        for symbol in forbidden:
            with self.subTest(symbol=symbol):
                line = f"0000000000000000 T {symbol}\n"
                self.assertEqual([line.rstrip()], MODULE.validate_symbols(line))

    def test_each_forbidden_test_hook_marker_is_reported_once(self) -> None:
        for marker in MODULE.FORBIDDEN_BYTES:
            with self.subTest(marker=marker):
                self.assertEqual(
                    [marker.decode("ascii")], MODULE.validate_binary(marker)
                )


if __name__ == "__main__":
    unittest.main()
