import base64
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from usb_diag_soak import command, parse_sample


def response(kernel='6.18.32-test', state='configured', payload=b'\0'*64):
    return ('SOAK_BEGIN_0\r\n'+kernel+'\r\n100.25 300.00\r\n'
            '12345678-1234-1234-1234-123456789abc\r\n'+state+
            '\r\nSOAK_DATA_0\r\n'+base64.b64encode(payload).decode()+
            '\r\nSOAK_DATA_END_0\r\nSOAK_END_0\r\n').encode()


class USBSoakProtocolTests(unittest.TestCase):
    def test_complete_kernel_and_payload_proof(self):
        result = parse_sample(response(), 0, 64)
        self.assertEqual(result['uptime_seconds'], 100.25)
        self.assertEqual(result['transfer_bytes'], 64)

    def test_wrong_kernel_or_unconfigured_link_rejected(self):
        for data in (response(kernel='4.19-test'), response(state='not attached')):
            with self.assertRaises(ValueError):
                parse_sample(data, 0, 64)

    def test_truncated_or_corrupt_payload_rejected(self):
        for data in (response(payload=b'\0'*63), response(payload=b'\0'*63+b'X'),
                     response().replace(b'SOAK_END_0', b'other')):
            with self.assertRaises(ValueError):
                parse_sample(data, 0, 64)

    def test_echoed_command_cannot_supply_response_markers(self):
        data = command(0, 64).encode()
        self.assertNotIn(b'SOAK_END_0', data)
        with self.assertRaises(ValueError):
            parse_sample(data, 0, 64)


if __name__ == '__main__':
    unittest.main()
