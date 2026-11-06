#!/usr/bin/env python3
"""Compare AArch64 ELF module imports with an explicit full-build Module.symvers.

CRC comparison is optional; signature, protected-export policy and loading remain separate.
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
    string_index = struct.unpack_from('<H', data, 62)[0]
    strings = sections[string_index]
    section_names = data[strings[4]:strings[4]+strings[5]]
    content = {}
    for section in sections:
        start = section[0]
        name = section_names[start:section_names.index(b'\0', start)].decode('ascii')
        content[name] = data[section[4]:section[4]+section[5]]
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
    versions = {}
    if '__version_ext_names' in content:
        names = content['__version_ext_names'].rstrip(b'\0').split(b'\0')
        crcs = content.get('__version_ext_crcs', b'')
        if len(crcs) != 4*len(names):
            raise ValueError('invalid extended modversion tables')
        versions = {name.decode('ascii'): crc for name, crc in zip(names, struct.unpack('<'+str(len(names))+'I', crcs))}
    elif '__versions' in content:
        table = content['__versions']
        if len(table) % 64:
            raise ValueError('invalid AArch64 modversion table')
        for pos in range(0, len(table), 64):
            crc = struct.unpack_from('<Q', table, pos)[0]
            name = table[pos+8:pos+64].split(b'\0', 1)[0].decode('ascii')
            versions[name] = crc
    modinfo = [item.decode('utf-8', errors='replace') for item in content.get('.modinfo', b'').split(b'\0') if item]
    return result, versions, modinfo


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--module', required=True, type=pathlib.Path)
    p.add_argument('--symvers', required=True, type=pathlib.Path)
    p.add_argument('--out', required=True, type=pathlib.Path)
    p.add_argument('--require-crcs', action='store_true', help='Fail for missing/mismatching strong import CRCs')
    p.add_argument('--kmi-list', type=pathlib.Path, help='Full distribution abi_symbollist.raw for a separate name audit')
    a = p.parse_args()
    symbols, versions, modinfo = imports(a.module.read_bytes())
    exports = {}
    for line in a.symvers.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 4:
            exports[fields[1]] = dict(crc=fields[0], provider=fields[2], export=fields[3], namespace=fields[4] if len(fields)>4 else '')
    if not exports or not symbols:
        raise ValueError('empty export or import table')
    missing = sorted(s for s, binding in symbols.items() if s not in exports and binding != 'weak')
    missing_crcs = sorted(s for s, binding in symbols.items() if binding != 'weak' and s not in versions)
    wrong_crcs = {s: dict(module=hex(crc), kernel=exports[s]['crc']) for s, crc in versions.items()
                  if s in exports and crc != int(exports[s]['crc'], 16)}
    report = dict(module_sha256=hashlib.sha256(a.module.read_bytes()).hexdigest(),
                  symvers_sha256=hashlib.sha256(a.symvers.read_bytes()).hexdigest(),
                  imports={s: dict(binding=b, export=exports.get(s)) for s,b in sorted(symbols.items())},
                  missing_strong_exports=missing,
                  modinfo=modinfo, version_entry_count=len(versions), missing_strong_import_crcs=missing_crcs,
                  mismatching_crcs=wrong_crcs,
                  qualification='Explicit symbol/CRC comparison only; signatures, protected-export policy and loading remain unverified.')
    if a.kmi_list:
        kmi = set(a.kmi_list.read_text().splitlines())
        report['kmi_list_sha256'] = hashlib.sha256(a.kmi_list.read_bytes()).hexdigest()
        report['imports_absent_from_kmi_names'] = sorted(set(symbols)-kmi)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(import_count=len(symbols), missing_strong_exports=missing,
                         version_entry_count=len(versions), missing_crc_count=len(missing_crcs), mismatching_crcs=wrong_crcs)))
    if missing or (a.require_crcs and (missing_crcs or wrong_crcs)):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
