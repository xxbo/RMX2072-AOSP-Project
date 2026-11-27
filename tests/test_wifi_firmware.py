"""Firmware and board-data boundaries in the actual initramfs payload."""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/build'))
from stage_m3_wifi_firmware import PREFIX, ramdisk_manifest, verify_ramdisk_firmware
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from run_ufs_trial import validate_live_trial_battery


def archive(items):
    data=bytearray()
    for name,payload in [*items,('TRAILER!!!',b'')]:
        encoded=name.encode()+b'\0'
        fields=[1,0o100644,0,0,1,0,len(payload),0,0,0,0,len(encoded),0]
        data.extend(b'070701'+''.join(f'{n:08x}' for n in fields).encode()+encoded)
        data.extend(b'\0'*(-len(data)%4));data.extend(payload);data.extend(b'\0'*(-len(data)%4))
    return bytes(data)


class FirmwareTests(unittest.TestCase):
    def manifest(self,raw):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ramdisk.gz';path.write_bytes(gzip.compress(raw))
            return ramdisk_manifest(path)

    def test_actual_payload_digest_and_mode(self):
        raw=archive([('lib/firmware/'+PREFIX+'amss.bin',b'payload')])
        manifest=self.manifest(raw)
        proof={'files':{PREFIX+'amss.bin':{'bytes':7,'sha256':hashlib.sha256(b'payload').hexdigest()}}}
        verify_ramdisk_firmware(manifest,proof)
        manifest['lib/firmware/'+PREFIX+'amss.bin']['sha256']='0'*64
        with self.assertRaises(ValueError):verify_ramdisk_firmware(manifest,proof)

    def test_unreviewed_board_file_is_rejected(self):
        manifest=self.manifest(archive([('lib/firmware/'+PREFIX+'board-2.bin',b'foreign')]))
        with self.assertRaises(ValueError):verify_ramdisk_firmware(manifest,{'files':{}})

    def test_truncation_duplicate_and_traversal_rejected(self):
        for raw in [archive([('amss.bin',b'x')])[:110],
                    archive([('a',b'1'),('a',b'2')]), archive([('../board.bin',b'x')])]:
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(ValueError):self.manifest(raw)

    def test_low_missing_invalid_battery_blocks_next_live_trial(self):
        for value in ('1','24','101','-1','','Permission denied','25\n0'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):validate_live_trial_battery(value)
        self.assertEqual(validate_live_trial_battery('25\n'),25)
