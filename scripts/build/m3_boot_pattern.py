"""Deterministic diagnostic input for the unchanged GSI BootAnimation renderer.

This is a static RGB/geometry test, not an Android boot-completion indicator.
Use the standard OEM archive location through a read-only vendor subtree bind.
No external image or binary input is required.
"""
import io
import struct
import zipfile
import zlib

WIDTH, HEIGHT = 1080, 2400
COLORS = ((255, 0, 0), (0, 255, 0), (0, 0, 255),
          (255, 255, 0), (0, 255, 255), (255, 0, 255))


def pixel(x, y):
    if x < 16 or x >= WIDTH-16 or y < 16 or y >= HEIGHT-16:
        return (255, 255, 255)
    if y < 160:
        return (255, 255, 255)
    if y >= HEIGHT-160:
        return (32, 32, 32)
    # An asymmetric white marker identifies the top-left orientation.
    if 48 <= x < 128 and 192 <= y < 384:
        return (255, 255, 255)
    if 300 <= x < 780 and 1000 <= y < 1400:
        return (255, 255, 255) if 1040 <= y < 1080 or 1160 <= y < 1200 else (0, 0, 0)
    return COLORS[x // 180]


def png_bytes():
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    rows = bytearray()
    for y in range(HEIGHT):
        rows.append(0)  # PNG filter None
        for x in range(WIDTH):
            rows.extend(pixel(x, y))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def archive_bytes():
    image = png_bytes()
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        for name, data in (('desc.txt', b'1080 2400 1\np 0 0 part0\n'),
                           ('part0/00000.png', image), ('part0/00001.png', image)):
            entry = zipfile.ZipInfo(name, (2009, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_STORED
            archive.writestr(entry, data)
    return result.getvalue()
