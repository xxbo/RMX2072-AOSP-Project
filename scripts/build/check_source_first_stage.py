"""Validate the actual static init build artifact and its resolved source pins."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def verify_source_first_stage(directory, binary):
    repo = Path(__file__).resolve().parents[2]
    pin = json.loads((repo / 'build/m2-first-stage-source.json').read_text())
    if json.loads((directory / 'source.json').read_text()) != pin:
        raise ValueError('First-stage build source pin differs from the project lock')
    hashes = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        name = Path(name.lstrip('*')).name
        if name in hashes or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid first-stage build digest manifest')
        hashes[name] = digest
    manifest = (directory / 'resolved-manifest.xml').read_bytes()
    if hashes.get('init') != hashlib.sha256(binary).hexdigest() or hashes.get('resolved-manifest.xml') != hashlib.sha256(manifest).hexdigest():
        raise ValueError('First-stage binary/source manifest digest mismatch')
    projects = {p.get('path', p.get('name')): p.get('revision') for p in ET.fromstring(manifest).findall('project')}
    if projects.get('system/core') != pin['system_core_commit']:
        raise ValueError('First-stage system/core revision differs')
    if not projects or any(not re.fullmatch('[0-9a-f]{40}', r or '') for r in projects.values()):
        raise ValueError('First-stage source manifest must resolve every project commit')
    product = (directory / 'rmx2072_m2_init.mk').read_bytes().replace(b'\r\n', b'\n')
    expected = (repo / 'device/realme/bladerunner_48m/m2-init/rmx2072_m2_init.mk').read_bytes().replace(b'\r\n', b'\n')
    if product != expected:
        raise ValueError('First-stage product recipe differs')
    return dict(origin='project-source-build', **pin, init_sha256=hashes['init'],
                resolved_manifest_sha256=hashes['resolved-manifest.xml'], source_projects=len(projects))
