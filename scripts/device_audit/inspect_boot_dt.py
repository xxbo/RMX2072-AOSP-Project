#!/usr/bin/env python3
"""Read stock boot-v2/DTBO containers and report board selectors, without flashing."""
import argparse
import hashlib
import json
import pathlib
import struct


def u32(data, offset):
    return struct.unpack_from('>I', data, offset)[0]


def fdt(data):
    magic, size, off_struct, off_strings, _, _, _, _, len_strings, len_struct = struct.unpack_from('>10I', data)
    if magic != 0xd00dfeed or size > len(data):
        raise ValueError('invalid FDT header')
    if off_struct + len_struct > size or off_strings + len_strings > size:
        raise ValueError('FDT blocks exceed declared size')
    strings = data[off_strings:off_strings+len_strings]
    pos, end, stack, props = off_struct, off_struct+len_struct, [], {}
    while pos < end:
        token = u32(data, pos)
        pos += 4
        if token == 1:
            stop = data.index(b'\0', pos, end)
            stack.append(data[pos:stop].decode('ascii', errors='replace'))
            pos = (stop+4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>2I', data, pos)
            pos += 8
            if pos+length > end:
                raise ValueError('truncated FDT property')
            stop = strings.index(b'\0', nameoff)
            name = strings[nameoff:stop].decode('ascii')
            if len(stack) == 1 and name in ('model', 'compatible', 'qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id'):
                value = data[pos:pos+length]
                if name in ('model', 'compatible'):
                    props[name] = value.rstrip(b'\0').decode('ascii', errors='replace').split('\0')
                elif length % 4 == 0:
                    props[name] = list(struct.unpack('>'+str(length//4)+'I', value))
            pos = (pos+length+3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            return dict(size_bytes=size, sha256=hashlib.sha256(data[:size]).hexdigest(), root=props)
        else:
            raise ValueError('unknown FDT token')
    raise ValueError('missing FDT end token')


def inspect(path):
    data = path.read_bytes()
    result = dict(file=path.name, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), trees=[])
    if data[:8] == b'ANDROID!':
        kernel, ramdisk, second = (struct.unpack_from('<I', data, n)[0] for n in (8, 16, 24))
        page, version = (struct.unpack_from('<I', data, n)[0] for n in (36, 40))
        if version != 2 or page < 2048 or page & (page-1):
            raise ValueError('only boot header v2 with a valid page size is supported')
        recovery_size = struct.unpack_from('<I', data, 1632)[0]
        dt_size = struct.unpack_from('<I', data, 1648)[0]
        align = lambda n: (n+page-1)//page*page
        start = page+align(kernel)+align(ramdisk)+align(second)+align(recovery_size)
        end = start+dt_size
        if end > len(data):
            raise ValueError('DTB section exceeds boot container')
        result.update(container='boot-v2', dtb_offset=start, dtb_size=dt_size)
        pos = start
        while pos < end:
            if data[pos:pos+4] != b'\xd0\x0d\xfe\xed':
                if not any(data[pos:end]):
                    break
                raise ValueError('unexpected data between concatenated DTBs')
            entry = fdt(data[pos:end])
            result['trees'].append(dict(index=len(result['trees']), offset=pos, **entry))
            pos += entry['size_bytes']
    elif u32(data, 0) == 0xd7b7ab1e:
        _, total, header_size, entry_size, count, entries, page, version = struct.unpack_from('>8I', data)
        if total > len(data) or header_size < 32 or entry_size < 32 or entries+entry_size*count > total:
            raise ValueError('invalid DTBO table')
        result.update(container='dtbo', version=version, page_size=page)
        for i in range(count):
            size, offset, ident, rev, *custom = struct.unpack_from('>8I', data, entries+i*entry_size)
            if offset+size > total:
                raise ValueError('DTBO entry exceeds table')
            entry = fdt(data[offset:offset+size])
            result['trees'].append(dict(index=i, offset=offset, id=ident, rev=rev, custom=custom, **entry))
    else:
        raise ValueError('unsupported container')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('images', nargs='+', type=pathlib.Path)
    p.add_argument('--out', required=True, type=pathlib.Path)
    args = p.parse_args()
    report = [inspect(path) for path in args.images]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    for item in report:
        print(item['file'], item['container'], len(item['trees']), 'trees')


if __name__ == '__main__':
    main()
