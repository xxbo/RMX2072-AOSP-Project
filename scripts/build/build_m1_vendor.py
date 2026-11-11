"""Build the small, labeled, read-only-test vendor image from project sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'device/realme/bladerunner_48m/m1-vendor'
EPOCH = 1230768000
UUID = '896e7471-c34c-40c8-b854-8efe96b80533'


def build(output):
    output = output.resolve()
    if ROOT in output.parents or output == ROOT:
        raise ValueError('Select an output outside the checkout')
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LC_ALL='C', TZ='UTC', E2FSPROGS_FAKE_TIME=str(EPOCH))
    paths = sorted(SOURCE.rglob('*'))
    contexts = []
    for row in (SOURCE/'etc/selinux/vendor_file_contexts').read_text().splitlines():
        pattern, label = row.split()
        contexts.append((re.compile(pattern), label))
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        stage = Path(tmp)
        image = stage/'vendor.img'
        image.write_bytes(bytes(2 * 1024 * 1024))
        subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '4096', '-I', '256',
                        '-N', '128', '-m', '0', '-L', 'rmx-m1-vendor', '-U', UUID,
                        '-O', 'none,extent,filetype,ext_attr,sparse_super',
                        '-E', 'root_owner=0:0,lazy_itable_init=0,hash_seed='+UUID, image],
                       check=True, env=env)
        commands = []
        hashes = {}
        for index, path in enumerate([SOURCE, *paths]):
            name = '/'+path.relative_to(SOURCE).as_posix() if path != SOURCE else '/'
            if not re.fullmatch(r'/[a-zA-Z0-9/_.-]*', name) or path.is_symlink():
                raise ValueError('Unexpected vendor source '+name)
            if path.is_file():
                data = path.read_bytes().replace(b'\r\n', b'\n')
                local = 'input-'+str(index)
                (stage/local).write_bytes(data)
                commands.append(f'write {local} {name}')
                hashes[name] = hashlib.sha256(data).hexdigest()
            elif name != '/':
                commands.append('mkdir '+name)
            mode = '040755' if path.is_dir() else '0100644'
            commands.append(f'set_inode_field {name} mode {mode}')
            for field in ('atime','ctime','mtime','crtime'):
                commands.append(f'set_inode_field {name} {field} @{EPOCH}')
            device_path = '/vendor'+name.rstrip('/')
            label = next(label for pattern, label in reversed(contexts) if pattern.fullmatch(device_path))
            local = 'label-'+str(index)
            (stage/local).write_bytes(label.encode()+b'\0')
            commands.append(f'ea_set -f {local} {name} security.selinux')
        (stage/'commands').write_text('\n'.join(commands)+'\n', encoding='ascii')
        result = subprocess.run(['debugfs','-w','-f','commands','vendor.img'], cwd=stage,
                                env=env, capture_output=True, text=True, check=True)
        if any('debugfs ' not in line for line in result.stderr.splitlines()):
            raise RuntimeError(result.stderr)
        subprocess.run(['e2fsck', '-fn', image], check=True, env=env)
        for name, digest in hashes.items():
            data = subprocess.check_output(['debugfs','-R','cat '+name,image], stderr=subprocess.DEVNULL)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Image content differs at '+name)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        image.replace(output/'vendor.img')
    (output/'vendor.json').write_text(json.dumps(dict(sha256=digest, files=hashes), indent=2)+'\n')
    return digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    print(build(parser.parse_args().output))
