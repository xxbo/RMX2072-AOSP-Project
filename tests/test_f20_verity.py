from pathlib import Path
import hashlib
import struct
import sys
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from check_verity import verified_vbmeta, verity_args


class F20VerityTests(unittest.TestCase):
    def test_signatures_cover_header_and_aux_block(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        n = private.public_key().public_numbers().n
        width = 256
        key = struct.pack('>II', 2048, (-pow(n, -1, 1 << 32)) & 0xffffffff)
        key += n.to_bytes(width, 'big') + pow(2, 4096, n).to_bytes(width, 'big')
        aux = key + bytes(-len(key) % 64)
        header = bytearray(256)
        struct.pack_into('>4sIIQQI', header, 0, b'AVB0', 1, 0, 320, len(aux), 1)
        struct.pack_into('>10Q', header, 32, 0, 32, 32, width, 0, len(key), len(key), 0, len(key), 0)
        message = bytes(header) + aux
        auth = hashlib.sha256(message).digest() + private.sign(message, padding.PKCS1v15(), hashes.SHA256()) + bytes(32)
        image = bytes(header) + auth + aux
        self.assertEqual(verified_vbmeta(image)[1], key)
        damaged = bytearray(image)
        damaged[288] ^= 1
        with self.assertRaises(InvalidSignature):
            verified_vbmeta(bytes(damaged))
        damaged = bytearray(image)
        damaged[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'authentication hash'):
            verified_vbmeta(bytes(damaged))

    def test_tree_and_fec_must_fit_linear_device(self):
        tree = dict(version=1, flags=0, data_block_bytes=4096, hash_block_bytes=4096,
                    image_bytes=8192, tree_offset=8192, tree_bytes=4096, fec_offset=12288,
                    fec_bytes=8192, fec_roots=2, algorithm='sha1', root_digest='af'*20, salt='01')
        self.assertEqual(verity_args(tree, '253:0', 20480)[5:8], ['2','2','sha1'])
        with self.assertRaisesRegex(ValueError, 'range mismatch'):
            verity_args(tree, '253:0', 16384)
