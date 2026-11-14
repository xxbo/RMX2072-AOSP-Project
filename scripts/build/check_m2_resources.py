"""Compare source DT resources with M1 measurements, resolving real phandles."""
import json
from pathlib import Path
from inspect_boot_dt import fdt

CELLS = {'clocks': '#clock-cells', 'assigned-clocks': '#clock-cells',
         'assigned-clock-parents': '#clock-cells', 'resets': '#reset-cells',
         'power-domains': '#power-domain-cells', 'iommus': '#iommu-cells',
         'interconnects': '#interconnect-cells', 'phys': '#phy-cells',
         'interrupts-extended': '#interrupt-cells', 'hwlocks': '#hwlock-cells',
         'mboxes': '#mbox-cells', 'dmas': '#dma-cells',
         'io-channels': '#io-channel-cells', 'thermal-sensors': '#thermal-sensor-cells'}
PLAIN = {'interrupt-parent', 'interrupt-affinity', 'memory-region', 'qcom,bcm-voters',
         'next-level-cache', 'cpu-idle-states'}
FIXED = {'syscon': 2}  # qcom,sfpb-mutex: syscon phandle, offset, stride.


def normalized_node(tree, path):
    ids = {n['phandle'][0]: p for p, n in tree.items() if 'phandle' in n}
    out = {}
    for key, value in tree[path].items():
        if key in ('phandle', 'linux,phandle'):
            continue
        if key in CELLS or key in PLAIN or key in FIXED or key.endswith('-supply'):
            pos, result = 0, []
            while pos < len(value):
                target = ids.get(value[pos])
                if target is None:
                    raise ValueError(f'Unresolved reference {path}/{key}: {value[pos]}')
                count = tree[target][CELLS[key]][0] if key in CELLS else FIXED.get(key, 0)
                if pos + count >= len(value):
                    raise ValueError(f'Truncated reference {path}/{key}')
                result.append(dict(target=target, args=value[pos + 1:pos + 1 + count]))
                pos += 1 + count
            value = result
        out[key] = value
    return out


def check_m2_resources(data):
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    reference = json.loads((Path(__file__).resolve().parents[2] / 'build/device/m2-m1-resource-reference.json').read_text())
    differences = []
    for path, props in reference['nodes'].items():
        if path not in tree:
            differences.append(path + ': absent')
            continue
        actual = normalized_node(tree, path)
        for key, value in props.items():
            if actual.get(key) != value:
                differences.append(f'{path}/{key}: {actual.get(key)!r} != {value!r}')
    if differences:
        raise ValueError('M1 resource mismatch:\n' + '\n'.join(differences))
    primary = '/soc/qcom,spmi@c440000/qcom,pm8150@0'
    if tree[primary].get('#address-cells') != [1] or tree[primary].get('#size-cells') != [0]:
        raise ValueError('Primary PMIC is not in the upstream peripheral-address form')
    pon = primary + '/pon@800'
    key = pon + '/pwrkey'
    expected = {'compatible': ['qcom,pm8941-pwrkey'], 'interrupts': [0, 8, 0, 3],
                'debounce': [15625], 'bias-pull-up': [], 'linux,code': [116]}
    if (tree[pon].get('compatible') != ['qcom,pm8998-pon'] or tree[pon].get('reg') != [0x800]
            or normalized_node(tree, key) != expected or primary + '/qcom,power-on@800' in tree):
        raise ValueError('Unexpected source PON binding or duplicate legacy PON')
    return dict(reference_boot_id=reference['boot_id'], checked_nodes=len(reference['nodes']),
                phandles_resolved_to_paths=True, source_pon='upstream-parent-child',
                scope='M1 bound platform devices and reserved memory; does not qualify inactive hardware')
