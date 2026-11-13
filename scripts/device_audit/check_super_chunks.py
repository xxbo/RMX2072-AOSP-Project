"""Prepare the RMX2072 F.20 stock recovery kit and verify full Firehose readbacks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
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


def stock_restore_xml():
    root = ET.fromstring(read_xml())
    # Geometry and slot metadata share the first chunk. Apply it last.
    first = root[0]
    root.remove(first)
    root.append(first)
    for row in root:
        row.tag='program'
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


def build_stock_kit(backup, directory, out, expected):
    """Package only the original bytes confirmed by both acquisition paths."""
    if backup.stat().st_size != SECTORS*SECTOR:
        raise ValueError('Incomplete stock Android backup')
    with backup.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest() != expected:
            raise ValueError('Android backup digest mismatch')
    manifest = verify(directory,expected)
    if out.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('Use a new private output directory outside the repository')
    out.mkdir(parents=True,exist_ok=False)
    for filename,_,_ in chunks():
        shutil.copyfile(directory/filename,out/filename)
    if verify(out,expected) != manifest:
        raise ValueError('Copied recovery payload differs from the original')
    (out/'stock-super-read.xml').write_bytes(read_xml())
    (out/'stock-super-restore.xml').write_bytes(stock_restore_xml())
    manifest.update(device='RMX2072', firmware='RMX2072_11_F.20', lun=0,
                    first_sector=FIRST, sector_bytes=SECTOR, sectors=SECTORS,
                    restore_xml_sha256=hashlib.sha256((out/'stock-super-restore.xml').read_bytes()).hexdigest())
    (out/'stock-super-kit.json').write_text(json.dumps(manifest,indent=2)+'\n')


def verify_restored_super(kit, readback, expected):
    """Compare a separately acquired post-program readback to the original kit."""
    if readback.resolve() == kit.resolve():
        raise ValueError('Provide the post-program readback directory separately from the kit')
    manifest = json.loads((kit / 'stock-super-kit.json').read_text())
    if manifest['sha256'] != expected:
        raise ValueError('Kit digest differs from the original stock digest')
    measured = verify(readback, expected)
    if measured['bytes'] != manifest['bytes'] or measured['parts'] != manifest['parts']:
        raise ValueError('Readback differs from the original kit manifest')
    return measured


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='op',required=True)
    commands.add_parser('xml').add_argument('--output',type=Path,required=True)
    check = commands.add_parser('verify')
    check.add_argument('--directory',type=Path,required=True)
    check.add_argument('--sha256',required=True)
    kit = commands.add_parser('stock-kit')
    for arg in ('android-backup','directory','output'):
        kit.add_argument('--'+arg,type=Path,required=True)
    kit.add_argument('--sha256',required=True)
    restored = commands.add_parser('verify-restore')
    restored.add_argument('--kit', type=Path, required=True)
    restored.add_argument('--readback', type=Path, required=True)
    restored.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.op=='xml':
        with args.output.open('xb') as out:
            out.write(read_xml())
    elif args.op=='verify':
        print(json.dumps(verify(args.directory,args.sha256),indent=2))
    elif args.op=='verify-restore':
        print(json.dumps(verify_restored_super(args.kit, args.readback, args.sha256), indent=2))
    else:
        build_stock_kit(args.android_backup,args.directory,args.output,args.sha256)
