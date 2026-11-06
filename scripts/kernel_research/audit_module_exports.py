#!/usr/bin/env python3
"""Compare AArch64 ELF module imports with an explicit full-build Module.symvers.

This is an export-presence audit, not CRC, signature, KMI-policy or load certification.
"""
import argparse
import hashlib
import json
import pathlib
import struct


def imports(data):
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('expected little-endian AArch64 ELF64 module')
    offset = struct.unpack_from('<Q', data, 40)[0]
    entry_size, count = struct.unpack_from('<HH', data, 58)
    if entry_size != 64 or offset+entry_size*count > len(data):
        raise ValueError('invalid or unsupported ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset+i*entry_size) for i in range(count)]
    result = {}
    for section in sections:
        if section[1] != 2:
            continue
        start, size, link, symbol_size = section[4], section[5], section[6], section[9]
        if symbol_size != 24 or start+size > len(data):
            raise ValueError('invalid ELF symbol table')
        strings = sections[link]
        names = data[strings[4]:strings[4]+strings[5]]
        for pos in range(start, start+size, symbol_size):
            name, info, other, index, value, length = struct.unpack_from('<IBBHQQ', data, pos)
            if index == 0 and info >> 4 in (1, 2):
                end = names.index(b'\0', name)
                symbol = names[name:end].decode('ascii')
                result[symbol] = 'weak' if info >> 4 == 2 else 'global'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--module', required=True, type=pathlib.Path)
    p.add_argument('--symvers', required=True, type=pathlib.Path)
    p.add_argument('--out', required=True, type=pathlib.Path)
    a = p.parse_args()
    symbols = imports(a.module.read_bytes())
    exports = {}
    for line in a.symvers.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 4:
            exports[fields[1]] = dict(crc=fields[0], provider=fields[2], export=fields[3], namespace=fields[4] if len(fields)>4 else '')
    if not exports or not symbols:
        raise ValueError('empty export or import table')
    missing = sorted(s for s, binding in symbols.items() if s not in exports and binding != 'weak')
    report = dict(module_sha256=hashlib.sha256(a.module.read_bytes()).hexdigest(),
                  symvers_sha256=hashlib.sha256(a.symvers.read_bytes()).hexdigest(),
                  imports={s: dict(binding=b, export=exports.get(s)) for s,b in sorted(symbols.items())},
                  missing_strong_exports=missing,
                  qualification='Export presence only; CRCs, signatures, KMI policy and device loading not verified.')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(import_count=len(symbols), missing_strong_exports=missing)))
    if missing:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
