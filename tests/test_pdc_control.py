from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/build'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from check_pdc import check_pdc_control


@unittest.skipUnless(shutil.which('dtc'),'requires device-tree-compiler')
class PdcControlTests(unittest.TestCase):
    def tree(self,change=''):
        source=(Path(__file__).parent/'fixtures/legacy-usb-base.dts').read_text()+'''
        / { soc {
            usb@a600000 { compatible = "qcom,snps-dwc3"; iommus = <&apps_smmu 0 0>; };
            qcom,spmi@c440000 { compatible = "qcom,spmi-pmic-arb"; interrupts-extended = <&pdc 1 4>; };
        }; };
        &apps_smmu { compatible = "qcom,sm8250-smmu-500"; };
        '''+change
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'tree.dtb'
            subprocess.run(['dtc','-q','-@','-I','dts','-O','dtb','-o',str(path)],input=source.encode(),capture_output=True,check=True)
            return path.read_bytes()

    def test_only_binding_changes(self):
        old=self.tree();fix='&pdc { compatible = "qcom,sm8250-pdc", "qcom,pdc"; };'
        self.assertEqual(check_pdc_control(old,self.tree(fix))['spmi_gic_spi'],481)
        for change in ('&tlmm { compatible = "qcom,sm8250-pinctrl"; };',
                       '&pdc { qcom,pdc-ranges = <0 481 138>; };',
                       '&pdc { status = "disabled"; };',
                       '/ { soc { qcom,spmi@c440000 { interrupts-extended = <&pdc 2 4>; }; }; };'):
            with self.subTest(change=change),self.assertRaises(ValueError):
                check_pdc_control(old,self.tree(fix+change))
