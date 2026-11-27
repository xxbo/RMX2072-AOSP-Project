"""Opt-in composition of the verified Wi-Fi RRO; no device or RF operation."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'device/realme/bladerunner_48m/wifi/overlay'
PIN = ROOT/'build/device/m3-wifi-overlay-2026-11-25.json'
APK = '/overlay/RmxWifiOverlay.apk'
CONTEXTS = '/etc/selinux/vendor_file_contexts'
LABEL = b'/vendor/overlay(/.*)? u:object_r:vendor_overlay_file:s0\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def overlay_payload(directory):
    # This record pins the APK whose signature and overlayable target were
    # checked at build time. An edited local provenance file is not authority
    # to admit another APK, target GSI, key or resource.
    pin = json.loads(PIN.read_text(encoding='utf-8'))
    proof = json.loads((directory/'provenance.json').read_text(encoding='utf-8'))
    if proof != pin:
        raise ValueError('Wi-Fi RRO differs from the reviewed build record')
    sources = {p.relative_to(SOURCE).as_posix(): sha(p.read_bytes())
               for p in SOURCE.rglob('*') if p.is_file()}
    if sources != pin['source_sha256']:
        raise ValueError('Rebuild and review the changed Wi-Fi RRO sources')
    apk = (directory/Path(APK).name).read_bytes()
    if sha(apk) != pin['apk_sha256']:
        raise ValueError('Wi-Fi RRO APK digest mismatch')
    return apk, proof


def add_wifi_android(files, directory):
    apk, proof = overlay_payload(directory)
    if APK in files and files[APK] != apk:
        raise ValueError('Wi-Fi RRO would replace a different vendor file')
    contexts = files[CONTEXTS]
    rules = [row.split() for row in contexts.decode().splitlines()
             if row.strip() and not row.lstrip().startswith('#')]
    def label_for(path):
        return next((label for pattern, label in reversed(rules)
                     if re.fullmatch(pattern, path)), None)
    # The input overlay normally installs this rule already. Add it only if
    # absent; do not change CIL, service ownership or existing overlay labels.
    if label_for('/vendor/overlay') != 'u:object_r:vendor_overlay_file:s0' or \
            label_for('/vendor'+APK) != 'u:object_r:vendor_overlay_file:s0':
        contexts = contexts.rstrip(b'\n') + b'\n' + LABEL
    files[CONTEXTS] = contexts
    files[APK] = apk
    return proof
