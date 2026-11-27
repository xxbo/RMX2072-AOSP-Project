"""Decode complete F.20 software TX records; do not imply wire/decoder capture."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from decode_m3_kms_snapshot import dsc_from_pps
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
from import_rm19795_panel import generate, packets as source_packets, SOURCE_SHA


def packets(text):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    result = []
    for line in text.splitlines():
        if '[drm:dsi_message_tx]' not in line:
            continue
        match = re.search(r'^\[\s*(\d+\.\d+)\].*dsi-ctrl-0: ((?:[0-9A-F]{2} ?)+)\s*$', line)
        if not match:
            raise ValueError('Malformed TX line')
        raw = bytes.fromhex(match[2])
        if len(raw) < 7 or len(raw) != 7 + int.from_bytes(raw[5:7], 'big'):
            raise ValueError('Truncated/extra packet payload')
        result.append(dict(seconds=float(match[1]), type=raw[0], last=raw[1],
                           channel=raw[2], flags_raw=raw[3], wait_ms=raw[4],
                           payload_bytes=len(raw)-7, payload_hex=raw[7:].hex()))
    if not result:
        raise ValueError('No complete TX records')
    return result


def analyze(record, baseline, panel_source):
    receipt = json.loads((record / 'capture.json').read_text())
    if receipt['firmware'] != 'RMX2072_11_F.20' or receipt['restored_logger'] != receipt['original_logger']:
        raise ValueError('Unverified F.20/restoration')
    for name, expected in receipt['results'].items():
        data = (record / (name + '.txt')).read_bytes()
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Capture digest mismatch: ' + name)
    text = (record / 'display-log.txt').read_text(encoding='utf-8')
    marker = receipt['marker']
    if any(text.count(marker + suffix) != 1 for suffix in (' BEGIN', ' SLEEP power=0', ' WAKE power=2', ' END')):
        raise ValueError('Incomplete display cycle markers')
    wake = text.split(marker + ' SLEEP power=0', 1)[1].split(marker + ' WAKE power=2', 1)[0]
    modes = re.findall(r'hactive=\s*(\d+),vactive=\s*(\d+),fps=(\d+)', wake)
    if modes != [('1080', '2400', '60')]:
        raise ValueError('Actual 60 Hz wake mode not confirmed')
    rows = packets(wake)
    vendor = [r for r in rows if r['type'] == 0x39 and r['payload_hex'].startswith('9e')]
    standard = [r for r in rows if r['type'] == 0x0a]
    display_on = [r for r in rows if r['type'] == 0x05 and r['payload_hex'] == '29']
    if len(vendor) != 1 or len(standard) != 1 or len(display_on) != 1:
        raise ValueError('Expected unique vendor PPS, standard PPS and display-on')
    v, s, on = vendor[0], standard[0], display_on[0]
    if v['payload_bytes'] != 89 or s['payload_bytes'] != 128 or not v['seconds'] < s['seconds'] < on['seconds']:
        raise ValueError('Incomplete or out-of-order PPS')
    vb, sb = bytes.fromhex(v['payload_hex'])[1:], bytes.fromhex(s['payload_hex'])
    vc, sc = dsc_from_pps(vb + bytes(40)), dsc_from_pps(sb)
    raw_source = panel_source.read_bytes()
    generate(raw_source)  # Enforces the pinned official source digest.
    source_text = re.sub(r'/\*.*?\*/|//[^\n]*', '', raw_source.decode(), flags=re.S)
    timing = source_text.split('timing@0', 1)[1].split('timing@1', 1)[0]
    command_bytes = bytes.fromhex(re.search(r'qcom,mdss-dsi-on-command\s*=\s*\[([^]]+)\]', timing)[1])
    source_on = source_packets(command_bytes)
    runtime_on = rows[:rows.index(s)]
    actual_on = [(r['type'], r['wait_ms'], bytes.fromhex(r['payload_hex'])) for r in runtime_on]
    prior = json.loads(baseline.read_text())
    return dict(firmware=receipt['firmware'], kernel=receipt['kernel'], boot_id=receipt['boot_id'],
        capture=receipt, actual_mode=[1080, 2400, 60], wake_packets=rows,
        vendor_pps_hex=vb.hex(), standard_pps_hex=sb.hex(),
        standard_after_vendor_ms=round((s['seconds']-v['seconds'])*1000, 3),
        standard_before_display_on_ms=round((on['seconds']-s['seconds'])*1000, 3),
        official_panel_source_sha256=SOURCE_SHA, on_command_count=len(runtime_on),
        on_types_payloads_delays_match_project=actual_on == source_on,
        on_lp_and_last_flags=all(r['flags_raw'] == 10 and r['last'] == 1 and r['channel'] == 0 for r in runtime_on),
        differing_pps_offsets=[i for i in range(88) if vb[i] != sb[i]],
        field_differences={k:dict(vendor=vc[k], standard=sc[k]) for k in vc if vc[k] != sc[k]},
        trial68_matches_vendor=prior['original_pps_hex'] == vb.hex(),
        trial68_matches_standard=prior['native_dsc_parameters'] == sc,
        trial68_baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        standard_reserved_tail_zero=sb[88:] == bytes(40),
        host_eot_runtime='UNAVAILABLE: debugfs, devmem, kprobes and function tracer disabled in stock config',
        physical_result='No candidate tested by this capture',
        scope='Actual F.20 driver TX log at 60 Hz, not wire capture or DDIC readback. ERROR is the logger severity, not evidence that these sends failed. Static vendor PPS is not the final runtime PPS. No full partition readback.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('record', 'baseline', 'panel-source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    result = analyze(a.record, a.baseline, a.panel_source)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('capture','wake_packets','vendor_pps_hex','standard_pps_hex')}, indent=2))


if __name__ == '__main__':
    main()
