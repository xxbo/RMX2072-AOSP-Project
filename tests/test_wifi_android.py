"""Keep optional supplicant staging separate from firmware and radio changes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/build'))
import stage_m3_wifi_android as stage
from rebuild_m3_graphics_trial import retained_wifi_flags, check_retained_peripherals


class WifiAndroidTests(unittest.TestCase):
    def test_existing_label_and_vendor_bytes_remain_unchanged(self):
        files = {stage.CONTEXTS: stage.LABEL, '/build.prop': b'original', '/lib64/libEGL.so': b'gpu'}
        original = deepcopy(files)
        with patch.object(stage, 'overlay_payload', return_value=(b'apk', {'proof': True})):
            stage.add_wifi_android(files, Path('unused'))
            self.assertEqual(set(files)-set(original), {stage.APK})
            self.assertTrue(all(files[k] == v for k, v in original.items()))
            # An identical repeated composition is harmless.
            stage.add_wifi_android(files, Path('unused'))
            self.assertEqual(files[stage.CONTEXTS], stage.LABEL)

    def test_missing_label_added_but_conflicting_apk_rejected(self):
        files = {stage.CONTEXTS: b'/vendor(/.*)? u:object_r:vendor_file:s0\n'}
        with patch.object(stage, 'overlay_payload', return_value=(b'apk', {})):
            stage.add_wifi_android(files, Path('unused'))
            self.assertTrue(files[stage.CONTEXTS].endswith(stage.LABEL))
            files[stage.APK] = b'other'
            before = deepcopy(files)
            with self.assertRaises(ValueError):
                stage.add_wifi_android(files, Path('unused'))
            self.assertEqual(files, before)

    def test_modified_artifact_proof_or_source_cannot_use_old_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source'
            source.mkdir()
            (source/'config.xml').write_bytes(b'source')
            pin = {'apk_sha256': hashlib.sha256(b'apk').hexdigest(),
                   'source_sha256': {'config.xml': hashlib.sha256(b'source').hexdigest()}}
            (root/'pin.json').write_text(json.dumps(pin))
            (root/'provenance.json').write_text(json.dumps(pin))
            apk = root/Path(stage.APK).name
            apk.write_bytes(b'apk')
            with patch.object(stage, 'PIN', root/'pin.json'), patch.object(stage, 'SOURCE', source):
                self.assertEqual(stage.overlay_payload(root), (b'apk', pin))
                apk.write_bytes(b'other')
                with self.assertRaises(ValueError): stage.overlay_payload(root)
                apk.write_bytes(b'apk')
                (root/'provenance.json').write_text(json.dumps(dict(pin, value=False)))
                with self.assertRaises(ValueError): stage.overlay_payload(root)
                (root/'provenance.json').write_text(json.dumps(pin))
                (source/'config.xml').write_bytes(b'changed')
                with self.assertRaises(ValueError): stage.overlay_payload(root)

    def test_vendor_rebuild_cannot_drop_or_replace_boot_firmware(self):
        proof = {'files': {'amss.bin': 'accepted'}}
        prior = {'wifi': True, 'wifi_firmware': proof}
        directory = Path('firmware')
        with self.assertRaises(ValueError): retained_wifi_flags(prior, None)
        with patch('stage_m3_wifi_firmware.wifi_firmware', return_value=({}, proof)):
            self.assertEqual(retained_wifi_flags(prior, directory),
                             ['--wifi', '--wifi-firmware', str(directory.resolve())])
        with patch('stage_m3_wifi_firmware.wifi_firmware', return_value=({}, {'changed': True})):
            with self.assertRaises(ValueError): retained_wifi_flags(prior, directory)

    def test_vendor_rebuild_keeps_radio_presence_and_rejects_new_firmware(self):
        self.assertEqual(retained_wifi_flags({}, None), [])
        self.assertEqual(retained_wifi_flags({'wifi': True}, None), ['--wifi'])
        for prior in ({}, {'wifi': False}, {'wifi': True}, {'wifi': 'true'}):
            with self.subTest(prior=prior):
                with self.assertRaises(ValueError): retained_wifi_flags(prior, Path('new'))

    def test_vendor_rebuild_cannot_silently_drop_90hz_gpu_or_touch(self):
        accepted = dict(panel_refresh=90, performance=True, input_devices=True, battery_gauge=True)
        check_retained_peripherals(accepted, accepted)
        for key, value in [('panel_refresh', 60), ('performance', False),
                           ('input_devices', False), ('battery_gauge', False)]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    check_retained_peripherals(accepted, dict(accepted, **{key: value}))


if __name__ == '__main__':
    unittest.main()
