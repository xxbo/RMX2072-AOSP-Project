"""A new HAL must not silently change the accepted graphics runtime."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/build'))
from stage_m3_graphics import merge_native_hal_payload


class HealthPayloadTests(unittest.TestCase):
    kind = "health"
    service = "android.hardware.health-service.example"

    def fixture(self, root):
        elf = bytearray(64)
        elf[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', elf, 18, 183)
        payload = {'/lib64/libbase.so':bytes(elf),
                   '/bin/hw/'+self.service:bytes(elf)}
        for name,data in payload.items():
            path = root/'vendor'/name.lstrip('/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        build = dict(kind=self.kind, source_verified=True, archive_digest_verified=True,
                     files={n:hashlib.sha256(d).hexdigest() for n,d in payload.items()})
        (root/'provenance.json').write_text(json.dumps(build))
        return payload

    def test_shared_runtime_must_remain_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.fixture(root)
            files = {'/lib64/libbase.so':b'existing accepted graphics library'}
            original = dict(files)
            with self.assertRaisesRegex(ValueError, 'replace a different'):
                merge_native_hal_payload(files, root, self.kind)
            self.assertEqual(files, original)
            files = {'/lib64/libbase.so':payload['/lib64/libbase.so']}
            merge_native_hal_payload(files, root, self.kind)
            self.assertEqual(files['/lib64/libbase.so'], payload['/lib64/libbase.so'])
            if self.kind == 'health':
                self.assertNotIn(b'service vendor.charger', files['/etc/init/android.hardware.health-service.example.rc'])

    def test_unverified_or_changed_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            path = root/'vendor/lib64/libbase.so'
            path.write_bytes(path.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError, 'inventory differs'):
                merge_native_hal_payload({}, root, self.kind)
            build = json.loads((root/'provenance.json').read_text())
            build['source_verified'] = False
            (root/'provenance.json').write_text(json.dumps(build))
            with self.assertRaisesRegex(ValueError, 'not verified'):
                merge_native_hal_payload({}, root, self.kind)


class PowerPayloadTests(HealthPayloadTests):
    kind = 'power'
    service = 'android.hardware.power-service.rmx2072'


if __name__ == '__main__':
    unittest.main()
