"""Check the RMX2072 PCIe0/power graph after the full 20607 board overlay.

This qualifies source wiring only, not firmware, RF calibration or connectivity.
"""
from inspect_boot_dt import fdt
from check_m2_resources import normalized_node


def check_m3_wifi(data, staged=False):
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    fabric = '/soc' + ('/display-fabric-lab' if staged else '')
    pins = '/soc' + ('/display-pins-lab' if staged else '') + '/pinctrl@f100000'
    host, phy, pmu = (fabric + p for p in ('/pcie@1c00000', '/phy@1c06000', '/qca6390-pmu'))
    endpoint = host + '/pcie@0/wifi@0'
    ids = {n['phandle'][0]: p for p, n in tree.items() if 'phandle' in n}

    def expect(path, properties):
        if any(tree.get(path, {}).get(k) != v for k, v in properties.items()):
            raise ValueError('RMX2072 WLAN wiring mismatch: ' + path)

    def ref(path, key, target):
        if normalized_node(tree, path).get(key) != [dict(target=target, args=[])]:
            raise ValueError('RMX2072 WLAN supply/provider mismatch: ' + path + '/' + key)

    expect(host, {'compatible': ['qcom,pcie-sm8250'], 'status': ['okay'],
        'reg': [0x1c00000, 0x3000, 0x60000000, 0xf1d, 0x60000f20, 0xa8,
                0x60001000, 0x1000, 0x60100000, 0x100000, 0x1c03000, 0x1000],
        'reg-names': ['parf', 'dbi', 'elbi', 'atu', 'config', 'mhi'],
        '#address-cells': [3], '#size-cells': [2], 'num-lanes': [1],
        'linux,pci-domain': [0], 'bus-range': [0, 255], 'dma-coherent': [],
        'interrupts': [v for irq in (*range(141, 149), 140) for v in (0, irq, 4)],
        'ranges': [0x01000000, 0, 0, 0x60200000, 0, 0x100000,
                   0x02000000, 0, 0x60300000, 0x60300000, 0, 0x3d00000]})
    iommu = tree[host].get('iommu-map', [])
    if (len(iommu) != 8 or iommu[::4] != [0, 0x100]
            or iommu[2::4] != [0x1c00, 0x1c01] or iommu[3::4] != [1, 1]
            or [ids.get(x) for x in iommu[1::4]] != ['/soc/apps-smmu@15000000'] * 2):
        raise ValueError('PCIe0 IOMMU stream mapping differs from SM8250')
    expect(phy, {'compatible': ['qcom,sm8250-qmp-gen3x1-pcie-phy'],
                 'reg': [0x1c06000, 0x1000], 'status': ['okay'],
                 '#phy-cells': [0], '#clock-cells': [0],
                 'clock-output-names': ['pcie_0_pipe_clk']})
    ref(host, 'phys', phy)
    # Reuse already checked 0.88 V/1.2 V native supplies, never dummy regulators.
    symbols = tree['/__symbols__']
    ref(phy, 'vdda-phy-supply', symbols['diag_l5'][0])
    ref(phy, 'vdda-pll-supply', symbols['diag_ufs_l9'][0])
    for path, key, number, polarity in ((host, 'perst-gpios', 79, 1),
            (host, 'wake-gpios', 81, 0), (pmu, 'wlan-enable-gpios', 20, 0),
            (pmu, 'bt-enable-gpios', 21, 0)):
        value = tree.get(path, {}).get(key, [])
        if len(value) != 3 or ids.get(value[0]) != pins or value[1:] != [number, polarity]:
            raise ValueError('WLAN GPIO mismatch: ' + key)
    expect(pins + '/pcie0-default-state/clkreq-pins',
           {'pins': ['gpio80'], 'function': ['pci_e0']})
    expect(pmu, {'compatible': ['qcom,qca6390-pmu']})
    rails = {
        'vddaon': ('diag-regulators/smps6', 950000, 952000),
        'vddpmu': ('wlan-digital-regulators/smps2', 950000, 952000),
        'vddrfa0p95': ('wlan-digital-regulators/smps2', 950000, 952000),
        'vddrfa1p3': ('display-regulators/smps8', 1350000, 1352000),
        'vddpcie1p3': ('display-regulators/smps8', 1350000, 1352000),
        'vddrfa1p9': ('diag-regulators/smps5', 1900000, 1904000),
        'vddpcie1p9': ('diag-regulators/smps5', 1900000, 1904000),
    }
    for name, (suffix, low, high) in rails.items():
        target = '/soc/rsc@18200000/' + suffix
        ref(pmu, name + '-supply', target)
        expect(target, {'regulator-min-microvolt': [low], 'regulator-max-microvolt': [high]})
    expect('/soc/rsc@18200000/wlan-digital-regulators',
           {'compatible': ['qcom,pm8009-rpmh-regulators'], 'qcom,pmic-id': ['f']})
    ref(pmu, 'vddio-supply', symbols['diag_ufs_s4'][0])
    expect(host + '/pcie@0', {'reg': [0, 0, 0, 0, 0], '#address-cells': [3], '#size-cells': [2]})
    expect(endpoint, {'compatible': ['pci17cb,1101'], 'reg': [0x10000, 0, 0, 0, 0]})
    outputs = {'vddrfacmn': 0, 'vddaon': 1, 'vddwlcx': 2, 'vddwlmx': 3,
               'vddrfa0p8': 5, 'vddrfa1p2': 6, 'vddrfa1p7': 7, 'vddpcie0p9': 8, 'vddpcie1p8': 9}
    for name, number in outputs.items():
        ref(endpoint, name + '-supply', pmu + '/regulators/ldo' + str(number))
    if any('calibration' in key or key in ('firmware-name', 'local-mac-address', 'mac-address')
           for key in tree[endpoint]):
        raise ValueError('No foreign calibration/MAC or firmware override is allowed')
    for path, compatible in (('/soc/qcom,pcie@1c00000', 'realme,rmx2072-parked-pcie'),
            ('/soc/qcom,cnss-qca6390@b0000000', 'realme,rmx2072-parked-cnss')):
        expect(path, {'status': ['disabled'], 'compatible': [compatible]})
    return dict(controller='PCIe0', endpoint='17cb:1101 (F.20 inventory)',
                gpio=[20, 21, 79, 80, 81], digital_rail='PM8009 S2 (20607)',
                physical_result='NOT RUN', firmware_supplied=False, connectivity='NOT TESTED')
