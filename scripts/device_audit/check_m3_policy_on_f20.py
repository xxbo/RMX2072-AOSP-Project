"""Strictly compile the pinned GSI policy using its own runtime on restored F.20.

Only private temporary files are written. The resulting policy is never loaded;
neither system's enforcing mode nor any partition is changed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--acceleration', action='store_true', help='Include native GPU firmware labels')
    a = p.parse_args()
    w = a.workspace.resolve()
    repo = Path(__file__).resolve().parents[2]
    restored = json.loads((a.record/'restored.json').read_text())
    def shell(command, timeout=30):
        return subprocess.check_output(['adb','-s','3c8304a6','shell','su -c '+shlex.quote(command)],
            timeout=timeout, stderr=subprocess.STDOUT).decode('utf-8',errors='replace').replace('\r','')
    identity = shell('getprop ro.build.display.id; getprop sys.boot_completed; cat /proc/sys/kernel/random/boot_id; getenforce').splitlines()
    if identity != ['RMX2072_11_F.20','1',restored['boot_id'],'Enforcing']:
        raise ValueError('Requires the identified restored F.20 boot')
    reference = json.loads((repo/'build/device/gsi17-mount-reference.json').read_text())
    with (w/'current/system.img').open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest() != reference['image_sha256']:
            raise ValueError('GSI image changed')
    runtime = {'secilc':'/system/bin/secilc','linker64':'/system/bin/bootstrap/linker64',
        **{n:'/system/lib64/bootstrap/'+n for n in ('libc.so','libm.so','libdl.so')}}
    policy = {
        'plat_sepolicy.cil':'/system/etc/selinux/plat_sepolicy.cil',
        '202604.cil':'/system/etc/selinux/mapping/202604.cil',
        'system_ext_sepolicy.cil':'/system/system_ext/etc/selinux/system_ext_sepolicy.cil',
        'product_sepolicy.cil':'/system/product/etc/selinux/product_sepolicy.cil',
        'plat_sepolicy_genfs_202604.cil':'/system/etc/selinux/plat_sepolicy_genfs_202604.cil'}
    payload = {}
    for name,path in dict(runtime,**policy).items():
        data = subprocess.check_output([str(w/'current/fs-tools/debugfs.exe'),'-R','cat '+path,
            str(w/'current/system.img')],stderr=subprocess.DEVNULL)
        if not data or (name in runtime and data[:6] != b'\x7fELF\x02\x01'):
            raise ValueError('Missing GSI input: '+path)
        payload[name] = data
    if sha(payload['secilc']) != 'ace5b9b5b26f28e0c81a070ac2be0106269f6a9f3912c80ea48663706444fac1':
        raise ValueError('Unexpected GSI compiler')
    sys.path.insert(0,str(repo/'scripts/build'))
    from stage_keymaster_reference import inventory
    files,_ = inventory(True,w/'current/rmx-m1-guard')
    cil = files['/etc/selinux/vendor_sepolicy.cil']
    for kind in ('graphics','health','power','audio'):
        cil += (repo/'device/realme/bladerunner_48m/m3-vendor'/(kind+'.cil')).read_bytes().replace(b'\r\n',b'\n')
    if a.acceleration:
        from stage_m3_acceleration import acceleration_policy
        cil = acceleration_policy(cil)
    payload['m3-vendor.cil'] = cil
    payload['plat_pub_versioned.cil'] = files['/etc/selinux/plat_pub_versioned.cil']
    local = w/'current/policy-check/f20-compile'
    local.mkdir(exist_ok=True)
    remote = '/data/local/tmp/rmx-m3-policy-f20'
    shell('mkdir -p '+remote+'; chown shell:shell '+remote+'; chmod 700 '+remote+'; restorecon -RF '+remote)
    for name,data in payload.items():
        path = local/name
        path.write_bytes(data)
        subprocess.run(['adb','-s','3c8304a6','push',str(path),remote+'/'+name],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
    shell('chmod 755 '+remote+'/linker64 '+remote+'/secilc')
    order = ('plat_sepolicy.cil','202604.cil','system_ext_sepolicy.cil','product_sepolicy.cil',
        'plat_pub_versioned.cil','m3-vendor.cil','plat_sepolicy_genfs_202604.cil')
    command = 'LD_LIBRARY_PATH='+remote+' '+remote+'/linker64 '+remote+'/secilc -m -M true -G -c 30 '+\
        ' '.join(remote+'/'+n for n in order)+' -o '+remote+'/policy -f '+remote+'/contexts'
    result = shell('timeout 180 sh -c '+shlex.quote(command),200)
    compiled = shell('sha256sum '+remote+'/policy').split()[0]
    if shell('cat /proc/sys/kernel/random/boot_id; getenforce').splitlines() != [restored['boot_id'],'Enforcing']:
        raise ValueError('Host boot/enforcing changed during compilation')
    (w/'current/policy-check/m3-vendor.cil').write_bytes(cil)
    report = dict(result='PASS_STRICT_COMPILE_ONLY',utc=datetime.now(timezone.utc).isoformat(),
        host_firmware='RMX2072_11_F.20',boot_id=restored['boot_id'],command=command,
        source_gsi_sha256=reference['image_sha256'],compiler_sha256=sha(payload['secilc']),
        compiler_matches_pinned_gsi=True,input_sha256={n:sha(d) for n,d in payload.items()},
        combined_vendor_policy_sha256=sha(cil),compiled_policy_sha256=compiled,
        cil_statements_match_current_sources=True,loaded=False,compiler_output=result,
        scope='Pinned Android 17 compiler/runtime on restored F.20; neverallow enabled; no policy load or enforcing change')
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    # Remove only the explicit private scratch filenames created by this tool.
    shell('rm -f '+' '.join(remote+'/'+n for n in (*payload,'policy','contexts'))+'; rmdir '+remote)
    print(json.dumps(dict(result=report['result'],compiled_policy_sha256=compiled)))


if __name__ == '__main__':
    main()
