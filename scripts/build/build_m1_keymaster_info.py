"""Build the project HIDL service/client against the accepted AOSP VNDK 30 runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

DEVICE = Path(__file__).resolve().parents[2] / 'device/realme/bladerunner_48m/m1-keymaster-info'


def build(ndk, headers, bionic, libraries, output, f20_hmac_control=False, f20_temp_key_control=False):
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
    runtime_report = {}
    names = ('f20-hmac-control',) if f20_hmac_control else ('service', 'client')
    if f20_temp_key_control:
        names = ('f20-temp-key-control',)
    for name in names:
        binary = output / ('rmx-keymaster-info-' + name)
        private_runtime = []
        if name in ('service', 'client'):
            # SELinux domain transitions set AT_SECURE: Bionic ignores
            # LD_LIBRARY_PATH. Embed the immutable vendor directory instead.
            # RUNPATH is not transitive, so make the entire accepted private
            # runtime direct dependencies, ahead of their indirect load tasks.
            runtime = sorted(Path(path).name for path in json.loads(
                (DEVICE / 'inputs.json').read_text()) if path.startswith('/lib64/'))
            private_runtime = ['-Wl,--enable-new-dtags,-rpath,/vendor/lib64/rmx-keymaster',
                               '-Wl,--no-as-needed']
            private_runtime += ['-l:' + library for library in runtime]
            private_runtime += ['-Wl,--as-needed']
        subprocess.run(args + [str(DEVICE / (name + '.cpp')), '-L' + str(libraries),
                       '-Wl,--no-undefined', '-Wl,--hash-style=both', '-Wl,--build-id=sha1',
                       '-Wl,--allow-shlib-undefined', '-Wl,-s'] + private_runtime + ['-l:android.hardware.keymaster@4.0.so',
                       '-lhidlbase', '-lutils', '-lc++', '-llog', '-o', str(binary)], check=True)
        manifest[binary.name] = hashlib.sha256(binary.read_bytes()).hexdigest()
        if private_runtime:
            readelf = next(p for p in (tools / 'llvm-readelf.exe', tools / 'llvm-readelf') if p.is_file())
            dynamic = subprocess.check_output([str(readelf), '-d', str(binary)], text=True)
            needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic)
            runpath = re.findall(r'\(RUNPATH\).*?\[(.*?)\]', dynamic)
            if not set(runtime) <= set(needed) or runpath != ['/vendor/lib64/rmx-keymaster']:
                raise ValueError('Keymaster private runtime closure/RUNPATH is incomplete')
            runtime_report[binary.name] = dict(sha256=manifest[binary.name], needed=needed, runpath=runpath,
                source_sha256=hashlib.sha256((DEVICE / (name + '.cpp')).read_bytes()).hexdigest())
    if runtime_report:
        (output / 'private-runtime.json').write_text(json.dumps(runtime_report, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ndk', 'headers', 'bionic', 'libraries', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--f20-temp-key-control', action='store_true',
                       help='Build the stock temporary HMAC key generation and deletion control')
    group.add_argument('--f20-hmac-control', action='store_true',
                        help='Build the separate stock parameter-retrieval control')
    build(**vars(parser.parse_args()))
