"""Offline RM19795 EoT/null-insertion audit; never reads or changes a phone."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from compare_m3_factory_panel import inspect, fdt, Fdt
from compare_m3_stock_dsc import load_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('boot', 'dtbo', 'cmdline', 'libfdt', 'record', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    command_bytes = args.cmdline.read_bytes()
    command = command_bytes.decode('utf-8')
    indices = {}
    for key in ('dtb', 'dtbo'):
        matches = re.findall(r'\bandroidboot\.' + key + r'_idx=(\d+)\b', command)
        if len(matches) != 1:
            raise ValueError('Ambiguous factory selector: ' + key)
        indices[key] = int(matches[0])
    panels = re.findall(r'\bmsm_drm\.dsi_display0=([^ :]+)', command)
    if len(panels) != 1 or not panels[0].startswith('qcom,mdss_dsi_rm19795'):
        raise ValueError('Expected selected factory RM19795 panel')
    trees, images = [], {}
    for key, path in [('dtb', args.boot), ('dtbo', args.dtbo)]:
        report = inspect(path)
        tree = report['trees'][indices[key]]
        trees.append(path.read_bytes()[tree['offset']:tree['offset'] + tree['size_bytes']])
        images[key] = dict(image_sha256=report['sha256'], index=indices[key], tree_sha256=tree['sha256'])
    dll_scope = os.add_dll_directory(str(args.libfdt.resolve().parent)) if os.name == 'nt' else None
    try:
        merged = Fdt(args.libfdt).apply(*trees)
    finally:
        if dll_scope:
            dll_scope.close()
    nodes = fdt(merged, ('**',))['matching_nodes']
    selected = [n for n in nodes if n['path'].endswith('/' + panels[0])]
    controllers = [n for n in nodes if n['path'].endswith('@ae94000')]
    if len(selected) != 1 or len(controllers) != 1 or \
            controllers[0]['properties'].get('compatible') != ['qcom,dsi-ctrl-hw-v2.4']:
        raise ValueError('Ambiguous panel or unexpected SM8250 controller')
    props = selected[0]['properties']
    keys = ('qcom,mdss-dsi-tx-eot-append', 'qcom,mdss-dsi-rx-eot-ignore',
            'qcom,mdss-dsi-force-clock-lane-hs', 'qcom,mdss-dsi-reset-sequence',
            'qcom,platform-reset-gpio')
    capture = load_capture(args.record)
    regs = capture['banks']['dsi0_ctrl']
    # Pinned ACK dsi_cfg.h: DSI_6G_REG_SHIFT=4; host_snapshot dumps the
    # adjusted ctrl_base. Downstream addresses are relative to the resource.
    # EOT CTRL: resource 0xcc -> snapshot 0xc8; NULL: 0x2b4 -> 0x2b0.
    eot, null = regs[0xcc - 4], regs[0x2b4 - 4]
    result = dict(
        scope='Offline original F.20 DT and accepted native snapshot; no handset access, partition reread or new display experiment.',
        images=images, command_line_sha256=hashlib.sha256(command_bytes).hexdigest(),
        selected_panel=panels[0], selected_panel_path=selected[0]['path'],
        panel_properties={k: dict(present=k in props, value=props.get(k)) for k in keys},
        null_insertion_nodes=[n['path'] for n in nodes if 'qcom,null-insertion-enabled' in n['properties']],
        boot_id=capture['boot'], snapshot_sha256=hashlib.sha256(capture['raw']).hexdigest(),
        register_base_shift=4,
        candidate_native=dict(eot_resource_offset='0xcc', eot_snapshot_offset='0xc8',
            eot_raw=hex(eot), tx_eot_append=bool(eot & 1), rx_eot_ignore=bool(eot & 16),
            null_resource_offset='0x2b4', null_snapshot_offset='0x2b0',
            null_raw=hex(null), null_insertion_enabled=bool(null & 1)),
        reference_driver_expectation=dict(tx_eot_append='qcom,mdss-dsi-tx-eot-append' in props,
            rx_eot_ignore='qcom,mdss-dsi-rx-eot-ignore' in props),
        tx_eot_configuration_difference=bool(eot & 1) != ('qcom,mdss-dsi-tx-eot-append' in props),
        stock_runtime_eot_register=None, stock_runtime_null_register=None,
        root_cause='NOT_ESTABLISHED',
        limitation='DT absence plus same-platform downstream read_bool semantics predicts configuration, not the exact F.20 executable or runtime register. This does not demonstrate that EoT causes corruption.',
        source_pins=dict(ack_mirror='cfa72fb3d7f89372c7e449a4de2477551ea4c29c',
                         downstream='b76eb6c93add8152b1aa873da0d8d7f495cccab0'))
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('boot_id', 'candidate_native', 'reference_driver_expectation', 'tx_eot_configuration_difference', 'root_cause')}, indent=2))


if __name__ == '__main__':
    main()
