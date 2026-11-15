"""Select a bounded source workspace for the real AOSP init_first_stage target."""
import argparse
import base64
import copy
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

EXACT = '''bionic bootable/recovery device/common device/generic/arm64
device/generic/common external/abseil-cpp external/arm-optimized-routines external/avb external/boringssl external/brotli
external/bzip2 external/e2fsprogs external/fec external/fmtlib external/gflags
external/go-cmp external/golang-protobuf external/google-benchmark external/google-highway
external/googletest external/gwp_asan external/icu external/jsoncpp external/libcap external/libchrome external/libcxx
external/libcxxabi external/libevent external/liburing external/libxml2 external/llvm-libc
external/lz4 external/lzma external/modp_b64 external/pcre external/pogreb external/protobuf external/selinux
external/scudo external/sqlite external/starlark-go external/tinyxml2 external/zlib external/zstd
external/rust/android-crates-io external/rust/cxx
frameworks/base frameworks/native frameworks/libs/native_bridge_support frameworks/libs/modules-utils
frameworks/proto_logging hardware/libhardware hardware/libhardware_legacy
hardware/interfaces kernel/configs libnativehelper packages/modules/Virtualization packages/modules/adb
packages/modules/common packages/services/Car
prebuilts/build-tools prebuilts/clang-tools prebuilts/clang/host/linux-x86
prebuilts/gcc/linux-x86/host/x86_64-linux-glibc2.17-4.8
prebuilts/go/linux-x86 prebuilts/jdk/jdk21 prebuilts/jdk/jdk25
prebuilts/misc prebuilts/ndk prebuilts/rust prebuilts/siso prebuilts/rust-toolchain/linux-x86
prebuilts/rust-toolchain/linux-musl-x86 prebuilts/sdk prebuilts/tools
prebuilts/remoteexecution-client prebuilts/bazel/common
toolchain/pgo-profiles tools/metalava tools/tradefederation/prebuilts'''.split()

# Native init and its storage/base libraries. Including every system project
# also analyzes unrelated keystore/network/service Rust flag libraries, whose
# framework declarations are deliberately absent from this native workspace.
SYSTEM = '''system/apex system/core system/extras system/fs/fs_mgr system/gsid
system/hardware/interfaces system/libartpalette system/libbase system/libfmq
system/libhidl system/libhwbinder system/libprocinfo system/librustutils
system/libsysprop system/libufdt system/libvintf system/libziparchive
system/linkerconfig system/logging system/memory/libdmabufheap system/memory/libion
system/memory/libmeminfo system/memory/libmemtrack system/memory/libmemunreachable
system/memory/libwrapfd system/sepolicy system/server_configurable_flags
system/testing/gtest_extras system/tools/aidl system/tools/hidl
system/tools/mkbootimg system/tools/sysprop system/tools/xsdc
system/unwinding system/update_engine'''.split()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--graphics', action='store_true')
    a=p.parse_args(); root=Path(__file__).resolve().parents[2]
    pin=json.loads((root/'build/m2-first-stage-source.json').read_text())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url='https://android.googlesource.com/platform/manifest/+/'+pin['aosp_manifest_commit']+'/default.xml?format=TEXT'
    data=base64.b64decode(opener.open(url,timeout=60).read())
    upstream=ET.fromstring(data)
    projects={x.attrib.get('path',x.attrib['name']):x for x in upstream.findall('project')}
    missing=sorted((set(EXACT) | set(SYSTEM))-projects.keys())
    if missing:raise ValueError('Unknown pinned project paths: '+repr(missing))
    selected=set(EXACT)|set(SYSTEM)|{x for x in projects if x.startswith('build/')}
    if a.graphics:
        graphics = set('''external/angle external/swiftshader external/minigbm
external/libdrm external/drm_hwcomposer external/libdisplay-info external/perfetto
external/libpng external/expat external/flatbuffers external/libjpeg-turbo
external/libyuv external/libvpx external/vulkan-headers
packages/modules/StatsD packages/modules/Gki test/vts-testcase/hal'''.split())
        unknown = graphics - projects.keys()
        if unknown:
            raise ValueError('Unknown pinned graphics projects: ' + repr(sorted(unknown)))
        selected |= graphics
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
