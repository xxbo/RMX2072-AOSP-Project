#!/usr/bin/env python3
"""Read stock boot-v2/DTBO containers and report board selectors, without flashing."""
import argparse
import hashlib
import json
import pathlib
import struct


def u32(data, offset):
    return struct.unpack_from('>I', data, offset)[0]


def fdt(data, compatible=()):
    magic, size, off_struct, off_strings, _, _, _, _, len_strings, len_struct = struct.unpack_from('>10I', data)
    if magic != 0xd00dfeed or size > len(data):
        raise ValueError('invalid FDT header')
    if off_struct + len_struct > size or off_strings + len_strings > size:
        raise ValueError('FDT blocks exceed declared size')
    strings = data[off_strings:off_strings+len_strings]
    pos, end, stack, props = off_struct, off_struct+len_struct, [], {}
    node_props, matches, fixups, symbols = [], [], {}, {}
    while pos < end:
        token = u32(data, pos)
        pos += 4
        if token == 1:
            stop = data.index(b'\0', pos, end)
            stack.append(data[pos:stop].decode('ascii', errors='replace'))
            node_props.append({})
            pos = (stop+4) & ~3
        elif token == 2:
            node = node_props.pop()
            if '**' in compatible or (compatible and ('*' in compatible or set(node.get('compatible', [])).intersection(compatible)) and 'compatible' in node):
                matches.append(dict(path='/'.join(stack), properties=node))
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>2I', data, pos)
            pos += 8
            if pos+length > end:
                raise ValueError('truncated FDT property')
            stop = strings.index(b'\0', nameoff)
            name = strings[nameoff:stop].decode('ascii')
            value = data[pos:pos+length]
            if compatible:
                if stack[-1] == '__fixups__':
                    fixups[name] = value.rstrip(b'\0').decode('ascii').split('\0')
                if stack[-1] == '__symbols__':
                    symbols[name] = value.rstrip(b'\0').decode('ascii')
                if name in ('compatible', 'status', 'qcom,clk-src') or (value and 33 <= value[0] < 127 and value.endswith(b'\0') and all(c == 0 or 32 <= c < 127 for c in value)):
                    node_props[-1][name] = value.rstrip(b'\0').decode('ascii', errors='replace').split('\0')
                elif length % 4 == 0:
                    node_props[-1][name] = list(struct.unpack('>'+str(length//4)+'I', value))
                else:
                    node_props[-1][name] = dict(hex=value.hex())
            if len(stack) == 1 and name in ('model', 'compatible', 'qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id', 'oplus,dtsi_no'):
                if name in ('model', 'compatible'):
                    props[name] = value.rstrip(b'\0').decode('ascii', errors='replace').split('\0')
                elif length % 4 == 0:
                    props[name] = list(struct.unpack('>'+str(length//4)+'I', value))
            pos = (pos+length+3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            result = dict(size_bytes=size, sha256=hashlib.sha256(data[:size]).hexdigest(), root=props)
            if compatible:
                result['matching_nodes'] = matches
                paths = tuple(m['path']+':' for m in matches)
                result['matching_overlay_fixups'] = {key: [v for v in values if v.startswith(paths)]
                    for key, values in fixups.items() if any(v.startswith(paths) for v in values)}
                result['matching_base_symbols'] = {key: value for key, value in symbols.items()
                    if value in {m['path'] for m in matches}}
                fragments = tuple('/'+m['path'].split('/')[1]+':target:' for m in matches if m['path'].startswith('/fragment@'))
                result['fragment_target_fixups'] = {key: [v for v in values if v.startswith(fragments)]
                    for key, values in fixups.items() if any(v.startswith(fragments) for v in values)}
            return result
        else:
            raise ValueError('unknown FDT token')
    raise ValueError('missing FDT end token')


def inspect(path, compatible=()):
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
            entry = fdt(data[pos:end], compatible)
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
            entry = fdt(data[offset:offset+size], compatible)
            result['trees'].append(dict(index=i, offset=offset, id=ident, rev=rev, custom=custom, **entry))
    else:
        raise ValueError('unsupported container')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('images', nargs='+', type=pathlib.Path)
    p.add_argument('--out', required=True, type=pathlib.Path)
    p.add_argument('--compatible', action='append', default=[], help='Include matching nodes and selected binding properties')
    p.add_argument('--index', type=int, help='Keep only this container entry in the report')
    args = p.parse_args()
    report = [inspect(path, args.compatible) for path in args.images]
    if args.index is not None:
        for item in report:
            item['trees'] = [tree for tree in item['trees'] if tree['index'] == args.index]
            if not item['trees']:
                p.error('selected index is absent from '+item['file'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    for item in report:
        print(item['file'], item['container'], len(item['trees']), 'trees')


if __name__ == '__main__':
    main()
