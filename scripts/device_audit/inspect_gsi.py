#!/usr/bin/env python3
"""Verify the selected official GSI ZIP and extract images locally; never flashes."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import zipfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def image_info(path):
    with path.open('rb') as stream:
        header = stream.read(4096)
    result = dict(size_bytes=path.stat().st_size, sha256=sha256(path))
    if header[:4] == b'\x3a\xff\x26\xed':
        magic, major, minor, file_header, chunk_header, block, blocks, chunks, checksum = struct.unpack_from('<I4H4I', header)
        if major != 1 or file_header < 28 or chunk_header < 12 or block == 0:
            raise ValueError('unsupported Android sparse header')
        result.update(format='android-sparse', expanded_size_bytes=block*blocks, block_size=block, chunks=chunks)
    elif header[1080:1082] == b'\x53\xef':
        result.update(format='ext4', expanded_size_bytes=result['size_bytes'])
    elif header[1024:1028] == b'\xe2\xe1\xf5\xe0':
        result.update(format='erofs', expanded_size_bytes=result['size_bytes'])
    elif header[:4] == b'AVB0':
        result.update(format='avb-vbmeta')
    else:
        result.update(format='unknown')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    project = pathlib.Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == project or project in output.parents:
        parser.error('GSI images must remain outside the public checkout')
    lock = json.loads((project/'build/gsi.json').read_text())
    actual = sha256(args.archive)
    if actual != lock['sha256']:
        raise ValueError('GSI ZIP SHA-256 mismatch; extraction refused')
    output.mkdir(parents=True, exist_ok=True)
    report = dict(selection=lock, archive_sha256=actual, zip_files=[], images={}, status='hash-verified-not-flashed')
    with zipfile.ZipFile(args.archive) as archive:
        entries = archive.infolist()
        report['zip_files'] = [dict(name=e.filename, size_bytes=e.file_size, compressed_bytes=e.compress_size) for e in entries]
        images = [e for e in entries if pathlib.PurePosixPath(e.filename).name in ('system.img', 'vbmeta.img')]
        if sum(pathlib.PurePosixPath(e.filename).name == 'system.img' for e in images) != 1:
            raise ValueError('expected exactly one system.img')
        if len({pathlib.PurePosixPath(e.filename).name for e in images}) != len(images):
            raise ValueError('ambiguous image names')
        if shutil.disk_usage(output).free < sum(e.file_size for e in images)+1024**3:
            raise ValueError('insufficient free space to extract GSI images')
        for entry in images:
            name = pathlib.PurePosixPath(entry.filename).name
            dest = output/name
            with archive.open(entry) as source, dest.open('wb') as target:
                shutil.copyfileobj(source, target, 8*1024*1024)
            report['images'][name] = image_info(dest)
    (output/'inspection.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report['images'], indent=2))


if __name__ == '__main__':
    main()
