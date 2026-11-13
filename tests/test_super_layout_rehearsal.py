from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from check_super_chunks import FIRST, SECTORS, read_xml
from rehearse_super_layout import allocate


class SuperLayoutTests(unittest.TestCase):
    def test_reads_cover_only_super_once(self):
        cursor = FIRST
        names = set()
        for row in ET.fromstring(read_xml()):
            self.assertEqual(row.tag,'read')
            self.assertEqual(row.get('physical_partition_number'),'0')
            self.assertEqual(int(row.get('start_sector')),cursor)
            self.assertEqual(row.get('SECTOR_SIZE_IN_BYTES'),'4096')
            self.assertNotIn(row.get('filename'),names)
            names.add(row.get('filename'))
            cursor += int(row.get('num_partition_sectors'))
        self.assertEqual(cursor,FIRST+SECTORS)
        self.assertEqual(len(names),17)

    def test_fragmented_allocation(self):
        gaps = [(8,16),(64,8)]
        self.assertEqual(allocate(gaps,20),[(8,16),(64,4)])
        self.assertEqual(allocate(gaps,4),[(68,4)])
        with self.assertRaises(ValueError):
            allocate(gaps,8)
