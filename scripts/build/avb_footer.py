"""Retain stock AVB envelope for modified payloads on the unlocked test handset.

The signed stock hash does NOT authenticate the modified payload. This is not
OEM signing, and these images must never be used on a locked/relocked device.
"""
import hashlib
import struct


def parse_footer(image):
    if len(image) < 64:
        raise ValueError('AVB footer missing')
    magic, major, minor, original, offset, size, reserved = struct.unpack('>4sIIQQQ28s', image[-64:])
    if magic != b'AVBf' or major != 1 or offset+size > len(image)-64 or original > offset:
        raise ValueError('Invalid AVB footer')
    metadata = image[offset:offset+size]
    if size < 256 or metadata[:4] != b'AVB0':
        raise ValueError('Invalid embedded AVB metadata')
    auth, aux = struct.unpack_from('>QQ', metadata, 12)
    if 256+auth+aux != size:
        raise ValueError('AVB metadata length mismatch')
    return dict(major=major, minor=minor, original_size=original, offset=offset,
                size=size, reserved=reserved, metadata=metadata)


def retain_envelope(stock, payload):
    old = parse_footer(stock)
    offset = (len(payload)+4095)//4096*4096
    if offset+old['size'] > len(stock)-64:
        raise ValueError('Payload and AVB envelope exceed partition')
    result = bytearray(len(stock))
    result[:len(payload)] = payload
    result[offset:offset+old['size']] = old['metadata']
    struct.pack_into('>4sIIQQQ28s', result, len(stock)-64, b'AVBf', old['major'], old['minor'],
                     len(payload), offset, old['size'], old['reserved'])
    check = parse_footer(result)
    if check['metadata'] != old['metadata'] or check['original_size'] != len(payload):
        raise ValueError('AVB envelope retention failed')
    return bytes(result), dict(payload_size=len(payload), vbmeta_offset=offset, vbmeta_size=old['size'],
                              retained_metadata_sha256=hashlib.sha256(old['metadata']).hexdigest(),
                              qualification='Stock metadata retained; its signed hash does not match modified payload; unlocked-device experiment only')
