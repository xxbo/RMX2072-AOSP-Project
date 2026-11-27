"""Check the bounded external-gauge path; this does not qualify charging."""
from inspect_boot_dt import fdt
from check_m2_resources import normalized_node


def check_m3_battery(data, staged):
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    fabric = '/soc' + ('/display-fabric-lab' if staged else '')
    pins = '/soc' + ('/display-pins-lab' if staged else '') + '/pinctrl@f100000'
    wrapper = fabric + '/geniqup@8c0000'
    host = wrapper + '/i2c@888000'
    gauge = host + '/battery@55'
    for path, expected in {
        wrapper: {'compatible': ['qcom,geni-se-qup'], 'reg': [0x8c0000, 0x6000]},
        host: {'compatible': ['qcom,geni-i2c'], 'reg': [0x888000, 0x4000],
               'interrupts': [0, 584, 4], 'clock-frequency': [100000]},
        gauge: {'compatible': ['ti,bq28z610'], 'reg': [0x55]},
        pins + '/gauge-i2c-state': {'pins': ['gpio48', 'gpio49'], 'function': ['qup16']},
    }.items():
        if any(tree.get(path, {}).get(k) != v for k, v in expected.items()):
            raise ValueError('Gauge wiring differs: ' + path)
    if set(tree[gauge]) - {'compatible', 'reg', 'phandle'}:
        raise ValueError('Gauge node must not carry programming or charger properties')
    if {p for p in tree if p.startswith(host + '/')} != {gauge}:
        raise ValueError('Only the external gauge may be enabled on this new bus')
    if normalized_node(tree, wrapper)['iommus'] != [
            dict(target='/soc/apps-smmu@15000000', args=[0x63, 0])]:
        raise ValueError('QUP2 DMA stream differs from the source SoC binding')
    ids = {n['phandle'][0]: p for p, n in tree.items() if 'phandle' in n}
    if [ids.get(x) for x in tree[host].get('pinctrl-0', [])] != [pins + '/gauge-i2c-state']:
        raise ValueError('Gauge must use the bounded native TLMM pins')
    for path in ('/soc/i2c@888000', '/soc/qcom,qupv3_2_geni_se@8c0000'):
        if tree.get(path, {}).get('status') != ['disabled']:
            raise ValueError('Legacy SE16/wrapper must remain disabled after OEM overlay')
    return dict(gauge='BQ28Z610, OEM board selection; hardware identity not yet read',
                bus='SE16 0x888000', address=0x55, gpio=[48, 49],
                rate_hz=100000, charging_control=False, hardware_result='NOT RUN')
