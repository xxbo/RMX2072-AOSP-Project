"""Decode the bounded pre-Android snapshot; never infer physical display success."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def extract(text, name):
    start = f'DRMSNAPSHOT begin={name} phase=after-flips\n'
    if text.count(start) != 1:
        raise ValueError(f'Requires exactly one {name} snapshot')
    rest = text.split(start, 1)[1]
    match = re.search(rf'\nDRMSNAPSHOT end={name} bytes=(\d+) limit_reached=0 read_errno=0\n', rest)
    if not match:
        raise ValueError(f'{name} snapshot is missing, incomplete, capped or failed')
    payload = rest[:match.start()]
    if len(payload.encode()) != int(match[1]):
        raise ValueError(f'{name} snapshot byte count mismatch')
    return payload


def register_banks(payload):
    banks = {}
    bank = None
    for line in payload.splitlines():
        heading = re.fullmatch(r'=+([^=]+)=+', line)
        if heading:
            bank = heading[1]
            if bank in banks:
                raise ValueError('Duplicate snapshot bank: '+bank)
            banks[bank] = {}
        row = re.fullmatch(r'0x([0-9a-f]+) : ((?:[0-9a-f]{8} ){3}[0-9a-f]{8})', line)
        if row:
            if bank is None:
                raise ValueError('Register row outside a bank')
            offset = int(row[1], 16)
            for index, value in enumerate(row[2].split()):
                address = offset + index * 4
                if address in banks[bank]:
                    raise ValueError('Duplicate register offset')
                banks[bank][address] = int(value, 16)
    return {name: regs for name, regs in banks.items() if regs}


def dsc_from_regs(r):
    enc, rc = r[4], r[0x38]
    return dict(
        picture=[r[8] >> 16, r[8] & 0xffff],
        slice=[r[12] >> 16, r[12] & 0xffff], chunk=r[16] >> 16,
        bpc=10 if enc & 1 else 8, bpp_6_4=(enc >> 8) & 0x3ff,
        line_buf_depth=(enc >> 3) & 15, simple_422=(enc >> 2) & 1,
        convert_rgb=(enc >> 1) & 1, block_pred_enable=(enc >> 7) & 1,
        initial_xmit_delay=r[0x14] & 0xffff, initial_dec_delay=r[0x14] >> 16,
        initial_scale=r[0x18], scale_decrement=r[0x1c], scale_increment=r[0x20],
        first_line_bpg=r[0x24], nfl_bpg=r[0x28] >> 16, slice_bpg=r[0x28] & 0xffff,
        initial_offset=r[0x2c] >> 16, final_offset=r[0x2c] & 0xffff,
        flatness_min_qp=r[0x30] & 31, flatness_max_qp=(r[0x30] >> 5) & 31,
        rc_model_size=r[0x34], rc_edge_factor=rc & 15,
        rc_quant_incr_limit0=(rc >> 4) & 31, rc_quant_incr_limit1=(rc >> 9) & 31,
        rc_tgt_offset_high=(rc >> 14) & 15, rc_tgt_offset_low=(rc >> 18) & 15,
        rc_buf_thresh=[r[0x3c+i*4] for i in range(14)],
        rc_range=[[r[0x74+i*4], r[0xb0+i*4], r[0xec+i*4] & 63] for i in range(15)],
    )


def route_from_regs(banks):
    # Report all banks; the caller must associate CTL/INTF with the live CRTC.
    # Nonzero registers in an unused bank are not evidence that it is active.
    mux = banks.get('dsc_input_mux')
    if mux is not None and not {0, 4, 8, 12}.issubset(mux):
        raise ValueError('Incomplete SM8250 DSC input mux row')
    return dict(
        dsc_input_mux=None if mux is None else [mux[i*4] for i in range(4)],
        ctl={name: dict(dsc_active=r[0xe8], intf_active=r[0xf4],
                        merge_3d_active=r[0xe4])
             for name, r in banks.items() if re.fullmatch(r'ctl_\d+', name)
             and {0xe8, 0xf4, 0xe4}.issubset(r)},
        intf_mux={name: r[0x25c] for name, r in banks.items()
                  if re.fullmatch(r'intf_\d+', name) and 0x25c in r},
        pingpong={name: dict(dsc_mode=r[0xa0], input_swap=r[0xac], output_swap=r[0xc8])
                  for name, r in banks.items() if re.fullmatch(r'pingpong_\d+', name)
                  and {0xa0, 0xac, 0xc8}.issubset(r)})


def dsc_from_pps(p):
    if len(p) != 128 or p[0] != 0x11:
        raise ValueError('Requires a complete DSC 1.1 reference PPS')
    def u16(i):
        return int.from_bytes(p[i:i+2], 'big')
    return dict(
        picture=[u16(8), u16(6)], slice=[u16(12), u16(10)], chunk=u16(14),
        bpc=p[3] >> 4, bpp_6_4=((p[4] & 3) << 8) | p[5],
        line_buf_depth=p[3] & 15, simple_422=(p[4] >> 3) & 1,
        convert_rgb=(p[4] >> 4) & 1, block_pred_enable=(p[4] >> 5) & 1,
        initial_xmit_delay=u16(16) & 0x3ff, initial_dec_delay=u16(18),
        initial_scale=p[21], scale_decrement=u16(24) & 0xfff, scale_increment=u16(22),
        first_line_bpg=p[27] & 31, nfl_bpg=u16(28), slice_bpg=u16(30),
        initial_offset=u16(32), final_offset=u16(34), flatness_min_qp=p[36] & 31,
        flatness_max_qp=p[37] & 31, rc_model_size=u16(38), rc_edge_factor=p[40] & 15,
        rc_quant_incr_limit0=p[41] & 31, rc_quant_incr_limit1=p[42] & 31,
        rc_tgt_offset_high=p[43] >> 4, rc_tgt_offset_low=p[43] & 15,
        rc_buf_thresh=list(p[44:58]),
        rc_range=[[(u16(58+i*2) >> 11) & 31, (u16(58+i*2) >> 6) & 31,
                   u16(58+i*2) & 63] for i in range(15)],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--pps-reference', type=Path, required=True)
    args = parser.parse_args()
    live = args.record/'live'
    boot = json.loads((live/'gsi-accepted.json').read_text())['identity'][2]
    raw = (live/'m3-display.txt').read_bytes()
    text = raw.decode('utf-8').replace('\r\n', '\n')
    if set(re.findall(r'^M3DISPLAY boot_id=(.+)$', text, re.M)) != {boot}:
        raise ValueError('Display snapshot does not belong to the accepted GSI boot')
    if 'DRMTEST exit=0\n' not in text:
        raise ValueError('Native probe did not complete successfully')
    chunks = {name: extract(text, name) for name in ('kms', 'state', 'fb')}
    banks = register_banks(chunks['kms'])
    if not {'dsc_0', 'dsc_1', 'dsi0_ctrl'}.issubset(banks):
        raise ValueError('Required SM8250 DSC/DSI banks absent')
    expected = dsc_from_pps(bytes.fromhex(json.loads(args.pps_reference.read_text())['computed_pps_hex']))
    decoded = {}
    for name, regs in banks.items():
        if re.fullmatch(r'dsc_\d+', name) and regs[4]:
            actual = dsc_from_regs(regs)
            decoded[name] = dict(common_mode=regs[0], initial_lines=regs[4] >> 20,
                last_group=(regs[4] >> 18) & 3, parameters=actual,
                differences={key: dict(actual=value, expected=expected[key])
                             for key, value in actual.items() if value != expected[key]})
    sspp = {}
    for name, r in banks.items():
        if re.fullmatch(r'sspp_\d+', name) and r[0]:
            sspp[name] = dict(source_size=[r[0] & 0xffff, r[0] >> 16],
                out_size=[r[12] & 0xffff, r[12] >> 16], stride0=r[0x24] & 0xffff,
                source_address0=hex(r[0x14]),
                source_format=hex(r[0x30]), unpack=hex(r[0x34]), op_mode=hex(r[0x38]),
                fetch_mode=(r[0x30] >> 30) & 3, bytes_per_pixel=((r[0x30] >> 9) & 3)+1,
                ubwc_enabled=bool(r[0x38] & 1))
    r = banks['dsi0_ctrl']
    result = dict(boot_id=boot, scope='Pre-Android native KMS; nonzero banks may include stale state. Not a live Android scanout or physical pass.',
        source_sha256=hashlib.sha256(raw).hexdigest(),
        reference_sha256=hashlib.sha256(args.pps_reference.read_bytes()).hexdigest(),
        route=route_from_regs(banks),
        dsc=decoded, sspp=sspp, dsi=dict(compression=hex(r[0x2a4]),
        compression2=hex(r[0x2a8]), stream=hex(r[0x54]), total=hex(r[0x58])),
        buffers=re.findall(r'^DRMTEST buffer=.*$', text, re.M),
        banks={name: {hex(offset): hex(value) for offset, value in regs.items()}
               for name, regs in banks.items()})
    (live/'kms-decoded.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    for name, payload in chunks.items():
        (live/f'native-{name}.txt').write_text(payload, encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'banks'}, indent=2))


if __name__ == '__main__':
    main()
