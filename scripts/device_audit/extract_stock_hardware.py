"""Extract explicitly selected ODM hardware files from the existing F.20 set.

Uses a checked host dump.erofs for compression. One temporary logical ODM
image is removed in finally; only small selected files and their provenance
remain. No handset access, partition writes or upload of stock contents.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import stat
import subprocess

from inventory_stock_vendor import DirectoryReader
from dissect.util.stream import MappingStream
from check_super import PREFIX, prefix_checks
from rehearse_super_layout import read_metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('stock', 'dump-erofs', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--path', action='append', required=True)
    a = p.parse_args()
    requested = set(a.path)
    if any(not n.startswith(('/firmware/', '/etc/wifi/', '/vendor/etc/wifi/'))
           or '..' in Path(n).parts or Path(n).suffix not in ('.bin', '.elf', '.cnt', '.ini')
           for n in requested):
        p.error('Only explicitly named ODM hardware files are supported')
    repo = Path(__file__).resolve().parents[2]
    out = a.output.resolve()
    if out.is_relative_to(repo):
        p.error('Stock hardware contents must remain outside the public checkout')
    out.mkdir(parents=True, exist_ok=False)
    temporary = out / 'odm-extract-temporary.img'
    acquisition = json.loads((a.stock / 'acquisition.json').read_text())
    if acquisition['identity'][:2] != ['RMX2072', 'RMX2072_11_F.20']:
        raise ValueError('Wrong original acquisition')
    parts = acquisition['partitions']['super']['parts']
    report = dict(source_super_sha256=acquisition['partitions']['super']['sha256'],
                  tool_sha256=hashlib.sha256(a.dump_erofs.read_bytes()).hexdigest(),
                  files={}, temporary_image_retained=False, handset_io=False)
    try:
        with ExitStack() as stack:
            source, total = MappingStream(), 0
            for i, row in enumerate(parts):
                f = a.stock / f'super-read-{i:02d}.bin'
                if f.stat().st_size != row['bytes']:
                    raise ValueError('Truncated original chunk')
                source.add(total, row['bytes'], stack.enter_context(f.open('rb')))
                total += row['bytes']
            prefix = source.read(PREFIX)
            prefix_checks(prefix)
            spans = read_metadata(prefix, 0)[-1]['odm']
            odm, size, checked = MappingStream(), 0, {0}
            for start, sectors in spans:
                odm.add(size, sectors * 512, source, start * 512)
                size += sectors * 512
                checked.update(range(start * 512 // (512 << 20),
                                     ((start + sectors) * 512 - 1) // (512 << 20) + 1))
            if not 0 < size < 2 << 30:
                raise ValueError('Unexpected ODM size')
            for i in checked:
                with (a.stock / f'super-read-{i:02d}.bin').open('rb') as f:
                    if hashlib.file_digest(f, 'sha256').hexdigest() != parts[i]['sha256']:
                        raise ValueError('Original chunk digest mismatch')
            reader = DirectoryReader(odm, size)
            selected = {n: node for n, node in reader.walk() if n in requested}
            if selected.keys() != requested or any(not stat.S_ISREG(n['mode'])
                    or not 0 < n['size'] <= 16 << 20 for n in selected.values()):
                raise ValueError('Missing, oversized or non-regular hardware file')
            odm.seek(0)
            with temporary.open('xb') as f:
                remaining = size
                while remaining:
                    block = odm.read(min(16 << 20, remaining))
                    if not block:
                        raise ValueError('Short logical ODM read')
                    f.write(block)
                    remaining -= len(block)
            for name, node in selected.items():
                r = subprocess.run([str(a.dump_erofs.resolve()), '--cat', '--path=' + name,
                                    str(temporary)], capture_output=True, timeout=60, check=True)
                if len(r.stdout) != node['size']:
                    raise ValueError('Decompressed size mismatch: ' + name)
                if node['layout'] in (0, 2) and node['size'] <= 65536:
                    if r.stdout != reader.small_flat_file(node):
                        raise ValueError('Independent flat-file comparison failed: ' + name)
                target = out / name.lstrip('/')
                if not target.resolve().is_relative_to(out):
                    raise ValueError('Extraction escaped output directory')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(r.stdout)
                report['files'][name] = dict(bytes=len(r.stdout),
                    sha256=hashlib.sha256(r.stdout).hexdigest(), source_layout=node['layout'])
            report['verified_local_chunks'] = sorted(checked)
            report['odm_extents'] = spans
    finally:
        if temporary.exists():
            if temporary.resolve().parent != out or temporary.name != 'odm-extract-temporary.img':
                raise ValueError('Unexpected temporary path; refusing removal')
            temporary.unlink()
    (out / 'extraction.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
