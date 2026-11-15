"""Build the GSI-only ARM64 allocator/EGL buffer diagnostic with the pinned NDK."""
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
    repo = Path(__file__).resolve().parents[2]
    output = a.output.resolve()
    if output.is_relative_to(repo):
        p.error('Keep generated binaries outside the repository')
    ndk = a.ndk.resolve()
    properties = (ndk/'source.properties').read_text()
    if 'Pkg.Revision = 28.2.13676358' not in properties:
        raise ValueError('Use the recorded NDK 28.2.13676358')
    output.mkdir(parents=True, exist_ok=True)
    source = repo/'scripts/device_audit/graphics_buffer_smoke.c'
    tools = ndk/'toolchains/llvm/prebuilt/windows-x86_64/bin'
    target = output/'graphics-buffer-smoke'
    subprocess.run([str(tools/'aarch64-linux-android35-clang.cmd'), '-O2',
                    '-Wall', '-Wextra', '-Werror', str(source), '-o', str(target),
                    '-lEGL', '-lGLESv2', '-landroid'], check=True)
    subprocess.run([str(tools/'llvm-strip.exe'), '--strip-all', str(target)], check=True)
    record = dict(ndk_revision='28.2.13676358', api=35, arch='arm64',
                  source_sha256=hashlib.sha256(source.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                  binary_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                  device_result='NOT RUN')
    (output/'build.json').write_text(json.dumps(record, indent=2)+'\n', newline='\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
