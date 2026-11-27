"""Build a fixed read-only network-interface diagnostic from project C source."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ndk', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = a.output.resolve()
    if output.is_relative_to(root):
        p.error('Build outside the source checkout')
    output.mkdir(parents=True, exist_ok=True)
    source = root/'scripts/device_audit/wifi_netdev_state.c'
    target = output/'rmx-wifi-state'
    clang = a.ndk/'toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android35-clang.cmd'
    subprocess.run([str(clang), '-O2', '-Wall', '-Wextra', '-Werror', '-fPIE', '-pie',
                    str(source), '-llog', '-o', str(target)], check=True)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    report = dict(source_sha256=sha(source.read_bytes().replace(b'\r\n', b'\n')),
                  binary_sha256=sha(target.read_bytes()),
                  compiler=str(clang), target='aarch64-linux-android35',
                  scope='Only SIOCGIFINDEX/SIOCGIFFLAGS/SIOCGIFHWADDR; no identifiers emitted or network writes')
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
