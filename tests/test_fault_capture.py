from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from run_guard_expiry import verify_fault_capture

BOOT='cea43da0-c26b-4667-a7b8-5a523c9f650a'
RECOVERY='8a40c470-5f00-4b4a-81ed-9cc20cbf2120'

class FaultCaptureTests(unittest.TestCase):
    def test_requires_correlated_reset_and_disarm(self):
        valid={'console-ramoops-0':'[ 10.000000][ T1365] RMX-M1-GUARD state=expired\n[ 39.000000][ C0] watchdog0: pretimeout event\n',
               'pmsg-ramoops-0':'RMX-M1-AUTO boot='+BOOT+' state=expired\n',
               'intermediate-boot.json':json.dumps({'boot_id':RECOVERY}),
               'recovery-providers.txt':'M1AUTO boot='+RECOVERY+' previous=RMX-M1-AUTO boot='+BOOT+' state=expired',
               'recovery-watchdog.log':'M1RECOVERY boot='+RECOVERY+' uptime=31\nM1RECOVERY AP watchdog disable ioctl rc=0 identity=qcom_wdt\n'}
        changes=[{}, {'console-ramoops-0':'another boot\nwatchdog0: pretimeout event'},
                 {'console-ramoops-0':valid['console-ramoops-0'].replace('39.000000','20.000000')},
                 {'recovery-providers.txt':valid['recovery-providers.txt'].replace(BOOT,RECOVERY)},
                 {'pmsg-ramoops-0':'RMX-M1-AUTO boot='+BOOT+' state=retained'},
                 {'intermediate-boot.json':json.dumps({'boot_id':BOOT})},
                 {'recovery-watchdog.log':valid['recovery-watchdog.log'].replace(RECOVERY,BOOT)},
                 {'recovery-watchdog.log':'M1RECOVERY boot='+RECOVERY+' uptime=31\nrecovery watchdog open: No such file or directory'}]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                for name,text in (valid|change).items():(root/name).write_text(text)
                if change:
                    with self.assertRaises(ValueError):verify_fault_capture(root,BOOT,True)
                else:self.assertEqual(verify_fault_capture(root,BOOT,True),RECOVERY)
