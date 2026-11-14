"""Add only pinned upstream projects named by missing-path build diagnostics.

Never synthesize source files or libraries. Existing selected projects, unknown
paths and missing module names alone cannot authorize a manifest addition.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


def missing_projects(log, upstream, selected):
    projects = {p.get('path', p.get('name')): p for p in upstream.findall('project')}
    found = set()
    for line in log.splitlines():
        if not re.search(r'not exist|not found|no such file|does not exist|cannot find|missing|failed to find', line, re.I):
            continue
        for path in projects.keys() - selected:
            if re.search(r'(?<![\w.-])' + re.escape(path) + r'(?=[/\s"\x27:)]|$)', line):
                found.add(path)
    return [projects[p] for p in sorted(found)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'upstream', 'log', 'record'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    path = a.workspace / '.repo/manifests/rmx2072-minimal.xml'
    manifest = ET.parse(path)
    selected = {p.get('path', p.get('name')) for p in manifest.getroot().findall('project')}
    projects = missing_projects(a.log.read_text(errors='replace'), ET.parse(a.upstream).getroot(), selected)
    if not projects:
        raise SystemExit('No missing pinned project can be inferred from this failure')
    added = []
    for project in projects:
        node = copy.deepcopy(project)
        node.attrib.pop('groups', None)
        manifest.getroot().append(node)
        added.append(node.get('path', node.get('name')))
    ET.indent(manifest)
    manifest.write(path, encoding='utf-8', xml_declaration=True)
    with a.record.open('a') as record:
        record.write(json.dumps(dict(log=a.log.name, added=added)) + '\n')
    subprocess.run(['repo', 'sync', '-c', '-j4', '--no-tags', '--no-clone-bundle', *added],
                   cwd=a.workspace, check=True)
    print('Added pinned dependencies:', ', '.join(added))


if __name__ == '__main__':
    main()
