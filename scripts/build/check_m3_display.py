"""Check the effective M3 graph after applying the complete source board overlay."""
from inspect_boot_dt import fdt
from check_m2_resources import check_m2_resources, normalized_node


def check_m3_display(data, staged=False):
    preserved = check_m2_resources(data, display=True)
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    for path, node in tree.items():
        if any(c in node.get('compatible', []) for c in ('qcom,kgsl-3d0', 'qcom,adreno', 'qcom,adreno-3xx', 'qcom,gpu-gmu')):
            if node.get('status') != ['disabled']:
                raise ValueError('CPU-rendered display profile must not bind the unported GPU/GMU: '+path)
    prefixes = {part: '/soc'+('/display-'+part+'-lab' if staged else '') for part in ('pins', 'fabric', 'core')}
    if staged:
        for path in prefixes.values():
            node = tree.get(path, {})
            if (node.get('compatible') != ['realme,rmx2072-diag-ufs-phy-bus']
                    or node.get('ranges') != [] or node.get('#address-cells') != [1]
                    or node.get('#size-cells') != [1]):
                raise ValueError('Display stage must use the existing explicitly bound population driver: '+path)
    base = prefixes['core']+'/display-subsystem@ae00000'
    pins = prefixes['pins']+'/pinctrl@f100000'
    expected = {
        base: ('qcom,sm8250-mdss', [0xae00000, 0x1000]),
        base+'/display-controller@ae01000': ('qcom,sm8250-dpu', [0xae01000, 0x8f000, 0xaeb0000, 0x3000]),
        base+'/dsi@ae94000': ('qcom,sm8250-dsi-ctrl', [0xae94000, 0x400]),
        base+'/phy@ae94400': ('qcom,dsi-phy-7nm', [0xae94400, 0x200, 0xae94600, 0x280, 0xae94900, 0x260]),
        prefixes['fabric']+'/clock-controller@af00000': ('qcom,sm8250-dispcc', [0xaf00000, 0x10000]),
        prefixes['fabric']+'/interconnect@1740000': ('qcom,sm8250-mmss-noc', [0x1740000, 0x1f080]),
        pins: ('qcom,sm8250-pinctrl', [0xf100000, 0x300000, 0xf500000, 0x300000, 0xf900000, 0x300000]),
    }
    for path, (compatible, reg) in expected.items():
        node = tree.get(path, {})
        if (compatible not in node.get('compatible', []) or node.get('reg') != reg
                or node.get('status', ['okay']) != ['okay']):
            raise ValueError('Native display resource mismatch: ' + path)
    reserved = tree[pins].get('gpio-reserved-ranges', [])
    if len(reserved) % 2:
        raise ValueError('Malformed TLMM GPIO reservation')
    valid = set(range(181))
    for start, count in zip(reserved[::2], reserved[1::2]):
        if count <= 0 or start + count > 181:
            raise ValueError('TLMM GPIO reservation outside the physical provider')
        valid.difference_update(range(start, start + count))
    if valid != {66, 75}:
        raise ValueError('Display TLMM must expose only TE 66 and reset 75; unmasked registration previously rebooted')
    legacy = ['pinctrl@f000000', 'qcom,dispcc@af00000', 'qcom,mdss_mdp@ae00000',
              'qcom,mdss_dsi_ctrl0@ae94000', 'qcom,mdss_dsi_ctrl1@ae96000',
              'qcom,mdss_dsi_phy0@ae94400', 'qcom,mdss_dsi_phy1@ae96400',
              'qcom,mdss_dsi_pll@ae94900', 'qcom,mdss_dsi_pll@ae96900']
    for name in legacy:
        if tree['/soc/'+name].get('status') != ['disabled']:
            raise ValueError('OEM overlay re-enabled an overlapping display provider: ' + name)
    if normalized_node(tree, base)['iommus'] != [dict(target='/soc/apps-smmu@15000000', args=[0x820, 0x402])]:
        raise ValueError('MDSS stream ID/mask differs from pinned SM8250')
    dsi = normalized_node(tree, base+'/dsi@ae94000')
    if 'assigned-clocks' in dsi or 'assigned-clock-parents' in dsi:
        raise ValueError('DSI parents must be selected by the host after PHY enable')
    names = dsi.get('clock-names', [])
    clocks = dsi.get('clocks', [])
    if len(names) != len(clocks) or len(set(names)) != len(names):
        raise ValueError('DSI clock names and providers do not match')
    sources = dict(zip(names, clocks))
    dispcc = prefixes['fabric']+'/clock-controller@af00000'
    expected_sources = {
        'byte_src': dict(target=dispcc, args=[3]),
        'pixel_src': dict(target=dispcc, args=[37]),
        'dsi_pll_byte': dict(target=base+'/phy@ae94400', args=[0]),
        'dsi_pll_pixel': dict(target=base+'/phy@ae94400', args=[1]),
    }
    if any(sources.get(name) != value for name, value in expected_sources.items()):
        raise ValueError('Deferred DSI source clocks differ from the SM8250 providers')
    ids = {n['phandle'][0]: p for p, n in tree.items() if 'phandle' in n}
    endpoints = {p: ids.get(n['remote-endpoint'][0]) for p,n in tree.items()
                 if p.startswith(base+'/') and 'remote-endpoint' in n}
    if len(endpoints) != 4 or any(endpoints.get(other) != path for path,other in endpoints.items()):
        raise ValueError('Display graph is not a reciprocal DPU -> DSI -> panel chain')
    panel = base+'/dsi@ae94000/panel@0'
    node = tree[panel]
    if node.get('compatible') != ['realme,rmx2072-rm19795-panel'] or node.get('reg') != [0]:
        raise ValueError('Wrong physical panel or DSI channel')
    reset = node['reset-gpios']
    if ids.get(reset[0]) != pins or reset[1:] != [75, 1]:
        raise ValueError('Panel reset must be TLMM 75, active low')
    for name, target, voltage in [
        ('vddio', '/soc/rsc@18200000/diag-regulators/ldo14', 1800000),
        ('vout', '/soc/rsc@18200000/display-regulators/ldo2', 1280000),
        ('vdd', '/soc/rsc@18200000/display-regulators/ldo11', 3000000),
    ]:
        if (ids.get(node[name+'-supply'][0]) != target or
                tree[target].get('regulator-min-microvolt') != [voltage] or
                tree[target].get('regulator-max-microvolt') != [voltage]):
            raise ValueError('Panel rail differs from official board source: ' + name)
    return dict(m1_resources=preserved, native_resources=list(expected), staged=staged,
                overlapping_legacy_providers_disabled=legacy, reciprocal_endpoints=endpoints,
                panel_mode='1080x2400@60, RGB888, DSC 8bpc/8bpp, 540x48 slices',
                reset='TLMM75 active-low', te='TLMM66 mdp_vsync', valid_gpio_offsets=sorted(valid),
                hardware_result='NOT RUN; this is a source resource check')
