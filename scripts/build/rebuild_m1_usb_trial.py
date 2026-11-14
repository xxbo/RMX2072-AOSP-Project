"""Rebuild the sole current USB/ADB candidate from verified retained inputs."""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--workspace',type=Path,required=True)
p.add_argument('--ndk',type=Path,required=True)
p.add_argument('--adb-public-key',type=Path,required=True)
p.add_argument('--trial',required=True)
p.add_argument('--autonomous-ufs',action='store_true')
p.add_argument('--reuse-super',action='store_true',help='Reuse verified current chunks only when both signed images are unchanged')
a=p.parse_args()
if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}',a.trial):p.error('Expected the recorded UFS trial naming')
w=a.workspace.resolve();current=w/'current';repo=Path(__file__).resolve().parents[2];build=repo/'scripts/build'
ndk=a.ndk.resolve();tool=ndk/'toolchains/llvm/prebuilt/windows-x86_64/bin'
def run(*args):subprocess.run([str(x) for x in args],check=True)
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
os.environ['PATH']=str(current/'fs-tools')+os.pathsep+os.environ['PATH']
run(sys.executable,build/'build_m1_usb_guard.py','--ndk',ndk,'--output',current/'rmx-m1-guard')
run(tool/'aarch64-linux-android35-clang.cmd','-static','-O2','-Wall','-Wextra','-Werror',repo/'scripts/device_audit/first_stage_witness.c','-o',current/'first-stage-witness')
run(tool/'llvm-strip.exe','--strip-all',current/'first-stage-witness')
run(sys.executable,build/'build_m1_vendor.py','--keymaster-info',current/'info-input','--usb-guard',current/'rmx-m1-guard','--output',current/'vendor')
report=json.loads((current/'vendor/vendor.json').read_text());assert sha(current/'vendor/vendor.img')==report['sha256']
avb=current/'avbtool.py';assert sha(avb)=='e5a664a38db623da00f080219bc0ee60a640a9dc4a872803616fae4938ac749b'
import shutil
shutil.copyfile(current/'vendor/vendor.img',current/'vendor-signed.img')
run(sys.executable,avb,'add_hashtree_footer','--image',current/'vendor-signed.img','--partition_name','vendor','--partition_size',17825792,'--algorithm','SHA256_RSA4096','--key',current/'engineering-vendor.pem','--hash_algorithm','sha256','--salt',report['sha256'],'--do_not_generate_fec')
run(sys.executable,build/'prepare_ufs_verification.py','--system',current/'system.img','--vendor',current/'vendor-signed.img','--vendor-key',current/'vendor.avbpubkey','--vendor-report',current/'vendor/vendor.json','--keymaster-info','--usb-guard',current/'rmx-m1-guard','--output',current/'verified-profile')
run(sys.executable,build/'build_diag_ramdisk.py','--busybox',current/'busybox','--reboot-helper',current/'reboot-edl','--entry-carrier',current/'entry-carry','--return-to-edl-after',180,'--gadget-bind-delay',20,'--trial-id',a.trial,'--ufs-host-g3-test','--super-tools-apks',current/'apks','--android-first-stage',current/'init','--first-stage-witness',current/'first-stage-witness','--ufs-first-stage',current/'verified-profile','--scratch-volumes',current/'volumes','--adb-public-key',a.adb_public_key.resolve(),'--output',current/'ramdisk',*(['--autonomous-ufs'] if a.autonomous_ufs else []))
kernel=json.loads((current/'kernel/provenance.json').read_text())
run(sys.executable,build/'pack_reacquired_ufs_boot.py','--stock-boot',w/'recovery/f20/boot.img','--stock-dtbo',w/'recovery/f20/dtbo.img','--overlays',current/'dt','--libfdt',current/'dtc-tools/libfdt-1.dll','--kernel',current/'kernel/Image','--expected-kernel-sha256',kernel['image_sha256'],'--ramdisk',current/'ramdisk/ramdisk.cpio.gz','--output',current/'boot',*([] if a.autonomous_ufs else ['--entry-probe',current/'native-entry-probe.bin']))
if a.reuse_super:
 sys.path.insert(0,str(repo/'scripts/device_audit'))
 from check_super_chunks import verify
 candidate=json.loads((current/'candidate/candidate.json').read_text())
 assert candidate['signed']==json.loads((current/'verified-profile/signed.json').read_text())
 assert candidate['signed']['system']['sha256']==sha(current/'system.img')
 assert candidate['signed']['vendor']['sha256']==sha(current/'vendor-signed.img')
 assert [x['sha256'] for x in verify(current/'candidate',candidate['sha256'])['parts']]==candidate['parts']
else:
 run(sys.executable,repo/'scripts/device_audit/build_ufs_candidate.py','--stock',w/'recovery/f20','--system',current/'system.img','--vendor',current/'vendor-signed.img','--profile',current/'verified-profile','--output',current/'candidate')
(current/'usb-build.json').write_text(json.dumps(dict(trial=a.trial,kernel=kernel['image_sha256'],guard=sha(current/'rmx-m1-guard'),witness=sha(current/'first-stage-witness'),vendor_unsigned=report['sha256'],vendor_signed=sha(current/'vendor-signed.img'),engineering_key='reused trial25 key',adb_public_key_sha256=json.loads((current/'ramdisk/ramdisk-provenance.json').read_text())['adb_public_key_sha256']),indent=2)+'\n')
print('Current guarded USB candidate rebuilt and validated.',flush=True)
