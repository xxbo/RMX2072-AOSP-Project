"""Stage the pinned SQE update while reusing the single F.20 GMU/ZAP copy.

No handset access or partition backup. Validate every input before replacing
the current firmware set; package the upstream license and notice alongside it.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import urllib.request

from stage_m3_acceleration import ROOT, gpu_firmware


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    a = p.parse_args()
    pin = json.loads((ROOT/'build/m3-gpu-firmware-source.json').read_text())
    original = json.loads((ROOT/'build/device/m3-gpu-firmware-2026-11-24.json').read_text())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checked = {}
    for name, entry in pin['files'].items():
        if not name.startswith('qcom/') or '..' in Path(name).parts:
            raise ValueError('Unexpected destination')
        target = a.directory/name
        data = target.read_bytes() if target.is_file() else b''
        if entry['origin'] == 'original F.20 acquisition':
            stock = original['files'][name]
            if any(entry[k] != stock[k] for k in ('bytes', 'sha256', 'source')):
                raise ValueError('Original GPU firmware provenance changed')
        elif entry['origin'] == 'linux-firmware':
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                with opener.open(entry['source']+'?format=TEXT', timeout=30) as response:
                    encoded = response.read(1 << 20)
                data = base64.b64decode(encoded, validate=True)
            blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if blob != entry['git_blob']:
                raise ValueError('Upstream Git blob mismatch: '+name)
        else:
            raise ValueError('Unknown firmware origin')
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('Firmware digest mismatch: '+name)
        checked[name] = data
    for name, data in checked.items():
        target = a.directory/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (a.directory/'provenance.json').write_text(json.dumps(pin, indent=2)+'\n')
    gpu_firmware(a.directory)
    print(json.dumps(dict(files=len(checked), bytes=sum(map(len, checked.values())),
                          sqe_version=pin['files']['qcom/a650_sqe.fw']['version'],
                          handset_access=False)))


if __name__ == '__main__':
    main()
