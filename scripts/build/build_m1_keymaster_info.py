"""Build the info-only HIDL service and its test client against the AOSP VNDK 30."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

DEVICE = Path(__file__).resolve().parents[2] / 'device/realme/bladerunner_48m/m1-keymaster-info'


def build(ndk, headers, bionic, libraries, output, f20_hmac_control=False):
    output.mkdir(parents=True, exist_ok=True)
    tools = next((ndk / 'toolchains/llvm/prebuilt').iterdir()) / 'bin'
    clang = next(p for p in (tools / 'clang++.exe', tools / 'clang++') if p.is_file())
    includes = [headers / 'system' / path for path in (
        'libhidl/base/include', 'libhidl/transport/include', 'libhwbinder/include',
        'core/libutils/include', 'core/libcutils/include', 'core/libsystem/include',
        'core/base/include', 'core/liblog/include_vndk')]
    generated = headers / 'generated-headers'
    for subtree in ('hardware/interfaces/keymaster/4.0', 'system/libhidl/transport'):
        includes.extend(sorted((generated / subtree).rglob('gen')))
    args = [str(clang), '--target=aarch64-linux-android30', '-std=c++17', '-O2',
            '-fno-rtti', '-fno-exceptions', '-nostdlib++', '-nostdinc++',
            '-isystem', str(headers / 'external/libcxx/include'),
            '-isystem', str(bionic),
            '-Wno-deprecated-declarations', '-Wall', '-Werror']
    for inc in includes:
        args.extend(['-isystem', str(inc)])
    manifest = {}
    names = ('f20-hmac-control',) if f20_hmac_control else ('service', 'client')
    for name in names:
        binary = output / ('rmx-keymaster-info-' + name)
        subprocess.run(args + [str(DEVICE / (name + '.cpp')), '-L' + str(libraries),
                       '-Wl,--no-undefined', '-Wl,--hash-style=both', '-Wl,--build-id=sha1',
                       '-Wl,--allow-shlib-undefined', '-Wl,-s', '-l:android.hardware.keymaster@4.0.so',
                       '-lhidlbase', '-lutils', '-lc++', '-llog', '-o', str(binary)], check=True)
        manifest[binary.name] = hashlib.sha256(binary.read_bytes()).hexdigest()
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ndk', 'headers', 'bionic', 'libraries', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--f20-hmac-control', action='store_true',
                        help='Build the separate stock parameter-retrieval control')
    build(**vars(parser.parse_args()))
