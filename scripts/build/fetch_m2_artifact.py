"""Install only checked current M2 build inputs, never a history of images."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
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
    p.add_argument('--kind', choices=('kernel', 'init'), required=True)
    a = p.parse_args()
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
    if a.kind == 'init':
        plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        archive = plain.open(url, timeout=120).read()
        if 'sha256:' + digest(archive) != artifact['digest']:
            raise ValueError('First-stage artifact archive digest mismatch')
        provenance['archive_digest_verified'] = True
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            wanted = {'init', 'source.json', 'resolved-manifest.xml', 'SHA256SUMS',
                      'build-host.txt', 'elf.txt', 'AndroidProducts.mk', 'BoardConfig.mk', 'rmx2072_m2_init.mk'}
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
    wanted = set(patches) | {'Image.gz', 'sm8250_bootstrap_dot_config', 'kernel.release',
                             'SHA256SUMS', 'build-metadata.txt', 'resolved-manifest.xml'}
    with RemoteZip(url, session=session, timeout=120, support_suffix_range=False) as z:
        files = {Path(n).name: z.read(n) for n in z.namelist() if Path(n).name in wanted}
    if files.keys() != wanted:
        raise ValueError('Incomplete source-PON kernel artifact')
    for name, path in patches.items():
        data = subprocess.check_output(['git', '-C', repo, 'show',
            a.commit + ':device/realme/bladerunner_48m/' + path])
        if digest(data) != files[name].decode().split()[0]:
            raise ValueError('Kernel source patch mismatch: ' + name)
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
    provenance.update(installing=False, source_pon=True, source_digests_verified=True,
                      dist_digests_verified=True, image_sha256=digest(raw),
                      selected_member_sha256={n: digest(d) for n, d in files.items()})
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print('Installed source-PON kernel:', provenance['image_sha256'])


if __name__ == '__main__':
    main()
