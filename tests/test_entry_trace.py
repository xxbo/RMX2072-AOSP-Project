import pathlib
import struct
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from inspect_entry_trace import inspect_trace, MAGIC


def record(counter, entry=0xa0200000):
    magic = int.from_bytes(MAGIC, 'little')
    return struct.pack('<8Q', magic, 0xa0080000, 0xa3f00000, 4, entry, counter, magic, magic)


class EntryTraceTest(unittest.TestCase):
    def test_repeated_consistent_records_with_fresh_seed(self):
        result = inspect_trace(b'RMX2072-SEED trial=test\n'+b''.join(record(i) for i in range(1, 5)), 'test')
        self.assertTrue(result['entry_reached'])
        self.assertEqual(result['kernel_physical'], '0xa0200000')

    def test_text_magic_is_not_execution_proof(self):
        self.assertIsNone(inspect_trace(b'RMX2072-SEED trial=test\n'+MAGIC*20, 'test')['entry_reached'])

    def test_stale_seed_rejected(self):
        self.assertIsNone(inspect_trace(b'RMX2072-SEED trial=old\n'+b''.join(record(i) for i in range(1, 5)), 'new')['entry_reached'])

    def test_corrupt_geometry_rejected(self):
        self.assertIsNone(inspect_trace(b'RMX2072-SEED trial=test\n'+b''.join(record(i, entry=0xa0200008) for i in range(1, 5)), 'test')['entry_reached'])

    def test_duplicates_do_not_replace_distinct_counter_evidence(self):
        self.assertIsNone(inspect_trace(b'RMX2072-SEED trial=test\n'+record(1)*4, 'test')['entry_reached'])

    def test_invalid_handoff_pointer_is_reported_not_hidden(self):
        data = bytearray(b'RMX2072-SEED trial=test\n')
        for counter in range(1, 5):
            row = bytearray(record(counter))
            struct.pack_into('<Q', row, 16, 0)
            data.extend(row)
        report = inspect_trace(data, 'test')
        self.assertTrue(report['entry_reached'])
        self.assertEqual(report['dtb_physical'], '0x0')
        self.assertFalse(report['dtb_in_captured_dram_range'])
