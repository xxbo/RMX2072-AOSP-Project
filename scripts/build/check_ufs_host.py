"""Verify native host resources and the inactive OEM host before and after OEM fixups."""
from check_usb_stream import require_sid0
from check_ufs_phy import GCC, LAB, L5, L9, PHY, REGULATORS, RPMHCC, nodes, verify_original_properties


def check_ufs_host(before, after, *, g3=False):
    old, new = nodes(before), nodes(after)
    soc = '/soc'
    host_bus, fabric = soc+'/ufs-host-lab', soc+'/ufs-fabric-lab'
    host, legacy = host_bus+'/ufs@1d84000', soc+'/ufshc@1d84000'
    voter = soc+'/rsc@18200000/ufs-bcm-voter'
    noc = {}
    labels = dict(diag_ufs_host=host, diag_ufs_phy=PHY, diag_ufs_l9=L9, diag_ufs_bcm=voter)
    rails = {'ldo6': ('diag_ufs_l6', 1200000), 'ldo17': ('diag_ufs_l17', 2504000),
             'smps4': ('diag_ufs_s4', 1800000)}
    for node, (label, _) in rails.items():
        labels[label] = REGULATORS+'/'+node
    for name, address, length, suffix in (
            ('cnoc', 0x1500000, 0xa580, 'config-noc'), ('', 0x1620000, 0x1c200, 'system-noc'),
            ('mc', 0x163d000, 0x1000, 'mc-virt'), ('a1', 0x16e0000, 0x1f180, 'aggre1-noc'),
            ('gem', 0x9100000, 0xb4000, 'gem-noc')):
        path = fabric+f'/interconnect@{address:x}'
        noc[path] = (address, length, suffix)
        if name:
            labels['diag_ufs_'+name] = path
    added = {LAB, host_bus, fabric, *labels.values(), *noc}
    if old.keys() & added or new.keys() != old.keys() | added:
        raise ValueError('Unexpected UFS host node additions or removals')
    parked = ['realme,rmx2072-parked-ufs-host']
    if 'qcom,ufshc' not in old[legacy]['compatible'] or new[legacy]['compatible'] != parked:
        raise ValueError('OEM host has not been isolated')
    old[legacy] = {**old[legacy], 'compatible': parked}
    xo = old['/__symbols__']['diag_xo'][0]
    if (old[xo]['clock-frequency'] != [19200000] or new[xo]['clock-frequency'] != [38400000]
            or new[RPMHCC]['clocks'] != new[xo]['phandle']):
        raise ValueError('Unexpected oscillator or RPMh clock parent')
    old[xo] = {**old[xo], 'clock-frequency': [38400000]}
    moved = verify_original_properties(old, new, {k: [v] for k, v in labels.items()})

    def check(path, **expected):
        if new[path].get('status', ['okay']) not in (['ok'], ['okay']):
            raise ValueError(f'Disabled UFS resource: {path}')
        for key, value in expected.items():
            if new[path].get(key) != value:
                raise ValueError(f'Unexpected {path}/{key}: {new[path].get(key)} != {value}')

    def ph(path):
        return new[path]['phandle'][0]

    for path in (LAB, fabric, host_bus):
        check(path, compatible=['realme,rmx2072-diag-ufs-phy-bus'], ranges=[],
              **{'#address-cells': [1], '#size-cells': [1]})
    check(voter, compatible=['qcom,bcm-voter'])
    for path, (address, length, suffix) in noc.items():
        check(path, reg=[address, length], compatible=['qcom,sm8250-'+suffix],
              **{'#interconnect-cells': [2], 'qcom,bcm-voters': [ph(voter)]})
    for path, uv in [(L5, 880000), (L9, 1200000)] + [
            (REGULATORS+'/'+node, uv) for node, (_, uv) in rails.items()]:
        check(path, **{'regulator-min-microvolt': [uv], 'regulator-max-microvolt': [uv]})
    gcc, rpmh = ph(GCC), ph(RPMHCC)
    check(PHY, compatible=['qcom,sm8250-qmp-ufs-phy'], reg=[0x1d87000, 0x1000],
          clocks=[rpmh, 0, gcc, 166, gcc, 148], resets=[ph(host), 0],
          **{'power-domains': [gcc, 4], 'reset-names': ['ufsphy'], 'vdda-phy-supply': [ph(L5)],
             'vdda-pll-supply': [ph(L9)], '#phy-cells': [0]})
    def resolve(label):
        return ph(new['/__symbols__'][label][0])

    smmu = resolve('apps_smmu')
    high = 300000000 if g3 else 37500000
    check(host, compatible=['qcom,sm8250-ufshc', 'qcom,ufshc', 'jedec,ufs-2.0'],
          reg=[0x1d84000, 0x3000], phys=[ph(PHY)], resets=[gcc, 33],
          interrupts=[0, 265, 4], iommus=[smmu, 0xe0, 0, smmu, 0x4e0, 0],
          clocks=[gcc, 162, gcc, 6, gcc, 161, gcc, 171, rpmh, 0, gcc, 170, gcc, 168, gcc, 169],
          interconnects=[resolve('diag_ufs_a1'), 7, 0, resolve('diag_ufs_mc'), 1, 0,
                         resolve('diag_ufs_gem'), 2, 0, resolve('diag_ufs_cnoc'), 45, 0],
          **{'interrupt-parent': [resolve('intc')], 'power-domains': [gcc, 4], '#reset-cells': [1],
             'interconnect-names': ['ufs-ddr', 'cpu-ufs'], 'phy-names': ['ufsphy'], 'reset-names': ['rst'],
             'vcc-supply': [resolve('diag_ufs_l17')], 'vccq-supply': [resolve('diag_ufs_l6')],
             'vccq2-supply': [resolve('diag_ufs_s4')], 'lanes-per-direction': [2], 'limit-hs-gear': [3 if g3 else 1],
             'freq-table-hz': [37500000, high, 0, 0, 0, 0, 37500000, high, 0, 0, 0, 0, 0, 0, 0, 0]})
    return dict(host=host, parked=legacy, phy=PHY, board_xo_hz=38400000, max_core_hz=high, interconnect_providers=len(noc),
                smmu_stream_ids=[0xe0, 0x4e0], relocated_reference_cells=moved,
                primary_usb_sid_mask=require_sid0(after, legacy_base=True))
