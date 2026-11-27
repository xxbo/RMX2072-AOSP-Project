"""Do not promote MHI setup or ath11k's default board ID to WLAN acceptance."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from capture_m3_wifi import firmware_discovery


class WifiDiscoveryTests(unittest.TestCase):
    def test_trial99_mhi_setup_is_not_a_running_firmware(self):
        log = '''6,1213,30487649,-,caller=T1469;mhi mhi0: Power on setup success
4,1214,30487778,-,caller=T102;mhi mhi0: Direct firmware load for ath11k/QCA6390/hw2.0/amss.bin failed with error -2
4,1216,30488045,-,caller=T1469;ath11k_pci 0000:01:00.0: failed to power up mhi: -110
3,1217,30488104,-,caller=T1469;ath11k_pci 0000:01:00.0: failed to start mhi: -110
'''
        result = firmware_discovery(log)
        self.assertTrue(result['mhi_setup_reported'])
        self.assertTrue(result['amss_missing'])
        self.assertFalse(result['qmi_target_response_observed'])
        self.assertEqual(result['mhi_start_errors'], [-110])

    def test_trial100_qmi_reply_keeps_default_board_id_unqualified(self):
        log = '''6,1206,30915016,-,caller=T14;ath11k_pci 0000:01:00.0: chip_id 0x0 chip_family 0xb board_id 0xff soc_id 0xffffffff
6,1207,30915227,-,caller=T14;ath11k_pci 0000:01:00.0: fw_version 0x10121492 fw_build_timestamp 2021-11-04 11:23 fw_build_id
4,1211,30916311,-,caller=T14;ath11k_pci 0000:01:00.0: qmi failed to fetch board file: -2
4,1212,30916419,-,caller=T14;ath11k_pci 0000:01:00.0: failed to load board data file: -2
'''
        result = firmware_discovery(log+log)
        self.assertTrue(result['qmi_target_response_observed'])
        self.assertTrue(result['board_data_missing'])
        self.assertFalse(result['amss_missing'])
        self.assertEqual(len(result['target_info']), 1)
        self.assertTrue(result['target_info'][0]['board_id_may_be_default'])
        self.assertEqual(result['firmware_versions'], [dict(version='0x10121492',
            timestamp='2021-11-04 11:23', build_id='')])
        self.assertFalse(result['board_compatibility_verified'])

    def test_other_errors_and_missing_logs_are_not_missing_firmware_proof(self):
        for log in ('', 'ath11k_pci 0000:01:00.0: failed to load board data file: -12',
                    'ath11k_pci 0000:01:00.0: qmi failed to fetch board file: -22'):
            result = firmware_discovery(log)
            self.assertFalse(result['board_data_missing'])
            self.assertFalse(result['qmi_target_response_observed'])


if __name__ == '__main__':
    unittest.main()
