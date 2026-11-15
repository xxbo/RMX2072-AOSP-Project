import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/build'))
from check_m2_resources import normalized_node


class ResourceReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tree={'/clock-a':{'phandle':[1],'#clock-cells':[1]},
                   '/clock-b':{'phandle':[2],'#clock-cells':[1]},
                   '/consumer':{'phandle':[3],'clocks':[1,5],'reg':[1,2]}}

    def test_equal_phandle_number_different_provider_is_not_equal(self):
        changed=copy.deepcopy(self.tree)
        changed['/clock-a']['phandle']=[2]
        changed['/clock-b']['phandle']=[1]
        self.assertNotEqual(normalized_node(self.tree,'/consumer'),normalized_node(changed,'/consumer'))

    def test_relocation_preserves_provider_and_arguments(self):
        changed=copy.deepcopy(self.tree)
        changed['/clock-a']['phandle']=[4]
        changed['/consumer']['clocks']=[4,5]
        self.assertEqual(normalized_node(self.tree,'/consumer'),normalized_node(changed,'/consumer'))
        self.assertEqual(normalized_node(changed,'/consumer')['reg'],[1,2])

    def test_bad_reference_or_missing_argument_is_rejected(self):
        for cells in ([9,5],[1]):
            with self.subTest(cells=cells),self.assertRaises(ValueError):
                changed=copy.deepcopy(self.tree)
                changed['/consumer']['clocks']=cells
                normalized_node(changed,'/consumer')
