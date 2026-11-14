"""Select a bounded source workspace for the real AOSP init_first_stage target."""
import argparse
import base64
import copy
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

EXACT = '''bionic bootable/recovery device/common device/generic/arm64
device/generic/common external/avb external/boringssl external/brotli
external/bzip2 external/e2fsprogs external/fec external/fmtlib external/gflags
external/go-cmp external/golang-protobuf external/google-benchmark
external/googletest external/jsoncpp external/libcap external/libcxx
external/libcxxabi external/libevent external/liburing external/libxml2
external/lz4 external/lzma external/pcre external/protobuf external/selinux
external/sqlite external/starlark-go external/tinyxml2 external/zlib external/zstd
external/rust/android-crates-io external/rust/cxx
frameworks/native frameworks/libs/native_bridge_support frameworks/libs/modules-utils
frameworks/proto_logging hardware/libhardware hardware/libhardware_legacy
hardware/interfaces packages/modules/Virtualization packages/modules/adb
prebuilts/build-tools prebuilts/clang-tools prebuilts/clang/host/linux-x86
prebuilts/gcc/linux-x86/host/x86_64-linux-glibc2.17-4.8
prebuilts/go/linux-x86 prebuilts/jdk/jdk21 prebuilts/jdk/jdk25
prebuilts/misc prebuilts/ndk prebuilts/rust prebuilts/rust-toolchain/linux-x86
prebuilts/rust-toolchain/linux-musl-x86 prebuilts/sdk prebuilts/tools
prebuilts/remoteexecution-client prebuilts/bazel/common
tools/metalava tools/tradefederation/prebuilts'''.split()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); root=Path(__file__).resolve().parents[2]
    pin=json.loads((root/'build/m2-first-stage-source.json').read_text())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url='https://android.googlesource.com/platform/manifest/+/'+pin['aosp_manifest_commit']+'/default.xml?format=TEXT'
    data=base64.b64decode(opener.open(url,timeout=60).read())
    upstream=ET.fromstring(data)
    projects={x.attrib.get('path',x.attrib['name']):x for x in upstream.findall('project')}
    missing=sorted(set(EXACT)-projects.keys())
    if missing:raise ValueError('Unknown pinned project paths: '+repr(missing))
    selected=set(EXACT)|{x for x in projects if x.startswith('build/') or
        (x.startswith('system/') and not x.startswith('system/software_defined_vehicle/'))}
    manifest=ET.Element('manifest')
    ET.SubElement(manifest,'remote',name='aosp',fetch='https://android.googlesource.com/')
    ET.SubElement(manifest,'default',remote='aosp',revision='refs/tags/'+pin['aosp_tag'])
    for path in sorted(selected):
        node=copy.deepcopy(projects[path]); node.attrib.pop('groups',None)
        # Keep each upstream per-project revision and all link/copy directives.
        manifest.append(node)
    ET.indent(manifest)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(manifest).write(a.output,encoding='utf-8',xml_declaration=True)
    a.output.with_suffix('.upstream.xml').write_bytes(data)
    print('Selected',len(selected),'pinned AOSP projects')


if __name__=='__main__':main()
