"""Fail closed on mixed supplicants, changed runtime files and stale ISA proof."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/build'))
import stage_m3_wifi_vendor as stage
from stage_m3_graphics import compose


class WifiVendorTests(unittest.TestCase):
    def test_assembled_manifest_preserves_only_the_pinned_instance(self):
        xml = b'''<!-- Input: upstream -->
<manifest version="9.0" type="device"><hal format="aidl">
<name>android.hardware.wifi.supplicant</name><version>5</version>
<fqname>ISupplicant/default</fqname></hal></manifest>'''
        stage.check_supplicant_manifest(xml)
        for changed in [xml.replace(b'>5<', b'>4<'), xml.replace(b'/default', b'/other'),
                        xml.replace(b'</manifest>', b'<hal format="aidl"/></manifest>')]:
            with self.assertRaises(ValueError): stage.check_supplicant_manifest(changed)

    def test_mainline_and_vendor_are_mutually_exclusive_before_io(self):
        with self.assertRaises(ValueError):
            compose(None, None, None, Path('rro'), Path('vendor'))
        files = {'/overlay/RmxWifiOverlay.apk': b'apk'}
        with self.assertRaises(ValueError):
            stage.add_wifi_vendor(files, Path('unused'))

    def test_invalid_or_changed_runtime_does_not_mutate_inventory(self):
        files = {'/etc/selinux/vendor_sepolicy.cil': b'policy\n',
                 '/etc/selinux/vendor_file_contexts': b'labels\n',
                 '/lib64/existing.so': b'accepted'}
        incoming = {'/bin/hw/wpa_supplicant': b'binary',
                    '/etc/init/android.hardware.wifi.supplicant-service.rc': b'init',
                    '/etc/vintf/manifest/android.hardware.wifi.supplicant.xml': b'manifest'}
        pins = {'sha256': {'external/wpa_supplicant_8/wpa_supplicant/aidl/'+Path(k).name:
                           stage.sha(v) for k,v in incoming.items() if k.startswith('/etc/')}}
        valid = {'isa_screen': {'sha256': stage.sha(b'binary'), 'sve_register_instruction_count': 0}}
        with tempfile.TemporaryDirectory() as directory:
            pin = Path(directory)/'pin.json'
            pin.write_text(json.dumps(pins))
            for proof, delta in [({}, {}), (valid, {'/bin/hw/wpa_supplicant': b'changed'}),
                    (valid, {'/etc/init/android.hardware.wifi.supplicant-service.rc': b'changed'})]:
                before = deepcopy(files)
                def merge(staged, *args):
                    payload = dict(incoming, **delta)
                    staged.update(payload)
                    return proof, payload
                with patch.object(stage, 'PIN', pin), patch.object(stage, 'merge_native_hal_payload', side_effect=merge):
                    with self.assertRaises(ValueError): stage.add_wifi_vendor(files, Path(directory))
                self.assertEqual(files, before)


if __name__ == '__main__':
    unittest.main()
