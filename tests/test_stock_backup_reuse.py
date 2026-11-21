import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from run_ufs_trial import verify_stock_readbacks, verify_stock_phone_digest
from record_gsi_usb_trial import requires_stock_readback


class StockBackupReuseTest(unittest.TestCase):
    def setUp(self):
        self.sha = 'a'*64
        self.original = {'partitions': {'boot': {'sha256': self.sha},
            'super': {'parts': [{'sha256': self.sha}]*17}}}

    def test_default_makes_no_full_stock_read_or_hash_call(self):
        boot, super_read, phone = Mock(), Mock(), Mock()
        self.assertFalse(verify_stock_readbacks(self.original, boot, super_read))
        self.assertIsNone(verify_stock_phone_digest(phone, self.sha))
        for callback in (boot, super_read, phone): callback.assert_not_called()

    def test_explicit_diagnostic_performs_reads_and_checks_digest(self):
        boot, super_read = Mock(), Mock()
        phone = Mock(return_value=self.sha+'  /dev/block/by-name/super')
        self.assertTrue(verify_stock_readbacks(self.original, boot, super_read, True))
        boot.assert_called_once_with('restored', self.sha)
        super_read.assert_called_once_with('restored-super', [self.sha]*17)
        self.assertEqual(verify_stock_phone_digest(phone, self.sha, True), self.sha)
        phone.assert_called_once_with('sha256sum /dev/block/by-name/super', 240)

    def test_explicit_digest_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_stock_phone_digest(Mock(return_value='b'*64+'  super'), self.sha, True)

    def receipt(self):
        return dict(stock_full_partition_readback=False,
            verification_policy='reuse-original-backup-write-ack-boot-and-lp-metadata',
            stock_write_acknowledged=True, boot_sha256=None, dtbo_sha256=None,
            super_sha256=None, expected_image_sha256=dict.fromkeys(('boot','dtbo','super'), self.sha))

    def test_explicit_reuse_receipt_is_not_fresh_hash_evidence(self):
        self.assertFalse(requires_stock_readback(self.receipt()))
        receipt = self.receipt()
        receipt['super_sha256'] = self.sha
        with self.assertRaises(AssertionError): requires_stock_readback(receipt)

    def test_legacy_receipt_still_requires_full_readbacks(self):
        self.assertTrue(requires_stock_readback({'super_sha256': self.sha}))

    def test_incomplete_reuse_receipt_is_rejected(self):
        receipt = self.receipt()
        receipt['stock_write_acknowledged'] = False
        with self.assertRaises(AssertionError): requires_stock_readback(receipt)


if __name__ == '__main__':
    unittest.main()
