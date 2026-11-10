import io
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from serve_gsi_usb import REFERENCE, read_packet, verify_image, verify_mount


class GsiUsbTests(unittest.TestCase):
    def test_random_read_including_final_sector(self):
        data = bytes(range(251))*16 + bytes(80)
        stream = io.BytesIO(data)
        for offset, count in ((3584,512), (0,4096), (1024,512)):
            response = read_packet(stream,len(data),offset,count)
            self.assertEqual(response[4:], data[offset:offset+count])
            self.assertEqual(struct.unpack('<I',response[:4])[0], zlib.crc32(response[4:]))

    def test_invalid_and_short_reads(self):
        stream = io.BytesIO(bytes(1024))
        for offset, count in ((0,0),(-512,512),(1024,512),(1,512),(0,8192),(0,1)):
            with self.assertRaises(ValueError):
                read_packet(stream,1024,offset,count)
        with self.assertRaises(IOError):
            read_packet(stream,4096,2048,1024)

    def test_image_hash_before_serving(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            verify_image(io.BytesIO(bytes(512)), {'image_bytes':512,'image_sha256':'0'*64})

    def test_mount_requires_the_pinned_root_and_device_files(self):
        ref = json.loads(REFERENCE.read_text())
        tree = ref['hashtree']
        sectors = tree['image_bytes']//512
        blocks = sectors//8
        footer = 'd'*64
        rows = [f"source_table=0 {ref['image_bytes']//512} user ",
                f"verity_table=0 {sectors} verity 1 254:0 254:0 4096 4096 {blocks} {blocks} sha256 {tree['root_digest']} {tree['salt']}",
                'mounted=/run/gsi17/mnt fs=ext4 options=ro,nosuid,nodev,noexec',
                f'verity_status=0 {sectors} verity V -', 'last_block_sha256='+footer,
                'ro.system.build.version.release=17', 'ro.system.build.version.sdk=37',
                'ro.system.build.id='+ref['build'], 'cleanup=0']
        rows += [f"file={name} sha256={item['sha256']}" for name,item in ref['files'].items()]
        log = '\n'.join(rows)
        verify_mount(log,ref,footer)
        with self.assertRaisesRegex(ValueError,'signed GSI descriptor'):
            verify_mount(log.replace(tree['root_digest'],'0'*64),ref,footer)
        with self.assertRaisesRegex(ValueError,'Missing mount result'):
            verify_mount('\n'.join(rows[:-1]),ref,footer)
