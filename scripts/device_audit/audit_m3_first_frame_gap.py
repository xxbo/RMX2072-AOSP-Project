"""Audit saved native evidence and pinned sources; never access the handset."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from compare_m3_stock_dsc import load_capture

PINS = {
    'dsi_host.c': '1c0841a1c101334ce2b097408668fb448f9dd821',
    'dpu_core_perf.c': '13cc658065c56a00a7dcdd0af4dec4aadfd0e6ed',
    'dsi_ctrl_hw_cmn.c': 'b57583c481a11cf56f4cc66d48fc2e5b25ed3c57',
    'dsi_panel.c': 'a45a2d8f5bc8ea7371225225b168a06b8f173c56',
}


def pinned(path, expected):
    raw = path.read_bytes().replace(b'\r\n', b'\n')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != expected:
        raise ValueError('Source pin mismatch: ' + str(path))
    return raw.decode()


def audit(record, pause_record, sources, dsi_xml):
    src = {name: pinned(sources / name, blob) for name, blob in PINS.items()}
    xml = pinned(dsi_xml, 'c7a7b633d747bc281bc27845c9df858f33c8bd2a')
    capture = load_capture(record, pause_record)
    regs = capture['banks']['dsi0_ctrl']
    named = {node.attrib['name']: int(node.attrib['offset'], 0)
             for node in ET.fromstring(xml).iter() if node.tag.endswith('reg32')
             and 'name' in node.attrib and 'offset' in node.attrib}
    selected = ('STATUS0', 'FIFO_STATUS', 'ACK_ERR_STATUS', 'TIMEOUT_STATUS',
                'CLK_STATUS', 'DLN0_PHY_ERR', 'ERR_INT_MASK0', 'INTR_CTRL')
    raw_regs = {name: hex(regs[named[name]]) for name in selected}

    # The common implementation in this pinned SM8250 downstream tree
    # clears mask bits to enable individual error IRQs (one means masked).
    routine = src['dsi_ctrl_hw_cmn.c'].split(
        'void dsi_ctrl_hw_cmn_enable_error_interrupts(', 1)[1].split('\n}', 1)[0]
    bits = re.findall(r'if \(errors & (DSI_\w+)\)\s+int_mask0 &= ~BIT\((\d+)\);', routine)
    if len(bits) != 25:
        raise ValueError('Unexpected downstream error mask mapping')
    mask = regs[named['ERR_INT_MASK0']]
    irq = {name: dict(mask_bit=int(bit), masked=bool(mask & (1 << int(bit))))
           for name, bit in bits}
    clocks = {}
    for phase, name, value in re.findall(
            r'DRMCLOCK phase=(\S+) clock=(\S+) field=clk_rate value=(\d+) truncated=0',
            capture['snapshot']):
        if name in ('disp_cc_mdss_mdp_clk', 'disp_cc_mdss_byte0_clk', 'disp_cc_mdss_pclk0_clk'):
            key = phase + ':' + name
            if key in clocks:
                raise ValueError('Duplicate clock sample')
            clocks[key] = int(value)
    host = src['dsi_host.c']
    return dict(
        boot_id=capture['boot'], snapshot_sha256=hashlib.sha256(capture['raw']).hexdigest(),
        scope='Offline review of trial 67 snapshot and source; no new device experiment',
        source_pins=PINS,
        ack_commit='ecdaacc9a0ee87eaf9544e1836d86bd9d590312e',
        ack_mirror='cfa72fb3d7f89372c7e449a4de2477551ea4c29c',
        downstream_commit='b76eb6c93add8152b1aa873da0d8d7f495cccab0',
        downstream_scope='SM8250 community source, not an attestation of the F.20 executable',
        raw_dsi_registers=raw_regs,
        irq_mask_semantics='1 masks the event, inferred from the pinned SM8250 downstream implementation',
        error_irq_mask=irq,
        clock_rates_hz=clocks,
        source_observations=dict(
            error_handler_clears_fifo='dsi_write(msm_host, REG_DSI_FIFO_STATUS, status);' in host,
            error_handler_clears_timeout='dsi_write(msm_host, REG_DSI_TIMEOUT_STATUS, status);' in host,
            byte_clock_rounding_present='clk_round_rate(msm_host->byte_clk' in host,
            fixed_perf_overrides_bandwidth='avg_bw = kms->perf.fix_core_ab_vote;' in src['dpu_core_perf.c']
                and 'peak_bw = kms->perf.fix_core_ib_vote;' in src['dpu_core_perf.c'],
            downstream_computes_transfer_budget='void dsi_panel_calc_dsi_transfer_time(' in src['dsi_panel.c'],
        ),
        limitations=[
            'These are after-flips register samples, not first-frame or latched error history.',
            'Masked interrupts do not prove an error occurred or that status cannot latch.',
            'CCF rate equality does not prove no PLL reprogramming occurred during earlier DCS transfers.',
            'Core clock reduction and missing upstream rounding are hypotheses, not a root-cause finding.',
            'A clock-only experiment must not zero the interconnect votes via perf_mode=FIXED.',
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('record', 'pause-record', 'sources', 'dsi-xml', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.record, args.pause_record, args.sources, args.dsi_xml)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(boot_id=result['boot_id'], source_observations=result['source_observations'],
                         masked_errors=[k for k, v in result['error_irq_mask'].items() if v['masked']]), indent=2))


if __name__ == '__main__':
    main()
