"""Associate complete host PPS, sampled encoder fields and raw panel responses."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from decode_m3_kms_snapshot import extract, register_banks, dsc_from_regs, dsc_from_pps


def transmitted_config(data):
    if len(data) != 88 or data[0] != 0x11:
        raise ValueError('Requires the complete vendor DSC 1.1 payload')
    # The shared decoder accepts the 128-byte standard container. All DSC 1.1
    # fields it reads end at byte 87; padding is not claimed as transmitted data.
    return dsc_from_pps(bytes(data) + bytes(40))


def transactions(text):
    tx, reads = [], []
    current_tx = current_read = None
    for line in text.splitlines():
        match = re.search(r'RMXPPS host-transfer ret=(\d+) payload=(\d+)', line)
        if match:
            current_tx = dict(returned=int(match[1]), expected=int(match[2]), data=bytearray())
            tx.append(current_tx)
        match = re.search(r'RMXPANEL read command=([0-9a-f]{2}) requested=(\d+) ret=(-?\d+)', line)
        if match:
            current_read = dict(command=match[1], requested=int(match[2]),
                                returned=int(match[3]), data=bytearray())
            reads.append(current_read)
        match = re.search(r'RMXPPS (tx|rx|power) offset=(\d+) bytes=([0-9a-f]+)', line)
        if not match:
            continue
        kind, offset, value = match[1], int(match[2]), bytes.fromhex(match[3])
        record = current_tx if kind == 'tx' else current_read
        if record is None or offset != len(record['data']) or not 0 < len(value) <= 32:
            raise ValueError('Missing/duplicated/out-of-order or oversized PPS chunk')
        if kind != 'tx' and (kind == 'power') != (record['command'] == '0a'):
            raise ValueError('Panel response attached to the wrong command')
        record['data'].extend(value)
    if not tx or not reads:
        raise ValueError('Missing transmit or readback witness')
    for row in tx:
        if row['expected'] != 88 or row['returned'] < 89 or len(row['data']) != 88:
            raise ValueError('Incomplete 88-byte transmitted PPS witness')
    for row in reads:
        if row['returned'] > row['requested'] or len(row['data']) != max(0, row['returned']):
            raise ValueError('Incomplete or inconsistent panel response witness')
    return tx, reads


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    live = a.record/'live'
    inputs = json.loads((a.record/'inputs.json').read_text(encoding='utf-8'))
    boot = json.loads((live/'gsi-accepted.json').read_text())['identity'][2]
    snapshot = (live/'m3-display.txt').read_text(encoding='utf-8')
    events = [json.loads(line) for line in (live/'host-events.jsonl').read_text().splitlines()]
    if (not inputs['boot'].get('panel_readback_test') or
        set(re.findall(r'^M3DISPLAY boot_id=(.+)$', snapshot, re.M)) != {boot} or
        not any(e.get('event') == 'display_gate_requested' and e.get('boot_id') == boot for e in events)):
        raise ValueError('Readback record does not match the accepted explicit test boot')
    raw = (live/'acm.log').read_bytes()
    text = raw.decode('utf-8', errors='strict')
    tx, reads = transactions(text)
    banks = register_banks(extract(snapshot, 'kms'))
    expected = transmitted_config(tx[0]['data'])
    actual = dsc_from_regs(banks['dsc_0'])
    differences = {key:dict(encoder=value, transmitted=expected[key])
                   for key,value in actual.items() if value != expected[key]}
    power = [r for r in reads if r['command'] == '0a']
    full = [r for r in reads if r['command'] == '9e' and r['returned'] == 88]
    relock = re.findall(r'RMXPANEL readback-end relock_ret=(-?\d+)', text)
    if len(power) != 1 or len(reads) > 3:
        raise ValueError('Readback was not bounded to one diagnostic sequence')
    power_ok = power[0]['data'] == b'\x9c' and power[0]['returned'] == 1
    if power_ok and relock != ['0']:
        raise ValueError('Panel key relock not confirmed')
    for row in tx + reads:
        row['hex'] = row.pop('data').hex()
    result = dict(boot_id=boot, acm_sha256=hashlib.sha256(raw).hexdigest(),
        transmitted=tx, panel_reads=reads, power_mode_matches_oem=power_ok,
        encoder_vs_transmit_differences=differences,
        all_transmitted_pps_identical=len({r['hex'] for r in tx}) == 1,
        relock_confirmed=relock == ['0'],
        full_vendor_response_available=bool(full),
        full_response_matches_tx=bool(full) and full[0]['hex'] == tx[0]['hex'],
        vendor_read_semantics='UNVERIFIED: 0x9e is a known write address; read responses are raw evidence',
        physical_acceptance='REQUIRES_OPERATOR_OBSERVATION',
        scope='Host transfer plus sampled native DSC registers; unavailable/zero reads do not prove decoder rejection.')
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key not in ('transmitted','panel_reads')}))


if __name__ == '__main__':
    main()
