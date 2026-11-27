"""Verify pinned QCA6390 boot firmware; deliberately exclude board/calibration data."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'ath11k/QCA6390/hw2.0/'
NAMES = {'amss.bin', 'm3.bin', 'Notice.txt', 'LICENSE.QualcommAtheros_ath10k'}


def ramdisk_manifest(path):
    """Inspect actual newc members, not just the builder's provenance JSON."""
    data = gzip.decompress(path.read_bytes())
    pos, entries = 0, {}
    while pos + 110 <= len(data):
        if data[pos:pos+6] != b'070701':
            raise ValueError('Invalid newc header')
        fields = [int(data[pos+6+n*8:pos+14+n*8], 16) for n in range(13)]
        size, namesize = fields[6], fields[11]
        name_end = pos + 110 + namesize
        start = (name_end + 3) & ~3
        end = start + size
        if namesize < 1 or end > len(data) or data[name_end-1] != 0:
            raise ValueError('Truncated newc member')
        name = data[pos+110:name_end-1].decode('utf-8')
        if name == 'TRAILER!!!':
            return entries
        if name in entries or name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Duplicate or unsafe newc member')
        entries[name] = dict(mode=fields[1], uid=fields[2], gid=fields[3], bytes=size,
                             sha256=hashlib.sha256(data[start:end]).hexdigest())
        pos = (end + 3) & ~3
    raise ValueError('Missing newc trailer')


def verify_ramdisk_firmware(manifest, proof):
    names = {'lib/firmware/'+n for n in proof['files']}
    prefix = 'lib/firmware/'+PREFIX
    actual = {n for n,e in manifest.items() if n.startswith(prefix) and e['mode'] & 0o170000 != 0o040000}
    if actual != names:
        raise ValueError('Ramdisk WLAN firmware set differs; board data must be absent')
    for name,entry in proof['files'].items():
        if manifest['lib/firmware/'+name] != dict(mode=0o100644,uid=0,gid=0,
                                                bytes=entry['bytes'],sha256=entry['sha256']):
            raise ValueError('Ramdisk WLAN payload mismatch: '+name)


def wifi_firmware(directory):
    pin = json.loads((ROOT/'build/device/m3-wifi-firmware-source-2026-11-25.json').read_text())
    if set(pin['files']) != NAMES:
        raise ValueError('Unexpected WLAN boot firmware file set')
    payloads, entries = {}, {}
    for name, entry in pin['files'].items():
        data = (directory/name).read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('WLAN firmware digest mismatch: ' + name)
        blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if blob != entry['git_blob']:
            raise ValueError('WLAN upstream Git blob mismatch: ' + name)
        payloads[PREFIX+name] = data
        entries[PREFIX+name] = dict(entry, origin='linux-firmware', commit=pin['commit'])
    proof = dict(files=entries, board_data_included=False, calibration_data_included=False,
                 partition_backup=False,
                 scope='QCA6390 hw2.0 boot firmware only; QMI board identity and board-data compatibility remain untested')
    return payloads, proof


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    a=p.parse_args()
    files,proof=wifi_firmware(a.directory)
    print(json.dumps(dict(files=len(files),bytes=sum(map(len,files.values())),proof=proof)))


if __name__ == '__main__':
    main()
