"""Verify the native SSPP bypass and cleanup, never physical image quality."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from decode_m3_kms_snapshot import extract, register_banks, dsc_from_regs


def phase_checks(banks, normal, color):
    r = banks['sspp_0']
    return dict(
        solid_fill_bit=bool(r[0x30] & (1 << 22)),
        constant_color=r[0x3c] == color,
        no_source_addresses=all(r[o] == 0 for o in (0x14, 0x18, 0x1c, 0x20)),
        no_source_strides=r[0x24] == 0 and r[0x28] == 0,
        full_frame_source=r[0] == (2400 << 16 | 1080),
        full_frame_destination=r[0x0c] == (2400 << 16 | 1080),
        single_dsc_route=banks['ctl_0'][0xe8] == 1 and banks['ctl_0'][0xf4] == 2
            and banks['ctl_0'][0xe4] == 0 and banks['dsc_input_mux'][0] == 0
            and banks['intf_1'][0x25c] & 15 == 0,
        unchanged_dsc=banks['dsc_0'][0] == 0 and
            dsc_from_regs(banks['dsc_0']) == dsc_from_regs(normal['dsc_0']),
        unchanged_packets=all(banks['dsi0_ctrl'][o] == normal['dsi0_ctrl'][o]
            for o in (0x3c, 0x40, 0x54, 0x58, 0x2a4, 0x2a8)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    live = a.record/'live'
    inputs = json.loads((a.record/'inputs.json').read_text())
    boot = json.loads((live/'gsi-accepted.json').read_text())['identity'][2]
    raw = (live/'m3-display.txt').read_bytes()
    text = raw.decode().replace('\r\n', '\n')
    if (set(re.findall(r'^M3DISPLAY boot_id=(.+)$', text, re.M)) != {boot}
            or not inputs['boot'].get('solid_fill_test')
            or not inputs['ramdisk'].get('solid_fill_test')):
        raise ValueError('Not the matching explicit solid-fill boot')
    normal = register_banks(extract(text, 'kms'))
    phases = {}
    for name, color in (('red', 0xff0000ff), ('green', 0xff00ff00), ('blue', 0xffff0000)):
        payload = extract(text, 'kms-solid-'+name)
        banks = register_banks(payload)
        phases[name] = dict(checks=phase_checks(banks, normal, color),
            snapshot_bytes=len(payload.encode()), snapshot_sha256=hashlib.sha256(payload.encode()).hexdigest(),
            sspp0={hex(o):hex(banks['sspp_0'][o]) for o in
                   (0, 0xc, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28, 0x30, 0x34, 0x38, 0x3c)})
    fb = extract(text, 'fb')
    state = extract(text, 'state')
    active = re.search(r'plane\[41\]:.*?\n\s+fb=(\d+)\b', state, re.S)
    if not active:
        raise ValueError('Cannot associate restored plane 41')
    mapping = re.search(r'ID:'+active[1]+r'\).*?offset=(\d+) pitch=(\d+).*?'
        r'vmas: \[mdp_kms: vm=[0-9a-f]+, ([0-9a-f]+), mapped\]', fb, re.S)
    if not mapping:
        raise ValueError('Cannot associate restored framebuffer mapping')
    cleanup = dict(
        probe_finished='DRMTEST exit=0\n' in text and 'DRMSOLID failure=' not in text,
        probe_cleared='DRMSOLID cleanup=ok parameter=0\n' in text,
        parent_cleared='M3SOLID parent_cleanup=ok parameter=0\n' in text,
        normal_fetch_restored=not (normal['sspp_0'][0x30] & (1 << 22)) and
            normal['sspp_0'][0x14] == int(mapping[3], 16) and int(mapping[1]) == 0 and
            normal['sspp_0'][0x24] & 65535 == int(mapping[2]))
    passed = all(cleanup.values()) and all(all(x['checks'].values()) for x in phases.values())
    result = dict(boot_id=boot, source_sha256=hashlib.sha256(raw).hexdigest(),
        phases=phases, cleanup=cleanup, bypass_checks_pass=passed,
        physical_acceptance='REQUIRES_SEPARATE_OPERATOR_OBSERVATION',
        scope='Native KMS only. Verified solid pixels bypass source addresses; clean colors would not exclude content-dependent compression faults.')
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(bypass_checks_pass=passed, cleanup=cleanup,
        failed={n:[k for k,v in x['checks'].items() if not v] for n,x in phases.items()})))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
