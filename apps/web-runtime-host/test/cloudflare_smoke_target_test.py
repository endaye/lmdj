#!/usr/bin/env python3
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from cloudflare_smoke import validate_target

class TargetTest(unittest.TestCase):
    def test_each_host_has_fixed_production_and_explicit_recovery_target(self):
        for host,worker in [('creator-web','creator'),('web-runtime-host','lab')]:
            for recovery in (False,True):
                target=worker+('-recovery' if recovery else '')
                self.assertEqual(validate_target(host,f'https://{target}.lmdj.workers.dev',False,recovery),target)
    def test_recovery_flag_cannot_address_production_or_inverse(self):
        for host,worker in [('creator-web','creator'),('web-runtime-host','lab')]:
            for recovery in (False,True):
                wrong=worker+('' if recovery else '-recovery')
                with self.assertRaises(ValueError):validate_target(host,f'https://{wrong}.lmdj.workers.dev',False,recovery)
    def test_version_preview_requires_exact_hex_prefix_and_explicit_flag(self):
        for host,worker in [('creator-web','creator'),('web-runtime-host','lab')]:
            for recovery in (False,True):
                target=worker+('-recovery' if recovery else '')
                for prefix in ('abcdef12','alias','abcdef123','zbcdef12'):
                    url=f'https://{prefix}-{target}.lmdj.workers.dev'
                    if prefix=='abcdef12':self.assertEqual(validate_target(host,url,True,recovery),target)
                    else:
                        with self.assertRaises(ValueError):validate_target(host,url,True,recovery)
                    with self.assertRaises(ValueError):validate_target(host,url,False,recovery)
    def test_other_host_account_or_suffix_is_rejected(self):
        for name in ('lab.lmdj.workers.dev','creator.foreign.workers.dev','creator.lmdj.workers.dev.evil.example'):
            with self.assertRaises(ValueError):validate_target('creator-web','https://'+name,True,False)
    def test_initialization_target_requires_explicit_matching_host_selection(self):
        for host, worker in [('creator-web', 'creator'), ('web-runtime-host', 'lab')]:
            target = worker + '-initialization'
            for prefix, preview in [('', False), ('abcdef12-', True)]:
                url = f'https://{prefix}{target}.lmdj.workers.dev'
                self.assertEqual(validate_target(host, url, preview, False, True), target)
                with self.assertRaises(ValueError):
                    validate_target(host, url, preview, False)
            for wrong in [worker, worker+'-recovery', target+'.foreign', 'other-initialization']:
                with self.assertRaises(ValueError):
                    validate_target(host, f'https://{wrong}.lmdj.workers.dev', False, False, True)
            with self.assertRaises(ValueError):
                validate_target(host, f'https://{target}.lmdj.workers.dev', False, True, True)

    def test_existing_local_emulator_target_remains_available(self):
        self.assertEqual(validate_target('creator-web','http://127.0.0.1:8787',False,False),'creator')

if __name__=='__main__':unittest.main()
