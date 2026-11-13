"""Pack original GSI blocks for a read-only RAM/USB comparison under dm-verity."""
import argparse
import hashlib
from itertools import groupby
import json
from pathlib import Path
import re

BS = 4096
REFERENCE = Path(__file__).resolve().parents[2]/'build/device/gsi17-mount-reference.json'


def hash_blocks(blocks, data_count):
    # AVB hashtree levels are stored root first, with 128 SHA-256 entries per block.
    levels = []
    count = data_count
    while count > 1:
        count = (count+127)//128
        levels.append(count)
    parents = {b for b in blocks if b < data_count}
    for i in range(len(levels)):
        parents = {b//128 for b in parents}
        start = data_count + sum(levels[i+1:])
        yield from (start + b for b in parents)


def contiguous(blocks):
    for _, group in groupby(enumerate(sorted(blocks)), lambda pair: pair[1]-pair[0]):
        run = [b for _,b in group]
        yield run[0],len(run)


def capture_inputs(reads, events):
    blocks = set()
    ref = json.loads(REFERENCE.read_text())
    for row in reads.read_text().splitlines():
        offset, count = map(int, row.split())
        if offset < 0 or count <= 0 or offset+count > ref['image_bytes']:
            raise ValueError('Read exceeds the GSI')
        blocks.update(range(offset//BS, (offset+count+BS-1)//BS))
    mappings = re.findall(r'^M1EVENT map=\S+ \S+ \S+ fe:01 (\d+) +(/\S+)$',events.read_text(),re.M)
    return dict(image_sha256=ref['image_sha256'], block_size=BS, read_ranges=list(contiguous(blocks)),
                mapped_inodes={path:int(ino) for ino,path in mappings})


def build(image, inputs, out, contexts=False):
    from dissect.extfs import ExtFS

    ref = json.loads(REFERENCE.read_text())
    blocks = set()
    with image.open('rb') as src:
        if hashlib.file_digest(src,'sha256').hexdigest() != ref['image_sha256']:
            raise ValueError('GSI identity mismatch')
        src.seek(0)
        fs = ExtFS(src)
        if inputs['image_sha256'] != ref['image_sha256'] or inputs['block_size'] != BS:
            raise ValueError('Unexpected seed input identity')
        for start,count in inputs['read_ranges']:
            if start < 0 or count <= 0 or (start+count)*BS > ref['image_bytes']:
                raise ValueError('Read exceeds the GSI')
            blocks.update(range(start,start+count))
        paths = inputs['mapped_inodes']
        if fs.block_size != BS or '/system/bin/init' not in paths:
            raise ValueError('Missing GSI mappings or unexpected filesystem geometry')
        extra = []
        if contexts:
            for directory in ('/system/etc/selinux', '/system/system_ext/etc/selinux', '/system/product/etc/selinux'):
                for node in fs.get(directory).iterdir():
                    if node.filename.endswith('_contexts'):
                        extra.append(directory+'/'+node.filename)
        for path,ino in paths.items():
            node = fs.get(path)
            if node.inum != ino:
                raise ValueError('Mapped inode mismatch for '+path)
        for path in [*paths,*extra]:
            node = fs.get(path)
            for first,count in node.dataruns():
                if first is not None:
                    blocks.update(range(first, first+count))
        hashes = set(hash_blocks(blocks,ref['hashtree']['image_bytes']//BS))
        blocks.update(hashes)
        out.mkdir(exist_ok=False)
        rows = []
        with (out/'blocks.bin').open('xb') as dst:
            for start,count in contiguous(blocks):
                rows.append(f'{start} {count}')
                src.seek(start*BS)
                data = src.read(count*BS)
                if len(data) != count*BS:
                    raise ValueError('Short GSI extent')
                dst.write(data)
    (out/'ranges.txt').write_text('\n'.join(rows)+'\n', encoding='ascii', newline='\n')
    report = dict(gsi_sha256=ref['image_sha256'], block_size=BS, blocks=len(blocks), ranges=len(rows),
                  mappings=paths, context_files=extra, blocks_sha256=hashlib.sha256((out/'blocks.bin').read_bytes()).hexdigest(),
                  ranges_sha256=hashlib.sha256((out/'ranges.txt').read_bytes()).hexdigest())
    (out/'seed.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('image','output'):
        p.add_argument('--'+arg, required=True, type=Path)
    p.add_argument('--inputs',type=Path,help='Archived read ranges and mapped inodes')
    p.add_argument('--reads',type=Path)
    p.add_argument('--events',type=Path)
    p.add_argument('--contexts', action='store_true', help='Include original platform, system_ext and product context files')
    a = p.parse_args()
    if a.inputs and not (a.reads or a.events):
        inputs = json.loads(a.inputs.read_text())
    elif not a.inputs and a.reads and a.events:
        inputs = capture_inputs(a.reads,a.events)
    else:
        p.error('Choose archived inputs or a pair of live read and event captures')
    build(a.image,inputs,a.output,a.contexts)
