"""Build and roll back an RMX2072 layout in a new regular host file."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct

from check_super import BLOCK, PREFIX, SLOT_BYTES, SLOTS, prefix_checks

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT/'build/device'
SECTOR = 512
PART = struct.Struct('<36s4I')
EXTENT = struct.Struct('<QIQI')
GROUP = struct.Struct('<36sIQ')
DEVICE = struct.Struct('<QIIQ36sI')


def name(raw):
    return raw.split(b'\0',1)[0].decode('ascii')


def read_metadata(prefix, slot):
    start = 3*BLOCK + slot*SLOT_BYTES
    meta = prefix[start:start+SLOT_BYTES]
    header = meta[:128]
    tables = []
    for i, fmt in enumerate((PART, EXTENT, GROUP, DEVICE)):
        offset, count, size = struct.unpack_from('<3I',header,80+i*12)
        if size != fmt.size or offset+count*size > struct.unpack_from('<I', header,44)[0]:
            raise ValueError('Invalid LP table descriptor')
        tables.append(list(fmt.iter_unpack(meta[128+offset:128+offset+count*size])))
    parts, extents, groups, devices = tables
    if len(devices) != 1 or name(devices[0][4]) != 'super':
        raise ValueError('Expected one physical super device')
    layout = {}
    for label, attr, first, count, group in parts:
        spans = extents[first:first+count]
        if len(spans) != count or not count or any(kind or source for _,kind,_,source in spans):
            raise ValueError('Expected allocated linear extents on super')
        layout[name(label)] = [(physical,length) for length,_,physical,_ in spans]
    return header, parts, groups, devices, layout


def allocate(available, count):
    spans = []
    for i,(start,length) in enumerate(available):
        if not length:
            continue
        n = min(length,count)
        spans.append((start,n))
        available[i] = (start+n,length-n)
        count -= n
        if not count:
            return spans
    raise ValueError('No aligned physical space for both images')


def make_candidate(prefix, sizes):
    hdr,parts,groups,devices,active = read_metadata(prefix,0)
    other = read_metadata(prefix,1)[-1]
    first,alignment,offset,capacity,_,_ = devices[0]
    # Protect retained data in both metadata views. The inactive F.20
    # system overlaps slot 0 partitions and cannot serve as a rollback image.
    protected = [extent for layout,skip in ((active,{'system','vendor','my_stock'}),(other,{'system'}))
                 for part,spans in layout.items() if part not in skip for extent in spans]
    free = []
    end = first
    for start,length in sorted(protected)+[(capacity//SECTOR,0)]:
        aligned = end + ((offset//SECTOR-end) % (alignment//SECTOR))
        if start > aligned:
            free.append((aligned,start-aligned))
        end = max(end,start+length)
    # Allocate each new extent on the advertised alignment, including the
    # remainder of a hole used by the other target.
    targets = {}
    for part in ('vendor','system'):
        targets[part] = allocate(free,sizes[part]//SECTOR)
        for i,(start,length) in enumerate(free):
            pad = min(length,(offset//SECTOR-start) % (alignment//SECTOR))
            free[i] = (start+pad,length-pad)
    new_parts, new_extents = [], []
    for label,attr,_,_,group in parts:
        part = name(label)
        if part == 'my_stock':
            continue
        spans = targets.get(part,active[part])
        new_parts.append(PART.pack(label,attr,len(new_extents),len(spans),group))
        new_extents.extend(EXTENT.pack(length,0,start,0) for start,length in spans)
    sections = [b''.join(new_parts),b''.join(new_extents),b''.join(GROUP.pack(*g) for g in groups),
                b''.join(DEVICE.pack(*d) for d in devices)]
    hdr = bytearray(hdr)
    pos = 0
    for i,(section,fmt) in enumerate(zip(sections,(PART,EXTENT,GROUP,DEVICE))):
        struct.pack_into('<3I',hdr,80+i*12,pos,len(section)//fmt.size,fmt.size)
        pos += len(section)
    blob = b''.join(sections)
    struct.pack_into('<I',hdr,44,len(blob))
    hdr[48:80] = hashlib.sha256(blob).digest()
    hdr[12:44] = bytes(32)
    hdr[12:44] = hashlib.sha256(hdr).digest()
    body = hdr+blob
    if len(body)>SLOT_BYTES:
        raise ValueError('Slot 0 metadata does not fit')
    result = bytearray(prefix)
    for slot in (0,SLOTS):
        at = 3*BLOCK+slot*SLOT_BYTES
        result[at:at+SLOT_BYTES] = body.ljust(SLOT_BYTES,b'\0')
    prefix_checks(result)
    new_layout = read_metadata(result,0)[-1]
    max_size = next(size for g,_,size in groups if name(g)=='qti_dynamic_partitions')
    new_total = sum(length*SECTOR for spans in new_layout.values() for _,length in spans)
    if new_total > max_size:
        raise ValueError('Group limit exceeded')
    return result,targets,max_size,new_total


def transfer(f, count, *, target=None, hasher=None):
    while count:
        data = f.read(min(count,4*1024*1024))
        if not data:
            raise ValueError('Truncated input')
        if target is not None:
            target.write(data)
        if hasher is not None:
            hasher.update(data)
        count -= len(data)


def partition_hashes(f, layout):
    hashes = {}
    for part,spans in layout.items():
        h = hashlib.sha256()
        for start,count in spans:
            f.seek(start*SECTOR)
            transfer(f,count*SECTOR,hasher=h)
        hashes[part] = h.hexdigest()
    return hashes


def file_hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def rehearse(stock, system, vendor, out, expected):
    if any(not stat.S_ISREG(p.stat().st_mode) for p in (stock,system,vendor)):
        raise ValueError('Inputs must be regular files')
    ref = json.loads((REFERENCE/'super-readonly-2026-11-10.json').read_text())
    gsi = json.loads((REFERENCE/'gsi17-mount-reference.json').read_text())
    control = json.loads((REFERENCE/'gsi17-enforcing-second-stage-2026-11-12.json').read_text())['trials'][-1]
    sizes = dict(system=system.stat().st_size,vendor=vendor.stat().st_size)
    if (stock.stat().st_size != ref['super_bytes'] or file_hash(stock)!=expected or
        sizes != dict(system=gsi['image_bytes'],vendor=2*1024*1024)):
        raise ValueError('Unexpected original super or target image size')
    pinned = dict(system=gsi['image_sha256'],vendor=control['vendor_image_sha256'])
    with stock.open('rb') as f:
        prefix = f.read(PREFIX)
        if prefix_checks(prefix)['prefix_sha256'] != ref['prefix_sha256']:
            raise ValueError('Unexpected stock geometry or LP metadata')
        layouts = [read_metadata(prefix,i)[-1] for i in range(SLOTS)]
        before = [partition_hashes(f,layout) for layout in layouts]
    for part,item in ref['linear_devices'].items():
        if before[0][part] != item['sha256']:
            raise ValueError('Stock logical partition mismatch: '+part)
    candidate,targets,limit,new_total = make_candidate(prefix,sizes)
    out = out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError('Use a new private directory outside the repository')
    out.mkdir(parents=True,exist_ok=False)
    disk = out/'working-super.raw'
    (out/'candidate-prefix.bin').write_bytes(candidate)
    with disk.open('xb') as dst, stock.open('rb') as src:
        shutil.copyfileobj(src,dst,4*1024*1024)
    with disk.open('r+b') as dst:
        dst.write(candidate)
        for part, image in (('vendor',vendor),('system',system)):
            h = hashlib.sha256()
            with image.open('rb') as src:
                for start,length in targets[part]:
                    dst.seek(start*SECTOR)
                    transfer(src,length*SECTOR,target=dst,hasher=h)
            if h.hexdigest() != pinned[part]:
                raise ValueError('Wrong target image: '+part)
        dst.seek(0)
        parsed = dst.read(PREFIX)
        prefix_checks(parsed)
        after = [partition_hashes(dst,read_metadata(parsed,i)[-1]) for i in range(SLOTS)]
    if (after[0] != {**{n:h for n,h in before[0].items() if n!='my_stock'},**pinned}
        or [n for n,h in after[1].items() if before[1][n]!=h] != ['system']):
        raise ValueError('Unexpected logical partition changes')
    candidate_sha = file_hash(disk)
    with disk.open('r+b') as dst, stock.open('rb') as src:
        shutil.copyfileobj(src,dst,4*1024*1024)
    if file_hash(disk) != expected:
        raise ValueError('Full host-file rollback failed')
    stock_total = sum(n*SECTOR for spans in layouts[0].values() for _,n in spans)
    keep_all = stock_total + sum(sizes.values()) - sum(n*SECTOR for p in sizes for _,n in layouts[0][p])
    return dict(source_bytes=stock.stat().st_size,source_sha256=expected,target_bytes=sizes,
                target_sha256=pinned,group_limit_bytes=limit,stock_allocated_bytes=stock_total,
                shortfall_with_both_targets_keeping_other_partitions=keep_all-limit,
                candidate_allocated_bytes=new_total,candidate_group_headroom_bytes=limit-new_total,
                slot0_removed=['my_stock'],slot0_replaced=['system','vendor'],
                slot1_metadata_preserved=True,slot1_payloads_changed=['system'],
                partitions_before=before,partitions_after=after,targets_in_512_byte_sectors=targets,
                candidate_prefix_sha256=hashlib.sha256(candidate).hexdigest(),candidate_full_sha256=candidate_sha,
                restored_regular_file_sha256=expected)


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('stock','system','vendor','private-out'):
        p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--stock-sha256',required=True)
    a=p.parse_args()
    result=rehearse(a.stock,a.system,a.vendor,a.private_out,a.stock_sha256)
    (a.private_out/'rehearsal.json').write_text(json.dumps(result,indent=2)+'\n')
