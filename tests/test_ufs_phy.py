import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts/build'))
from check_ufs_phy import verify_original_properties


class UFSOEMPropertiesTests(unittest.TestCase):
    def test_relocated_supply_still_resolves_to_same_node(self):
        old = {'/rail': {'phandle': [20]}, '/ufs': {'vcc-supply': [20], 'reg': [20, 4]}}
        new = {'/rail': {'phandle': [22]}, '/ufs': {'vcc-supply': [22], 'reg': [20, 4]}}
        self.assertEqual(verify_original_properties(old, new), 2)
        new['/ufs']['reg'] = [22, 4]
        with self.assertRaises(ValueError):
            verify_original_properties(old, new)

    def test_reject_supply_retarget_and_symbol_collision(self):
        old = {'/l5': {'phandle': [1]}, '/l9': {'phandle': [2]}, '/ufs': {'vdda-phy-supply': [1]}}
        new = dict(old, **{'/ufs': {'vdda-phy-supply': [2]}})
        with self.assertRaises(ValueError):
            verify_original_properties(old, new)
        old = {'/__symbols__': {'diag_ufs_phy': ['/oem']}}
        new = {'/__symbols__': {'diag_ufs_phy': ['/soc/ufs-phy-lab/phy@1d87000'],
                               'diag_ufs_l9': ['/soc/rsc@18200000/diag-regulators/ldo9']}}
        with self.assertRaises(ValueError):
            verify_original_properties(old, new)
