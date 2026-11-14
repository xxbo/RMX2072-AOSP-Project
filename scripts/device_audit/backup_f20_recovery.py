"""Reacquire one private F.20 recovery set without a duplicate raw super image.

Read-only ADB collection. This does not replace an independent EDL read check.
Never remove the only recovery copy to make room for a test image.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from check_super_chunks import chunks, stock_restore_xml, read_xml, verify, SECTOR, SECTORS

EXPECTED = {
    'boot': '9ae2f907fd029e88c841121f4fbeb6f3a1ae32322a6703d8d142bbba31bb93c3',
    'dtbo': '61d9b3ac8426a886de63cf4cde0552e2cab3cd5c47f83ef4335a624b657949ef',
    'super': 'f7785aedd24616b251143cbcf6006612274b1cae9dac8dea1f634c5800c50532',
}


def adb(serial, command):
    return ['adb', '-s', serial, 'exec-out', 'su -c ' + shlex.quote(command)]


def query(serial, command):
    return subprocess.check_output(adb(serial, command), timeout=180).decode().strip()


def copy_exact(stream, target, length):
    digest = hashlib.sha256()
    remaining = length
    with target.open('xb') as out:
        while remaining:
            data = stream.read(min(4 * 1024 * 1024, remaining))
            if not data:
                raise ValueError('Incomplete partition read: ' + target.name)
            out.write(data)
            digest.update(data)
            remaining -= len(data)
    return digest.hexdigest()


def acquire(serial, output):
    if output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('Recovery bytes must remain outside the repository')
    identity = query(serial, 'getprop ro.product.model; getprop ro.build.display.id; '
                     'getprop sys.boot_completed; cat /proc/sys/kernel/random/boot_id').splitlines()
    if identity[:3] != ['RMX2072', 'RMX2072_11_F.20', '1']:
        raise ValueError('Expected the running F.20 RMX2072')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, utc=datetime.now(timezone.utc).isoformat(),
                  identity=identity, acquisition='read-only Android ADB',
                  edl_independent_verification=False, partitions={})
    for name, expected in EXPECTED.items():
        device = '/dev/block/by-name/' + name
        length = int(query(serial, 'blockdev --getsize64 ' + device))
        if name == 'super' and length != SECTOR * SECTORS:
            raise ValueError('Unexpected super geometry')
        outputs = [(filename, count * SECTOR) for filename, _, count in chunks()] \
            if name == 'super' else [(name + '.img', length)]
        with subprocess.Popen(adb(serial, 'cat ' + device), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as proc:
            try:
                for filename, size in outputs:
                    copy_exact(proc.stdout, output / filename, size)
                    print('Saved', filename, size, flush=True)
                if proc.stdout.read(1):
                    raise ValueError('Partition exceeds expected length')
                error = proc.stderr.read()
                if proc.wait(timeout=30):
                    raise RuntimeError('ADB read failed: ' + error.decode(errors='replace'))
            except BaseException:
                proc.kill()
                raise
        if name == 'super':
            measurement = verify(output, expected)
        else:
            with (output / (name + '.img')).open('rb') as saved:
                digest = hashlib.file_digest(saved, 'sha256').hexdigest()
            if digest != expected:
                raise ValueError('Saved ' + name + ' differs from recorded F.20 bytes')
            measurement = dict(bytes=length, sha256=digest)
        remote = query(serial, 'sha256sum ' + device).split()[0]
        if remote != expected:
            raise ValueError('Independent device-side digest mismatch: ' + name)
        report['partitions'][name] = dict(**measurement, device_sha256=remote)
        (output / 'acquisition.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'stock-super-read.xml').write_bytes(read_xml())
    (output / 'stock-super-restore.xml').write_bytes(stock_restore_xml())
    print('All three partitions match the prior verified F.20 baseline.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    acquire(args.serial, args.output)
