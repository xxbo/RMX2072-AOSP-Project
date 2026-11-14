from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from check_m2_boot import check_m2_boot


class M2BootTests(unittest.TestCase):
    def test_matches_source_init_and_both_trees_on_one_boot(self):
        boot='78202cbf-6e86-46fd-bb95-24e2d731b27c'
        init='a'*64
        values=dict(boot_id=boot,kernel_release='6.18-test',base_source='20607-q-24a15224-m2',
                    overlay_source='20607-q-24a15224-m2',first_stage_init_sha256=init,runtime_fdt_sha256='b'*64)
        text=''.join(f'M2BOOT {k}={v}\n' for k,v in values.items())
        events='M1EVENT boot_id='+boot+'\n'+''.join(f'M1EVENT disk=sd{n} ro=1\n' for n in 'abcdef')
        self.assertEqual(check_m2_boot(text,boot,init,'6.18-test',events),dict(values,read_only_ufs_luns=['sd'+n for n in 'abcdef']))
        for field in values:
            with self.subTest(field=field),self.assertRaises(ValueError):
                check_m2_boot(text.replace(values[field],'wrong'),boot,init,'6.18-test',events)
        with self.assertRaises(ValueError):
            check_m2_boot(text+'M2BOOT boot_id='+boot+'\n',boot,init,'6.18-test',events)
        for changed in (events.replace('disk=sdf ro=1','disk=sdf ro=0'),events.replace('M1EVENT disk=sdf ro=1\n',''),events+'M1EVENT disk=sda ro=1\n',events.replace(boot,'00000000-0000-0000-0000-000000000000')):
            with self.subTest(events=changed),self.assertRaises(ValueError):
                check_m2_boot(text,boot,init,'6.18-test',changed)
