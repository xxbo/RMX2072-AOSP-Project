"""The native packed pixels and Android archive must describe the same frame."""
import io
from pathlib import Path
import struct
import sys
import unittest
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/build'))
from m3_boot_pattern import WIDTH, HEIGHT, archive_bytes, rgb_bytes


class PatternTest(unittest.TestCase):
    def test_identical_native_and_android_pixels_with_row_markers(self):
        rgb = rgb_bytes()
        self.assertEqual(len(rgb), 1080*2400*3)
        with zipfile.ZipFile(io.BytesIO(archive_bytes())) as archive:
            png = archive.read('part0/00000.png')
            self.assertEqual(png, archive.read('part0/00001.png'))
            self.assertEqual(archive.read('desc.txt'), b'1080 2400 1\np 0 0 part0\n')
        pos, compressed = 8, bytearray()
        while pos < len(png):
            size = struct.unpack_from('>I', png, pos)[0]
            kind, data = png[pos+4:pos+8], png[pos+8:pos+8+size]
            self.assertEqual(zlib.crc32(kind+data), struct.unpack_from('>I', png, pos+8+size)[0])
            if kind == b'IDAT': compressed.extend(data)
            pos += size+12
        rows = zlib.decompress(compressed)
        stride = WIDTH*3+1
        self.assertEqual(len(rows), stride*HEIGHT)
        self.assertTrue(all(rows[y*stride] == 0 for y in range(HEIGHT)))
        self.assertEqual(b''.join(rows[y*stride+1:(y+1)*stride] for y in range(HEIGHT)), rgb)
        # Neighboring groups carry different labels; top/bottom are asymmetric.
        def region(x0, y0, w, h):
            return b''.join(rgb[((y0+y)*WIDTH+x0)*3:((y0+y)*WIDTH+x0+w)*3] for y in range(h))
        self.assertNotEqual(region(24,240,36,15), region(24,264,36,15))
        self.assertNotEqual(region(144,240,500,1), region(144,241,500,1))
        self.assertNotEqual(region(100,50,100,1), region(100,2300,100,1))


if __name__ == '__main__':
    unittest.main()
