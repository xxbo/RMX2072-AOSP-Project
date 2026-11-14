"""Fetch only checked kernel members from a successful pinned Actions artifact.

Requires remotezip/requests in WORKSPACE/host-deps and the existing GitHub Git
credential. No full archive or historical image directory is retained.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--run-json',type=Path,required=True)
    p.add_argument('--artifacts-json',type=Path,required=True)
    p.add_argument('--expected-commit',required=True)
    p.add_argument('--pon-power',action='store_true')
    p.add_argument('--verify-only',action='store_true',help='Check the artifact without replacing any current input')
    a=p.parse_args();pin=a.expected_commit
    assert re.fullmatch('[0-9a-f]{40}',pin)
    w=a.workspace.resolve();repo=Path(__file__).resolve().parents[2]
    out=(w/'current/kernel').resolve()
    assert out.is_relative_to(w) and not out.is_relative_to(repo)
    run=json.loads(a.run_json.read_text());artifacts=json.loads(a.artifacts_json.read_text())['artifacts']
    assert run['head_sha']==pin and run['status']=='completed' and run['conclusion']=='success'
    assert run['path']=='.github/workflows/sm8250-bootstrap.yml'
    artifacts=[x for x in artifacts if re.fullmatch(r'sm8250-618-bootstrap-\d+',x['name'])]
    assert len(artifacts)==1
    artifact=artifacts[0]
    assert not artifact['expired'] and artifact['workflow_run']['id']==run['id'] and artifact['workflow_run']['head_sha']==pin
    sources={'keymaster-lookup.sha256':'bootstrap-probes/rmx2072-keymaster-lookup.c',
             'keymaster-transport.sha256':'bootstrap-probes/rmx2072-keymaster-transport.h',
             'listener.sha256':'bootstrap-probes/rmx2072-listener.inc',
             'tzmem-patch.sha256':'bootstrap-patches/rmx2072-tzmem-status.patch',
             'board-patch.sha256':'bootstrap-patches/rmx2072-scm-edl.patch',
             'phy-test.sha256':'bootstrap-probes/rmx2072-ufs-phy-test.c'}
    if a.pon_power:sources['pon-power-patch.sha256']='bootstrap-patches/rmx2072-pon-power.patch'
    wanted=set(sources)|{'Image.gz','sm8250_bootstrap_dot_config','kernel.release','SHA256SUMS','build-metadata.txt','resolved-manifest.xml'}
    sys.path.insert(0,str(w/'host-deps'))
    from remotezip import RemoteZip
    import requests
    os.environ['GIT_TERMINAL_PROMPT']='0'
    credential=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=True)
    values=dict(x.split('=',1) for x in credential.stdout.splitlines() if '=' in x)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request(artifact['archive_download_url']+'?fresh='+str(time.time_ns()),headers={'Authorization':'Bearer '+values['password'],'Cache-Control':'no-cache'})
    try:
        opener.open(request,timeout=30)
        raise RuntimeError('Expected authenticated artifact redirect')
    except urllib.error.HTTPError as error:
        if error.code!=302:raise RuntimeError('Artifact access failed with HTTP '+str(error.code)) from None
        url=error.headers['Location']
    session=requests.Session();session.trust_env=False
    selected={};digests={}
    with RemoteZip(url,session=session,timeout=90,support_suffix_range=False) as archive:
        for name in sorted(wanted):
            matches=[x for x in archive.infolist() if PurePosixPath(x.filename).name==name]
            assert len(matches)==1 and matches[0].file_size<=(128*1024*1024 if name=='Image.gz' else 8*1024*1024)
            member=matches[0].filename;data=archive.read(member)
            selected[name]=data;digests[member]=hashlib.sha256(data).hexdigest()
            print('Fetched',member,len(data),flush=True)
    for manifest,source in sources.items():
        source_bytes=subprocess.check_output(['git','-C',str(repo),'show',pin+':device/realme/bladerunner_48m/'+source])
        assert hashlib.sha256(source_bytes).hexdigest()==selected[manifest].decode().split()[0]
    sums={PurePosixPath(line.split(maxsplit=1)[1].strip()).name:line.split()[0]
          for line in selected['SHA256SUMS'].decode().splitlines()}
    for name in ('Image.gz','kernel.release','sm8250_bootstrap_dot_config'):
        assert hashlib.sha256(selected[name]).hexdigest()==sums[name]
    config=selected['sm8250_bootstrap_dot_config'].decode().splitlines()
    required=['CONFIG_QCOM_TZMEM_MODE_SHMBRIDGE','CONFIG_QCOM_PDC','CONFIG_SPMI_MSM_PMIC_ARB','CONFIG_MFD_SPMI_PMIC','CONFIG_QCOM_WDT']
    if a.pon_power:required+=['CONFIG_INPUT_PM8941_PWRKEY','CONFIG_POWER_RESET_MSM']
    assert all(option+'=y' in config for option in required)
    with gzip.GzipFile(fileobj=io.BytesIO(selected.pop('Image.gz'))) as compressed:
        raw=compressed.read(256*1024*1024+1)
    assert 8*1024*1024<len(raw)<=256*1024*1024 and raw[56:60]==b'ARMd'
    digest=hashlib.sha256(raw).hexdigest();assert digest==sums['Image']
    record=dict(run_id=run['id'],source_commit=pin,artifact_id=artifact['id'],
                artifact_archive_digest=artifact['digest'],archive_digest_verified=False,
                selected_member_sha256=digests,image_sha256=digest,source_digests_verified=True,
                dist_digests_verified=True,pon_power=a.pon_power,installing=False)
    if a.verify_only:
        print('Artifact verified without installation',digest,flush=True)
        return
    # No live input is replaced until every selected member and source is checked.
    # A partial local install is explicitly unusable by the image builder.
    out.mkdir(parents=True,exist_ok=True)
    (out/'provenance.json').write_text(json.dumps(dict(installing=True))+'\n')
    for name,data in dict(selected,Image=raw).items():
        pending=out/(name+'.new');pending.write_bytes(data);pending.replace(out/name)
    (out/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
    # The compressed duplicate is unnecessary for packing the current boot.
    duplicate=out/'Image.gz'
    if duplicate.exists():duplicate.unlink()
    print('Verified current kernel',digest,flush=True)


if __name__=='__main__':main()
