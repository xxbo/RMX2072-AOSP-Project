"""Check the recorded single-DSC isolation; physical acceptance stays separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from decode_m3_kms_snapshot import extract, register_banks, route_from_regs, dsc_from_regs


def load(record):
    inputs = json.loads((record/'inputs.json').read_text())
    accepted = json.loads((record/'live/gsi-accepted.json').read_text())
    raw = (record/'live/m3-display.txt').read_bytes()
    text = raw.decode().replace('\r\n', '\n')
    if set(re.findall(r'^M3DISPLAY boot_id=(.+)$', text, re.M)) != {accepted['identity'][2]}:
        raise ValueError('Native snapshot boot does not match accepted GSI')
    if 'DRMTEST exit=0\n' not in text:
        raise ValueError('Native test did not complete')
    return inputs, register_banks(extract(text, 'kms')), accepted['identity'][2], hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    old, before, old_boot, old_hash = load(a.baseline)
    new, after, new_boot, new_hash = load(a.candidate)
    route = route_from_regs(after)
    packet_offsets = (0x3c, 0x40, 0x54, 0x58, 0x2a4, 0x2a8)
    def reported_rates(record):
        return sorted(set(re.findall(r'Set clk rates: pclk=(\d+), byteclk=(\d+)',
                          (record/'live/m3-display.txt').read_text())))
    old_rates, new_rates = reported_rates(a.baseline), reported_rates(a.candidate)
    checks = {
        'different_boot': old_boot != new_boot,
        'explicit_single_dsc_request': new['boot'].get('single_dsc_test') is True and
            'msm.rmx2072_single_dsc=1' in new['boot']['cmdline'].split(),
        'unchanged_super_and_seeds': old['candidate'] == new['candidate'] and old['scratch'] == new['scratch'],
        'unchanged_dtb_dtbo_init': all(old['boot'][k] == new['boot'][k]
            for k in ('dtbo_sha256', 'dtb_bundle_sha256', 'first_stage_init_sha256')),
        'unchanged_pattern': old['ramdisk']['pattern_rgb_sha256'] == new['ramdisk']['pattern_rgb_sha256'],
        'baseline_ctl0_dual_dsc': before['ctl_0'][0xe8] == 3,
        'candidate_ctl0_single_dsc': after['ctl_0'][0xe8] == 1,
        'candidate_ctl0_intf1_only': after['ctl_0'][0xf4] == 2,
        'candidate_no_generic_merge_enabled': after['ctl_0'][0xe4] == 0,
        'candidate_dsc0_input_pp0': route['dsc_input_mux'] is not None and route['dsc_input_mux'][0] == 0,
        'candidate_intf1_input_pp0': after['intf_1'][0x25c] & 15 == 0,
        'candidate_dsc0_no_split_or_multiplex': after['dsc_0'][0] == 0,
        'unchanged_dsc_pps_fields': dsc_from_regs(before['dsc_0']) == dsc_from_regs(after['dsc_0']),
        'unchanged_dsi_packets': all(before['dsi0_ctrl'][k] == after['dsi0_ctrl'][k] for k in packet_offsets),
        'unchanged_reported_dsi_rates': bool(old_rates) and old_rates == new_rates,
        'native_state_uses_sspp0': 'sspp[0]=sspp_0' in extract((a.candidate/'live/m3-display.txt').read_text(), 'state'),
    }
    result = dict(baseline_boot=old_boot, candidate_boot=new_boot,
        source_sha256=dict(baseline=old_hash, candidate=new_hash), checks=checks,
        isolation_checks_pass=all(checks.values()), route=route,
        reported_dsi_rates=dict(baseline=old_rates, candidate=new_rates),
        scope='Native after-flips CTL0/DSC0/INTF1 route comparison. Unused banks may be stale. Not Android runtime DPU or panel decoder readback.',
        physical_acceptance='REQUIRES_SEPARATE_OPERATOR_OBSERVATION')
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(isolation_checks_pass=result['isolation_checks_pass'],
                         failed=[k for k,v in checks.items() if not v])))
    if not result['isolation_checks_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
