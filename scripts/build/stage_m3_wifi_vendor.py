"""Explicit source vendor supplicant integration; no mainline RRO or RF claims."""
import json
import re
from stage_m3_graphics import ROOT, SOURCE, merge_native_hal_payload, sha

PIN = ROOT/'build/m3-wifi-source.json'


CONFIG_FILES = {
    '/etc/wifi/wpa_supplicant.conf': 'wpa_supplicant.conf',
    '/etc/init/rmx-wifi-data.rc': 'wifi-data.rc',
}


def add_wifi_vendor(files, directory):
    if '/overlay/RmxWifiOverlay.apk' in files:
        raise ValueError('Vendor supplicant cannot be combined with the mainline RRO')
    # Validate everything before changing the caller's inventory.
    staged = dict(files)
    proof, incoming = merge_native_hal_payload(staged, directory, 'wifi')
    executable = incoming['/bin/hw/wpa_supplicant']
    isa = proof.get('isa_screen', {})
    if isa.get('sha256') != sha(executable) or isa.get('sve_register_instruction_count') != 0:
        raise ValueError('Source supplicant has not passed the bound ISA screen')
    pins = json.loads(PIN.read_text())['sha256']
    for name, prefix in [('android.hardware.wifi.supplicant-service.rc', '/etc/init/'),
                         ('android.hardware.wifi.supplicant.xml', '/etc/vintf/manifest/')]:
        key = 'external/wpa_supplicant_8/wpa_supplicant/aidl/'+name
        if sha(incoming.get(prefix+name, b'')) != pins[key]:
            raise ValueError('Supplicant init/VINTF payload differs from pinned upstream: '+name)
    labels = [
        '/vendor/bin/hw/wpa_supplicant u:object_r:rmx_wpa_exec:s0',
        '/vendor/etc/wifi(/.*)? u:object_r:vendor_configs_file:s0',
        '/data/vendor/wifi/wpa(/.*)? u:object_r:wpa_data_file:s0',
        '/data/vendor_ce/[0-9]+/wifi/wpa(/.*)? u:object_r:wpa_user_data_file:s0',
    ]
    for name in sorted(incoming):
        if name.startswith('/lib64/') and name not in files:
            labels.append(re.escape('/vendor'+name)+' u:object_r:same_process_hal_file:s0')
    integration = {}
    for target, name in CONFIG_FILES.items():
        data = (SOURCE/name).read_bytes().replace(b'\r\n', b'\n')
        if target in staged and staged[target] != data:
            raise ValueError('Wi-Fi configuration would replace '+target)
        staged[target] = data
        integration[name] = sha(data)
    cil = (SOURCE/'wifi.cil').read_bytes().replace(b'\r\n', b'\n')
    integration['wifi.cil'] = sha(cil)
    staged['/etc/selinux/vendor_sepolicy.cil'] += cil
    staged['/etc/selinux/vendor_file_contexts'] += ('\n'.join(labels)+'\n').encode()
    files.update(staged)
    return proof, integration
