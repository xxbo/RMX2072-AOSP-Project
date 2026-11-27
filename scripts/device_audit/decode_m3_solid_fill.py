"""Verify the native SSPP bypass and cleanup, never physical image quality."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from decode_m3_kms_snapshot import extract, register_banks, dsc_from_regs


def route_checks(banks, normal):
    return dict(
        single_dsc_route=banks['ctl_0'][0xe8] == 1 and banks['ctl_0'][0xf4] == 2
            and banks['ctl_0'][0xe4] == 0 and banks['dsc_input_mux'][0] == 0
            and banks['intf_1'][0x25c] & 15 == 0,
        unchanged_dsc=banks['dsc_0'][0] == 0 and
            dsc_from_regs(banks['dsc_0']) == dsc_from_regs(normal['dsc_0']),
        unchanged_packets=all(banks['dsi0_ctrl'][o] == normal['dsi0_ctrl'][o]
            for o in (0x3c, 0x40, 0x54, 0x58, 0x2a4, 0x2a8)))


def phase_checks(banks, normal, color):
    r = banks['sspp_0']
    return dict(route_checks(banks, normal),
        solid_fill_bit=bool(r[0x30] & (1 << 22)),
        constant_color=r[0x3c] == color,
        no_source_addresses=all(r[o] == 0 for o in (0x14, 0x18, 0x1c, 0x20)),
        no_source_strides=r[0x24] == 0 and r[0x28] == 0,
        full_frame_source=r[0] == (2400 << 16 | 1080),
        full_frame_destination=r[0x0c] == (2400 << 16 | 1080))


def framebuffer_mapping(fb, identity):
    blocks = [b for b in re.split(r'(?=^user fb:)', fb, flags=re.M)
              if re.search(r'ID:'+str(identity)+r'\)', b)]
    if len(blocks) != 1:
        raise ValueError('Cannot uniquely associate framebuffer '+str(identity))
    mapping = re.search(r'offset=(\d+) pitch=(\d+).*?'
        r'vmas: \[mdp_kms: vm=[0-9a-f]+, ([0-9a-f]+), mapped\]', blocks[0], re.S)
    if not mapping:
        raise ValueError('Cannot associate framebuffer mapping')
    return dict(id=int(identity), offset=int(mapping[1]), pitch=int(mapping[2]),
                iova=int(mapping[3], 16))


def fetch_matches(banks, mapping):
    r = banks['sspp_0']
    return (not (r[0x30] & (1 << 22)) and mapping['offset'] == 0
            and r[0x14] == mapping['iova'] and r[0x24] & 65535 == mapping['pitch'])


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
    mapping = framebuffer_mapping(fb, active[1])
    memory_line = re.findall(r'^DRMSOLID memory_color=red format=XRGB8888 '
        r'value=0x00ff0000 fb=(\d+) pitch=(\d+) size=(\d+) hold_seconds=8$', text, re.M)
    if len(memory_line) != 1:
        raise ValueError('Missing or duplicate memory-red probe metadata')
    memory_fb, pitch, size = map(int, memory_line[0])
    memory_mapping = framebuffer_mapping(fb, memory_fb)
    payload = extract(text, 'kms-memory-red')
    memory = register_banks(payload)
    phases['memory_red'] = dict(
        checks=dict(route_checks(memory, normal),
            normal_fetch=fetch_matches(memory, memory_mapping),
            matching_pitch=memory_mapping['pitch'] == pitch,
            sufficient_allocation=size >= pitch * 2400 and pitch >= 1080 * 4,
            full_frame_source=memory['sspp_0'][0] == (2400 << 16 | 1080),
            full_frame_destination=memory['sspp_0'][0x0c] == (2400 << 16 | 1080),
            same_fetch_format=all(memory['sspp_0'][o] == normal['sspp_0'][o]
                for o in (0x30, 0x34, 0x38)),
            separate_pattern_buffer=memory_fb != mapping['id']),
        framebuffer=memory_mapping,
        cpu_pixel_value='0x00ff0000',
        snapshot_bytes=len(payload.encode()), snapshot_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        content_scope='Probe writes RGB red using returned pitch; fetched pixels are not read back.')
    cleanup = dict(
        probe_finished='DRMTEST exit=0\n' in text and 'DRMSOLID failure=' not in text,
        probe_cleared='DRMSOLID cleanup=ok parameter=0\n' in text,
        parent_cleared='M3SOLID parent_cleanup=ok parameter=0\n' in text,
        normal_fetch_restored=fetch_matches(normal, mapping))
    passed = all(cleanup.values()) and all(all(x['checks'].values()) for x in phases.values())
    result = dict(boot_id=boot, source_sha256=hashlib.sha256(raw).hexdigest(),
        phases=phases, restored_framebuffer=mapping, cleanup=cleanup, bypass_checks_pass=passed,
        physical_acceptance='REQUIRES_SEPARATE_OPERATOR_OBSERVATION',
        scope='Native KMS only. Hardware colors bypass source addresses; compare hardware red with fetched red. Clean colors alone do not exclude content-dependent compression faults.')
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(bypass_checks_pass=passed, cleanup=cleanup,
        failed={n:[k for k,v in x['checks'].items() if not v] for n,x in phases.items()})))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
