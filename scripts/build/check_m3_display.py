"""Check the effective M3 graph after applying the complete source board overlay."""
from inspect_boot_dt import fdt
from check_m2_resources import check_m2_resources, normalized_node


def check_m3_display(data):
    preserved = check_m2_resources(data, display=True)
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    base = '/soc/display-subsystem@ae00000'
    expected = {
        base: ('qcom,sm8250-mdss', [0xae00000, 0x1000]),
        base+'/display-controller@ae01000': ('qcom,sm8250-dpu', [0xae01000, 0x8f000, 0xaeb0000, 0x3000]),
        base+'/dsi@ae94000': ('qcom,sm8250-dsi-ctrl', [0xae94000, 0x400]),
        base+'/phy@ae94400': ('qcom,dsi-phy-7nm', [0xae94400, 0x200, 0xae94600, 0x280, 0xae94900, 0x260]),
        '/soc/clock-controller@af00000': ('qcom,sm8250-dispcc', [0xaf00000, 0x10000]),
        '/soc/interconnect@1740000': ('qcom,sm8250-mmss-noc', [0x1740000, 0x1f080]),
        '/soc/pinctrl@f100000': ('qcom,sm8250-pinctrl', [0xf100000, 0x300000, 0xf500000, 0x300000, 0xf900000, 0x300000]),
    }
    for path, (compatible, reg) in expected.items():
        node = tree.get(path, {})
        if (compatible not in node.get('compatible', []) or node.get('reg') != reg
                or node.get('status', ['okay']) != ['okay']):
            raise ValueError('Native display resource mismatch: ' + path)
    legacy = ['pinctrl@f000000', 'qcom,dispcc@af00000', 'qcom,mdss_mdp@ae00000',
              'qcom,mdss_dsi_ctrl0@ae94000', 'qcom,mdss_dsi_ctrl1@ae96000',
              'qcom,mdss_dsi_phy0@ae94400', 'qcom,mdss_dsi_phy1@ae96400',
              'qcom,mdss_dsi_pll@ae94900', 'qcom,mdss_dsi_pll@ae96900']
    for name in legacy:
        if tree['/soc/'+name].get('status') != ['disabled']:
            raise ValueError('OEM overlay re-enabled an overlapping display provider: ' + name)
    if normalized_node(tree, base)['iommus'] != [dict(target='/soc/apps-smmu@15000000', args=[0x820, 0x402])]:
        raise ValueError('MDSS stream ID/mask differs from pinned SM8250')
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
    if ids.get(reset[0]) != '/soc/pinctrl@f100000' or reset[1:] != [75, 1]:
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
    return dict(m1_resources=preserved, native_resources=list(expected),
                overlapping_legacy_providers_disabled=legacy, reciprocal_endpoints=endpoints,
                panel_mode='1080x2400@60, RGB888, DSC 8bpc/8bpp, 540x48 slices',
                reset='TLMM75 active-low', te='TLMM66 mdp_vsync',
                hardware_result='NOT RUN; this is a source resource check')
