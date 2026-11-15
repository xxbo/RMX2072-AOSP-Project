"""Build a pure DSC calculation probe from the exact ACK helper sources.

This does not open devices, change display state or read kernel memory. Run the
ARM64 result through a bounded ADB shell and compare its 128-byte PPS hex output
with the imported factory panel PPS. The kernel helper/table bytes stay intact.
"""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for arg in ('source','output','ndk'):p.add_argument('--'+arg,type=Path,required=True)
a=p.parse_args();base=a.source.resolve();out=a.output.resolve()
if out.is_relative_to(Path(__file__).resolve().parents[2]):p.error('Keep generated binaries outside the checkout')
out.mkdir(parents=True,exist_ok=True)
pins={
 'drivers/gpu/drm/display/drm_dsc_helper.c':'a4d0df3f61fff2846a94f95928e2267e76f3b2c4c6cd57d2920f7b0dc7367fef',
 'include/drm/display/drm_dsc.h':'f57cf45be321cdf4def25491ef54e2adfef9627c18cebc53bd9e2acd0fd2a394',
 'include/drm/display/drm_dsc_helper.h':'dd0a8f30ee0c78d5ff61081f7dd928e85fd58436f6f41367e8d927ed36014f08'}
for name,digest in pins.items():
 if hashlib.sha256((base/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
  raise ValueError('ACK helper differs from pinned source: '+name)
header=(base/'include/drm/display/drm_dsc.h').read_text(encoding='utf-8')
helper=(base/'drivers/gpu/drm/display/drm_dsc_helper.c').read_text(encoding='utf-8')
decl=(base/'include/drm/display/drm_dsc_helper.h').read_text(encoding='utf-8')
header=re.sub(r'^#include.*$', '',header,flags=re.M)
decl=re.sub(r'^#include.*$', '',decl,flags=re.M)
core=helper[helper.index('void drm_dsc_pps_payload_pack('):helper.index('static void drm_dsc_dump_config_main_params(')]
prefix='''#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef uint16_t __be16;
#ifndef __packed
#define __packed __attribute__((packed))
#endif
struct dp_sdp_header { u8 HB0, HB1, HB2, HB3; };
#define DP_SDP_PPS_HEADER_PAYLOAD_BYTES_MINUS_1 127
#define cpu_to_be16(x) __builtin_bswap16(x)
#define BUILD_BUG_ON(x) _Static_assert(!(x), "size")
#define EXPORT_SYMBOL(x)
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define WARN_ON_ONCE(x) (!!(x))
#define DRM_DEBUG_KMS(...) fprintf(stderr, __VA_ARGS__)
'''
main='''int main(void) {
 struct drm_dsc_config c={0}; struct drm_dsc_picture_parameter_set p;
 c.dsc_version_major=1; c.dsc_version_minor=1; c.slice_width=540; c.slice_height=48;
 c.slice_count=2; c.bits_per_component=8; c.bits_per_pixel=128; c.block_pred_enable=true;
 c.pic_width=1080;c.pic_height=2400;c.simple_422=0;c.convert_rgb=1;c.vbr_enable=0;
 drm_dsc_set_const_params(&c);drm_dsc_set_rc_buf_thresh(&c);
 if(drm_dsc_setup_rc_params(&c,DRM_DSC_1_1_PRE_SCR))return 2;
 c.initial_scale_value=drm_dsc_initial_scale_value(&c);c.line_buf_depth=c.bits_per_component+1;
 if(drm_dsc_compute_rc_parameters(&c))return 3;
 drm_dsc_pps_payload_pack(&p,&c);
 for(unsigned i=0;i<sizeof(p);i++)printf("%02x",((unsigned char*)&p)[i]);puts("");return 0;
}
'''
source=out/'compare.c';source.write_text(prefix+header+decl+core+main,encoding='utf-8',newline='\n')
clang=a.ndk.resolve()/'toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android35-clang.cmd'
subprocess.run([str(clang),'-static','-O2',str(source),'-o',str(out/'dsc-compare')],check=True)
record=dict(ack_commit='ecdaacc9a0ee87eaf9544e1836d86bd9d590312e',sources=pins,
 generated_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
 binary_sha256=hashlib.sha256((out/'dsc-compare').read_bytes()).hexdigest(),
 scope='Pure arithmetic only; no hardware validation',parameters=dict(width=1080,height=2400,slice_width=540,slice_height=48,bpc=8,bpp=8,version='1.1',table='DRM_DSC_1_1_PRE_SCR'))
(out/'build.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
