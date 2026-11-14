import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/'scripts/device_audit/gsi_adb_accept.py'
spec=importlib.util.spec_from_file_location('gsi_accept',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BOOT='36f78fb1-b358-4aac-996e-a65775b23da6'
IDENTITY='\n'.join(['37',m.RELEASE,BOOT,'Enforcing','running','running','armed','adb'])+'\n'
RESP=[IDENTITY,'/system/bin/init\x00second_stage\x00','/dev/block/dm-14 / ext4 ro,seclabel 0 0\n/dev/block/dm-15 /vendor ext4 ro,seclabel 0 0\n','/sys/devices/platform/soc/soc:ufs-host-lab/1d84000.ufs/host0/sda10\nNODE=dm-14\nSLAVE=dm-0\nNODE=dm-0\nSLAVE=sda10\nNODE=dm-15\nSLAVE=dm-1\nNODE=dm-1\nSLAVE=sda10\n']

class GsiAcceptanceTests(unittest.TestCase):
    def test_wrong_boot_never_requests_keep(self):
        with patch.object(m,'shell',return_value=IDENTITY.replace(BOOT,'old-boot')) as sh:
            with self.assertRaises(ValueError):m.accept(Path('.'),BOOT)
            self.assertEqual(sh.call_count,1)
    def test_missing_ufs_backing_cannot_be_accepted(self):
        with patch.object(m,'shell',side_effect=RESP[:3]+['loop0']):
            with self.assertRaises(ValueError):m.inspect(Path('.'),BOOT)
    def test_unrelated_ufs_device_cannot_validate_loop_backing(self):
        with patch.object(m,'shell',side_effect=RESP[:3]+[RESP[3].replace('SLAVE=sda10','SLAVE=loop0')]):
            with self.assertRaises(ValueError):m.inspect(Path('.'),BOOT)
    def test_missing_pid_one_cannot_be_accepted(self):
        with patch.object(m,'shell',side_effect=[IDENTITY,'Permission denied']):
            with self.assertRaises(ValueError):m.inspect(Path('.'),BOOT)
    def test_valid_identity_still_requires_guardian_ack(self):
        with patch.object(m,'shell',side_effect=RESP+['rejected']):
            with self.assertRaises(ValueError):m.accept(Path('.'),BOOT)
    def test_accepted_lease_is_bound_to_boot(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m,'shell',side_effect=RESP+['lease','lease']) as sh:
            proof=m.accept(Path(d),BOOT)
            self.assertEqual(proof['identity'][2],BOOT)
            self.assertTrue((Path(d)/'gsi-accepted.json').exists())
            self.assertIn('--keep '+BOOT,sh.call_args_list[4].args[0])
    def test_soak_failure_requests_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            import json
            p=Path(d);(p/'gsi-accepted.json').write_text(json.dumps({'identity':['37',m.RELEASE,BOOT]}))
            with patch.object(m,'inspect',side_effect=ValueError('USB lost')),patch.object(m,'shell',return_value='rollback') as sh:
                with self.assertRaises(ValueError):m.soak_and_retain(p)
                self.assertIn('--rollback '+BOOT,sh.call_args.args[0])
