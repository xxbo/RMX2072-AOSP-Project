"""Compare original PHY timing against trial 66; physical acceptance is separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from compare_m3_stock_dsc import compare as compare_dsc, load_capture

PANEL_SHA256 = '219f47d58006b129d9f46628389c161283debc5e04892e88ad6ff02a12074372'
BASELINE = bytes.fromhex('0017060721200606040204001616')


def compare(baseline, record, reference, panel_source, pause_record=None):
    panel_raw = panel_source.read_bytes()
    panel_bytes = panel_raw.replace(b'\r\n', b'\n')
    if hashlib.sha256(panel_bytes).hexdigest() != PANEL_SHA256:
        raise ValueError('Original panel source does not match the pinned file')
    tables = re.findall(r'qcom,mdss-dsi-panel-phy-timings\s*=\s*\[([^]]+)\]', panel_bytes.decode())
    tables = {bytes.fromhex(t) for t in tables}
    if len(tables) != 1 or len(next(iter(tables))) != 14:
        raise ValueError('Ambiguous or incomplete original timing table')
    expected = next(iter(tables))
    # Reuse DSC/clock/route/fixed-input checks. Unlike trial 66, both inputs
    # already have original DSC; remove only its old-DSC experiment predicate.
    result = compare_dsc(baseline, record, reference, pause_record)
    checks = result['checks']
    del checks['baseline_has_no_stock_dsc']
    old, new = [json.loads((r / 'inputs.json').read_text(encoding='utf-8')) for r in (baseline, record)]
    previous, current = load_capture(baseline), load_capture(record, pause_record)
    values = [[c['banks']['dsi0_phy'][0xb4 + 4 * i] for i in range(14)] for c in (previous, current)]
    host = [c['banks']['dsi0_ctrl'][0xc0] for c in (previous, current)]
    entry = re.findall(r'RMXPHY timing stage=enable-entry bytes=([0-9a-f]{28})\b', current['acm'])
    programmed = re.findall(r'RMXPHY timing stage=after-program bytes=([0-9a-f]{28})\b', current['acm'])
    requests = re.findall(r'RMXPHY stock-timing bit=(\d+) clk_trail=(\d+) clk_pre=(\d+) clk_post=(\d+)', current['acm'])
    changed = [i for i in range(14) if values[0][i] != values[1][i]]
    checks.update(
        baseline_original_dsc=old['boot'].get('stock_dsc_test') is True,
        baseline_default_phy=not old['boot'].get('stock_phy_test', False),
        explicit_stock_phy=new['boot'].get('stock_phy_test') is True and
            'msm.rmx2072_stock_phy=1' in new['boot']['cmdline'].split(),
        expected_baseline_phy=values[0] == list(BASELINE),
        all_fourteen_phy_values_match_original=values[1] == list(expected),
        only_three_phy_fields_changed=changed == [3, 12, 13],
        baseline_host_pre_post=host[0] == 0x1616,
        host_uses_original_pre_post=host[1] == expected[12] | (expected[13] << 8),
        entry_timing_recorded=bool(entry),
        programmed_timing_matches=bool(programmed) and set(programmed) == {expected.hex()},
        timing_requests_match=bool(requests) and set(requests) == {('660000000', '5', '20', '21')},
        no_timing_rejection='RMXPHY stock-timing rejected' not in current['acm'],
    )
    result.update(all_setup_checks_pass=all(checks.values()),
        original_panel_lf_sha256=PANEL_SHA256,
        original_panel_raw_sha256=hashlib.sha256(panel_raw).hexdigest(), original_phy_hex=expected.hex(),
        baseline_phy_values=values[0], candidate_phy_values=values[1], changed_timing_indices=changed,
        baseline_host_clkout=hex(host[0]), candidate_host_clkout=hex(host[1]),
        entry_timing_hex=entry, programmed_timing_hex=programmed, requests=requests,
        scope='Native PHY/host timing, encoder, PPS, CCF and fixed inputs. Entry is not presumed untouched bootloader state. Physical output requires operator observation.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'record', 'reference', 'panel-source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--pause-record', type=Path,
                   help='Published digest manifest for an interrupted candidate; does not grant GSI acceptance')
    a = p.parse_args()
    result = compare(a.baseline, a.record, a.reference, a.panel_source, a.pause_record)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('boot_id', 'all_setup_checks_pass', 'checks')}, indent=2))
    if not result['all_setup_checks_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
