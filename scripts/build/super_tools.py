"""Fetch or verify the Alpine aarch64 ELF files for the F.20 super diagnostic."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import urllib.request


LOCK = Path(__file__).resolve().parents[2] / 'build/super-readonly-apks.json'


def read_tools(cache, download=False):
    lock = json.loads(LOCK.read_text())
    binaries = {}
    for relative, expected, members in lock['packages']:
        apk = cache / Path(relative).name
        data = apk.read_bytes() if apk.exists() else b''
        if download and hashlib.sha256(data).hexdigest() != expected:
            with urllib.request.urlopen(lock['base_url'] + relative, timeout=90) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f'Download checksum mismatch: {apk.name}')
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as partial:
                partial.write(data)
            Path(partial.name).replace(apk)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'APK checksum mismatch: {apk.name}')
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz', ignore_zeros=True) as archive:
            for name, member in members.items():
                if name in binaries or Path(name).name != name:
                    raise ValueError(f'Invalid runtime filename: {name}')
                elf = archive.extractfile(member).read()
                if elf[:6] != b'\x7fELF\x02\x01' or int.from_bytes(elf[18:20], 'little') != 183:
                    raise ValueError(f'Expected aarch64 ELF: {name}')
                binaries[name] = elf
    return binaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    print(f'{len(read_tools(args.cache, download=True))} verified ARM64 runtime files')
