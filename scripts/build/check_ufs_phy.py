"""Check the isolated QMP provider and preserve the existing OEM resource graph."""
from check_usb_stream import require_sid0
from inspect_boot_dt import fdt


LAB = '/soc/ufs-phy-lab'
PHY = LAB + '/phy@1d87000'
TEST = LAB + '/ufs-phy-exercise'
REGULATORS = '/soc/rsc@18200000/diag-regulators'
L5, L9 = REGULATORS + '/ldo5', REGULATORS + '/ldo9'
GCC = '/soc/clock-controller@100000'
RPMHCC = '/soc/rsc@18200000/diag-clock-controller'


def nodes(data):
    return {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}


def phandles(tree):
    values = [((p.get('phandle') or p.get('linux,phandle'))[0], path)
              for path, p in tree.items() if p.get('phandle') or p.get('linux,phandle')]
    result = dict(values)
    if len(result) != len(values) or 0 in result or 0xffffffff in result:
        raise ValueError('Invalid or duplicate phandle')
    return result


def verify_original_properties(old, new):
    old_ids, new_ids = phandles(old), phandles(new)
    renumbered = 0
    for path, original in old.items():
        props = new[path]
        if path == '/__symbols__':
            labels = {'diag_ufs_phy': [PHY], 'diag_ufs_l9': [L9]}
            if original.keys() & labels.keys() or props != {**original, **labels}:
                raise ValueError('OEM symbol target changed')
            continue
        if props.keys() != original.keys():
            raise ValueError(f'Original property set changed at {path}')
        for key, left in original.items():
            right = props[key]
            if left == right:
                continue
            # libfdt relocates OEM-local phandles above the new base maximum.
            if (key in ('reg', 'ranges', 'interrupts', 'clock-frequency', 'qcom,msm-id', 'qcom,board-id')
                    or key.startswith('#') or not isinstance(left, list)
                    or not isinstance(right, list) or len(left) != len(right)):
                raise ValueError(f'Original property changed: {path}/{key}')
            for a, b in zip(left, right):
                if a != b:
                    if a not in old_ids or old_ids[a] != new_ids.get(b):
                        raise ValueError(f'Original cell changed: {path}/{key} {a} -> {b}')
                    renumbered += 1
    return renumbered


def check_ufs_phy(before, after):
    old, new = nodes(before), nodes(after)
    additions = {LAB, PHY, TEST, L9}
    if old.keys() & additions or new.keys() != old.keys() | additions:
        raise ValueError('Unexpected PHY control node changes')
    renumbered = verify_original_properties(old, new)

    def ph(path):
        props = new[path]
        if props.get('status', ['okay']) not in (['ok'], ['okay']):
            raise ValueError(f'Disabled supplier: {path}')
        return props['phandle'][0]

    phy, test = new[PHY], new[TEST]
    for path in (LAB, PHY, TEST, REGULATORS, GCC, RPMHCC):
        if new[path].get('status', ['okay']) not in (['okay'], ['ok']):
            raise ValueError(f'Disabled provider or consumer: {path}')
    if (new[REGULATORS].get('compatible') != ['qcom,pm8150-rpmh-regulators']
            or new[REGULATORS].get('qcom,pmic-id') != ['a']
            or new[GCC].get('compatible') != ['qcom,gcc-sm8250']
            or new[RPMHCC].get('compatible') != ['qcom,sm8250-rpmh-clk']):
        raise ValueError('Unexpected regulator or clock provider binding')
    if (new[LAB].get('compatible') != ['realme,rmx2072-diag-ufs-phy-bus']
            or new[LAB].get('ranges') != [] or new[LAB].get('#address-cells') != [1]
            or new[LAB].get('#size-cells') != [1] or phy.get('reg') != [0x1d87000, 0x1000]
            or phy.get('compatible') != ['qcom,sm8250-qmp-ufs-phy'] or phy.get('#phy-cells') != [0]
            or phy.get('clock-names') != ['ref', 'ref_aux', 'qref']
            or phy.get('clocks') != [ph(RPMHCC), 0, ph(GCC), 166, ph(GCC), 148]
            or phy.get('power-domains') != [ph(GCC), 4]
            or phy.get('vdda-phy-supply') != [ph(L5)] or phy.get('vdda-pll-supply') != [ph(L9)]):
        raise ValueError('Unexpected QMP resources, supplies, clocks or power domain')
    for path, voltage in ((L5, 880000), (L9, 1200000)):
        for key in ('regulator-min-microvolt', 'regulator-max-microvolt'):
            if new[path].get(key) != [voltage]:
                raise ValueError(f'{path}: incorrect {key}')
    if (test.get('compatible') != ['realme,rmx2072-diag-ufs-phy-test']
            or test.get('phys') != [ph(PHY)] or test.get('phy-names') != ['ufsphy']
            or test.get('power-domains') != [ph(GCC), 4] or test.get('resets') != [ph(GCC), 33]
            or test.get('reset-names') != ['rst']):
        raise ValueError('Incorrect diagnostic consumer wiring')
    return dict(provider=PHY, consumer=TEST, supply_microvolts=[880000, 1200000],
                original_nodes_preserved=len(old), relocated_reference_cells=renumbered,
                primary_usb_sid_mask=require_sid0(after, legacy_base=True))
