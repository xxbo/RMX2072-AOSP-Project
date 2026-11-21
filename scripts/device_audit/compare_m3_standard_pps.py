"""Validate standard PPS isolation against trial 68; never infer physical pass."""
import argparse
import json
from pathlib import Path
import re

from compare_m3_stock_dsc import compare as compare_dsc, load_capture
from decode_m3_first_frame import decode
from decode_m3_panel_readback import transactions
from decode_m3_kms_snapshot import dsc_from_regs


def standard_packets(text):
    rows = []
    current = None
    for line in text.splitlines():
        m = re.search(r'RMXPPS standard-transfer ret=(-?\d+) payload=(\d+)', line)
        if m:
            current = dict(returned=int(m[1]), expected=int(m[2]), data=bytearray())
            rows.append(current)
        elif 'RMXPPS standard-transfer ' in line:
            raise ValueError('Malformed standard PPS transfer record')
        m = re.search(r'RMXPPS standard-tx offset=(\d+) bytes=([0-9a-f]+)', line)
        if not m:
            if 'RMXPPS standard-tx ' in line:
                raise ValueError('Malformed standard PPS record')
            continue
        data = bytes.fromhex(m[2])
        if current is None or int(m[1]) != len(current['data']) or not 0 < len(data) <= 32:
            raise ValueError('Missing, duplicated or out-of-order standard PPS chunk')
        current['data'].extend(data)
    if not rows or any(r['returned'] < 128 or r['expected'] != 128 or len(r['data']) != 128 for r in rows):
        raise ValueError('Incomplete or failed standard PPS transfer')
    return rows


def compare(baseline, record, reference):
    result = compare_dsc(baseline, record, reference)
    checks = result['checks']
    del checks['baseline_has_no_stock_dsc']
    old, new = [json.loads((p / 'inputs.json').read_text(encoding='utf-8')) for p in (baseline, record)]
    previous, current = load_capture(baseline), load_capture(record)
    tx, _ = transactions(current['acm'])
    standard = standard_packets(current['acm'])
    expected = bytes.fromhex(result['original_pps_hex']) + bytes(40)
    trace = decode(current['snapshot'], current['boot'])
    old_trace = decode(previous['snapshot'], previous['boot'])
    standard_events = [r for r in trace.get('transactions', []) if r['type'] == 0x0a]
    vendor_events = [r for r in trace.get('transactions', []) if r['type'] == 0x39 and r['opcode'] == 0x9e]
    on_events = [r for r in trace.get('transactions', []) if r['type'] == 0x05 and r['opcode'] == 0x29]
    standard_begin = [s for s in trace.get('steps', []) if s['step'] == 'dcs-begin' and s['b'] >> 32 == 0x0a]
    old_types = [(r['type'], r['opcode']) for r in old_trace.get('transactions', [])]
    new_types = [(r['type'], r['opcode']) for r in trace.get('transactions', []) if r['type'] != 0x0a]
    checks.update(
        prior_standard_absent=not old['boot'].get('standard_pps_test', False) and 'RMXPPS standard-transfer' not in previous['acm'],
        standard_opt_in=new['boot'].get('standard_pps_test') is True and new['boot']['cmdline'] == old['boot']['cmdline'] + ' panel_samsung_rm19795.pps=1',
        same_old_flags=all(old['boot'].get(k) == new['boot'].get(k) for k in ('first_frame_trace', 'stock_phy_test', 'stock_dsc_test', 'stock_linkclock_test')),
        standard_same_encoder_and_vendor=all(bytes(r['data']) == expected for r in standard),
        one_standard_per_vendor=len(standard) == len(tx),
        complete_first_frame_trace=trace['complete'] and old_trace['complete'],
        one_native_standard=len(standard_events) == len(vendor_events) == len(on_events) == 1,
        native_order=len(standard_events) == len(vendor_events) == len(on_events) == 1 and
            vendor_events[0]['end_ns'] < standard_events[0]['begin_ns'] < standard_events[0]['end_ns'] < on_events[0]['begin_ns'],
        native_standard_lp_and_length=len(standard_begin) == 1 and standard_begin[0]['c'] == 128 and (standard_begin[0]['d'] & 0xffffffff) == 2,
        only_standard_packet_added=old_types == new_types,
        same_eot=previous['banks']['dsi0_ctrl'][0xc8] == current['banks']['dsi0_ctrl'][0xc8],
        same_null_insertion=previous['banks']['dsi0_ctrl'][0x2b0] == current['banks']['dsi0_ctrl'][0x2b0],
        same_host_pre_post=previous['banks']['dsi0_ctrl'][0xc0] == current['banks']['dsi0_ctrl'][0xc0],
        same_phy=all(previous['banks']['dsi0_phy'][0xb4 + 4*i] == current['banks']['dsi0_phy'][0xb4 + 4*i] for i in range(14)),
        same_native_encoder_parameters=dsc_from_regs(previous['banks']['dsc_0']) == dsc_from_regs(current['banks']['dsc_0']),
    )
    for row in standard:
        row['hex'] = row.pop('data').hex()
    result.update(all_setup_checks_pass=all(checks.values()), standard_transmitted=standard,
        first_frame=dict(complete=trace['complete'], problems=trace['problems'], errors=trace.get('errors'),
                         standard_events=standard_events, standard_begin=standard_begin),
        eot_ctrl=hex(current['banks']['dsi0_ctrl'][0xc8]),
        physical_acceptance='REQUIRES_OPERATOR_OBSERVATION',
        scope='One added LP standard PPS generated from unchanged trial-68 DSC. Not stock final RC replication, not DDIC readback, not a physical pass.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'record', 'reference', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    result = compare(a.baseline, a.record, a.reference)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('boot_id','all_setup_checks_pass','checks')}, indent=2))
    if not result['all_setup_checks_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
