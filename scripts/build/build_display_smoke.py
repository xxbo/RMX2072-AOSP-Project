"""Build a static ARM64 KMS test against the pinned ACK DRM userspace headers."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ndk', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    source = root / 'scripts/device_audit/drm_panel_smoke.c'
    output = a.output.resolve()
    if output.is_relative_to(root):
        p.error('Keep generated binaries outside the repository')
    output.mkdir(parents=True, exist_ok=True)
    ack = next(s for s in json.loads((root/'sources/SOURCE_LOCK.json').read_text())['sources']
               if s['id'] == 'android17-gki-618')['commit']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {}
    for name in ('drm.h', 'drm_mode.h'):
        url = f'https://android.googlesource.com/kernel/common/+/{ack}/include/uapi/drm/{name}?format=TEXT'
        data = base64.b64decode(opener.open(url, timeout=60).read(), validate=True)
        path = output/'include/drm'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        headers[name] = hashlib.sha256(data).hexdigest()
    tools = a.ndk.resolve()/'toolchains/llvm/prebuilt/windows-x86_64/bin'
    target = output/'drm-panel-smoke'
    subprocess.run([str(tools/'aarch64-linux-android35-clang.cmd'), '-static', '-O2',
                    '-Wall', '-Wextra', '-Werror', '-I'+str(output/'include'),
                    str(source), '-o', str(target)], check=True)
    subprocess.run([str(tools/'llvm-strip.exe'), '--strip-all', str(target)], check=True)
    record = dict(ack_commit=ack, headers=headers,
                  source_sha256=hashlib.sha256(source.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                  binary_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    scan_source = root/'scripts/device_audit/drm_scanout_state.c'
    scan_target = output/'drm-scanout-state'
    subprocess.run([str(tools/'aarch64-linux-android35-clang.cmd'), '-static', '-O2',
                    '-Wall', '-Wextra', '-Werror', '-I'+str(output/'include'),
                    str(scan_source), '-o', str(scan_target)], check=True)
    subprocess.run([str(tools/'llvm-strip.exe'), '--strip-all', str(scan_target)], check=True)
    record['scanout_source_sha256'] = hashlib.sha256(scan_source.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    record['scanout_binary_sha256'] = hashlib.sha256(scan_target.read_bytes()).hexdigest()
    from m3_boot_pattern import rgb_bytes, png_bytes, PATTERN_VERSION
    rgb = rgb_bytes()
    (output/'pattern.rgb').write_bytes(rgb)
    (output/'pattern.png').write_bytes(png_bytes(rgb))
    record['pattern'] = dict(version=PATTERN_VERSION, bytes=len(rgb),
                            rgb_sha256=hashlib.sha256(rgb).hexdigest(),
                            png_sha256=hashlib.sha256((output/'pattern.png').read_bytes()).hexdigest())
    (output/'build.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
