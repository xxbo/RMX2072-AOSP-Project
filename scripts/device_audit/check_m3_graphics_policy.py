"""Compile the composed graphics policy on a retained GSI without loading it."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from gsi_adb_accept import inspect, shell


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--performance', action='store_true', help='Compile the exact hardware acceleration policy')
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    work, record = a.workspace.resolve(), a.record.resolve()
    if record.parent != work/'records':
        raise ValueError('Use a handset record from this workspace')
    inputs = json.loads((record/'inputs.json').read_text())
    stable = json.loads((record/'live/gsi-stable.json').read_text())
    boot = stable['identity'][2]
    proof = inspect(record/'live', boot)
    if proof['identity'][6] != 'retained':
        raise ValueError('Requires the retained matching GSI')
    reference = json.loads((repo/'build/device/gsi17-mount-reference.json').read_text())
    if inputs['candidate']['signed']['system']['sha256'] != reference['image_sha256']:
        raise ValueError('The active GSI differs from the policy reference')
    sys.path.insert(0, str(repo/'scripts/build'))
    from stage_keymaster_reference import inventory
    if sha((work/'current/rmx-m1-guard').read_bytes()) != inputs['usb_build']['guard']:
        raise ValueError('The local guardian differs from the active vendor')
    files, _ = inventory(True, work/'current/rmx-m1-guard')
    cil = files['/etc/selinux/vendor_sepolicy.cil'] + (
        repo/'device/realme/bladerunner_48m/m3-vendor/graphics.cil').read_bytes().replace(b'\r\n', b'\n')
    cil += (repo/'device/realme/bladerunner_48m/m3-vendor/health.cil').read_bytes().replace(b'\r\n', b'\n')
    cil += (repo/'device/realme/bladerunner_48m/m3-vendor/power.cil').read_bytes().replace(b'\r\n', b'\n')
    cil += (repo/'device/realme/bladerunner_48m/m3-vendor/audio.cil').read_bytes().replace(b'\r\n', b'\n')
    if a.performance:
        from stage_m3_acceleration import acceleration_policy
        cil = acceleration_policy(cil)
    local = work/'current/policy-check'
    candidate = local/'candidate-vendor.cil'
    candidate.write_bytes(cil)
    compiler = local/'secilc'
    # Read the signed GSI image without modifying it. The shell cannot read
    # its root-only compiler in /system, so execute this identical scratch copy.
    expected_compiler = subprocess.check_output([
        str(work/'current/fs-tools/debugfs.exe'), '-R', 'cat /system/bin/secilc',
        str(work/'current/system.img')], stderr=subprocess.DEVNULL, timeout=30)
    if (expected_compiler[:6] != b'\x7fELF\x02\x01'
            or compiler.read_bytes() != expected_compiler
            or sha(expected_compiler) != 'ace5b9b5b26f28e0c81a070ac2be0106269f6a9f3912c80ea48663706444fac1'):
        raise ValueError('Expected the byte-identical pinned ARM64 GSI policy compiler')
    remote = '/data/local/tmp/rmx-m3-policy'
    shell('mkdir -p '+remote)
    for source, target in ((compiler, 'secilc'), (candidate, 'm3-vendor.cil')):
        subprocess.run(['adb', '-s', 'RMX2072-M1', 'push', str(source), remote+'/'+target],
                       check=True, capture_output=True, timeout=30)
    shell('chmod 755 '+remote+'/secilc')
    policy_inputs = [
        '/system/etc/selinux/plat_sepolicy.cil',
        '/system/etc/selinux/mapping/202604.cil',
        '/system_ext/etc/selinux/system_ext_sepolicy.cil',
        '/product/etc/selinux/product_sepolicy.cil',
        '/vendor/etc/selinux/plat_pub_versioned.cil',
        remote+'/m3-vendor.cil',
        '/system/etc/selinux/plat_sepolicy_genfs_202604.cil',
    ]
    command = '/system/bin/timeout 180 /system/bin/linker64 '+remote+'/secilc -m -M true -G -c 30 '
    command += ' '.join(policy_inputs)+' -o '+remote+'/policy -f '+remote+'/contexts'
    result = shell(command+' > '+remote+'/compile.log 2>&1; echo SECILC_RC=$?', 195).strip()
    log = shell('cat '+remote+'/compile.log')
    (record/'live/m3-policy-compile.txt').write_text(result+'\n'+log, encoding='utf-8')
    if result != 'SECILC_RC=0':
        raise ValueError('Strict compilation failed; previous accepted proof unchanged: '+result+' '+log[:2000])
    policy_sha = shell('sha256sum '+remote+'/policy').split()[0]
    input_hashes = shell('sha256sum '+' '.join(policy_inputs))
    proof = inspect(record/'live', boot)
    if proof['identity'][6] != 'retained':
        raise ValueError('Retained boot changed during policy compilation')
    report = dict(result='PASS_STRICT_COMPILE_ONLY', utc=datetime.now(timezone.utc).isoformat(),
                  command=command, boot_id=boot, trial=inputs['trial'],
                  source_gsi_sha256=reference['image_sha256'],
                  compiler_sha256=sha(compiler.read_bytes()), input_sha256=input_hashes.splitlines(),
                  compiler_matches_pinned_gsi=True,
                  combined_vendor_policy_sha256=sha(cil), compiled_policy_sha256=policy_sha,
                  cil_statements_match_current_sources=True, loaded=False,
                  scope='Strict compiler through GSI ADB; neverallow checks enabled; no policy load or enforcing change')
    (local/'m3-vendor.cil').write_bytes(cil)
    a.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(result=report['result'], boot_id=boot, compiled_policy_sha256=policy_sha)))


if __name__ == '__main__':
    main()
