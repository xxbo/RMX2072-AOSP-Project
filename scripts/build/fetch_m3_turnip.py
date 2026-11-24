"""Stage one pinned, digest-verified source Turnip artifact for Android ARM64."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.error
import urllib.request
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--readelf', type=Path, required=True)
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--artifact-id', type=int, required=True)
    p.add_argument('--commit', required=True)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = a.workspace.resolve()/'current/turnip'
    if output.is_relative_to(repo) or output.exists():
        raise ValueError('Use a new current/turnip directory outside the checkout')
    result = subprocess.run(['git', 'credential', 'fill'],
        input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True, check=True)
    credential = dict(x.split('=', 1) for x in result.stdout.splitlines() if '=' in x)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def request(path):
        return opener.open(urllib.request.Request(
            'https://api.github.com/repos/xxbo/RMX2072-AOSP-Project/'+path,
            headers={'Authorization': 'Bearer '+credential['password'],
                     'Accept': 'application/vnd.github+json'}), timeout=60)
    run = json.load(request('actions/runs/'+str(a.run_id)))
    artifact = json.load(request('actions/artifacts/'+str(a.artifact_id)))
    limit = 96*1024*1024
    if (run['head_sha'] != a.commit or run['conclusion'] != 'success'
            or run['status'] != 'completed' or run['path'] != '.github/workflows/m3-turnip.yml'
            or artifact['workflow_run']['id'] != a.run_id
            or artifact['workflow_run']['head_sha'] != a.commit or artifact['expired']
            or artifact['size_in_bytes'] > limit):
        raise ValueError('Not a successful pinned Turnip artifact')
    try:
        request('actions/artifacts/'+str(a.artifact_id)+'/zip')
        raise ValueError('Expected storage redirect')
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise
        url = error.headers['Location']
    plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with plain.open(url, timeout=120) as response:
        archive = response.read(limit+1)
    if len(archive) > limit or 'sha256:'+digest(archive) != artifact['digest']:
        raise ValueError('Artifact archive digest/size mismatch')
    wanted = {'source.json', 'project-commit.txt', 'SHA256SUMS', 'turnip-vendor.tar.gz',
              'configure.log', 'driver-elf.txt', 'STATUS.txt', 'subprojects.sha256'}
    files = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for n in z.infolist():
            if n.filename in wanted:
                if n.filename in files or n.file_size > limit:
                    raise ValueError('Duplicate or oversized archive member')
                files[n.filename] = z.read(n)
    if files.keys() != wanted or files['project-commit.txt'].decode().strip() != a.commit:
        raise ValueError('Incomplete build provenance')
    pin = json.loads((repo/'build/m3-turnip-source.json').read_text())
    built_pin = json.loads(subprocess.check_output(['git', '-C', str(repo), 'show',
                                                   a.commit+':build/m3-turnip-source.json']))
    if json.loads(files['source.json']) != pin or pin != built_pin:
        raise ValueError('Mesa source pin changed')
    sums = {Path(x.split(maxsplit=1)[1]).name: x.split()[0]
            for x in files['SHA256SUMS'].decode().splitlines()}
    if digest(files['turnip-vendor.tar.gz']) != sums['turnip-vendor.tar.gz']:
        raise ValueError('Vendor tar digest mismatch')
    payload = {}
    with tarfile.open(fileobj=io.BytesIO(files['turnip-vendor.tar.gz']), mode='r:gz') as tar:
        for member in tar:
            if member.isdir():
                continue
            name = member.name.removeprefix('./')
            if (name != 'lib64/hw/vulkan.freedreno.so' or not member.isfile()
                    or name in payload or member.size > limit):
                raise ValueError('Unexpected Turnip payload')
            payload[name] = tar.extractfile(member).read()
    if set(payload) != {'lib64/hw/vulkan.freedreno.so'}:
        raise ValueError('Missing Turnip driver')
    driver = payload['lib64/hw/vulkan.freedreno.so']
    if (driver[:6] != b'\x7fELF\x02\x01' or driver[18:20] != b'\xb7\x00'
            or digest(driver) != sums['vulkan.freedreno.so']):
        raise ValueError('Expected hashed ARM64 driver')
    # ELF parsing uses the same NDK tools as the build, before any image packing.
    output.mkdir(parents=True)
    target = output/'vendor/lib64/hw/vulkan.freedreno.so'
    target.parent.mkdir(parents=True)
    target.write_bytes(driver)
    elf = subprocess.check_output([str(a.readelf), '--dynamic', str(target)], text=True)
    needed = re.findall(r'Shared library: \[(.*?)\]', elf)
    allowed = {'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libz.so',
               'libnativewindow.so', 'libsync.so', 'libandroid.so'}
    if not needed or set(needed)-allowed or '[vulkan.freedreno.so]' not in elf:
        raise ValueError('Unexpected runtime dependency or SONAME: '+repr(needed))
    proof = dict(run_id=a.run_id, source_commit=a.commit, artifact_id=a.artifact_id,
        artifact_archive_digest=artifact['digest'], archive_digest_verified=True,
        source_verified=True, source=pin, needed=needed,
        files={'/lib64/hw/vulkan.freedreno.so': digest(driver)},
        hardware_result='NOT RUN')
    for name, data in files.items():
        if name != 'turnip-vendor.tar.gz':
            (output/name).write_bytes(data)
    (output/'provenance.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
