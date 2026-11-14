from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from run_ufs_trial import validate_boot_only


class BootOnlyTests(unittest.TestCase):
    def setUp(self):
        self.candidate={'sha256':'a'*64,'parts':['b'*64]}
        self.scratch={'data':{'sha256':'c'*64}}
        self.previous={'candidate':deepcopy(self.candidate),'scratch':deepcopy(self.scratch),'boot':{'boot_sha256':'d'*64}}
        self.stable={'identity':['37','kernel','9d9585b2-a24a-4117-8390-fb2a29e471a1','Enforcing','running','','retained','adb'],'guardian':'retained','seconds':193.6}
        self.live=deepcopy(self.stable)

    def check(self):
        return validate_boot_only(self.previous,self.stable,self.candidate,self.scratch,self.live)

    def test_valid_baseline(self):
        self.assertEqual(self.check(),'d'*64)

    def test_rejects_changed_super_or_scratch(self):
        for field in ('candidate','scratch'):
            with self.subTest(field=field):
                old=deepcopy(self.previous[field]); self.previous[field]={}
                with self.assertRaises(ValueError):self.check()
                self.previous[field]=old

    def test_rejects_new_boot_or_lost_retention(self):
        for index,value in ((2,'6783f265-27da-49aa-9e2c-286c62f18d69'),(6,'lease')):
            with self.subTest(index=index):
                self.live=deepcopy(self.stable);self.live['identity'][index]=value
                with self.assertRaises(ValueError):self.check()

    def test_rejects_incomplete_soak(self):
        self.stable['seconds']=189
        with self.assertRaises(ValueError):self.check()
