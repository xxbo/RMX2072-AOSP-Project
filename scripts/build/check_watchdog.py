"""Compare the SID0 baseline and watchdog control at the same overlay stage."""
from check_usb_stream import require_sid0
from inspect_boot_dt import fdt


def check_watchdog_control(before, after):
    path = '/soc/qcom,wdt@17c10000'
    clock_path = '/diag-sleep-clock'
    gic_path = '/soc/interrupt-controller@17a00000'
    before_nodes, after_nodes = (
        {node['path']: node['properties'] for node in fdt(blob, ('**',))['matching_nodes']}
        for blob in (before, after)
    )
    if before_nodes.keys() != after_nodes.keys():
        raise ValueError('Watchdog overlay added or removed a node')
    changes = [key for key in before_nodes if before_nodes[key] != after_nodes[key]]
    if changes != [path]:
        raise ValueError(f'Expected only {path} to change, got {changes}')
    old, wdt = before_nodes[path], after_nodes[path]
    keys = {key for key in old.keys() | wdt.keys() if old.get(key) != wdt.get(key)}
    if old.get('compatible') != ['qcom,msm-watchdog'] or keys != {'compatible', 'clocks', 'interrupts'}:
        raise ValueError(f'Unexpected baseline or changed watchdog properties: {sorted(keys)}')
    expected = ['qcom,apss-wdt-sm8250', 'qcom,kpss-wdt']
    if (wdt.get('compatible') != expected or wdt.get('reg') != [0x17c10000, 0x1000]
            or wdt.get('interrupts') != [0, 0, 1] or 'interrupts-extended' in wdt):
        raise ValueError('Incorrect watchdog compatible, registers or bark IRQ')
    soc = after_nodes['/soc']
    if soc.get('#address-cells') != [1] or soc.get('#size-cells') != [1]:
        raise ValueError('Unexpected downstream /soc register encoding')
    clock, gic = after_nodes[clock_path], after_nodes[gic_path]
    for node in (wdt, soc, clock, gic):
        if node.get('status', ['okay']) not in (['ok'], ['okay']):
            raise ValueError('Watchdog or supplier disabled')
    if (clock.get('compatible') != ['fixed-clock'] or clock.get('clock-frequency') != [32764]
            or clock.get('#clock-cells') != [0] or not clock.get('phandle')
            or wdt.get('clocks') != clock['phandle']):
        raise ValueError('Watchdog clock must resolve to the configured 32764 Hz sleep clock')
    parent = next((n['interrupt-parent'] for n in (wdt, soc, after_nodes['']) if 'interrupt-parent' in n), None)
    if ('arm,gic-v3' not in gic.get('compatible', []) or 'interrupt-controller' not in gic
            or gic.get('#interrupt-cells') != [3] or not parent or parent != gic.get('phandle')):
        raise ValueError('Watchdog bark interrupt must resolve to the primary GICv3')
    return dict(path=path, reg=wdt['reg'], interrupts=wdt['interrupts'], gic=gic_path,
                sleep_clock_hz=clock['clock-frequency'][0], changed_properties=sorted(keys),
                primary_usb_sid_mask=require_sid0(after, legacy_base=True))
