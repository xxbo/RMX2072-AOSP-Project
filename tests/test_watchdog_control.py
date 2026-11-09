import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts/build'))
from check_watchdog import check_watchdog_control


@unittest.skipUnless(shutil.which('dtc'), 'requires device-tree-compiler')
class WatchdogControlTests(unittest.TestCase):
    def compile(self, extra=''):
        source = (pathlib.Path(__file__).parent / 'fixtures/legacy-usb-base.dts').read_text()
        source += '''
        / {
            diag_sleep: diag-sleep-clock {
                phandle = <42>;
                compatible = "fixed-clock"; #clock-cells = <0>; clock-frequency = <32764>;
            };
            soc { usb@a600000 { compatible = "qcom,snps-dwc3"; iommus = <&apps_smmu 0 0>; }; };
        };
        &apps_smmu { compatible = "qcom,sm8250-smmu-500"; };
        ''' + extra
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / 'fixture.dtb'
            subprocess.run(['dtc', '-q', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(output)],
                           input=source.encode(), capture_output=True, check=True)
            return output.read_bytes()

    def test_only_modern_watchdog_changes(self):
        new = '&wdog { compatible = "qcom,apss-wdt-sm8250", "qcom,kpss-wdt"; clocks = <&diag_sleep>; interrupts = <0 0 1>; };'
        old = self.compile()
        self.assertEqual(check_watchdog_control(old, self.compile(new))['sleep_clock_hz'], 32764)
        for change in ('/ { extraneous = <1>; };', '&wdog { interrupts = <0 0 4>; };',
                       '&wdog { clocks = <&intc>; };', '&wdog { interrupt-parent = <&apps_smmu>; };'):
            with self.subTest(change=change), self.assertRaises(ValueError):
                check_watchdog_control(old, self.compile(new + change))
