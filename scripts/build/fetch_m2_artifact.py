"""Install only checked current M2 build inputs, never a history of images."""
import argparse
import gzip
import hashlib
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import tarfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from check_source_first_stage import verify_source_first_stage
from build_diag_ramdisk import read_static_arm64


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--artifact-id', type=int, required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--kind', choices=('kernel', 'init', 'graphics', 'health', 'power', 'audio'), required=True)
    p.add_argument('--display', action='store_true', help='Require the M3 panel source digests and DRM configuration')
    p.add_argument('--input-devices', action='store_true', help='Require the GTX8 source digests and built-in driver')
    p.add_argument('--battery-gauge', action='store_true', help='Require the pinned BQ28Z610 driver without NVM updates')
    a = p.parse_args()
    if a.display and a.kind != 'kernel':
        p.error('--display requires a kernel artifact')
    if a.input_devices and not a.display:
        p.error('--input-devices requires --display')
    if a.battery_gauge and not a.input_devices:
        p.error('--battery-gauge requires --input-devices')
    repo = Path(__file__).resolve().parents[2]
    work = a.workspace.resolve()
    if work.is_relative_to(repo):
        p.error('Build inputs must remain outside the public checkout')
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    result = subprocess.run(['git', 'credential', 'fill'],
        input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True, check=True)
    credential = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    api = 'https://api.github.com/repos/xxbo/RMX2072-AOSP-Project/'
    def request(path):
        return opener.open(urllib.request.Request(api + path + '?fresh=' + str(time.time_ns()),
            headers={'Authorization': 'Bearer ' + credential['password'], 'Accept': 'application/vnd.github+json'}), timeout=90)
    run = json.load(request('actions/runs/' + str(a.run_id)))
    artifact = json.load(request('actions/artifacts/' + str(a.artifact_id)))
    if (run['head_sha'] != a.commit or run['conclusion'] != 'success' or run['status'] != 'completed'
            or artifact['workflow_run']['id'] != a.run_id or artifact['workflow_run']['head_sha'] != a.commit
            or artifact['expired']):
        raise ValueError('Artifact does not belong to the successful pinned build')
    try:
        request('actions/artifacts/' + str(a.artifact_id) + '/zip')
        raise ValueError('Expected artifact storage redirect')
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise
        url = error.headers['Location']
    provenance = dict(run_id=a.run_id, source_commit=a.commit, artifact_id=a.artifact_id,
                      artifact_archive_digest=artifact['digest'], archive_digest_verified=False)
    if a.kind in ('graphics', 'health', 'power', 'audio'):
        archive_name = a.kind + '-vendor.tar.gz'
        if run['path'] != '.github/workflows/m3-'+a.kind+'.yml' or artifact['size_in_bytes'] > 512*1024*1024:
            raise ValueError('Unexpected graphics build or oversized artifact')
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with plain.open(url, timeout=120) as response:
            archive = response.read(512*1024*1024+1)
        if len(archive) > 512*1024*1024 or 'sha256:'+digest(archive) != artifact['digest']:
            raise ValueError('Graphics archive digest/size mismatch')
        wanted = {archive_name, 'vendor-files.sha256', 'resolved-manifest.xml',
                  'SHA256SUMS', 'project-commit.txt', 'target-dependencies.json', 'STATUS.txt',
                  'hardwarebuffer-source.json', 'vendor-output-path.txt'}
        if a.kind == 'health':
            wanted.update({'health-source.sha256', 'connectivity-sparse.txt', 'bpf-sparse.txt'})
        if a.kind in ('power', 'audio'):
            wanted.update({a.kind+'-source.sha256', 'project-'+a.kind+'-source.sha256'})
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            files = {Path(n).name: z.read(n) for n in z.namelist() if Path(n).name in wanted}
        if files.keys() != wanted or files['project-commit.txt'].decode().strip() != a.commit:
            raise ValueError('Incomplete graphics artifact provenance')
        if a.kind in ('power', 'audio'):
            manifest = ET.fromstring(files['resolved-manifest.xml'])
            revisions = {x.get('path'): x.get('revision') for x in manifest.findall('project')}
            pinned = json.loads((repo/('build/m3-'+a.kind+'-source.json')).read_text())
            if any(revisions.get(path) != rev for path, rev in pinned['projects'].items()):
                raise ValueError(a.kind+' AIDL source revision changed')
            source_hashes = {line.split(maxsplit=1)[1]:line.split()[0]
                             for line in files[a.kind+'-source.sha256'].decode().splitlines()}
            if source_hashes != pinned['sha256']:
                raise ValueError(a.kind+' AIDL source differs from pinned upstream')
            project_hashes = {line.split(maxsplit=1)[1]:line.split()[0]
                              for line in files['project-'+a.kind+'-source.sha256'].decode().splitlines()}
            source_dir = 'device/realme/bladerunner_48m/m3-'+a.kind+'/'
            if set(project_hashes) != {source_dir+n for n in ('Android.bp', 'service.cpp', a.kind+'.rc', a.kind+'.xml')}:
                raise ValueError('Incomplete project '+a.kind+' source inventory')
            for path, expected_sha in project_hashes.items():
                data = subprocess.check_output(['git', '-C', str(repo), 'show', a.commit+':'+path])
                if digest(data) != expected_sha:
                    raise ValueError('Project '+a.kind+' source mismatch: '+path)
        if a.kind == 'health':
            manifest = ET.fromstring(files['resolved-manifest.xml'])
            revisions = {x.get('path'): x.get('revision') for x in manifest.findall('project')}
            pinned_health = json.loads((repo/'build/m3-health-source.json').read_text())
            for path, revision in pinned_health['projects'].items():
                if revisions.get(path) != revision:
                    raise ValueError('Health source revision changed: '+path)
            health_hashes = {line.split(maxsplit=1)[1]:line.split()[0]
                            for line in files['health-source.sha256'].decode().splitlines()}
            if health_hashes != pinned_health['sha256']:
                raise ValueError('Health source hashes differ from pinned upstream')
            if (set(files['connectivity-sparse.txt'].decode().splitlines())
                    != {'/bpf/headers/', '/bpf/syscall_wrappers/'}
                    or set(files['bpf-sparse.txt'].decode().splitlines())
                    != {'/Android.bp', '/NOTICE', '/include/'}):
                raise ValueError('Health native BPF selection changed')
        from prepare_m3_hardwarebuffer import PINNED, SELECTED_MODULES
        hardwarebuffer = json.loads(files['hardwarebuffer-source.json'])
        if hardwarebuffer['original_files'] != PINNED or hardwarebuffer['selected_modules'] != SELECTED_MODULES:
            raise ValueError('Graphics source declaration selection differs from pinned upstream')
        closure = json.loads(files['target-dependencies.json'])
        if closure['missing_dependency_commands'] or closure['command_count'] < 1:
            raise ValueError('Graphics dependency closure is incomplete')
        sums = {Path(line.split(maxsplit=1)[1]).name: line.split()[0]
                for line in files['SHA256SUMS'].decode().splitlines()}
        for name in (archive_name, 'resolved-manifest.xml', 'vendor-output-path.txt'):
            if digest(files[name]) != sums[name]:
                raise ValueError('Graphics member digest mismatch: '+name)
        vendor_output = files['vendor-output-path.txt'].decode().strip()
        if vendor_output not in ('out/target/product/rmx2072_m3/vendor',
                                 'out/target/product/rmx2072_m3/system/vendor'):
            raise ValueError('Unexpected AOSP vendor output path')
        expected = {}
        for line in files['vendor-files.sha256'].decode().splitlines():
            sha256, name = line.split(maxsplit=1)
            prefix = vendor_output+'/'
            if not name.startswith(prefix):
                raise ValueError('Non-vendor file in graphics manifest')
            expected['/'+name[len(prefix):]] = sha256
        payload = {}
        with tarfile.open(fileobj=io.BytesIO(files[archive_name]), mode='r:gz') as tar:
            for member in tar:
                if member.isdir():
                    continue
                name = member.name.removeprefix('./')
                if (not member.isfile() or not re.fullmatch(r'[a-zA-Z0-9+@/_.-]+', name)
                        or Path(name).is_absolute() or '..' in Path(name).parts
                        or '/'+name in payload or member.size > 128*1024*1024):
                    raise ValueError('Unsafe or unexpected graphics payload member')
                data = tar.extractfile(member).read()
                payload['/'+name] = data
                if sum(map(len, payload.values())) > 512*1024*1024 or len(payload) > 2048:
                    raise ValueError('Graphics payload exceeds staging bounds')
        if {n:digest(data) for n,data in payload.items()} != expected:
            raise ValueError('Graphics files differ from build manifest')
        output = work/'current'/a.kind
        if output.exists():
            raise ValueError('Current graphics payload already exists; reconcile it before replacing')
        for name,data in payload.items():
            target = output/'vendor'/name.lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name,data in files.items():
            if name != archive_name:
                (output/name).write_bytes(data)
        provenance.update(source_verified=True, archive_digest_verified=True, files=expected,
                          kind=a.kind, target_closure=closure, payload_bytes=sum(map(len,payload.values())))
        (output/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
        print('Installed verified source graphics payload:', len(payload), 'files')
        return
    if a.kind == 'init':
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        archive = plain.open(url, timeout=120).read()
        if 'sha256:' + digest(archive) != artifact['digest']:
            raise ValueError('First-stage artifact archive digest mismatch')
        provenance['archive_digest_verified'] = True
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            wanted = {'init', 'source.json', 'resolved-manifest.xml', 'SHA256SUMS',
                      'build-host.txt', 'elf.txt', 'AndroidProducts.mk', 'BoardConfig.mk',
                      'rmx2072_m2_init.mk', 'frameworks-base-sparse.txt', 'car-sparse.txt',
                      'apex-sparse.txt', 'avf-sparse.txt', 'modules-common-sparse.txt',
                      'icu-sparse.txt', 'target-dependencies.json'}
            files = {Path(n).name: z.read(n) for n in z.namelist() if Path(n).name in wanted}
        if files.keys() != wanted:
            raise ValueError('Incomplete first-stage artifact')
        output = work / 'current/init-build'
        output.mkdir(exist_ok=True)
        for name, data in files.items():
            if name != 'init':
                (output / name).write_bytes(data)
        checked = verify_source_first_stage(output, files['init'])
        target = work / 'current/init'
        target.write_bytes(files['init'])
        read_static_arm64(target)
        provenance.update(checked)
        (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
        print('Installed source first-stage init:', checked['init_sha256'])
        return
    # The kernel distribution also contains many modules and debug files. Fetch
    # selected ZIP members only, checking them against the build's dist digests.
    sys.path.insert(0, str(work / 'host-deps'))
    from remotezip import RemoteZip
    import requests
    session = requests.Session()
    session.trust_env = False
    patches = {'board-patch.sha256': 'bootstrap-patches/rmx2072-scm-edl.patch',
               'tzmem-patch.sha256': 'bootstrap-patches/rmx2072-tzmem-status.patch',
               'source-pon-patch.sha256': 'bootstrap-patches/rmx2072-source-pon.patch',
               'phy-test.sha256': 'bootstrap-probes/rmx2072-ufs-phy-test.c',
               'keymaster-lookup.sha256': 'bootstrap-probes/rmx2072-keymaster-lookup.c',
               'keymaster-transport.sha256': 'bootstrap-probes/rmx2072-keymaster-transport.h',
               'listener.sha256': 'bootstrap-probes/rmx2072-listener.inc'}
    if a.display:
        patches['display-clock-patch.sha256'] = 'bootstrap-patches/rmx2072-display-clock.patch'
        # Require every packet patch present at the selected source commit.
        # Earlier artifacts remain verifiable against their own original source.
        for name in ('upstream-dsi-dsc-all-slices-flag',
                     'upstream-msm-dsi-dsc-slices-per-packet',
                     'rmx2072-dsc-packet-trace', 'rmx2072-dsc-route-test',
                     'rmx2072-dpu-solid-fill-test', 'rmx2072-stock-linkclock-test',
                     'rmx2072-stock-dsc-test', 'rmx2072-stock-phy-timing-test',
                     'rmx2072-first-frame-trace'):
            path = 'bootstrap-patches/' + name + '.patch'
            exists = subprocess.run(['git', '-C', str(repo), 'cat-file', '-e',
                a.commit + ':device/realme/bladerunner_48m/' + path],
                capture_output=True).returncode == 0
            if exists:
                patches[name + '.sha256'] = path
    if a.input_devices:
        patches['touch-source.sha256'] = 'input/goodix_gtx8.c'
        patches['touch-header.sha256'] = 'input/goodix_gtx8.h'
    wanted = set(patches) | {'Image.gz', 'sm8250_bootstrap_dot_config', 'kernel.release',
                             'SHA256SUMS', 'build-metadata.txt', 'resolved-manifest.xml'}
    if a.display:
        wanted.add('display-source.sha256')
    if a.battery_gauge:
        wanted.add('battery-source.sha256')
    with RemoteZip(url, session=session, timeout=120, support_suffix_range=False) as z:
        files = {Path(n).name: z.read(n) for n in z.namelist() if Path(n).name in wanted}
    if files.keys() != wanted:
        raise ValueError('Incomplete source-PON kernel artifact')
    for name, path in patches.items():
        data = subprocess.check_output(['git', '-C', repo, 'show',
            a.commit + ':device/realme/bladerunner_48m/' + path])
        if digest(data) != files[name].decode().split()[0]:
            raise ValueError('Kernel source patch mismatch: ' + name)
    if a.display:
        rows = {Path(line.split(maxsplit=1)[1]).name: line.split()[0]
                for line in files['display-source.sha256'].decode().splitlines()}
        if set(rows) != {'panel-samsung-rm19795.c', 'rm19795-commands.h'}:
            raise ValueError('Incomplete panel source manifest')
        for name, expected in rows.items():
            data = subprocess.check_output(['git', '-C', repo, 'show',
                a.commit + ':device/realme/bladerunner_48m/display/' + name])
            if digest(data) != expected:
                raise ValueError('Panel source mismatch: ' + name)
    sums = {Path(line.split(maxsplit=1)[1]).name: line.split()[0] for line in files['SHA256SUMS'].decode().splitlines()}
    for name in ('Image.gz', 'sm8250_bootstrap_dot_config', 'kernel.release'):
        if digest(files[name]) != sums[name]:
            raise ValueError('Kernel distribution digest mismatch: ' + name)
    raw = gzip.decompress(files['Image.gz'])
    if digest(raw) != sums['Image'] or raw[56:60] != b'ARM\x64':
        raise ValueError('Raw kernel image digest/header mismatch')
    lock = json.loads((repo / 'sources/SOURCE_LOCK.json').read_text())['sources']
    ack = next(s for s in lock if s['id'] == 'android17-gki-618')
    common = next(n for n in ET.fromstring(files['resolved-manifest.xml']).findall('project') if n.get('path') == 'common')
    if common.get('revision') != ack['mirror_commit']:
        raise ValueError('Kernel manifest did not resolve the pinned common source')
    config = files['sm8250_bootstrap_dot_config'].decode().splitlines()
    for key in ('POWER_RESET_QCOM_PON', 'INPUT_PM8941_PWRKEY', 'POWER_RESET_MSM', 'QCOM_TZMEM_MODE_SHMBRIDGE'):
        if 'CONFIG_' + key + '=y' not in config:
            raise ValueError('Missing kernel configuration: ' + key)
    if a.display:
        for key in ('DRM_MSM', 'DRM_MSM_DPU', 'DRM_MSM_DSI', 'DRM_MSM_DSI_7NM_PHY',
                    'DRM_PANEL_RMX2072_RM19795', 'REGULATOR_QCOM_REFGEN'):
            if 'CONFIG_' + key + '=y' not in config:
                raise ValueError('Missing display configuration: ' + key)
    if a.input_devices and 'CONFIG_TOUCHSCREEN_GOODIX_GTX8=y' not in config:
        raise ValueError('GTX8 driver is not built in')
    if a.battery_gauge:
        pinned = json.loads(subprocess.check_output(['git', '-C', repo, 'show',
            a.commit + ':build/m3-battery-source.json']))
        rows = {Path(line.split(maxsplit=1)[1]).name: line.split()[0]
                for line in files['battery-source.sha256'].decode().splitlines()}
        if rows != pinned['files'] or pinned['ack_commit'] != common.get('revision'):
            raise ValueError('Gauge source does not match the pinned ACK driver')
        if (any('CONFIG_' + k + '=y' not in config for k in ('BATTERY_BQ27XXX', 'BATTERY_BQ27XXX_I2C'))
                or '# CONFIG_BATTERY_BQ27XXX_DT_UPDATES_NVM is not set' not in config):
            raise ValueError('Gauge driver missing or nonvolatile writes enabled')
    output = work / 'current/kernel'
    provenance.update(installing=True)
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    for name, data in files.items():
        if name != 'Image.gz':
            (output / name).write_bytes(data)
    (output / 'Image').write_bytes(raw)
    # Only obsolete metadata is removed, never a recovery file or image history.
    old = output / 'pon-power-patch.sha256'
    if old.is_file():
        old.unlink()
    provenance.update(installing=False, source_pon=True, display=a.display, input_devices=a.input_devices, battery_gauge=a.battery_gauge, source_digests_verified=True,
                      dist_digests_verified=True, image_sha256=digest(raw),
                      selected_member_sha256={n: digest(d) for n, d in files.items()})
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print('Installed source-PON kernel:', provenance['image_sha256'])


if __name__ == '__main__':
    main()
