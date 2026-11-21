/* SPDX-License-Identifier: GPL-2.0-only */
/* Read-only DRM plane/FB metadata. No master, modeset, PRIME import or mapping. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>

#define PTR(p) ((uint64_t)(uintptr_t)(p))
#define LIMIT 128

static int call(int fd, unsigned long op, void *arg, const char *name)
{
	int rc;
	do { rc = ioctl(fd, op, arg); } while (rc < 0 && errno == EINTR);
	if (rc < 0) printf("DRMSCAN error=%s errno=%d\n", name, errno);
	return rc;
}

static void stamp(const char *phase)
{
	struct timespec t;
	if (clock_gettime(CLOCK_BOOTTIME, &t)) { puts("DRMSCAN error=clock"); return; }
	printf("DRMSCAN phase=%s uptime=%lld.%09ld\n", phase, (long long)t.tv_sec, t.tv_nsec);
}

static int properties(int fd, uint32_t id)
{
	uint32_t ids[LIMIT]; uint64_t values[LIMIT];
	struct drm_mode_obj_get_properties p = {.obj_id=id, .obj_type=DRM_MODE_OBJECT_PLANE};
	if (call(fd, DRM_IOCTL_MODE_OBJ_GETPROPERTIES, &p, "property-count") || p.count_props > LIMIT) return -1;
	uint32_t cap=p.count_props;
	p.props_ptr=PTR(ids); p.prop_values_ptr=PTR(values);
	if (call(fd, DRM_IOCTL_MODE_OBJ_GETPROPERTIES, &p, "properties") || p.count_props > cap) return -1;
	for (uint32_t i=0; i<p.count_props; i++) {
		struct drm_mode_get_property prop = {.prop_id=ids[i]};
		if (call(fd, DRM_IOCTL_MODE_GETPROPERTY, &prop, "property-name")) return -1;
		prop.name[sizeof(prop.name)-1]=0;
		printf("DRMSCAN plane=%u property=%s value=%" PRIu64 "\n", id, prop.name, (uint64_t)values[i]);
	}
	return 0;
}

static int snapshot(void)
{
	char boot[64]={0}, driver[64]={0};
	int result=1, bootfd=open("/proc/sys/kernel/random/boot_id",O_RDONLY|O_CLOEXEC);
	setvbuf(stdout,NULL,_IONBF,0);
	if (bootfd < 0) return 1;
	ssize_t n=read(bootfd,boot,sizeof(boot)-1);close(bootfd);
	if (n != 37) return 1;
	boot[36]=0; printf("DRMSCAN boot_id=%s scope=live-DRM-metadata\n",boot);
	stamp("begin");
	int fd=open("/dev/dri/card0",O_RDWR|O_CLOEXEC);
	if (fd < 0) { printf("DRMSCAN error=open errno=%d\n",errno); return 1; }
	struct drm_version v={.name_len=sizeof(driver)-1,.name=driver};
	if (call(fd,DRM_IOCTL_VERSION,&v,"version") || strcmp(driver,"msm")) goto out;
	/* Changes visibility only on this file descriptor, never hardware state. */
	struct drm_set_client_cap cap={.capability=DRM_CLIENT_CAP_UNIVERSAL_PLANES,.value=1};
	if (call(fd,DRM_IOCTL_SET_CLIENT_CAP,&cap,"universal-planes")) goto out;
	cap.capability=DRM_CLIENT_CAP_ATOMIC;
	if (call(fd,DRM_IOCTL_SET_CLIENT_CAP,&cap,"atomic-property-visibility")) goto out;
	uint32_t ids[LIMIT];
	struct drm_mode_get_plane_res res={0};
	if (call(fd,DRM_IOCTL_MODE_GETPLANERESOURCES,&res,"plane-count") || res.count_planes > LIMIT) goto out;
	uint32_t count=res.count_planes;res.plane_id_ptr=PTR(ids);
	if (call(fd,DRM_IOCTL_MODE_GETPLANERESOURCES,&res,"planes") || res.count_planes > count) goto out;
	unsigned active=0;
	for (uint32_t i=0;i<res.count_planes;i++) {
		struct drm_mode_get_plane p={.plane_id=ids[i]};
		if (call(fd,DRM_IOCTL_MODE_GETPLANE,&p,"plane")) goto out;
		if (!p.crtc_id || !p.fb_id) continue;
		active++;
		printf("DRMSCAN plane=%u crtc=%u fb=%u\n",p.plane_id,p.crtc_id,p.fb_id);
		struct drm_mode_fb_cmd2 fb={.fb_id=p.fb_id};
		if (call(fd,DRM_IOCTL_MODE_GETFB2,&fb,"fb2")) goto out;
		printf("DRMSCAN fb=%u width=%u height=%u fourcc=0x%08x flags=0x%x allocation_length=unknown\n",
		       fb.fb_id,fb.width,fb.height,fb.pixel_format,fb.flags);
		for (int j=0;j<4;j++) {
			printf("DRMSCAN fb=%u component=%d pitch=%u offset=%u modifier=0x%016" PRIx64 " handle_returned=%d\n",
			       fb.fb_id,j,fb.pitches[j],fb.offsets[j],(uint64_t)fb.modifier[j],fb.handles[j] != 0);
			/* GETFB2 can return new handles to privileged callers. Close each unique one. */
			int unique=fb.handles[j] != 0;
			for (int k=0;k<j;k++) if (fb.handles[k]==fb.handles[j]) unique=0;
			if (unique) { struct drm_gem_close close_arg={.handle=fb.handles[j]};
				if (call(fd,DRM_IOCTL_GEM_CLOSE,&close_arg,"close-fb-handle")) goto out; }
		}
		if (properties(fd,p.plane_id)) goto out;
		struct drm_mode_get_plane after={.plane_id=p.plane_id};
		if (call(fd,DRM_IOCTL_MODE_GETPLANE,&after,"plane-after")) goto out;
		printf("DRMSCAN plane=%u fb_after=%u crtc_after=%u stable_binding=%d\n",p.plane_id,
		       after.fb_id,after.crtc_id,after.fb_id==p.fb_id && after.crtc_id==p.crtc_id);
	}
	printf("DRMSCAN active_planes=%u\n",active);
	result=active ? 0 : 2;
out:
	close(fd);stamp("end");printf("DRMSCAN exit=%d\n",result);return result;
}

int main(void)
{
	/* Fixed engineering output and schedule; no arbitrary path or command API. */
	int out=open("/data/vendor/rmx-m3-diag/scanout.txt",O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW|O_CLOEXEC,0644);
	if (out < 0) return 1;
	if (dup2(out,STDOUT_FILENO)<0 || dup2(out,STDERR_FILENO)<0) { close(out); return 1; }
	close(out);
	sleep(10);
	int first=snapshot();
	sleep(5);
	int second=snapshot();
	return first || second;
}
