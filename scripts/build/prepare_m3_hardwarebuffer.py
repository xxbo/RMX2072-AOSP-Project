"""Select byte-identical upstream HardwareBuffer build declarations.

The native VINTF tool needs this real AIDL header and its license, not the Java
framework product. Source and selected declaration bytes are independently
hashed. No source/header/library implementation is synthesized.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PINNED = {
    'Android.bp': '9039665725aa013a88f222430e33a1a3e662e23ec87090f253592ee28ec2f545',
    'core/java/Android.bp': 'bde0ed0b9eae4dda4170e84d700c2acf445938f107dd0c094e2cfd1535578fd4',
    'core/java/android/hardware/HardwareBuffer.aidl': '287035e1d41954725d17f0729fa6c163dac80e0cd8980653720366dc2a9b71e9',
}
SELECTED_MODULES = {
    'frameworks_base_license': '7108aa5f46797e8b32b8a288e0b81c82601f534ad711afa52519256d8316f877',
    'HardwareBuffer_aidl': '8cd2f8140323288bf190a80288d4bab4059bb7897ac9b78da28cf6190322c988',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def select(inputs):
    if {name: sha(data) for name, data in inputs.items()} != PINNED:
        raise ValueError('Pinned Android 17 HardwareBuffer source changed')
    outputs = {}
    selected = {}
    for path, kind, name in [('Android.bp', 'license', 'frameworks_base_license'),
                             ('core/java/Android.bp', 'aidl_library', 'HardwareBuffer_aidl')]:
        data = inputs[path]
        packages = re.findall(rb'^package \{\n.*?^\}', data, re.M | re.S)
        modules = [m for m in re.findall(b'^'+kind.encode()+rb' \{\n.*?^\}', data, re.M | re.S)
                   if ('name: "'+name+'"').encode() in m]
        if len(packages) != 1 or len(modules) != 1:
            raise ValueError('Unexpected pinned declaration layout: '+path)
        # Preserve the upstream blocks exactly, including all real dependencies.
        outputs[path] = b'// Selected verbatim from pinned AOSP Android 17; native graphics build only.\n'+packages[0]+b'\n\n'+modules[0]+b'\n'
        selected[name] = sha(modules[0])
    if selected != SELECTED_MODULES:
        raise ValueError('Selected upstream module bytes differ')
    return outputs, dict(original_files=PINNED, selected_modules=selected,
                        selected_files={n: sha(v) for n,v in outputs.items()},
                        aidl_implementation='unmodified upstream HardwareBuffer.aidl',
                        omitted_scope='Unrelated Java framework product declarations only')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    inputs = {n: subprocess.check_output(['git', '-C', a.source, 'show', 'HEAD:'+n]) for n in PINNED}
    if (a.source/'core/java/android/hardware/HardwareBuffer.aidl').read_bytes() != inputs['core/java/android/hardware/HardwareBuffer.aidl']:
        raise ValueError('Checked-out HardwareBuffer AIDL differs from upstream')
    outputs, report = select(inputs)
    for n, data in outputs.items():
        (a.source/n).write_bytes(data)
    a.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
