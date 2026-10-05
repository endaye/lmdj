#!/usr/bin/env python3
"""Native test children must start in a fresh process image (#1752)."""

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[3]
NON_CODE = re.compile(
    r'//(?:\\\n|[^\n])*|/\*.*?\*/|'
    r'(?:u8|u|U|L)?R"(?P<delimiter>[^\s()\\"]{0,16})\(.*?\)(?P=delimiter)"|'
    r'"(?:\\.|[^"\\])*"|(?<!\w)(?:u8|u|U|L)?\'(?:\\.|[^\'\\\n])*\'',
    re.DOTALL,
)
FORK_CALL = re.compile(r'\b(?:fork|vfork)\s*\(')


def fork_lines(source: str) -> list[int]:
    # Preserve newlines so failures name the actual call, not explanatory prose.
    code = NON_CODE.sub(lambda m: re.sub(r'[^\n]', ' ', m[0]), source)
    return [code.count('\n', 0, m.start()) + 1 for m in FORK_CALL.finditer(code)]


class NativeChildProcessTest(unittest.TestCase):
    def test_native_tests_do_not_call_fork(self):
        paths = subprocess.check_output(
            ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
            cwd=ROOT,
        ).decode().split('\0')
        violations = []
        for name in sorted(set(paths)):
            path = Path(name)
            if path.suffix not in {'.cpp', '.cc', '.cxx', '.c', '.hpp', '.h'}:
                continue
            if not {'test', 'tests'}.intersection(path.parts):
                continue
            # A staged deletion need not still exist in the working tree.
            if not (ROOT / path).is_file():
                continue
            for line in fork_lines((ROOT / path).read_text()):
                violations.append(f'{name}:{line}')
        self.assertFalse(
            violations,
            'why: native test fork calls can die in Darwin ASan child handlers '
            'before test code executes: ' + ', '.join(violations) +
            '; remedy: launch a fresh test-binary child role with posix_spawn '
            'and retain its existing crash boundaries and far-side assertions',
        )

    def test_comments_and_literals_are_not_calls(self):
        source = '''// fork();
/* ::fork(); */
const char* a = "fork(\\\"argument\\\")";
const auto b = R"note(::fork(); "nested")note";
const char c = '(';
'''
        self.assertEqual(fork_lines(source), [])

    def test_call_tokens_survive_comments_and_line_breaks(self):
        self.assertEqual(fork_lines('::fork /* explanatory */\n();\n::vfork();'), [1, 3])

    def test_numeric_separators_do_not_hide_calls(self):
        self.assertEqual(fork_lines("auto n = 12'000;\nfork();\nauto m = 34'000;"), [2])


if __name__ == '__main__':
    unittest.main()
