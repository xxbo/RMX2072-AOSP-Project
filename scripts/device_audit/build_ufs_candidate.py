"""Build and validate one private UFS candidate directly in recovery-sized chunks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from check_super_chunks import CHUNK, SECTOR as UFS_SECTOR, SECTORS, chunks, stock_restore_xml, verify
from check_super import PREFIX, prefix_checks
from rehearse_super_layout import make_candidate, read_metadata, partition_hashes


class ChunkedImage:
    """Bounded random access without assembling another full raw image."""
    def __init__(self, paths, chunk_bytes, *, writable=False):
        self.paths = list(paths)
        self.chunk_bytes = chunk_bytes
        self.length = sum(p.stat().st_size for p in self.paths)
        if not self.paths or any(p.stat().st_size != chunk_bytes for p in self.paths[:-1]):
            raise ValueError('Incomplete image chunks')
        if not 0 < self.paths[-1].stat().st_size <= chunk_bytes:
            raise ValueError('Invalid last chunk')
        self.position = 0
        self.writable = writable

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError('Invalid seek mode')
        target = offset + (0 if whence == 0 else self.position if whence == 1 else self.length)
        if not 0 <= target <= self.length:
            raise ValueError('Seek outside image')
        self.position = target
        return target

    def read(self, count):
        if count < 0:
            raise ValueError('Specify a bounded read size')
        count = min(count, self.length - self.position)
        result = bytearray()
        while count:
            index, offset = divmod(self.position, self.chunk_bytes)
            size = min(count, self.chunk_bytes - offset)
            with self.paths[index].open('rb') as source:
                source.seek(offset)
                data = source.read(size)
            if len(data) != size:
                raise ValueError('Short chunk read')
            result.extend(data)
            self.position += size
            count -= size
        return bytes(result)

    def write(self, data):
        if not self.writable or self.position + len(data) > self.length:
            raise ValueError('Write outside writable candidate')
        done = 0
        while done < len(data):
            index, offset = divmod(self.position, self.chunk_bytes)
            size = min(len(data) - done, self.chunk_bytes - offset)
            with self.paths[index].open('r+b') as target:
                target.seek(offset)
                if target.write(data[done:done+size]) != size:
                    raise ValueError('Short candidate write')
            self.position += size
            done += size
        return done


def build(stock, system, vendor, profile, output):
    repo = Path(__file__).resolve().parents[2]
    if output.resolve().is_relative_to(repo):
        raise ValueError('Keep private images outside the repository')
    reference = json.loads((repo/'build/device/super-readonly-2026-11-10.json').read_text())
    expected = 'f7785aedd24616b251143cbcf6006612274b1cae9dac8dea1f634c5800c50532'
    original = verify(stock, expected)
    signed = json.loads((profile/'signed.json').read_text())
    for name, path in [('system', system), ('vendor', vendor)]:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != signed[name]['sha256'] or path.stat().st_size != signed[name]['bytes']:
            raise ValueError('Image differs from verified profile: ' + name)
    source = ChunkedImage([stock/name for name, _, _ in chunks()], CHUNK*UFS_SECTOR)
    prefix = source.read(PREFIX)
    if prefix_checks(prefix)['prefix_sha256'] != reference['prefix_sha256']:
        raise ValueError('Stock LP metadata differs from the recorded geometry')
    before = [partition_hashes(source, read_metadata(prefix, slot)[-1]) for slot in (0, 1)]
    for name, item in reference['linear_devices'].items():
        if before[0][name] != item['sha256']:
            raise ValueError('Stock logical partition differs: ' + name)
    sizes = {name: signed[name]['bytes'] for name in ('system', 'vendor')}
    new_prefix, targets, limit, total = make_candidate(prefix, sizes)
    output.mkdir(parents=True, exist_ok=False)
    for name, _, _ in chunks():
        shutil.copyfile(stock/name, output/name)
    target = ChunkedImage([output/name for name, _, _ in chunks()], CHUNK*UFS_SECTOR, writable=True)
    target.write(new_prefix)
    for name, path in [('vendor', vendor), ('system', system)]:
        with path.open('rb') as image:
            for start, sectors in targets[name]:
                target.seek(start*512)
                remaining = sectors*512
                while remaining:
                    data = image.read(min(remaining, 4*1024*1024))
                    if not data:
                        raise ValueError('Short candidate input')
                    target.write(data)
                    remaining -= len(data)
    target.seek(0)
    measured_prefix = target.read(PREFIX)
    if measured_prefix != new_prefix:
        raise ValueError('Candidate metadata write differs')
    after = [partition_hashes(target, read_metadata(new_prefix, slot)[-1]) for slot in (0, 1)]
    wanted = {**{n: h for n, h in before[0].items() if n != 'my_stock'},
              **{n: signed[n]['sha256'] for n in ('system', 'vendor')}}
    if after[0] != wanted or [n for n in before[1] if before[1][n] != after[1][n]] != ['system']:
        raise ValueError('Unexpected partition changes in candidate')
    full = hashlib.sha256()
    parts = []
    for name, _, _ in chunks():
        digest = hashlib.sha256()
        with (output/name).open('rb') as stream:
            while data := stream.read(4*1024*1024):
                digest.update(data)
                full.update(data)
        parts.append(digest.hexdigest())
    changed = [i for i, h in enumerate(parts) if h != original['parts'][i]['sha256']]
    root = ET.fromstring(stock_restore_xml())
    for row in list(root):
        if int(row.attrib['filename'][11:13]) not in changed:
            root.remove(row)
    (output/'candidate.xml').write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
    manifest = dict(bytes=SECTORS*UFS_SECTOR, sha256=full.hexdigest(), source_sha256=expected,
                    parts=parts, changed_chunks=changed, signed=signed, targets=targets,
                    prefix_sha256=hashlib.sha256(new_prefix).hexdigest(), headroom=limit-total,
                    partitions_before=before, partitions_after=after)
    (output/'candidate.json').write_text(json.dumps(manifest, indent=2)+'\n')
    layout = dict(signed_images=signed, candidate=dict(
        super_sha256=manifest['sha256'], metadata_prefix_sha256=manifest['prefix_sha256'],
        active_extents_in_512b_sectors=targets, group_headroom_bytes=limit-total))
    (output/'layout.json').write_text(json.dumps(layout, indent=2)+'\n')
    print(json.dumps(dict(sha256=manifest['sha256'], changed_chunks=changed, headroom=limit-total)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('stock', 'system', 'vendor', 'profile', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    build(**vars(parser.parse_args()))
