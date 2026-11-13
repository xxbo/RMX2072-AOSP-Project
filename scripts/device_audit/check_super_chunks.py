"""Generate read-only Firehose requests and verify a complete RMX2072 super read."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

# F.20 sda10: sysfs start and length are in 512-byte sectors. Firehose uses
# the 4096-byte UFS logical sector size. The device is LUN 0.
SECTOR = 4096
FIRST = 193032
SECTORS = 2164736
CHUNK = 131072


def chunks():
    for index,offset in enumerate(range(0,SECTORS,CHUNK)):
        yield f'super-read-{index:02d}.bin', FIRST+offset, min(CHUNK, SECTORS-offset)


def read_xml():
    root = ET.Element('data')
    for name,first,count in chunks():
        ET.SubElement(root,'read',dict(SECTOR_SIZE_IN_BYTES=str(SECTOR),filename=name,
                     physical_partition_number='0',start_sector=str(first),
                     num_partition_sectors=str(count),label='super'))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def verify(directory, expected):
    full = hashlib.sha256()
    parts = []
    for name,_,count in chunks():
        path = directory/name
        if not path.is_file() or path.stat().st_size != count*SECTOR:
            raise ValueError('Missing or incomplete Firehose read: '+name)
        digest = hashlib.sha256()
        with path.open('rb') as src:
            while data := src.read(4*1024*1024):
                digest.update(data)
                full.update(data)
        parts.append(dict(bytes=count*SECTOR,sha256=digest.hexdigest()))
    if full.hexdigest()!=expected:
        raise ValueError('Firehose bytes differ from the complete Android backup')
    return dict(bytes=SECTORS*SECTOR,sha256=full.hexdigest(),parts=parts)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='op',required=True)
    commands.add_parser('xml').add_argument('--output',type=Path,required=True)
    check = commands.add_parser('verify')
    check.add_argument('--directory',type=Path,required=True)
    check.add_argument('--sha256',required=True)
    args = parser.parse_args()
    if args.op=='xml':
        with args.output.open('xb') as out:
            out.write(read_xml())
    else:
        print(json.dumps(verify(args.directory,args.sha256),indent=2))
