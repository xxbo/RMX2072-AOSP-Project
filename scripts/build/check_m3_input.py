"""Validate source input wiring after the complete board overlay is applied."""
from inspect_boot_dt import fdt
from check_m2_resources import normalized_node


def check_m3_input(data, staged):
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    ids = {n['phandle'][0]: p for p, n in tree.items() if 'phandle' in n}
    pins = '/soc' + ('/display-pins-lab' if staged else '') + '/pinctrl@f100000'
    fabric = '/soc' + ('/display-fabric-lab' if staged else '')
    host = fabric + '/geniqup@ac0000/i2c@a94000'
    touch = host + '/touchscreen@5d'
    pmic = '/soc/qcom,spmi@c440000/qcom,pm8150@0/pinctrl@c000'
    for path, expected in {
        host: {'compatible': ['qcom,geni-i2c'], 'reg': [0xa94000, 0x4000],
               'interrupts': [0, 358, 4], 'clock-frequency': [400000]},
        touch: {'compatible': ['goodix,gt9886'], 'reg': [0x5d],
                'interrupts': [39, 2], 'touchscreen-size-x': [1080],
                'touchscreen-size-y': [2400]},
        pmic: {'compatible': ['qcom,pm8150-gpio'], 'reg': [0xc000],
               '#interrupt-cells': [2], 'gpio-reserved-ranges': [0, 5, 7, 3]},
    }.items():
        actual = tree[path]
        if any(actual.get(k) != v for k, v in expected.items()):
            raise ValueError('Input wiring differs: ' + path)
    t = tree[touch]
    if ids[t['interrupt-parent'][0]] != pins or t['reset-gpios'][1:] != [38, 1] or ids[t['reset-gpios'][0]] != pins:
        raise ValueError('Touch IRQ/reset must use the native bounded TLMM')
    for key, voltage, provider in [('avdd', 3008000, 'ldo13'), ('vddio', 1800000, 'ldo14')]:
        rail = ids[t[key + '-supply'][0]]
        if (rail != '/soc/rsc@18200000/diag-regulators/' + provider or
                tree[rail].get('regulator-min-microvolt') != [voltage] or
                tree[rail].get('regulator-max-microvolt') != [voltage]):
            raise ValueError('Touch supply differs: ' + key)
    if normalized_node(tree, fabric + '/geniqup@ac0000')['iommus'] != [
            dict(target='/soc/apps-smmu@15000000', args=[0x43, 0])]:
        raise ValueError('QUP1 DMA stream must match source and F.20')
    for name, gpio, code in [('vol_up', 6, 115), ('vol_down', 7, 114)]:
        node = tree['/soc/gpio_keys/' + name]
        if ids[node['gpios'][0]] != pmic or node['gpios'][1:] != [gpio, 1] or node['linux,code'] != [code]:
            raise ValueError('Volume-key board wiring differs: ' + name)
    legacy = tree['/soc/i2c@a94000']
    if (legacy['compatible'] != ['realme,rmx2072-parked-i2c'] or
            legacy.get('status') != ['disabled']):
        raise ValueError('Legacy I2C controller must remain disabled after the board overlay; '
                         'a parked compatible still creates a duplicate a94000.i2c device')
    return dict(touch='GT9886 at native SE13 0xa94000, address 0x5d',
                coordinates=[1080, 2400], reset_gpio=38, irq_gpio=39,
                volume_up='PM8150 GPIO6 active-low, KEY_VOLUMEUP',
                volume_down='PM8150 GPIO7 active-low, KEY_VOLUMEDOWN',
                power='Existing upstream PON power-key binding retained',
                hardware_result='NOT RUN')
