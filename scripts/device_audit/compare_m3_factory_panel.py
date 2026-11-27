"""Compare selected F.20 panel bytes with the pinned Q source, without flashing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
from inspect_boot_dt import inspect, fdt
from build_m2_device_tree import Fdt
from import_rm19795_panel import SOURCE_SHA


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(value):
    if isinstance(value, dict) and set(value) == {'hex'}:
        return bytes.fromhex(value['hex'])
    if isinstance(value, list) and all(isinstance(x, int) for x in value):
        return b''.join(x.to_bytes(4, 'big') for x in value)
    raise ValueError('Property is not a raw byte array')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('boot', 'dtbo', 'cmdline', 'source', 'libfdt', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    source = a.source.read_bytes().replace(b'\r\n', b'\n')
    if sha(source) != SOURCE_SHA:
        raise ValueError('Official panel source does not match the pinned blob')
    cmdline = a.cmdline.read_text(encoding='utf-8').strip()
    selectors = {}
    for name in ('dtb', 'dtbo'):
        matches = re.findall(r'\bandroidboot\.' + name + r'_idx=(\d+)\b', cmdline)
        if len(matches) != 1:
            raise ValueError('Ambiguous or absent factory selector: ' + name)
        selectors[name] = int(matches[0])
    selected = re.findall(r'\bmsm_drm\.dsi_display0=([^ :]+)', cmdline)
    if len(selected) != 1 or not selected[0].startswith('qcom,mdss_dsi_rm19795'):
        raise ValueError('Factory command line does not select the expected panel')
    trees, images = [], {}
    for name, path in [('dtb', a.boot), ('dtbo', a.dtbo)]:
        report = inspect(path)
        tree = report['trees'][selectors[name]]
        trees.append(path.read_bytes()[tree['offset']:tree['offset'] + tree['size_bytes']])
        images[name] = dict(image_sha256=report['sha256'], index=selectors[name],
                            tree_sha256=tree['sha256'])
    dll_scope = os.add_dll_directory(str(a.libfdt.resolve().parent)) if os.name == 'nt' else None
    try:
        merged = Fdt(a.libfdt).apply(*trees)
    finally:
        if dll_scope:
            dll_scope.close()
    nodes = fdt(merged, ('**',))['matching_nodes']
    suffix = '/' + selected[0] + '/qcom,mdss-dsi-display-timings/timing@0'
    matches = [n for n in nodes if n['path'].endswith(suffix)]
    if len(matches) != 1:
        raise ValueError('Selected 60 Hz factory timing is ambiguous or absent')
    props = matches[0]['properties']
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', source.decode(), flags=re.S)
    timing = text.split('timing@0', 1)[1].split('timing@1', 1)[0]
    arrays = {}
    for name in ('on-command', 'post-on-backlight', 'off-command', 'panel-phy-timings'):
        key = 'qcom,mdss-dsi-' + name
        official = bytes.fromhex(re.search(re.escape(key) + r'\s*=\s*\[([^]]+)\]', timing)[1])
        factory = raw(props[key])
        arrays[name] = dict(equal=official == factory, q_bytes=len(official),
            f20_bytes=len(factory), q_sha256=sha(official), f20_sha256=sha(factory))
    scalars = {}
    for key in ('qcom,mdss-dsi-panel-width', 'qcom,mdss-dsi-panel-height',
                'qcom,mdss-dsi-panel-framerate', 'qcom,mdss-dsi-panel-clockrate',
                'qcom,mdss-dsi-h-front-porch', 'qcom,mdss-dsi-h-back-porch',
                'qcom,mdss-dsi-h-pulse-width', 'qcom,mdss-dsi-v-front-porch',
                'qcom,mdss-dsi-v-back-porch', 'qcom,mdss-dsi-v-pulse-width',
                'qcom,mdss-dsc-encoders', 'qcom,mdss-dsc-slice-height',
                'qcom,mdss-dsc-slice-width', 'qcom,mdss-dsc-slice-per-pkt',
                'qcom,mdss-dsc-bit-per-component', 'qcom,mdss-dsc-bit-per-pixel'):
        match = re.search(re.escape(key) + r'\s*=\s*<([^>]+)>', timing)
        official = [int(v, 0) for v in match[1].split()]
        scalars[key] = dict(q=official, f20=props[key], equal=official == props[key])
    result = dict(images=images, command_line_sha256=sha(a.cmdline.read_bytes()),
        selected_panel=selected[0], source_sha256=SOURCE_SHA, arrays=arrays,
        scalars=scalars, all_compared_equal=all(v['equal'] for v in [*arrays.values(), *scalars.values()]),
        scope='Selected factory DT configuration compared with source; not runtime F.20 registers or panel readback. No handset writes.')
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(all_compared_equal=result['all_compared_equal'], arrays=len(arrays), scalars=len(scalars))))


if __name__ == '__main__':
    main()
