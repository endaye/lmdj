#!/usr/bin/env python3
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from cloudflare_release_stage import export_stage,identity,StageError


class ReleaseStageTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir()
        self.git_env=dict(os.environ,GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1')
        self.git('init','-b','feat/stage-fixture','--template=')
        (self.repo/'README').write_text('exact verified source\n')
        self.git('add','README')
        self.git('-c','user.name=Stage Test','-c','user.email=stage@example.invalid','-c','commit.gpgsign=false','commit','-m','test fixture')
        self.source=self.git('rev-parse','HEAD').strip()
        self.dist=self.root/'dist';self.dist.mkdir();(self.dist/'index.html').write_bytes(b'index')
        (self.dist/'payload.wasm').write_bytes(b'\x00asm')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo),*args],env=self.git_env,text=True,stderr=subprocess.DEVNULL)

    def inputs(self,host='creator-web'):
        manifest={'host_id':host,'host_version':'3.0.0','product_build':'1.0.42.0'}
        (self.dist/'host-manifest.json').write_text(json.dumps(manifest))
        prefix={'creator-web':'lmdj-creator-web','web-runtime-host':'lmdj-web-runtime-host'}[host]
        archive=self.root/f'{prefix}-3.0.0-product-1.0.42.0.zip';archive.write_bytes(b'upstream-verified archive fixture')
        checksum=Path(str(archive)+'.sha256');checksum.write_bytes(b'upstream-verified checksum fixture')
        signature=Path(str(checksum)+'.asc');signature.write_bytes(b'upstream-verified signature fixture')
        return dict(repo_root=self.repo,source=self.source,tag='lmdj-v1.0.42.0',dist=self.dist,archive=archive,checksum=checksum,signature=signature,
                    archive_sha256=identity(archive)['sha256'],index_sha256=identity(self.dist/'index.html')['sha256'],
                    manifest_sha256=identity(self.dist/'host-manifest.json')['sha256'],output=self.root/'retained')

    def test_both_hosts_retain_exact_inputs_source_and_file_identities(self):
        for host in ('creator-web','web-runtime-host'):
            args=self.inputs(host);args['output']=self.root/host
            receipt=export_stage(**args);out=args['output']
            self.assertEqual(receipt['host_id'],host)
            self.assertEqual(receipt['source'],self.source)
            self.assertEqual(receipt['files']['payload.wasm'],identity(self.dist/'payload.wasm'))
            for key in ('archive','checksum','signature'):
                self.assertEqual((out/'release'/args[key].name).read_bytes(),args[key].read_bytes())
            self.assertEqual(receipt['source_archive'],identity(out/'source.tar'))
            self.assertEqual(json.loads((out/'stage.json').read_text()),receipt)

    def test_changed_verified_archive_is_rejected_without_creating_output(self):
        args=self.inputs();args['archive'].write_bytes(b'changed')
        with self.assertRaises(StageError):export_stage(**args)
        self.assertFalse(args['output'].exists())

    def test_changed_verified_entry_is_rejected(self):
        args=self.inputs();(self.dist/'index.html').write_bytes(b'changed')
        with self.assertRaises(StageError):export_stage(**args)
        self.assertFalse(args['output'].exists())

    def test_existing_or_relative_output_is_never_overwritten(self):
        args=self.inputs();out=args['output'];out.mkdir();(out/'keep').write_text('keep')
        with self.assertRaises(StageError):export_stage(**args)
        self.assertEqual((out/'keep').read_text(),'keep')
        args['output']=Path('relative-output')
        with self.assertRaises(StageError):export_stage(**args)

    def test_wrong_tag_or_asset_name_is_rejected(self):
        args=self.inputs();args['tag']='lmdj-v1.0.43.0'
        with self.assertRaises(StageError):export_stage(**args)
        args=self.inputs();args['signature']=self.root/'wrong.asc';args['signature'].write_bytes(b'wrong')
        with self.assertRaises(StageError):export_stage(**args)

    def test_symlink_payload_is_rejected(self):
        args=self.inputs();(self.dist/'link').symlink_to(args['archive'])
        with self.assertRaises(StageError):export_stage(**args)
        self.assertFalse(args['output'].exists())


if __name__=='__main__':unittest.main()
