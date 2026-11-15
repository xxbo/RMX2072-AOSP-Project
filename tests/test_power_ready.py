from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from check_power_ready import check_power_ready


class PowerReadyTests(unittest.TestCase):
    def test_upstream_requires_parent_child_and_primary_revision(self):
        boot='78202cbf-6e86-46fd-bb95-24e2d731b27c'
        primary='c440000.qcom,spmi:qcom,pm8150@0:pon@800'
        valid='\n'.join(['M1POWER boot='+boot,
            'DEVICE=0-00 DRIVER=/sys/bus/spmi/drivers/pmic-spmi',
            'PLATFORM='+primary+' DRIVER=/sys/bus/platform/drivers/qcom-pon',
            'PLATFORM='+primary+':pwrkey DRIVER=/sys/bus/platform/drivers/pm8941-pwrkey',
            'PLATFORM=c264000.restart DRIVER=/sys/bus/platform/drivers/msm-restart',
            '[ 0.85] pm8941-pwrkey '+primary+':pwrkey: PON revision=1 subtype=4; upstream binding'])
        self.assertEqual(check_power_ready(valid,boot)['binding'],'upstream-pon-parent-pwrkey-child')
        for old,new in [('drivers/qcom-pon','drivers/unbound'),('drivers/pm8941-pwrkey','drivers/unbound'),
                        ('@0:pon@800:pwrkey: PON','@2:pon@800:pwrkey: PON'),('subtype=4','subtype=5')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_power_ready(valid.replace(old,new),boot)

    def test_requires_primary_bindings_and_this_boot(self):
        boot='78202cbf-6e86-46fd-bb95-24e2d731b27c'
        valid='\n'.join(['M1POWER boot='+boot,
            'DEVICE=0-00 DRIVER=/sys/bus/spmi/drivers/pmic-spmi',
            'PLATFORM=c440000.qcom,spmi:qcom,pm8150@0:qcom,power-on@800 DRIVER=/sys/bus/platform/drivers/pm8941-pwrkey',
            'PLATFORM=c264000.restart DRIVER=/sys/bus/platform/drivers/msm-restart',
            '[ 0.85] RMX2072 primary PON revision=1 subtype=4; preserving pull/debounce'])
        self.assertEqual(check_power_ready(valid,boot)['pon_subtype'],4)
        for old,new in [('boot='+boot,'boot=182b2715-fbcc-41f0-81ec-61213cfe1034'),
                        ('pm8150@0','pm8150@1'),('msm-restart','unbound'),
                        ('subtype=4','subtype=5'),('pm8941-pwrkey','unbound'),
                        ('DEVICE=0-00','DEVICE=0-01')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_power_ready(valid.replace(old,new),boot)
