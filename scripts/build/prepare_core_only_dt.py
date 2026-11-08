#!/usr/bin/env python3
"""Derive a diagnostic-only core DT from the pinned project upstream DTB.

Requires maxcpus=1 cpuidle.off=1 console=ttynull at packaging time. No USB,
storage, watchdog, frequency scaling or peripheral functionality is claimed.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'device_audit'))
from inspect_boot_dt import fdt

SOURCE = '118bb1e3476de516b14dd8336e52ab433934129a66e3ebc061e101f993d0c542'
CORE_COMPATIBLES = {'arm,gic-v3', 'arm,armv8-timer', 'arm,psci-1.0'}
CPU_DEPENDENCIES = ('clocks', 'power-domains', 'power-domain-names', 'qcom,freq-domain',
                    'operating-points-v2', 'interconnects')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    p.add_argument('--libfdt', help='Native library path, or default system libfdt')
    a = p.parse_args()
    data = a.input.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE:
        raise ValueError('Core profile requires the exact pinned project DTB')
    nodes = fdt(data, ('**',))['matching_nodes']
    library_name = a.libfdt or ctypes.util.find_library('fdt')
    if not library_name:
        raise ValueError('Native libfdt unavailable')
    if pathlib.Path(library_name).exists():
        library_name = str(pathlib.Path(library_name).resolve())
    library = ctypes.CDLL(library_name)
    library.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_path_offset.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    library.fdt_setprop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int]
    library.fdt_delprop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    library.fdt_pack.argtypes = [ctypes.c_void_p]
    buffer = ctypes.create_string_buffer(2*1024*1024)
    if library.fdt_open_into(ctypes.create_string_buffer(data), buffer, len(buffer)):
        raise ValueError('libfdt could not open input')
    def node_offset(path):
        result = library.fdt_path_offset(buffer, (path or '/').encode())
        if result < 0:
            raise ValueError('Lost node path: '+path)
        return result
    disabled, removed, preserved = [], {}, []
    for node in nodes:
        path, props = node['path'], node['properties']
        if path.startswith('/cpus/cpu@'):
            for key in CPU_DEPENDENCIES:
                if key in props:
                    if library.fdt_delprop(buffer, node_offset(path), key.encode()):
                        raise ValueError('Failed removing CPU dependency: '+path+'/'+key)
                    removed.setdefault(path, []).append(key)
        if path == '/chosen' and 'stdout-path' in props:
            if library.fdt_delprop(buffer, node_offset(path), b'stdout-path'):
                raise ValueError('Could not remove console selection')
        compatible = set(props.get('compatible', []))
        if (path in ('', '/soc@0', '/soc') or path.startswith('/cpus/') or
                path.startswith('/reserved-memory/') or not compatible):
            continue
        if compatible & CORE_COMPATIBLES:
            preserved.append(path)
            continue
        if library.fdt_setprop(buffer, node_offset(path), b'status', b'disabled\0', 9):
            raise ValueError('Could not disable peripheral: '+path)
        disabled.append(path)
    marker = b'core-only\0'
    if library.fdt_setprop(buffer, 0, b'rmx2072,diagnostic-profile', marker, len(marker)):
        raise ValueError('Could not mark core profile')
    if library.fdt_pack(buffer):
        raise ValueError('Could not pack core DT')
    result = buffer.raw[:int.from_bytes(buffer.raw[4:8], 'big')]
    after = {n['path']: n['properties'] for n in fdt(result, ('**',))['matching_nodes']}
    if not all(after[path].get('status') == ['disabled'] for path in disabled):
        raise ValueError('Peripheral disable validation failed')
    for node in nodes:
        if node['path'].startswith('/reserved-memory/') and after[node['path']] != node['properties']:
            raise ValueError('Reserved-memory properties changed')
    if set(after['']['rmx2072,diagnostic-profile']) != {'core-only'}:
        raise ValueError('Core marker missing')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(result)
    report = dict(scope='Core handoff isolation only; no hardware-support claim', input_sha256=SOURCE,
                  output_sha256=hashlib.sha256(result).hexdigest(), size_bytes=len(result),
                  disabled_nodes=disabled, preserved_core_nodes=preserved, removed_cpu_dependencies=removed,
                  required_cmdline=['maxcpus=1', 'cpuidle.off=1', 'console=ttynull'],
                  status='prepared-not-device-tested')
    a.output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(output_sha256=report['output_sha256'], disabled_nodes=len(disabled),
                          removed_cpu_nodes=len(removed), preserved_core_nodes=preserved)))


if __name__ == '__main__':
    main()
