"""EDL has no live Android identity; partition mismatches must block writes."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from gsi_adb_accept import RELEASE
from run_ufs_trial import validate_edl_boot_only, verify_edl_boot_only_readbacks


class EdlBootOnlyTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {'sha256': 'a'*64, 'parts': [format(n, '064x') for n in range(17)]}
        self.scratch = {'data': {'sha256': 'b'*64}, 'metadata': {'sha256': 'c'*64}}
        self.previous = dict(candidate=deepcopy(self.candidate), scratch=deepcopy(self.scratch),
                             boot={'boot_sha256': 'd'*64, 'dtbo_sha256': 'e'*64})
        self.stable = dict(identity=['37', RELEASE, '9d9585b2-a24a-4117-8390-fb2a29e471a1',
                                     'Enforcing', 'running', '', 'retained', 'adb'],
                           guardian='retained', seconds=195)

    def validate(self):
        return validate_edl_boot_only(self.previous, self.stable, self.candidate, self.scratch)

    def test_accepts_historical_inputs_without_a_live_identity(self):
        self.assertEqual(self.validate(), 'd'*64)

    def test_rejects_changed_super_and_scratch(self):
        for field in ('candidate', 'scratch'):
            with self.subTest(field=field):
                old=self.previous[field]; self.previous[field]={}
                with self.assertRaises(ValueError): self.validate()
                self.previous[field]=old

    def test_rejects_unaccepted_or_wrong_platform_history(self):
        for index,value in ((0,'36'),(1,'stock-kernel'),(3,'Permissive'),(6,'lease')):
            with self.subTest(index=index):
                old=self.stable['identity'][index]; self.stable['identity'][index]=value
                with self.assertRaises(ValueError): self.validate()
                self.stable['identity'][index]=old
        self.stable['seconds']=189
        with self.assertRaises(ValueError): self.validate()

    def test_rejects_incomplete_partition_manifest(self):
        for key in ('boot_sha256', 'dtbo_sha256'):
            old=self.previous['boot'][key]; self.previous['boot'][key]='invalid'
            with self.assertRaises(ValueError): self.validate()
            self.previous['boot'][key]=old
        self.candidate['parts'].pop(); self.previous['candidate']=deepcopy(self.candidate)
        with self.assertRaises(ValueError): self.validate()

    def test_reads_boot_pair_then_all_super_chunks(self):
        calls=[]
        verify_edl_boot_only_readbacks(self.previous,
            lambda *args: calls.append(('boot',args)), lambda *args: calls.append(('super',args)))
        self.assertEqual(calls, [('boot',('before','d'*64,'e'*64)),
                                ('super',('candidate-super-read',self.candidate['parts']))])

    def test_boot_mismatch_does_not_continue_to_super(self):
        read_super=Mock()
        with self.assertRaisesRegex(ValueError,'mismatch'):
            verify_edl_boot_only_readbacks(self.previous,Mock(side_effect=ValueError('mismatch')),read_super)
        read_super.assert_not_called()

    def test_partial_super_failure_does_not_pass_the_gate(self):
        with self.assertRaises(TimeoutError):
            verify_edl_boot_only_readbacks(self.previous,Mock(),Mock(side_effect=TimeoutError()))
