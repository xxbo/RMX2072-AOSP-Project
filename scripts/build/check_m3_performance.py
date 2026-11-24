"""Validate native performance bindings after the real OEM overlay is applied."""
from inspect_boot_dt import fdt
from check_m2_resources import normalized_node


def check_m3_performance(data, staged):
    tree = {n['path']: n['properties'] for n in fdt(data, ('**',))['matching_nodes']}
    fabric = '/soc' + ('/display-fabric-lab' if staged else '')
    cpu = '/soc/cpufreq@18591000'
    gpu = fabric + '/gpu@3d00000'
    gmu = fabric + '/gmu@3d6a000'
    smmu = fabric + '/iommu@3da0000'
    ids = {n['phandle'][0]: p for p, n in tree.items() if 'phandle' in n}
    # ACK add_gpu_components() examines only the first compatible node.
    gpu_matches = [p for p, n in tree.items() if set(n.get('compatible', [])) &
                   {'qcom,adreno', 'qcom,adreno-3xx', 'amd,imageon', 'qcom,kgsl-3d0'}]
    if not gpu_matches or gpu_matches[0] != gpu:
        raise ValueError('The disabled legacy KGSL node shadows native Adreno discovery')
    for path, expected in {
        cpu: {'compatible': ['qcom,sm8250-cpufreq-epss', 'qcom,cpufreq-epss'],
              'reg': [0x18591000, 0x1000, 0x18592000, 0x1000, 0x18593000, 0x1000],
              '#freq-domain-cells': [1]},
        gpu: {'compatible': ['qcom,adreno-650.2', 'qcom,adreno'],
              'reg': [0x3d00000, 0x40000], 'interrupts': [0, 300, 4]},
        gmu: {'reg': [0x3d6a000, 0x30000, 0x3de0000, 0x10000, 0xb290000, 0x10000, 0xb490000, 0x10000]},
        '/soc/thermal-sensor@c263000': {'reg': [0xc263000, 0x1ff, 0xc222000, 0x1ff]},
        '/soc/thermal-sensor@c265000': {'reg': [0xc265000, 0x1ff, 0xc223000, 0x1ff]},
        '/soc/clock-controller@3d90000': {'compatible': ['qcom,sm8250-gpucc']},
        gpu + '/zap-shader': {'firmware-name': ['qcom/rmx2072/a650_zap.mdt']},
    }.items():
        if any(tree.get(path, {}).get(k) != v for k, v in expected.items()):
            raise ValueError('Performance resource mismatch: ' + path)
    if staged:
        paths = list(tree)
        if not paths.index(smmu) < paths.index(gmu) < paths.index(gpu):
            raise ValueError('Staged GPU consumers precede their SMMU provider')
        if any(p.startswith(fabric + '/') and any(c in n.get('compatible', [])
                for c in ('qcom,tsens-v2', 'qcom,cpufreq-epss', 'qcom,sm8250-gpucc'))
               for p, n in tree.items()):
            raise ValueError('Early performance provider was placed behind the userspace gate')
    for i in range(8):
        path = '/cpus/cpu@' + (format(i << 8, 'x') if i else '0')
        node = tree[path]
        domain = 0 if i < 4 else 1 if i < 7 else 2
        freq = node['qcom,freq-domain']
        if len(freq) != 2 or ids.get(freq[0]) != cpu or freq[1] != domain:
            raise ValueError('Legacy CPU frequency specifier survived the board overlay')
        if node['capacity-dmips-mhz'] != [448 if i < 4 else 1024]:
            raise ValueError('CPU capacity topology differs from native SM8250')
    for path, sid in ((gpu, [0, 0x401]), (gmu, [5, 0x400])):
        if normalized_node(tree, path)['iommus'] != [dict(target=smmu, args=sid)]:
            raise ValueError('Adreno/GMU SMMU stream mismatch')
    zap = normalized_node(tree, gpu + '/zap-shader')['memory-region']
    if zap != [dict(target='/reserved-memory/pil_gpu_region@8e21a000', args=[])]:
        raise ValueError('GPU secure firmware must use the measured board reservation')
    opps = [n['opp-hz'][-1] for p, n in tree.items()
            if p.startswith(gpu + '/opp-table/') and 'opp-hz' in n]
    if sorted(opps) != [305000000, 400000000, 441600000, 490000000, 525000000, 587000000]:
        raise ValueError('GPU frequency envelope differs from stock and native source')
    for path in ['/soc/qcom,cpufreq-hw', '/soc/qcom,kgsl-3d0@3d00000',
                 '/soc/qcom,gmu@3d6a000', '/soc/qcom,gpucc@3d90000',
                 '/soc/qcom,kgsl-iommu@3da0000', '/soc/tsens@c222000', '/soc/tsens@c223000']:
        if tree.get(path, {}).get('status') != ['disabled']:
            raise ValueError('Legacy performance resource is active: ' + path)
    for name in ('little', 'big', 'gpu'):
        zone = '/thermal-zones/m3-' + name + '-thermal'
        if tree[zone + '/trips/critical'].get('temperature') != [100000]:
            raise ValueError('Missing conservative critical thermal trip')
    return dict(cpu_domains=[list(range(4)), [4, 5, 6], [7]],
                cpu_frequency_source='hardware LUT; native EPSS driver',
                gpu_max_hz=max(opps), thermal_control='TSENS with cooling maps',
                provider_lifetime='TSENS, EPSS and GPUCC populated during normal boot',
                firmware='retained F.20 GPU firmware, separately inventoried',
                status='compiled-resource-check-only; device execution NOT RUN')
