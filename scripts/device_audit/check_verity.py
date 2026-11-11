"""Validate the F.20 normal-boot AVB metadata and capture its live verity filesystems."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

NORMAL = ('vbmeta', 'boot', 'dtbo', 'vbmeta_system', 'vbmeta_vendor')
DIGEST = 'c7e079f263ab8df3bf215863dbdbdc928fd7e6ec04bd53dae451148a89d7b6dc'
ROOT_KEY = '2605744918d80c93a084ea53794358fe064c43fb8121793afc39cf8b731c2855'
TARGETS = {'system': ('vbmeta_system', '/', 'erofs', ('system/bin/init', 'system/build.prop')),
           'vendor': ('vbmeta_vendor', '/vendor', 'erofs', ('build.prop', 'etc/fstab.qcom')),
           'product': ('vbmeta_system', '/product', 'ext4', ('etc/build.prop', 'etc/apns-conf.xml'))}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def field(data, offset, size):
    require(offset <= len(data) and size <= len(data)-offset, 'AVB field outside its block')
    return data[offset:offset+size]


def verified_vbmeta(data):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    require(len(data) >= 256 and data[:4] == b'AVB0', 'Missing AVB header')
    header = data[:256]
    auth_size, aux_size, algorithm = struct.unpack_from('>QQI', header, 12)
    require(algorithm in (1, 2) and auth_size % 64 == aux_size % 64 == 0, 'Unsupported F.20 AVB algorithm or alignment')
    require(struct.unpack_from('>I', header, 120)[0] == 0, 'AVB flags disable verification')
    auth = field(data, 256, auth_size)
    aux = field(data, 256+auth_size, aux_size)
    ho, hs, so, ss, ko, ks, _, _, do, ds = struct.unpack_from('>10Q', header, 32)
    bits = {1: 2048, 2: 4096}[algorithm]
    width = bits//8
    key = field(aux, ko, ks)
    require(len(key) == 8+2*width and int.from_bytes(key[:4], 'big') == bits, 'Unexpected AVB RSA key shape')
    modulus = int.from_bytes(key[8:8+width], 'big')
    require(modulus.bit_length() == bits and ss == width, 'Unexpected AVB RSA signature width')
    message = header+aux
    require(field(auth, ho, hs) == hashlib.sha256(message).digest(), 'AVB authentication hash mismatch')
    rsa.RSAPublicNumbers(65537, modulus).public_key().verify(field(auth, so, ss), message, padding.PKCS1v15(), hashes.SHA256())
    body = field(aux, do, ds)
    offset = 0
    chains, trees = {}, {}
    while offset < len(body):
        tag, length = struct.unpack('>QQ', field(body, offset, 16))
        require(length % 8 == 0, 'Misaligned AVB descriptor')
        desc = field(body, offset+16, length)
        offset += 16+length
        if tag == 4:
            location, nl, kl = struct.unpack('>III', field(desc, 0, 12))
            name = field(desc, 76, nl).decode('ascii')
            require(name not in chains, 'Duplicate chain descriptor')
            chains[name] = (location, field(desc, 76+nl, kl))
        elif tag == 1:
            version, image, tree, tree_size, db, hb, roots, fec, fec_size = struct.unpack('>IQQQIIIQQ', field(desc, 0, 56))
            alg = field(desc, 56, 32).rstrip(b'\0').decode('ascii')
            nl, sl, rl, flags = struct.unpack('>IIII', field(desc, 88, 16))
            name = field(desc, 164, nl).decode('ascii')
            require(name not in trees, 'Duplicate hashtree descriptor')
            trees[name] = dict(version=version, image_bytes=image, tree_offset=tree, tree_bytes=tree_size,
                data_block_bytes=db, hash_block_bytes=hb, fec_roots=roots, fec_offset=fec, fec_bytes=fec_size,
                algorithm=alg, salt=field(desc,164+nl,sl).hex(), root_digest=field(desc,164+nl+sl,rl).hex(), flags=flags)
    return header+auth+aux, key, chains, trees


def verified_chain(images):
    parsed = {n: verified_vbmeta(data) for n, data in images.items()}
    root, key, chains, _ = parsed['vbmeta']
    require(sha(key) == ROOT_KEY, 'Unexpected F.20 root key fingerprint')
    require(list(chains) == ['boot','dtbo','recovery','vbmeta_system','vbmeta_vendor'], 'Unexpected F.20 chain order')
    require(len({loc for loc, _ in chains.values()}) == len(chains), 'Duplicate rollback index locations')
    for name, (_, expected) in chains.items():
        require(parsed[name][1] == expected, 'Chained key mismatch: '+name)
    digest_input = b''.join(parsed[n][0] for n in NORMAL)
    require(sha(digest_input) == DIGEST, 'Mismatch against the F.20 normal-boot vbmeta digest')
    return parsed, len(digest_input)


def verity_args(t, dev, full_size):
    db, hb = t['data_block_bytes'], t['hash_block_bytes']
    size, tree, fec = t['image_bytes'], t['tree_offset'], t['fec_offset']
    alg = t['algorithm']
    require(t['version'] == 1 and db == hb == 4096 and t['flags'] == 0 and alg in ('sha256','sha1'),
            'Unsupported F.20 hashtree')
    require(size == tree and size > 0 and size % db == 0 and t['tree_bytes'] > 0 and t['tree_bytes'] % hb == 0
            and tree+t['tree_bytes'] == fec and t['fec_roots'] == 2 and t['fec_bytes'] > 0
            and fec+t['fec_bytes'] <= full_size, 'Hashtree or FEC range mismatch')
    require(len(t['root_digest']) == hashlib.new(alg).digest_size*2 and t['salt'], 'Invalid root digest or salt')
    return ['1',dev,dev,str(db),str(hb),str(size//db),str(tree//hb),alg,t['root_digest'],t['salt']]


def capture(serial):
    def shell(cmd):
        return subprocess.check_output(['adb','-s',serial,'exec-out',"su -c '"+cmd+"'"],timeout=150)
    def val(cmd):
        return shell(cmd).decode().strip()
    def image(name):
        dev = '/dev/block/bootdevice/by-name/'+name
        size = int(val('blockdev --getsize64 '+dev))
        if name.startswith('vbmeta'):
            require(size == 65536, 'Unexpected physical vbmeta partition size')
            raw = shell('cat '+dev)
            require(len(raw) == size, 'Incomplete vbmeta read')
            return raw
        footer = shell(f'dd if={dev} bs=4096 skip={size//4096-1} count=1 2>/dev/null')[-64:]
        require(len(footer) == 64 and footer[:4] == b'AVBf', 'Missing chained metadata footer: '+name)
        offset, length = struct.unpack_from('>QQ', footer, 20)
        require(256 <= length <= 65536 and offset+length <= size-64, 'Invalid embedded vbmeta bounds')
        raw = shell(f'dd if={dev} bs=4096 skip={offset//4096} count={(offset%4096+length+4095)//4096} 2>/dev/null')
        return field(raw,offset%4096,length)
    require(val('getprop ro.product.model; getprop ro.build.display.id; getprop sys.boot_completed').split() ==
            ['RMX2072','RMX2072_11_F.20','1'], 'Expected a booted F.20')
    images = {n:image(n) for n in (*NORMAL,'recovery')}
    parsed, total = verified_chain(images)
    require(val('getprop ro.boot.vbmeta.digest') == DIGEST and int(val('getprop ro.boot.vbmeta.size')) == total,
            'Bootloader vbmeta digest or size mismatch')
    mounts = [s.split() for s in val('cat /proc/1/mounts').splitlines()]
    part = {}
    for name,(parent,where,fs,files) in TARGETS.items():
        t = parsed[parent][3][name]
        base = '/dev/block/mapper/'+name
        linear = val('readlink -f '+base).split('/')[-1]
        dev = val('cat /sys/class/block/'+linear+'/dev')
        args = verity_args(t,dev,int(val('blockdev --getsize64 '+base)))
        fec_blocks = str(t['fec_offset']//t['data_block_bytes'])
        opts = ['10','restart_on_corruption','ignore_zero_blocks','use_fec_from_device',dev,
                'fec_blocks',fec_blocks,'fec_start',fec_blocks,'fec_roots','2']
        table = val('dmctl table '+name+'-verity').splitlines()[-1].split()
        require(table == [f"0-{t['image_bytes']//512}:",'verity,']+args+opts, 'Signed descriptor and F.20 table differ: '+name)
        verified = val('readlink -f '+base+'-verity')
        require(any(m[:3] == [verified,where,fs] and 'ro' in m[3].split(',') for m in mounts), 'Unexpected Android mount: '+name)
        require(val('dmctl status '+name+'-verity').endswith('verity, V'), 'Unhealthy Android verity device: '+name)
        def digest(path):
            h = val('sha256sum '+path).split()[0]
            require(re.fullmatch('[0-9a-f]{64}',h), 'Invalid read digest')
            return h
        part[name] = dict(parent=parent,filesystem=fs,descriptor=t,verified_data_sha256=digest(verified),
                          files={f:digest(where.rstrip('/')+'/'+f) for f in files})
    return dict(normal_vbmeta_sha256=DIGEST, normal_vbmeta_bytes=total, root_key_sha256=ROOT_KEY,
        metadata={n:dict(structure_sha256=sha(v[0]),pubkey_sha256=sha(v[1]),bytes=len(v[0])) for n,v in parsed.items()},
        gpt_vbmeta_sha256={n:sha(images[n]) for n in NORMAL if n.startswith('vbmeta')}, partitions=part)


def verify_trial(ref, metadata, transcript):
    avb = metadata.splitlines()
    lines = transcript.splitlines()
    for name, h in ref['gpt_vbmeta_sha256'].items():
        require(avb.count(f'vbmeta={name} sha256={h}') == 1, 'Live vbmeta mismatch: '+name)
    results = {}
    for name, part in ref['partitions'].items():
        t = part['descriptor']
        table_rows = [s.split() for s in lines if s.startswith('verity_table='+name+' ')]
        sizes = re.findall(r'^mapped='+name+r' sectors=(\d+) ro=1$', transcript, re.M)
        require(len(table_rows) == len(sizes) == 1, 'Missing loaded verity or linear device: '+name)
        row = table_rows[0]
        require(len(row) > 5 and re.fullmatch(r'\d+:\d+',row[5]), 'Invalid backing device')
        dev = row[5]
        core = verity_args(t,dev,int(sizes[0])*512)
        sectors = t['image_bytes']//512
        fec = str(t['fec_offset']//t['data_block_bytes'])
        opts = ['8','use_fec_from_device',dev,'fec_blocks',fec,'fec_start',fec,'fec_roots','2']
        require(row[1:] == ['0',str(sectors),'verity']+core+opts, 'Kernel table differs from descriptor: '+name)
        require(f"verified={name} sectors={sectors} sha256={part['verified_data_sha256']}" in lines,
                'Verified-device hash differs: '+name)
        mount = re.search(r'^mounted=/run/rmx-super/mnt-'+name+r' fs=(\w+) dev=(\d+:\d+) options=(\S+)$',transcript,re.M)
        require(mount and mount[1] == part['filesystem'] and mount[2] != dev
                and {'ro','nodev','nosuid','noexec'} <= set(mount[3].split(',')), 'Unexpected mount: '+name)
        for path, digest in part['files'].items():
            require(f'file={name}/{path} sha256={digest}' in lines, 'Mounted file differs: '+path)
        require(f'health={name} 0 {sectors} verity V 0' in lines and f'verity_cleanup={name} rc=0' in lines,
                'Verity status or cleanup failed: '+name)
        results[name] = dict(filesystem=part['filesystem'],algorithm=t['algorithm'],verified_bytes=t['image_bytes'],
                             whole_device_sha256=part['verified_data_sha256'],files_matched=list(part['files']))
    require('wrong_root=product read=EIO health=C' in lines and
            re.search(r'^reject_read_rc=[1-9]\d*$',transcript,re.M) and
            re.search(r'^reject_status=0 \d+ verity C -$',transcript,re.M), 'Missing wrong-root rejection')
    require('cleanup_status=0' in lines, 'Linear device cleanup failed')
    return results


def verify_odm(serial, ref):
    """Authenticate the footer F.20 actually selects with its vendor fstab key."""
    def read(command):
        return subprocess.check_output(['adb','-s',serial,'exec-out',"su -c '"+command+"'"], timeout=150)

    base = '/dev/block/mapper/odm'
    require(read('getprop ro.build.display.id').strip() == b'RMX2072_11_F.20', 'Expected F.20')
    size = int(read('blockdev --getsize64 '+base))
    require(size == ref['logical_bytes'] and size % 4096 == 0, 'Unexpected ODM size')

    def block(index):
        data = read(f'dd if={base} bs=4096 skip={index} count=1 2>/dev/null')
        require(len(data) == 4096, 'Incomplete ODM block')
        return data

    last = block(size//4096-1)
    require(last[-64:-60] == b'AVBf' and sha(last) == ref['footer_block_sha256'], 'ODM footer mismatch')
    offset, length = struct.unpack_from('>QQ', last, len(last)-44)
    require(offset == 4096*ref['vbmeta_block'] and 256 <= length <= 4096 and offset+length <= size-64,
            'Unexpected ODM vbmeta range')
    page = block(offset//4096)
    structure, key, _, trees = verified_vbmeta(page[:length])
    require(sha(page) == ref['vbmeta_block_sha256'] and sha(structure) == ref['vbmeta_sha256'],
            'ODM vbmeta hash mismatch')
    require(sha(key) == ref['key_sha256'] and key == read('cat /vendor/etc/oplus_avb.pubkey'),
            'ODM signature does not match the vendor key')
    require(trees == {'odm':ref['descriptor']}, 'ODM signed descriptor mismatch')
    tree = trees['odm']
    dev = read('cat /sys/class/block/$(basename $(readlink -f '+base+'))/dev').decode().strip()
    args = verity_args(tree,dev,size)
    fec = str(tree['fec_offset']//tree['data_block_bytes'])
    table = read('dmctl table odm-verity').decode().splitlines()[-1].split()
    require(table == [f"0-{tree['image_bytes']//512}:",'verity,']+args+['10','restart_on_corruption',
            'ignore_zero_blocks','use_fec_from_device',dev,'fec_blocks',fec,'fec_start',fec,'fec_roots','2'],
            'F.20 kernel ODM table differs from its signed footer')
    return dict(signed_vbmeta_sha256=sha(structure), active_root=tree['root_digest'], vendor_key_sha256=sha(key))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest='mode', required=True)
    cap = modes.add_parser('capture')
    cap.add_argument('--serial', required=True)
    cap.add_argument('--output', required=True, type=Path)
    verify = modes.add_parser('verify')
    odm = modes.add_parser('verify-odm')
    odm.add_argument('--serial', required=True)
    odm.add_argument('--reference', required=True, type=Path)
    for name in ('reference','metadata','transcript'):
        verify.add_argument('--'+name, required=True, type=Path)
    args = p.parse_args()
    if args.mode == 'capture':
        args.output.write_text(json.dumps(capture(args.serial),indent=2)+'\n',encoding='utf-8')
    elif args.mode == 'verify-odm':
        print(json.dumps(verify_odm(args.serial, json.loads(args.reference.read_text())), indent=2))
    else:
        result = verify_trial(json.loads(args.reference.read_text()), args.metadata.read_text(), args.transcript.read_text())
        print(json.dumps(result, indent=2))
