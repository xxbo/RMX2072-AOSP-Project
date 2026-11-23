"""Strictly compile a candidate policy in private scratch on the running GSI.

Uses the pinned GSI compiler and policy inputs, with neverallow checks enabled.
Does not load the output, change enforcing, or require a stock-system reboot.
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
    p.add_argument('--boot-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    work = a.workspace.resolve()
    repo = Path(__file__).resolve().parents[2]
    adb = ['adb', '-s', 'RMX2072-M1']

    def shell(command, timeout=30):
        return subprocess.check_output(adb + ['shell', command], timeout=timeout,
            stderr=subprocess.STDOUT).decode('utf-8', errors='replace').replace('\r', '')

    identity = 'getprop ro.build.version.sdk; getprop sys.boot_completed; cat /proc/sys/kernel/random/boot_id; getenforce'
    expected = ['37', '1', a.boot_id, 'Enforcing']
    if shell(identity).splitlines() != expected:
        raise ValueError('Requires the identified boot-complete enforcing Android 17 GSI')
    reference = json.loads((repo/'build/device/gsi17-mount-reference.json').read_text())
    with (work/'current/system.img').open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != reference['image_sha256']:
            raise ValueError('Pinned GSI image changed')
    paths = {
        'secilc': '/system/bin/secilc',
        'plat_sepolicy.cil': '/system/etc/selinux/plat_sepolicy.cil',
        '202604.cil': '/system/etc/selinux/mapping/202604.cil',
        'system_ext_sepolicy.cil': '/system/system_ext/etc/selinux/system_ext_sepolicy.cil',
        'product_sepolicy.cil': '/system/product/etc/selinux/product_sepolicy.cil',
        'plat_sepolicy_genfs_202604.cil': '/system/etc/selinux/plat_sepolicy_genfs_202604.cil',
    }
    payload = {}
    for name, path in paths.items():
        data = subprocess.check_output([str(work/'current/fs-tools/debugfs.exe'), '-R',
            'cat '+path, str(work/'current/system.img')], stderr=subprocess.DEVNULL)
        if not data:
            raise ValueError('Missing pinned GSI input: '+path)
        # The live system has /system_ext and /product mount aliases.
        live = path.replace('/system/system_ext/', '/system_ext/').replace('/system/product/', '/product/')
        # shell cannot read the installed secilc executable under enforcing.
        # Its extracted copy is pinned below; all live policy inputs are read.
        if name != 'secilc' and shell('sha256sum '+shlex.quote(live)).split()[0] != sha(data):
            raise ValueError('Live GSI input differs from pinned image: '+live)
        payload[name] = data
    if sha(payload['secilc']) != 'ace5b9b5b26f28e0c81a070ac2be0106269f6a9f3912c80ea48663706444fac1':
        raise ValueError('Unexpected GSI compiler')
    sys.path.insert(0, str(repo/'scripts/build'))
    from stage_keymaster_reference import inventory
    files, _ = inventory(True, work/'current/rmx-m1-guard')
    cil = files['/etc/selinux/vendor_sepolicy.cil']
    for kind in ('graphics', 'health', 'power', 'audio'):
        cil += (repo/'device/realme/bladerunner_48m/m3-vendor'/(kind+'.cil')).read_bytes().replace(b'\r\n', b'\n')
    payload['m3-vendor.cil'] = cil
    payload['plat_pub_versioned.cil'] = files['/etc/selinux/plat_pub_versioned.cil']
    local = work/'current/policy-check/gsi-compile'
    local.mkdir(parents=True, exist_ok=True)
    remote = '/data/local/tmp/rmx-m3-policy-gsi'
    shell('mkdir -p '+remote+'; chmod 700 '+remote)
    for name, data in payload.items():
        (local/name).write_bytes(data)
        subprocess.run(adb+['push', str(local/name), remote+'/'+name], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    shell('chmod 700 '+remote+'/secilc')
    order = ('plat_sepolicy.cil', '202604.cil', 'system_ext_sepolicy.cil',
             'product_sepolicy.cil', 'plat_pub_versioned.cil', 'm3-vendor.cil',
             'plat_sepolicy_genfs_202604.cil')
    command = remote+'/secilc -m -M true -G -c 30 '+\
        ' '.join(remote+'/'+n for n in order)+' -o '+remote+'/policy -f '+remote+'/contexts'
    result = shell('timeout 180 sh -c '+shlex.quote(command), 200)
    compiled = shell('sha256sum '+remote+'/policy').split()[0]
    if shell(identity).splitlines() != expected:
        raise ValueError('Boot or enforcing changed during compilation')
    (work/'current/policy-check/m3-vendor.cil').write_bytes(cil)
    report = dict(result='PASS_STRICT_COMPILE_ONLY', utc=datetime.now(timezone.utc).isoformat(),
        host_firmware='Android 17 GSI', boot_id=a.boot_id, command=command,
        source_gsi_sha256=reference['image_sha256'], compiler_sha256=sha(payload['secilc']),
        compiler_matches_pinned_gsi=True, live_policy_inputs_match_pinned_gsi=True,
        input_sha256={n: sha(d) for n, d in payload.items()},
        combined_vendor_policy_sha256=sha(cil), compiled_policy_sha256=compiled,
        cil_statements_match_current_sources=True, loaded=False, compiler_output=result,
        scope='Pinned Android 17 compiler and live-matched inputs; neverallow enabled; no policy load or enforcing change')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    # Explicit files only: preserve unrelated shell scratch and user data.
    shell('rm -f '+' '.join(remote+'/'+n for n in (*payload, 'policy', 'contexts'))+'; rmdir '+remote)
    print(json.dumps(dict(result=report['result'], compiled_policy_sha256=compiled)))


if __name__ == '__main__':
    main()
