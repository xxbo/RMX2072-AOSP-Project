"""Verify a stock-clock isolation experiment without inferring screen success."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from decode_m3_kms_snapshot import extract, register_banks, route_from_regs, dsc_from_regs
from decode_m3_panel_readback import transactions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    inputs = [json.loads((r/'inputs.json').read_text(encoding='utf-8')) for r in (a.baseline,a.record)]
    old, new = inputs
    live = a.record/'live'
    boot = json.loads((live/'gsi-accepted.json').read_text())['identity'][2]
    raw = (live/'m3-display.txt').read_bytes()
    snapshot = raw.decode('utf-8').replace('\r\n','\n')
    if set(re.findall(r'^M3DISPLAY boot_id=(.+)$',snapshot,re.M)) != {boot}:
        raise ValueError('Snapshot/accepted boot mismatch')
    checks = {
        'explicit_stock_clock_request': new['boot'].get('stock_linkclock_test') is True and
            'msm.rmx2072_stock_linkclk=1' in new['boot']['cmdline'].split(),
        'baseline_default_clock': not old['boot'].get('stock_linkclock_test',False),
        'same_super_and_verified_partitions': old['candidate']==new['candidate'],
        'same_scratch_seeds': old['scratch']==new['scratch'],
        'same_source_device_trees': old['boot']['device_tree_build']['outputs']==new['boot']['device_tree_build']['outputs'],
    }
    for key in ('single_dsc_test','panel_readback_test','solid_fill_test'):
        checks['same_'+key]=old['boot'].get(key)==new['boot'].get(key)
    for key in ('display_probe_sha256','pattern_rgb_sha256','first_stage_init_sha256','witness_sha256'):
        checks['same_'+key]=old['ramdisk'][key]==new['ramdisk'][key]
    baseline_snapshot=(a.baseline/'live/m3-display.txt').read_text(encoding='utf-8')
    before=register_banks(extract(baseline_snapshot,'kms'))
    after=register_banks(extract(snapshot,'kms'))
    checks['same_dsc_parameters']=dsc_from_regs(before['dsc_0'])==dsc_from_regs(after['dsc_0'])
    routes=[route_from_regs(bank) for bank in (before,after)]
    # Both probes request the reviewed single DSC route. Ignore stale values
    # in unused banks; preserve the complete routes below for manual review.
    selected=lambda r: dict(ctl0=r['ctl']['ctl_0'],dsc0_input=r['dsc_input_mux'][0],
        intf1=r['intf_mux']['intf_1'],pingpong0=r['pingpong']['pingpong_0'])
    checks['same_selected_native_route']=selected(routes[0])==selected(routes[1])
    checks['single_dsc_native_route']=routes[1]['ctl']['ctl_0']==dict(dsc_active=1,intf_active=2,merge_3d_active=0) and routes[1]['dsc_input_mux'][0]==0
    for off in (0x54,0x58,0x2a4,0x2a8):
        checks['same_dsi_packet_'+hex(off)]=before['dsi0_ctrl'][off]==after['dsi0_ctrl'][off]
    baseline_acm=(a.baseline/'live/acm.log').read_text(encoding='utf-8')
    acm=(live/'acm.log').read_text(encoding='utf-8')
    old_tx,_=transactions(baseline_acm)
    new_tx,_=transactions(acm)
    checks['same_complete_transmitted_pps']={bytes(x['data']) for x in old_tx}=={bytes(x['data']) for x in new_tx}
    requests=re.findall(r'RMXLINK stock-clock requested bit=(\d+) byte=(\d+) pixel=(\d+)',acm)
    checks['host_requests_match']=bool(requests) and set(requests)=={('660000000','82500000','110000000')}
    clocks={}
    expected={'dsi0_pll_bit_clk':660000000,'dsi0_phy_pll_out_byteclk':82500000,
              'dsi0_phy_pll_out_dsiclk':110000000,'disp_cc_mdss_byte0_clk':82500000,
              'disp_cc_mdss_pclk0_clk':110000000}
    for phase in ('before-modeset','after-modeset','after-flips'):
        rows=re.findall(r'DRMCLOCK phase='+phase+r' clock=(\S+) field=clk_rate value=(\d+) truncated=0',snapshot)
        if len(rows)!=len(dict(rows)):
            raise ValueError('Duplicate clock sample')
        clocks[phase]={k:int(v) for k,v in rows}
        if phase!='before-modeset':
            for name,value in expected.items():
                checks[phase+'_'+name]=name in clocks[phase] and abs(clocks[phase][name]-value)<=1000
    result=dict(boot_id=boot,baseline_boot_id=json.loads((a.baseline/'live/gsi-accepted.json').read_text())['identity'][2],
        checks=checks,all_setup_checks_pass=all(checks.values()),clock_rates_hz=clocks,
        requested_clocks=requests,baseline_route=routes[0],candidate_route=routes[1],
        snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        phy_pll_log=[line for line in acm.splitlines() if 'M3 DSI0 prepare-result' in line or 'M3 DSI0 phy-enable-exit' in line],
        physical_acceptance='REQUIRES_OPERATOR_OBSERVATION',
        scope='Isolation/CCF evidence; neither completed requests nor cached rates prove correct physical pixels or measured wire frequency.')
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('boot_id','all_setup_checks_pass','checks','clock_rates_hz')},indent=2))


if __name__=='__main__':
    main()
