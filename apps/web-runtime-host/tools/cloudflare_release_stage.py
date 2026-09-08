#!/usr/bin/env python3
"""Retain an already verified Host release for Cloudflare command composition.

Called only after the stable Host verifier succeeds. This private staging receipt
is not a deployment Contract or independent permission to publish. Consumers must
reverify retained signatures/artifacts before a later cloud operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


class StageError(RuntimeError):
    def __init__(self, why):
        super().__init__(f'why: {why}; remedy: preserve any incomplete stage and rerun verification into a new absolute directory')


def identity(path):
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk);size += len(chunk)
    return {'sha256': digest.hexdigest(), 'bytes': size}


def export_stage(*, repo_root, source, tag, dist, archive, checksum, signature,
                 archive_sha256, index_sha256, manifest_sha256, output):
    output = Path(output)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise StageError('stage output must be an absent absolute path')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise StageError('source must be an exact commit SHA')
    for digest in (archive_sha256, index_sha256, manifest_sha256):
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise StageError('verified digest is malformed')
    if (identity(archive)['sha256'] != archive_sha256
            or identity(dist / 'index.html')['sha256'] != index_sha256
            or identity(dist / 'host-manifest.json')['sha256'] != manifest_sha256):
        raise StageError('verified input changed before export')
    manifest = json.loads((dist / 'host-manifest.json').read_text())
    prefix = {'creator-web':'lmdj-creator-web', 'web-runtime-host':'lmdj-web-runtime-host'}.get(manifest.get('host_id'))
    if prefix is None or tag != 'lmdj-v' + manifest['product_build'] or not re.fullmatch(r'lmdj-v\d+\.\d+\.\d+\.\d+', tag):
        raise StageError('tag and Host identity do not match')
    expected = f"{prefix}-{manifest['host_version']}-product-{manifest['product_build']}.zip"
    if archive.name != expected or checksum.name != expected + '.sha256' or signature.name != expected + '.sha256.asc':
        raise StageError('release asset filenames do not match verified Host identity')
    for path in [dist, archive, checksum, signature, *dist.rglob('*')]:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise StageError('stage inputs contain a symlink or special file')
    resolved = subprocess.check_output(['git','-C',str(repo_root),'rev-parse','--verify',source+'^{commit}'], text=True).strip()
    if resolved != source:
        raise StageError('source object is not the verified commit')
    # Exclusive creation prevents overwriting earlier audit/rollback material.
    output.mkdir(mode=0o700)
    shutil.copytree(dist, output/'dist')
    assets = output/'release';assets.mkdir(mode=0o700)
    for path in (archive, checksum, signature):shutil.copyfile(path, assets/path.name)
    subprocess.run(['git','-C',str(repo_root),'archive','--format=tar','--output',str(output/'source.tar'),source], check=True)
    retained_archive = identity(assets/archive.name)
    if retained_archive['sha256'] != archive_sha256:
        raise StageError('archive changed during export')
    if identity(output/'dist/index.html')['sha256'] != index_sha256 or identity(output/'dist/host-manifest.json')['sha256'] != manifest_sha256:
        raise StageError('entry point changed during export')
    files = {str(path.relative_to(output/'dist')):identity(path) for path in sorted((output/'dist').rglob('*')) if path.is_file()}
    receipt = {'kind':'verified-host-stage','source':source,'tag':tag,'host_id':manifest['host_id'],
               'product_build':manifest['product_build'],'host_version':manifest['host_version'],
               'archive':{'name':archive.name,**retained_archive},
               'checksum':{'name':checksum.name,**identity(assets/checksum.name)},
               'signature':{'name':signature.name,**identity(assets/signature.name)},
               'source_archive':identity(output/'source.tar'),'files':files}
    # Persist all copied inputs before publishing the final completion marker.
    for path in output.rglob('*'):
        if path.is_file():
            with path.open('rb') as f:os.fsync(f.fileno())
    for path in sorted((p for p in output.rglob('*') if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    with (output/'stage.json').open('x') as f:
        json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    for path in (output,output.parent):
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo-root','dist','archive','checksum','signature','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    for name in ('source','tag','archive-sha256','index-sha256','manifest-sha256'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        receipt=export_stage(**vars(args))
        print(json.dumps({'output':str(args.output),'receipt':receipt},sort_keys=True))
    except (StageError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
