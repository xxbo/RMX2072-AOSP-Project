"""Verify original DSC parameter isolation; physical acceptance stays separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from decode_m3_kms_snapshot import extract, register_banks, route_from_regs, dsc_from_regs
from decode_m3_panel_readback import transactions, transmitted_config


def load_capture(record):
    live = record / 'live'
    boot = json.loads((live / 'gsi-accepted.json').read_text())['identity'][2]
    raw = (live / 'm3-display.txt').read_bytes()
    snapshot = raw.decode('utf-8').replace('\r\n', '\n')
    if set(re.findall(r'^M3DISPLAY boot_id=(.+)$', snapshot, re.M)) != {boot}:
        raise ValueError('Snapshot/accepted boot mismatch')
    if 'DRMTEST exit=0\n' not in snapshot:
        raise ValueError('Native probe did not complete')
    return dict(boot=boot, raw=raw, snapshot=snapshot,
                banks=register_banks(extract(snapshot, 'kms')),
                acm=(live / 'acm.log').read_text(encoding='utf-8'))


def verify_pps(banks, acm, expected):
    tx, _ = transactions(acm)
    actual = dsc_from_regs(banks['dsc_0'])
    checks = dict(
        complete_original_pps_transmitted=bool(tx) and all(bytes(t['data']) == expected for t in tx),
        active_encoder_matches_original_pps=actual == transmitted_config(expected),
        original_rc_calculation_verified=bool(re.search(r'RMXDSC stock-pps bytes=88 match=1 ret=0\b', acm))
            and not re.search(r'RMXDSC stock-pps bytes=88 match=0', acm),
    )
    return checks, actual


def compare(baseline, record, reference):
    old, new = [json.loads((r / 'inputs.json').read_text(encoding='utf-8')) for r in (baseline, record)]
    previous, current = [load_capture(r) for r in (baseline, record)]
    expected = bytes.fromhex(json.loads(reference.read_text())['factory_pps_hex'])
    if len(expected) != 88:
        raise ValueError('Expected complete original DSC 1.1 payload')
    checks, parameters = verify_pps(current['banks'], current['acm'], expected)
    checks.update(
        baseline_has_no_stock_dsc=not old['boot'].get('stock_dsc_test', False),
        explicit_stock_dsc=new['boot'].get('stock_dsc_test') is True and
            'msm.rmx2072_stock_dsc=1' in new['boot']['cmdline'].split(),
        stock_clock_retained=old['boot'].get('stock_linkclock_test') is True and
            new['boot'].get('stock_linkclock_test') is True,
        same_super_and_verified_partitions=old['candidate'] == new['candidate'],
        same_scratch_seeds=old['scratch'] == new['scratch'],
        same_source_device_trees=old['boot']['device_tree_build']['outputs'] == new['boot']['device_tree_build']['outputs'],
    )
    for key in ('single_dsc_test', 'panel_readback_test', 'solid_fill_test'):
        checks['same_' + key] = old['boot'].get(key) == new['boot'].get(key)
    for key in ('display_probe_sha256', 'pattern_rgb_sha256', 'first_stage_init_sha256', 'witness_sha256'):
        checks['same_' + key] = old['ramdisk'][key] == new['ramdisk'][key]
    routes = [route_from_regs(c['banks']) for c in (previous, current)]
    def selected(r):
        return dict(ctl0=r['ctl']['ctl_0'], dsc0_input=r['dsc_input_mux'][0],
                    intf1=r['intf_mux']['intf_1'], pingpong0=r['pingpong']['pingpong_0'])
    checks['same_selected_route'] = selected(routes[0]) == selected(routes[1])
    checks['single_dsc_route'] = routes[1]['ctl']['ctl_0'] == dict(dsc_active=1, intf_active=2, merge_3d_active=0) and routes[1]['dsc_input_mux'][0] == 0
    for off in (0x54, 0x58, 0x2a4, 0x2a8):
        checks['same_dsi_packet_' + hex(off)] = previous['banks']['dsi0_ctrl'][off] == current['banks']['dsi0_ctrl'][off]
    expected_clocks = {'dsi0_pll_bit_clk': 660000000, 'dsi0_phy_pll_out_byteclk': 82500000,
                       'dsi0_phy_pll_out_dsiclk': 110000000, 'disp_cc_mdss_byte0_clk': 82500000,
                       'disp_cc_mdss_pclk0_clk': 110000000}
    clocks = {}
    for phase in ('after-modeset', 'after-flips'):
        rows = re.findall(r'DRMCLOCK phase=' + phase + r' clock=(\S+) field=clk_rate value=(\d+) truncated=0', current['snapshot'])
        if len(rows) != len(dict(rows)):
            raise ValueError('Duplicate clock sample')
        clocks[phase] = {key: int(value) for key, value in rows}
        for key, value in expected_clocks.items():
            checks[phase + '_' + key] = key in clocks[phase] and abs(clocks[phase][key] - value) <= 1000
    return dict(boot_id=current['boot'], baseline_boot_id=previous['boot'],
        checks=checks, all_setup_checks_pass=all(checks.values()),
        original_pps_hex=expected.hex(), native_dsc_parameters=parameters,
        clock_rates_hz=clocks, baseline_route=routes[0], candidate_route=routes[1],
        snapshot_sha256=hashlib.sha256(current['raw']).hexdigest(),
        acm_sha256=hashlib.sha256((record / 'live/acm.log').read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        physical_acceptance='REQUIRES_OPERATOR_OBSERVATION',
        scope='Pre-Android native encoder, host PPS and CCF evidence; not panel-internal readback or correct physical pixels.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'record', 'reference', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    result = compare(a.baseline, a.record, a.reference)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('boot_id', 'all_setup_checks_pass', 'checks')}, indent=2))
    if not result['all_setup_checks_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
