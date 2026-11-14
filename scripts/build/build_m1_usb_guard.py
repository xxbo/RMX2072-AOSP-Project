"""Build the static engineering watchdog owner and its same-boot client."""
import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--ndk',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[2]
source=root/'device/realme/bladerunner_48m/m1-usb/rmx-m1-guard.c'
tool=a.ndk/'toolchains/llvm/prebuilt/windows-x86_64/bin'
a.output.parent.mkdir(parents=True,exist_ok=True)
subprocess.run([tool/'aarch64-linux-android35-clang.cmd','-static','-O2','-Wall','-Wextra','-Werror',source,'-o',a.output],check=True)
subprocess.run([tool/'llvm-strip.exe','--strip-all',a.output],check=True)
a.output.with_suffix('.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),binary_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),ndk='28.2.13676358',api=35),indent=2)+'\n')
