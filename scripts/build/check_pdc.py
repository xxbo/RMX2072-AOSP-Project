"""Constrain the PDC-only trial to one compatible change, including after OEM DTBO."""
from inspect_boot_dt import fdt
from check_usb_stream import require_sid0


def check_pdc_control(before, after):
    path='/soc/interrupt-controller@b220000'
    spmi='/soc/qcom,spmi@c440000'
    gic='/soc/interrupt-controller@17a00000'
    old,new=({n['path']:n['properties'] for n in fdt(blob,('**',))['matching_nodes']}
             for blob in (before,after))
    if old.keys()!=new.keys() or [p for p in old if old[p]!=new[p]]!=[path]:
        raise ValueError('PDC control must preserve every other node')
    expected=dict(old[path],compatible=['qcom,sm8250-pdc','qcom,pdc'])
    if old[path].get('compatible')!=['qcom,kona-pdc'] or new[path]!=expected:
        raise ValueError('Only the legacy PDC compatible may change')
    pdc=new[path]
    if (pdc.get('reg')!=[0xb220000,0x30000,0x17c000f0,0x60] or
        pdc.get('qcom,pdc-ranges')!=[0,480,94,94,609,31,125,63,1,126,716,12] or
        pdc.get('#interrupt-cells')!=[2] or 'interrupt-controller' not in pdc or
        pdc.get('status',['okay']) not in (['ok'],['okay'])):
        raise ValueError('PDC resources or ranges differ from the measured board')
    parent=next((n['interrupt-parent'] for n in (pdc,new['/soc'],new['']) if 'interrupt-parent' in n),None)
    if parent!=new[gic].get('phandle') or 'arm,gic-v3' not in new[gic].get('compatible',[]):
        raise ValueError('PDC parent must resolve to the original GIC')
    if not pdc.get('phandle') or new.get(spmi,{}).get('interrupts-extended')!=pdc['phandle']+[1,4]:
        raise ValueError('SPMI must retain PDC pin 1, level high')
    return dict(changed_path=path,changed_properties=['compatible'],spmi_parent_pin=1,
                spmi_gic_spi=481,other_nodes_identical=True,
                primary_usb_sid_mask=require_sid0(after,legacy_base=True))
