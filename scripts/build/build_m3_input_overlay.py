"""Build the source RRO against the exact GSI framework; keep keys/images private."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('build-tools', 'java-home', 'framework', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source = repo / 'device/realme/bladerunner_48m/input/overlay'
    out = a.output.resolve()
    if out.is_relative_to(repo):
        p.error('Keep generated APK and engineering key outside the public repo')
    if digest(a.framework) != 'b77f17c2f4014fdb2754e3ed5fc020e3912507e2e92a837d9eca341f021fa05a':
        raise ValueError('Expected the exact signed GSI framework resources')
    out.mkdir(parents=True, exist_ok=True)
    tools = a.build_tools.resolve()
    java = a.java_home.resolve() / 'bin'
    def run(*args):
        subprocess.run([str(x) for x in args], check=True)
    run(tools / 'aapt2.exe', 'compile', '--dir', source / 'res', '-o', out / 'resources.zip')
    run(tools / 'aapt2.exe', 'link', '-I', a.framework.resolve(),
        '--manifest', source / 'AndroidManifest.xml', '--auto-add-overlay',
        '--no-resource-deduping', '--no-resource-removal',
        '-o', out / 'unsigned.apk', out / 'resources.zip')
    run(tools / 'zipalign.exe', '-f', '4', out / 'unsigned.apk', out / 'aligned.apk')
    key = out / 'engineering.jks'
    if not key.exists():
        run(java / 'keytool.exe', '-genkeypair', '-keystore', key,
            '-storepass', 'android', '-keypass', 'android', '-alias', 'rmx-input',
            '-keyalg', 'RSA', '-keysize', '2048', '-validity', '3650',
            '-dname', 'CN=RMX2072 Engineering Overlay', '-noprompt')
    apk = out / 'RmxCpuInputOverlay.apk'
    run(java / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'sign',
        '--ks', key, '--ks-key-alias', 'rmx-input', '--ks-pass', 'pass:android',
        '--key-pass', 'pass:android', '--v4-signing-enabled', 'false',
        '--out', apk, out / 'aligned.apk')
    run(java / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'verify', '--verbose', apk)
    result = dict(framework_sha256=digest(a.framework), apk_sha256=digest(apk),
                  source_sha256={x.relative_to(source).as_posix(): digest(x)
                                 for x in source.rglob('*') if x.is_file()},
                  aapt2_sha256=digest(tools / 'aapt2.exe'),
                  apksigner_sha256=digest(tools / 'lib/apksigner.jar'),
                  signing='Local engineering certificate; no factory/platform signing key',
                  scope='Only config_displayColorFadeDisabled=true; no code or policy changes',
                  handset_result='NOT RUN')
    (out / 'provenance.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
