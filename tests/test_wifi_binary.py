"""The actual trial 102 failure must not pass the baseline artifact screen."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/build'))
from check_m3_wifi_binary import sve_register_instructions


class WifiBinaryTests(unittest.TestCase):
    def test_actual_constructor_instructions_are_rejected(self):
        text = '''  2cf580: 10451881 adr x1, 0x359890 <hash+0x8>
  2cf584: 04f74000 index z0.d, #0x0, #-0x9
  2cf588: 3900a01f strb wzr, [x0, #0x28]
  2cf590: 25e0c620 add z0.d, z0.d, #0x31
'''
        found = sve_register_instructions(text)
        self.assertEqual(len(found), 2)
        self.assertIn('2cf584', found[0])

    def test_neon_and_symbol_names_are_not_sve_operands(self):
        self.assertEqual(sve_register_instructions('''  2cf58c: ad400901 ldp q1, q2, [x8]
  2cf598: 3d800020 str q0, [x1]
  2cf580: 10451881 adr x1, 0x359890 <label_z0.d>
'''), [])


if __name__ == '__main__':
    unittest.main()
