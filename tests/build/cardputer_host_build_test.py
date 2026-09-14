"""Stable command boundaries; fake SDK calls are not target-build evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
PIN = 'fff9895c82d744c7237be8847347bdd1b07c6643'


class CardputerBuildCommandTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cardputer-command-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'repo with spaces'
        (self.root / 'scripts').mkdir(parents=True)
        self.script = self.root / 'scripts/cardputer-host.sh'
        shutil.copyfile(REPO / 'scripts/cardputer-host.sh', self.script)
        self.sdk = self.base / 'sdk'
        (self.sdk / 'tools').mkdir(parents=True)
        (self.sdk / 'tools/idf.py').write_text(
            'import json,os,sys\n'
            'with open(os.environ["CALLS"], "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'sys.exit(int(os.environ.get("SDK_EXIT", "0")))\n')
        self.venv = self.base / 'python env'
        (self.venv / 'bin').mkdir(parents=True)
        (self.venv / 'bin/python').symlink_to(sys.executable)
        self.bin = self.base / 'commands'
        self.bin.mkdir()
        git = self.bin / 'git'
        git.write_text('#!/bin/sh\nprintf "%s\\n" "$SDK_REVISION"\n')
        git.chmod(0o755)
        self.header = self.base / 'explicit config.hpp'
        self.header.write_text('// external research configuration\n')
        self.calls = self.base / 'calls.jsonl'
        self.env = dict(os.environ, IDF_PATH=str(self.sdk),
                        IDF_PYTHON_ENV_PATH=str(self.venv), SDK_REVISION=PIN,
                        CALLS=str(self.calls), PATH=str(self.bin) + os.pathsep + os.environ['PATH'])

    def run_command(self, *args):
        return subprocess.run(['bash', str(self.script), *map(str, args)],
                              cwd=self.root, env=self.env, text=True, capture_output=True)

    def assert_rejected_without_sdk_call(self, result, code=2):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())
        if code == 2:
            self.assertIn('why:', result.stderr)
            self.assertIn('remedy:', result.stderr)

    def test_missing_action(self):
        self.assert_rejected_without_sdk_call(self.run_command(), 64)

    def test_flash_is_not_an_implicit_build_operation(self):
        self.assert_rejected_without_sdk_call(self.run_command('flash', self.header), 64)

    def test_configure_accepts_assembly_from_product_sources(self):
        result = self.run_command('configure')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extra_configuration_argument_is_rejected(self):
        self.assert_rejected_without_sdk_call(self.run_command('build', self.header), 64)

    def test_missing_sdk(self):
        self.env.pop('IDF_PATH')
        self.assert_rejected_without_sdk_call(self.run_command('build'))

    def test_missing_python_environment(self):
        self.env.pop('IDF_PYTHON_ENV_PATH')
        self.assert_rejected_without_sdk_call(self.run_command('build'))

    def test_wrong_sdk_revision(self):
        self.env['SDK_REVISION'] = '0' * 40
        self.assert_rejected_without_sdk_call(self.run_command('build'))

    def test_redirected_build_root(self):
        (self.root / 'build').symlink_to(self.sdk, target_is_directory=True)
        self.assert_rejected_without_sdk_call(self.run_command('build'))

    def test_configure_passes_exact_paths_with_spaces(self):
        result = self.run_command('configure')
        self.assertEqual(result.returncode, 0, result.stderr)
        build = self.root / 'build/core/cardputer-host'
        self.assertEqual([json.loads(line) for line in self.calls.read_text().splitlines()], [[
            '-C', str(self.root / 'apps/cardputer-host'), '-B', str(build),
            '-D', 'SDKCONFIG=' + str(build / 'sdkconfig'), 'reconfigure']])

    def test_build_reconfigures_before_build(self):
        result = self.run_command('build')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual([call[-1] for call in calls], ['reconfigure', 'build'])
        self.assertEqual(calls[0][:-1], calls[1][:-1])

    def test_configuration_failure_prevents_build(self):
        self.env['SDK_EXIT'] = '17'
        result = self.run_command('build')
        self.assertEqual(result.returncode, 17)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual([call[-1] for call in calls], ['reconfigure'])

    def test_test_command_rejects_unknown_preset(self):
        self.assert_rejected_without_sdk_call(self.run_command('test', 'unknown'), 64)

    def test_target_outputs_are_excluded_from_source_inventory(self):
        result = subprocess.run(['git', 'check-ignore', '--no-index', 'build/core/cardputer-host/sdkconfig'],
                                cwd=REPO, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def fake_native_commands(self):
        for name in ('cmake', 'ctest'):
            command = self.bin / name
            command.write_text('#!' + sys.executable + '\n'
                               'import json,os,sys\n'
                               'from pathlib import Path\n'
                               'with open(os.environ["CALLS"], "a") as f: f.write(json.dumps([Path(sys.argv[0]).name]+sys.argv[1:])+"\\n")\n'
                               'sys.exit(int(os.environ.get("NATIVE_EXIT", "0")))\n')
            command.chmod(0o755)

    def test_native_dispatch_preserves_sanitizer_selection(self):
        self.fake_native_commands()
        result = self.run_command('test', 'asan')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(calls, [
            ['cmake', '--preset', 'asan'],
            ['cmake', '--build', '--preset', 'asan', '--target', 'lmdj_cardputer_audio_lifecycle_tests'],
            ['ctest', '--preset', 'asan', '--output-on-failure', '--no-tests=error', '-R', r'^platform\.cardputer\.'],
        ])

    def test_native_configuration_failure_prevents_stale_test_run(self):
        self.fake_native_commands()
        self.env['NATIVE_EXIT'] = '19'
        result = self.run_command('test')
        self.assertEqual(result.returncode, 19)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(calls, [['cmake', '--preset', 'dev']])


if __name__ == '__main__':
    unittest.main()
