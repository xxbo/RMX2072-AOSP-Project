"""List F.20 EROFS firmware directly from the one local recovery set.

No handset access, image copy or decompression. The metadata/configuration
reader supports the flat/inline EROFS layout used by this measured F.20 image;
other layouts fail closed. On-disk structures: Linux v6.18 fs/erofs/erofs_fs.h.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import stat
import struct

from dissect.util.stream import MappingStream
from check_super import PREFIX, prefix_checks
from rehearse_super_layout import read_metadata


class DirectoryReader:
    def __init__(self, stream, size):
        self.stream, self.size = stream, size
        sb = self.read(1024, 128)
        if struct.unpack_from('<I', sb)[0] != 0xe0f5e1e2 or sb[12] != 12:
            raise ValueError('Expected the measured F.20 4 KiB EROFS vendor')
        self.root = struct.unpack_from('<H', sb, 14)[0]
        self.meta = struct.unpack_from('<I', sb, 40)[0] * 4096
        # This reader does not implement 48-bit IDs, metabox or external devices.
        if (struct.unpack_from('<I', sb, 80)[0] & ~1
                or struct.unpack_from('<H', sb, 86)[0] or sb[90]):
            raise ValueError('External devices or alternative directory block size unsupported')

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.size:
            raise ValueError('EROFS read exceeds the logical vendor')
        self.stream.seek(offset)
        data = self.stream.read(size)
        if len(data) != size:
            raise ValueError('Short EROFS read')
        return data

    def inode(self, nid):
        offset = self.meta + nid * 32
        raw = self.read(offset, 64)
        fmt, xattrs, mode = struct.unpack_from('<3H', raw)
        if fmt & ~0xf:
            raise ValueError('Unsupported EROFS inode format')
        return dict(offset=offset, inode_bytes=64 if fmt & 1 else 32,
                    layout=(fmt >> 1) & 7, mode=mode,
                    size=struct.unpack_from('<Q' if fmt & 1 else '<I', raw, 8)[0],
                    block=struct.unpack_from('<I', raw, 16)[0],
                    xattr_bytes=12 + (xattrs - 1) * 4 if xattrs else 0)

    def children(self, inode):
        if inode['layout'] not in (0, 2) or inode['size'] > 16 * 1024 * 1024:
            raise ValueError('Unsupported or oversized EROFS directory')
        for pos in range(0, inode['size'], 4096):
            length = min(4096, inode['size'] - pos)
            inline = inode['layout'] == 2 and length < 4096
            offset = (inode['offset'] + inode['inode_bytes'] + inode['xattr_bytes']
                      if inline else inode['block'] * 4096 + pos)
            block = self.read(offset, length)
            first = struct.unpack_from('<H', block, 8)[0]
            if not 12 <= first <= length or first % 12:
                raise ValueError('Invalid EROFS directory name offset')
            entries = list(struct.iter_unpack('<QHBB', block[:first]))
            for index, (nid, start, kind, reserved) in enumerate(entries):
                end = entries[index + 1][1] if index + 1 < len(entries) else length
                if not first <= start < end <= length or reserved:
                    raise ValueError('Invalid EROFS directory entry')
                name = block[start:end].rstrip(b'\0').decode('utf-8')
                if not name or len(name.encode()) > 255 or '/' in name or '\0' in name:
                    raise ValueError('Invalid EROFS filename')
                if name not in ('.', '..'):
                    yield name, nid

    def small_flat_file(self, node):
        if node['layout'] not in (0, 2) or node['size'] > 65536:
            raise ValueError('Only small uncompressed configuration files are supported')
        data = bytearray()
        for pos in range(0, node['size'], 4096):
            length = min(4096, node['size'] - pos)
            offset = (node['offset'] + node['inode_bytes'] + node['xattr_bytes']
                      if node['layout'] == 2 and length < 4096 else node['block'] * 4096 + pos)
            data.extend(self.read(offset, length))
        return bytes(data)

    def walk(self):
        pending, visited, count = [('', self.root)], set(), 0
        while pending:
            path, nid = pending.pop()
            node = self.inode(nid)
            count += 1
            if count > 100000:
                raise ValueError('Vendor inventory exceeded bound')
            yield path or '/', node
            if stat.S_ISDIR(node['mode']):
                if nid in visited:
                    raise ValueError('Directory cycle')
                visited.add(nid)
                pending.extend((path + '/' + name, child) for name, child in self.children(node))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stock', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--partition', choices=('vendor', 'odm', 'my_product', 'my_stock', 'product'), default='vendor')
    p.add_argument('--text-path', action='append', default=[],
                   help='Read one explicitly named small uncompressed rc/xml/conf file to the report')
    a = p.parse_args()
    if any(not path.startswith('/') or '..' in Path(path).parts
           or Path(path).suffix not in ('.rc', '.xml', '.conf', '.sh') for path in a.text_path):
        p.error('--text-path accepts only absolute configuration paths')
    acquisition = json.loads((a.stock / 'acquisition.json').read_text())
    if acquisition['identity'][:2] != ['RMX2072', 'RMX2072_11_F.20']:
        raise ValueError('Wrong stock acquisition')
    rows = acquisition['partitions']['super']['parts']
    with ExitStack() as stack:
        super_stream, total = MappingStream(), 0
        for index, row in enumerate(rows):
            file = a.stock / f'super-read-{index:02d}.bin'
            if file.stat().st_size != row['bytes']:
                raise ValueError('Truncated stock chunk')
            super_stream.add(total, row['bytes'], stack.enter_context(file.open('rb')))
            total += row['bytes']
        prefix = super_stream.read(PREFIX)
        prefix_checks(prefix)
        spans = read_metadata(prefix, 0)[-1][a.partition]
        vendor, size, checked = MappingStream(), 0, {0}
        for start, sectors in spans:
            vendor.add(size, sectors * 512, super_stream, start * 512)
            size += sectors * 512
            checked.update(range(start * 512 // (512 << 20),
                                 ((start + sectors) * 512 - 1) // (512 << 20) + 1))
        for index in checked:
            with (a.stock / f'super-read-{index:02d}.bin').open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != rows[index]['sha256']:
                    raise ValueError('Stock chunk digest mismatch')
        selected, text_files = [], {}
        reader = DirectoryReader(vendor, size)
        for path, node in reader.walk():
            if path in a.text_path:
                if not stat.S_ISREG(node['mode']):
                    raise ValueError('Configuration must be a regular file')
                data = reader.small_flat_file(node)
                text_files[path] = dict(sha256=hashlib.sha256(data).hexdigest(), text=data.decode('utf-8'))
            if (any(key in path for key in ('/firmware/', '/etc/wifi/', '/etc/vintf/'))
                    or any(key in path.lower() for key in ('fingerprint', 'goodix', 'gatekeeper', 'tfa98', 'aw8697'))):
                selected.append(dict(path=path, size=node['size'], mode=oct(node['mode']), layout=node['layout']))
        if set(text_files) != set(a.text_path):
            raise ValueError('Requested configuration missing')
    result = dict(source='Existing F.20 recovery chunks; no phone access or image copy',
                  super_sha256=acquisition['partitions']['super']['sha256'],
                  verified_local_chunks=sorted(checked), vendor_extents=spans,
                  partition=a.partition,
                  text_files=text_files,
                  inventory=sorted(selected, key=lambda x: x['path']),
                  scope='Metadata and explicitly requested plain configuration; compressed firmware not extracted or qualified')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Inventoried {len(selected)} matching entries; local chunks {sorted(checked)} verified.')


if __name__ == '__main__':
    main()
