"""Resolve the primary SM8250 USB DMA master's IOMMU in an applied DTB."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'device_audit'))
from inspect_boot_dt import fdt


def primary_usb_stream(data, *, legacy_base, allow_unmapped=False):
    if legacy_base:
        usb_path = '/soc/usb@a600000'
        smmu_path = '/soc/apps-smmu@15000000'
        usb_compat = 'qcom,snps-dwc3'
    else:
        usb_path = '/soc@0/usb@a6f8800/usb@a600000'
        smmu_path = '/soc@0/iommu@15000000'
        usb_compat = 'snps,dwc3'
    nodes = {n['path']: n['properties'] for n in
             fdt(data, (usb_compat, 'qcom,sm8250-smmu-500'))['matching_nodes']}
    usb, smmu = nodes.get(usb_path, {}), nodes.get(smmu_path, {})
    if allow_unmapped and 'iommus' not in usb:
        return None  # Marker and initial bridge controls predate the IOMMU overlay.
    for node, compatible, path in ((usb, usb_compat, usb_path),
                                    (smmu, 'qcom,sm8250-smmu-500', smmu_path)):
        if (compatible not in node.get('compatible', [])
                or node.get('status', ['okay']) not in (['ok'], ['okay'])):
            raise ValueError(f'Missing or disabled {compatible} at {path}')
    spec = usb.get('iommus', [])
    if (smmu.get('#iommu-cells') != [2] or len(spec) != 3
            or spec[0] in (0, 0xffffffff) or smmu.get('phandle') != [spec[0]]):
        raise ValueError(f'{usb_path}: expected one two-cell mapping to {smmu_path}, got {spec}')
    return spec[1:]


def require_sid0(data, *, legacy_base):
    stream = primary_usb_stream(data, legacy_base=legacy_base)
    if stream != [0, 0]:
        raise ValueError(f'Expected primary USB SID 0 and mask 0, got {stream}')
    return stream
