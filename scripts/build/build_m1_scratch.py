"""Build blank, labeled ext4 filesystems for a volatile Android boot trial."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

VOLUMES = {
    'data': (512, '56baa650-68d8-498b-95f3-a9ac4e11127d',
             [('/', 'system_data_root_file', '0771', 1000, 1000),
              ('/misc', 'system_data_file', '1771', 1000, 9998),
              ('/misc/keystore', 'keystore_data_file', '0700', 1017, 1017)]),
    'metadata': (32, 'bc013e05-6b24-476b-ab5c-dd4ccf0d5308',
                 [('/', 'metadata_file', '0755', 0, 0)]),
}


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve()
    env = dict(os.environ, LC_ALL='C', TZ='UTC', E2FSPROGS_FAKE_TIME='1230768000')
    records = {}
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name, (mib, uuid, directories) in VOLUMES.items():
            image = directory/(name+'.ext4')
            with image.open('xb') as file:
                file.truncate(mib * 1024 * 1024)
            subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '4096', '-I', '256',
                            '-m', '0', '-U', uuid, '-L', 'm1-'+name, '-O',
                            'none,extent,filetype,ext_attr,sparse_super,large_file',
                            '-E', 'root_owner=0:0,hash_seed='+uuid, image], check=True, env=env)
            commands = []
            for index, (path, label, mode, uid, gid) in enumerate(directories):
                if path != '/':
                    commands.append('mkdir '+path)
                for key, value in [('mode', '04'+mode), ('uid', uid), ('gid', gid)]:
                    commands.append(f'set_inode_field {path} {key} {value}')
                (directory/f'label{index}').write_bytes(f'u:object_r:{label}:s0\0'.encode())
                commands.append(f'ea_set -f label{index} {path} security.selinux')
            script = directory/'commands'
            script.write_text('\n'.join(commands)+'\n')
            result = subprocess.run(['debugfs', '-w', '-f', script, image], cwd=directory,
                                    capture_output=True, text=True, check=True, env=env)
            if any('debugfs ' not in line for line in result.stderr.splitlines()):
                raise ValueError(result.stderr)
            for index, (path, *_rest) in enumerate(directories):
                check = directory/'label-read'
                check.unlink(missing_ok=True)
                subprocess.run(['debugfs', '-R', f'ea_get -f label-read {path} security.selinux', image],
                               cwd=directory, check=True, env=env)
                if check.read_bytes() != (directory/f'label{index}').read_bytes():
                    raise ValueError('Wrong ext4 label: '+path)
            subprocess.run(['e2fsck', '-fn', image], check=True, env=env)
            packed = output/(name+'.ext4.gz')
            with image.open('rb') as src, packed.open('xb') as dest:
                digest = hashlib.file_digest(src, 'sha256').hexdigest()
                src.seek(0)
                with gzip.GzipFile(fileobj=dest, mode='wb', filename='', mtime=0) as compressed:
                    shutil.copyfileobj(src, compressed, 1024*1024)
            records[name] = dict(bytes=image.stat().st_size, sha256=digest, uuid=uuid,
                                 gzip_sha256=hashlib.sha256(packed.read_bytes()).hexdigest())
    (output/'scratch.json').write_text(json.dumps(records, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
