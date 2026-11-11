"""Cross-compile the static read-only GSI backend with an Android NDK."""
import argparse
import os
from pathlib import Path
import subprocess

from build_diag_ramdisk import read_static_arm64


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--init-probe', action='store_true', help='Build the restricted init launcher')
    mode.add_argument('--first-stage-witness', action='store_true', help='Build the PID 1 mount observer')
    args = parser.parse_args()
    exe = 'clang.exe' if os.name == 'nt' else 'clang'
    compilers = list(args.ndk.glob('toolchains/llvm/prebuilt/*/bin/'+exe))
    if len(compilers) != 1:
        parser.error('Select an NDK containing the toolchain for the build host')
    name = 'first_stage_witness.c' if args.first_stage_witness else 'gsi_init_probe.c' if args.init_probe else 'gsi_usb_reader.c'
    src = Path(__file__).resolve().parents[1]/'device_audit'/name
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([compilers[0], '--target=aarch64-linux-android21', '-static', '-O2', '-s',
                    '-Wall', '-Wextra', '-Werror', src, '-lz', '-o', args.output], check=True)
    read_static_arm64(args.output)
