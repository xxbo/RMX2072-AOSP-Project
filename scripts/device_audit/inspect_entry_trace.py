#!/usr/bin/env python3
"""Verify repeated early native-entry records; literal magic alone is not proof."""
import argparse
import collections
import json
import pathlib
import struct

MAGIC = b'RMX618E0'


def inspect_trace(data, trial_id):
    records = []
    offset = data.find(MAGIC)
    while offset >= 0:
        if offset+64 <= len(data):
            w = struct.unpack_from('<8Q', data, offset)
            if (data[offset+48:offset+64] == MAGIC*2 and not w[1]&3 and
                    w[4] == w[1]+0x180000 and w[3] in (0, 4, 8, 12) and 1 <= w[5] <= 64):
                records.append((w[1], w[2], w[3], w[4], w[5]))
        offset = data.find(MAGIC, offset+1)
    groups = collections.Counter(record[:4] for record in records)
    winner, count = groups.most_common(1)[0] if groups else (None, 0)
    counters = sorted({r[4] for r in records if r[:4] == winner})
    seed = ('RMX2072-SEED trial='+trial_id).encode() in data
    proven = seed and len(counters) >= 3
    return dict(trial_id=trial_id, expected_seed_found=seed, valid_records=len(records),
                consensus_records=count, distinct_record_counters=counters,
                entry_reached=True if proven else None,
                wrapper_physical=hex(winner[0]) if winner else None,
                dtb_physical=hex(winner[1]) if winner else None,
                current_el=winner[2]//4 if winner else None,
                kernel_physical=hex(winner[3]) if winner else None,
                kernel_2m_aligned=not bool(winner[3]&0x1fffff) if winner else None,
                dtb_8byte_aligned=not bool(winner[1]&7) if winner else None,
                dtb_in_captured_dram_range=0x80000000 <= winner[1] < 0x280000000 if winner else None,
                el_matches_boot_protocol=winner[2] in (4, 8) if winner else None,
                qualification='Absence is inconclusive; RAM continuity and positive controls are required')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pmsg', required=True, type=pathlib.Path)
    p.add_argument('--trial-id', required=True)
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    report = inspect_trace(a.pmsg.read_bytes(), a.trial_id)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    if not report['entry_reached']:
        raise SystemExit('Early entry proof not established')


if __name__ == '__main__':
    main()
