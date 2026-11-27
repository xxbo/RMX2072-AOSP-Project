"""Verify QCA6390 boot firmware and an optional exact same-handset board ELF."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct

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
        raise ValueError('Ramdisk WLAN firmware set differs from the reviewed payload')
    for name,entry in proof['files'].items():
        if manifest['lib/firmware/'+name] != dict(mode=0o100644,uid=0,gid=0,
                                                bytes=entry['bytes'],sha256=entry['sha256']):
            raise ValueError('Ramdisk WLAN payload mismatch: '+name)


def board_firmware(path):
    pin = json.loads((ROOT/'build/device/m3-wifi-firmware-source-2026-11-25.json').read_text())['board_candidate']
    data = path.read_bytes()
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('Expected the unchanged same-handset F.20 ODM board ELF')
    if not 84 <= len(data) <= 256*1024 or data[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('Board data must retain its bounded ELF32 little-endian wrapper')
    kind, machine, version, entry, phoff, _, _, ehsize, phsize, phnum, *_ = struct.unpack_from('<HHIIIIIHHHHHH', data, 16)
    if (kind, machine, version, ehsize, phsize, phnum) != (2, 40, 1, 52, 32, 1) or phoff+32 > len(data):
        raise ValueError('Unexpected board ELF program header')
    ptype, offset, vaddr, paddr, size, memsize, flags, align = struct.unpack_from('<IIIIIIII', data, phoff)
    if (ptype != 1 or not size or size > memsize or offset+size > len(data)
            or offset < phoff+phsize or flags != 6 or align != 1024):
        raise ValueError('Unexpected or truncated board ELF LOAD segment')
    # The entire ELF is sent as QMI BDF_TYPE_ELF. Do not extract its .data,
    # patch a board ID, change a MAC or add caldata from another device.
    return data, dict(bytes=len(data), sha256=pin['sha256'], origin=pin['origin'],
        source_name='bdwlan.elf', target_name='board.bin', elf_wrapper_preserved=True,
        elf=dict(machine=machine, entry=entry, segment_offset=offset, segment_bytes=size,
                 vaddr=vaddr, paddr=paddr), acceptance='NOT RUN')


def wifi_firmware(directory, board_file=None):
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
    if board_file is not None:
        board, entry = board_firmware(board_file)
        payloads[PREFIX+'board.bin'] = board
        entries[PREFIX+'board.bin'] = entry
        proof.update(board_data_included=True, calibration_data_included=None,
            separate_calibration_file_included=False,
            scope='Exact same-handset F.20 board ELF via ath11k API1; internal calibration contents not decoded; firmware acceptance and RF remain untested')
    return payloads, proof


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--board-file',type=Path,help='Exact retained F.20 ODM bdwlan.elf, preserved whole')
    a=p.parse_args()
    files,proof=wifi_firmware(a.directory,a.board_file)
    print(json.dumps(dict(files=len(files),bytes=sum(map(len,files.values())),proof=proof)))


if __name__ == '__main__':
    main()
