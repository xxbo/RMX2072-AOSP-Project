import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from build_ufs_candidate import ChunkedImage


class ChunkedImageTests(unittest.TestCase):
    def test_cross_boundary_and_short_final_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory)/str(i) for i in range(3)]
            for path, data in zip(paths, (b'abcd', b'efgh', b'ij')):
                path.write_bytes(data)
            image = ChunkedImage(paths, 4, writable=True)
            image.seek(3)
            self.assertEqual(image.read(6), b'defghi')
            image.seek(3)
            image.write(b'123456')
            self.assertEqual(b''.join(p.read_bytes() for p in paths), b'abc123456j')
            image.seek(-2, 2)
            self.assertEqual(image.read(99), b'6j')
            self.assertEqual(image.read(1), b'')
            before = [p.read_bytes() for p in paths]
            with self.assertRaises(ValueError):
                image.write(b'outside')
            self.assertEqual([p.read_bytes() for p in paths], before)
            with self.assertRaises(ValueError):
                ChunkedImage(paths, 4).write(b'x')

    def test_rejects_hole_and_invalid_seek(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'short'
            path.write_bytes(b'a')
            with self.assertRaises(ValueError):
                ChunkedImage([path, path], 4)
            image = ChunkedImage([path], 4)
            for position in (-1, 2):
                with self.assertRaises(ValueError):
                    image.seek(position)
