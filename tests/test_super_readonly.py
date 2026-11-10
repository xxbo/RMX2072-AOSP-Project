import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from check_super import BLOCK, PREFIX, SLOT_BYTES, lp_tables, prefix_checks, verify_metadata


class SuperReadOnlyTests(unittest.TestCase):
    def test_header_and_table_hashes_checked_even_when_copies_agree(self):
        prefix = bytearray(PREFIX)
        geom = bytearray(BLOCK)
        struct.pack_into('<II', geom, 0, 0x616c4467, 52)
        struct.pack_into('<III', geom, 40, SLOT_BYTES, 2, BLOCK)
        geom[8:40] = hashlib.sha256(geom[:52]).digest()
        prefix[BLOCK:3*BLOCK] = geom * 2
        slot = bytearray(SLOT_BYTES)
        struct.pack_into('<IHHI', slot, 0, 0x414c5030, 10, 0, 128)
        struct.pack_into('<I', slot, 44, 8)
        slot[48:80] = hashlib.sha256(slot[128:136]).digest()
        slot[12:44] = hashlib.sha256(slot[:128]).digest()
        prefix[3*BLOCK:] = slot * 4
        prefix_checks(prefix)
        for copy in (0, 2):
            prefix[3*BLOCK+SLOT_BYTES*copy+128] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            prefix_checks(prefix)

    def test_fragment_order_and_slot_identity(self):
        dump = 'Partition table:\n' + ''.join(
            '------------------------\nName: '+name+'\nExtents:\n'+extents
            for name, extents in [('system', '0 .. 7 linear super 2048\n'),
                                  ('vendor', '0 .. 3 linear super 4000\n4 .. 7 linear super 3000\n'),
                                  ('product', '0 .. 7 linear super 5000\n')])
        slots = [lp_tables(dump), lp_tables(dump.replace('4000', '6000'))]
        self.assertEqual(slots[0]['vendor'], [[0, 4, 4000], [4, 4, 3000]])
        with self.assertRaises(ValueError):
            lp_tables(dump.replace('4 .. 7', '5 .. 7'))
        digest = 'f'*64
        trace = digest+'  /run/rmx-super/prefix\n'
        for i, table in enumerate(slots):
            trace += f'slot={i}\n'
            for name, rows in table.items():
                for start, length, phys in rows:
                    trace += f'{name} {start} {length} {phys}\n'
        ref = {'slots': slots, 'prefix_sha256': digest}
        self.assertEqual(verify_metadata(ref, trace)[0]['linear_extents'], 4)
        with self.assertRaises(ValueError):
            verify_metadata(ref, trace.replace('6000', '4000'))
