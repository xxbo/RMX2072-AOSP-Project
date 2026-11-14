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
        self.assertEqual(check_m2_boot(text,boot,init,'6.18-test'),values)
        for field in values:
            with self.subTest(field=field),self.assertRaises(ValueError):
                check_m2_boot(text.replace(values[field],'wrong'),boot,init,'6.18-test')
        with self.assertRaises(ValueError):
            check_m2_boot(text+'M2BOOT boot_id='+boot+'\n',boot,init,'6.18-test')
