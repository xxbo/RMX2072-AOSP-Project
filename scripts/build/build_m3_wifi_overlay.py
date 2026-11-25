"""Build the optional mainline-supplicant RRO for the exact retained GSI.

No installation or interface creation. Reuse the private engineering RRO key;
the resource is explicitly vendor-overlayable in the installed Wi-Fi APK.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('build-tools', 'java-home', 'framework', 'wifi-resources', 'keystore', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source = repo / 'device/realme/bladerunner_48m/wifi/overlay'
    out = a.output.resolve()
    if out.is_relative_to(repo):
        p.error('Generated APK and keys must remain outside the public checkout')
    if (sha(a.framework) != 'b77f17c2f4014fdb2754e3ed5fc020e3912507e2e92a837d9eca341f021fa05a'
            or sha(a.wifi_resources) != '0838fe0e6454de12f485c47bf5ca8a510b1f20121f747dd575fe36b12ea51663'):
        raise ValueError('Expected the measured CP3A.260905.010 framework and Wi-Fi resources')
    tools, java = a.build_tools.resolve(), a.java_home.resolve() / 'bin'
    def run(*args):
        subprocess.run([str(x) for x in args], check=True)
    listing = subprocess.check_output([str(tools / 'aapt2.exe'), 'dump', 'overlayable',
                                      str(a.wifi_resources.resolve())], text=True)
    group = listing.split('name="WifiCustomization" actor=""', 1)[1].split('\nname=', 1)[0]
    if ('policies="odm|product|system|vendor"' not in group
            or 'bool/config_wifiMainlineSupplicantEnabled' not in group):
        raise ValueError('Mainline supplicant resource is not vendor overlayable')
    out.mkdir(parents=True, exist_ok=True)
    run(tools / 'aapt2.exe', 'compile', '--dir', source / 'res', '-o', out / 'resources.zip')
    run(tools / 'aapt2.exe', 'link', '-I', a.framework.resolve(),
        '--manifest', source / 'AndroidManifest.xml', '--auto-add-overlay',
        '-o', out / 'unsigned.apk', out / 'resources.zip')
    run(tools / 'zipalign.exe', '-f', '4', out / 'unsigned.apk', out / 'aligned.apk')
    apk = out / 'RmxWifiOverlay.apk'
    run(java / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'sign',
        '--ks', a.keystore.resolve(), '--ks-key-alias', 'rmx-input', '--ks-pass', 'pass:android',
        '--key-pass', 'pass:android', '--v4-signing-enabled', 'false',
        '--out', apk, out / 'aligned.apk')
    run(java / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'verify', '--verbose', apk)
    report = dict(apk_sha256=sha(apk), framework_sha256=sha(a.framework),
        wifi_resources_sha256=sha(a.wifi_resources),
        source_sha256={f.relative_to(source).as_posix(): sha(f) for f in source.rglob('*') if f.is_file()},
        target_package='com.google.android.wifi.resources', target_name='WifiCustomization',
        resource='bool/config_wifiMainlineSupplicantEnabled', value=True,
        signing='Existing local engineering RRO key; no platform key',
        aapt2_sha256=sha(tools / 'aapt2.exe'), apksigner_sha256=sha(tools / 'lib/apksigner.jar'),
        installed=False, device_result='NOT RUN',
        requires=['native WLAN netdev', 'Android 17 policy', 'mainline supplicant flag and binary'])
    (out / 'provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
