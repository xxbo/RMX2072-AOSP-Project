#!/usr/bin/env python3
"""Generate or verify a repo overlay from a successful build's resolved manifest."""
import argparse
import pathlib
import re
import subprocess
import xml.etree.ElementTree as ET


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['overlay', 'verify'])
    p.add_argument('--manifest', required=True, type=pathlib.Path)
    p.add_argument('--workspace', required=True, type=pathlib.Path)
    a = p.parse_args()
    root = ET.parse(a.manifest).getroot()
    projects = root.findall('project')
    assert projects, 'empty dependency lock'
    for item in projects:
        assert re.fullmatch('[0-9a-f]{40}', item.get('revision', '')), item.attrib
        path = pathlib.PurePosixPath(item.get('path', item.get('name')))
        assert not path.is_absolute() and '..' not in path.parts
    if a.mode == 'verify':
        for item in projects:
            path = a.workspace/item.get('path', item.get('name'))
            actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
            assert actual == item.get('revision'), (str(path), actual, item.get('revision'))
        print(f'Verified {len(projects)} immutable project revisions')
        return
    overlay = ET.Element('manifest')
    for remote in root.findall('remote'):
        if remote.get('name') != 'aosp':
            overlay.append(remote)
    for item in projects:
        path = item.get('path', item.get('name'))
        if path == 'common':
            ET.SubElement(overlay, 'remove-project', path='common')
            overlay.append(item)
        else:
            attrs = dict(name=item.get('name'), path=path, revision=item.get('revision'))
            if item.get('upstream'):
                attrs['upstream'] = item.get('upstream')
            ET.SubElement(overlay, 'extend-project', **attrs)
    dest = a.workspace/'.repo/local_manifests/99-rmx2072-pinned.xml'
    dest.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(overlay).write(dest, encoding='utf-8', xml_declaration=True)
    print(f'Locked {len(projects)} projects in {dest.name}')


if __name__ == '__main__':
    main()
