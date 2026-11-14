import importlib.util
import json
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
    def test_autonomous_capture_does_not_request_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with patch.object(m,'shell',side_effect=[BOOT,'M1EVENT autonomous=1\nM1EVENT boot_id='+BOOT+'\n']) as sh:
                self.assertEqual(m.fetch_autonomous(p),BOOT)
                self.assertEqual([x.args[0] for x in sh.call_args_list],['cat /proc/sys/kernel/random/boot_id','cat /data/local/tmp/rmx-m1-boot.txt'])
            self.assertEqual(json.loads((p/'host-events.jsonl').read_text())['event'],'autonomous_handoff_observed')
            with patch.object(m,'shell',side_effect=[BOOT,'M1EVENT autonomous=1\nM1EVENT boot_id=old\n']):
                with self.assertRaises(ValueError):m.fetch_autonomous(p)
    def test_restricted_gsi_requires_matching_independent_witness(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'host-events.jsonl').write_text(json.dumps(dict(event='handoff_requested',boot_id=BOOT))+'\n')
            witness='M1EVENT boot_id='+BOOT+'\nM1EVENT ufs_super=/sys/devices/1d84000.ufs/block/sda/sda10 dev=8:10 ro=1\n'
            for part,dm,lower in [('system',14,0),('vendor',15,1)]:
                witness+=f'Created logical partition {part} on device /dev/block/dm-{lower}\nM1EVENT verified_ufs_mount={part} dev=254:{dm}\nM1EVENT table={part} 0 100 linear 8:10 200\nM1EVENT table={part}-verity 0 96 verity 1 254:{lower} 254:{lower} rest\nM1EVENT status={part}-verity 0 96 verity V 0\n'
            path=p/'acm.log';path.write_text(witness)
            responses=[IDENTITY.replace('running\nrunning','running\n')]+RESP[1:3]+[RESP[3].split('NODE=')[0]]
            with patch.object(m,'shell',side_effect=responses):
                self.assertIn('same-boot ACM',m.inspect(p,BOOT)['ufs_evidence'])
            autonomous=witness
            for part,lower in [('system',0),('vendor',1)]:
                autonomous=autonomous.replace(f'Created logical partition {part} on device /dev/block/dm-{lower}',f'M1EVENT linear_mapper={part} dev=254:{lower}')
            (p/'boot-events.txt').write_text(autonomous)
            (p/'host-events.jsonl').write_text(json.dumps(dict(event='autonomous_handoff_observed',boot_id=BOOT))+'\n')
            with patch.object(m,'shell',side_effect=responses):
                self.assertIn('autonomous device',m.inspect(p,BOOT)['ufs_evidence'])
            (p/'boot-events.txt').unlink()
            for bad in [witness.replace(BOOT,'old-boot'),witness.replace('linear 8:10','linear 7:0'),witness.replace('254:1 254:1','254:2 254:2'),witness.replace('dev=254:15','dev=254:16')]:
                path.write_text(bad)
                with patch.object(m,'shell',side_effect=responses):
                    with self.assertRaises(ValueError):m.inspect(p,BOOT)
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
    def test_autonomous_boot_must_retain_without_host_keep(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'boot-events.txt').write_text('autonomous fixture')
            with patch.object(m,'shell',side_effect=RESP) as sh:
                with self.assertRaises(ValueError):m.accept(p,BOOT)
                self.assertEqual(sh.call_count,4)
            with patch.object(m,'shell',side_effect=[IDENTITY.replace('armed','retained')]+RESP[1:]+['retained','retained']):
                self.assertEqual(m.accept(p,BOOT)['guard_mode_at_acceptance'],'retained')
    def test_soak_failure_requests_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            import json
            p=Path(d);(p/'gsi-accepted.json').write_text(json.dumps({'identity':['37',m.RELEASE,BOOT]}))
            with patch.object(m,'inspect',side_effect=ValueError('USB lost')),patch.object(m,'shell',return_value='rollback') as sh:
                with self.assertRaises(ValueError):m.soak_and_retain(p)
                self.assertIn('--rollback '+BOOT,sh.call_args.args[0])
