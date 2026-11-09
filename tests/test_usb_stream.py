import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts/build'))
from check_usb_stream import require_sid0


@unittest.skipUnless(shutil.which('dtc'), 'requires device-tree-compiler')
class PrimaryUSBStreamTests(unittest.TestCase):
    def tree(self, spec='&apps 0 0', cells=2):
        source = f'''/dts-v1/;
        / {{ soc {{
            apps: apps-smmu@15000000 {{
                compatible = "qcom,sm8250-smmu-500";
                #iommu-cells = <{cells}>;
            }};
            other: iommu@2000 {{ #iommu-cells = <2>; }};
            usb@a600000 {{
                compatible = "qcom,snps-dwc3";
                iommus = <{spec}>;
            }};
        }}; }};'''
        return subprocess.run(['dtc', '-q', '-@', '-I', 'dts', '-O', 'dtb'],
                              input=source.encode(), capture_output=True, check=True).stdout

    def test_exact_stream_on_apps_smmu(self):
        self.assertEqual(require_sid0(self.tree(), legacy_base=True), [0, 0])

    def test_refuse_wrong_sid_mask_provider_or_cell_count(self):
        for spec, cells in (('&apps 0x740 0', 2), ('&apps 0 1', 2),
                            ('&other 0 0', 2), ('&apps 0 0', 1)):
            with self.subTest(spec=spec, cells=cells), self.assertRaises(ValueError):
                require_sid0(self.tree(spec, cells), legacy_base=True)
