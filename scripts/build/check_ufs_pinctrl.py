"""Verify the storage-isolated GPIO provider control on an applied RMX2072 tree."""
from check_usb_stream import require_sid0
from inspect_boot_dt import fdt

UFS_INITCALLS = ('ufs_qcom_pltform_init', 'qmp_ufs_driver_init')


def check_ufs_pinctrl(before, after):
    tlmm = '/soc/pinctrl@f000000'
    pdc = '/soc/interrupt-controller@b220000'
    host = '/soc/ufshc@1d84000'
    phy = '/soc/ufsphy_mem@1d87000'
    old, new = ({n['path']: n['properties'] for n in fdt(blob, ('**',))['matching_nodes']}
                for blob in (before, after))
    allowed = {tlmm: {'compatible', 'reg', 'reg-names', 'gpio-ranges'}, pdc: {'compatible'}}
    if old.keys() != new.keys():
        raise ValueError('Unexpected nodes added or removed in TLMM control')
    for path in old:
        changed = {key for key in old[path].keys() | new[path].keys()
                   if old[path].get(key) != new[path].get(key)}
        if changed - allowed.get(path, set()):
            raise ValueError(f'Unexpected property change at {path}: {changed}')
    gpio, wake = new[tlmm], new[pdc]
    banks = [0xf100000, 0x300000, 0xf500000, 0x300000, 0xf900000, 0x300000]
    ranges = [0, 480, 94, 94, 609, 31, 125, 63, 1, 126, 716, 12]
    if (old[tlmm].get('compatible') != ['qcom,kona-pinctrl']
            or old[pdc].get('compatible') != ['qcom,kona-pdc']
            or new['/soc'].get('#address-cells') != [1] or new['/soc'].get('#size-cells') != [1]
            or gpio.get('compatible') != ['qcom,sm8250-pinctrl'] or gpio.get('reg') != banks
            or gpio.get('reg-names') != ['west', 'south', 'north']
            or gpio.get('interrupts') != [0, 208, 4] or not gpio.get('phandle')
            or gpio.get('gpio-ranges') != gpio['phandle'] + [0, 0, 181]):
        raise ValueError('Invalid TLMM banks, GPIO range or parent IRQ')
    if (wake.get('compatible') != ['qcom,sm8250-pdc', 'qcom,pdc'] or not wake.get('phandle')
            or gpio.get('wakeup-parent') != wake['phandle'] or wake.get('#interrupt-cells') != [2]
            or wake.get('reg') != [0xb220000, 0x30000, 0x17c000f0, 0x60]
            or wake.get('qcom,pdc-ranges') != ranges):
        raise ValueError('Invalid PDC wake supplier, resources or ranges')
    if any(n.get('status', ['okay']) not in (['ok'], ['okay']) for n in (gpio, wake)):
        raise ValueError('TLMM and PDC must be enabled')
    if any(path not in new for path in (host, phy)):
        raise ValueError('Expected the existing OEM UFS host and PHY')
    return dict(tlmm_banks=gpio['reg-names'], gpio_count=181, ufs_reset_group=180,
                storage_nodes_unchanged=True, primary_usb_sid_mask=require_sid0(after, legacy_base=True))
