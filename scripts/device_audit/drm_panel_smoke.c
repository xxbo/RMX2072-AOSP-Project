/* SPDX-License-Identifier: GPL-2.0-only */
/* Physical KMS smoke test, no EGL, GPU, framebuffer address guesses or storage writes.
 * Run in the disposable pre-policy initramfs. Always release DRM master before
 * Android starts. Success means KMS accepted scanout, not operator-confirmed light.
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>

#define PTR(p) ((uint64_t)(uintptr_t)(p))
#define LIMIT 64

static int call(int fd, unsigned long op, void *arg, const char *name)
{
	int ret;
	do { ret = ioctl(fd, op, arg); } while (ret < 0 && errno == EINTR);
	if (ret < 0) printf("DRMTEST failure=%s errno=%d message=%s\n", name, errno, strerror(errno));
	return ret;
}

struct buffer { struct drm_mode_create_dumb dumb; uint32_t fb; void *map; };

static int alloc_buffer(int fd, struct buffer *b, uint32_t width, uint32_t height, int alternate)
{
	struct drm_mode_map_dumb map = {0};
	struct drm_mode_fb_cmd fb = {0};
	b->dumb.width = width; b->dumb.height = height; b->dumb.bpp = 32;
	if (call(fd, DRM_IOCTL_MODE_CREATE_DUMB, &b->dumb, "create-dumb")) return -1;
	if (b->dumb.size > 64 * 1024 * 1024 || b->dumb.pitch < width * 4) return -1;
	map.handle = b->dumb.handle;
	if (call(fd, DRM_IOCTL_MODE_MAP_DUMB, &map, "map-dumb")) return -1;
	b->map = mmap(NULL, b->dumb.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
	if (b->map == MAP_FAILED) { b->map = NULL; perror("mmap"); return -1; }
	for (uint32_t y = 0; y < height; y++) {
		uint32_t *line = (uint32_t *)((char *)b->map + y * b->dumb.pitch);
		const uint32_t colors[] = {0xff0000, 0x00ff00, 0x0000ff, 0xffffff, 0x606060, 0};
		for (uint32_t x = 0; x < width; x++)
			line[x] = colors[(x * 6 / width + alternate * 3) % 6];
	}
	fb.width = width; fb.height = height; fb.pitch = b->dumb.pitch;
	fb.bpp = 32; fb.depth = 24; fb.handle = b->dumb.handle;
	if (call(fd, DRM_IOCTL_MODE_ADDFB, &fb, "add-fb")) return -1;
	b->fb = fb.fb_id;
	printf("DRMTEST buffer=%u size=%llu pitch=%u\n", b->fb, (unsigned long long)b->dumb.size, b->dumb.pitch);
	return 0;
}

int main(void)
{
	uint32_t connectors[LIMIT], crtcs[LIMIT], encoders[LIMIT];
	struct drm_mode_modeinfo modes[LIMIT], mode = {0};
	struct drm_mode_card_res res = {0};
	struct drm_mode_get_connector conn = {0};
	struct drm_mode_crtc scanout = {0};
	struct buffer buffers[2] = {0};
	uint32_t crtc = 0, connector = 0;
	uint32_t last_sequence = 0;
	uint64_t last_event_us = 0;
	int fd = -1, result = 1, active = 0;
	setvbuf(stdout, NULL, _IONBF, 0);
	for (int retry = 0; retry < 8; retry++) {
		fd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
		if (fd >= 0) break;
		sleep(1);
	}
	if (fd < 0) { printf("DRMTEST blocked=no-card0 errno=%d\n", errno); return 2; }
	char driver[64] = {0};
	struct drm_version version = {.name_len = sizeof(driver) - 1, .name = driver};
	if (call(fd, DRM_IOCTL_VERSION, &version, "version")) goto out;
	if (strcmp(driver, "msm")) { printf("DRMTEST rejected-driver=%s\n", driver); goto out; }
	printf("DRMTEST driver=%s\n", driver);
	if (call(fd, DRM_IOCTL_SET_MASTER, NULL, "master")) goto out;
	if (call(fd, DRM_IOCTL_MODE_GETRESOURCES, &res, "resources-count")) goto out;
	if (res.count_connectors > LIMIT || res.count_crtcs > 32) goto out;
	res.connector_id_ptr = PTR(connectors); res.crtc_id_ptr = PTR(crtcs);
	res.count_fbs = 0; res.count_encoders = 0;
	if (call(fd, DRM_IOCTL_MODE_GETRESOURCES, &res, "resources")) goto out;
	if (res.count_connectors > LIMIT || res.count_crtcs > 32) goto out;
	for (uint32_t i = 0; i < res.count_connectors; i++) {
		memset(&conn, 0, sizeof(conn)); conn.connector_id = connectors[i];
		if (call(fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn, "connector-count")) goto out;
		printf("DRMTEST connector=%u type=%u connection=%u modes=%u\n", conn.connector_id,
		       conn.connector_type, conn.connection, conn.count_modes);
		if (conn.connection != 1 || conn.connector_type != DRM_MODE_CONNECTOR_DSI) continue;
		if (conn.count_modes > LIMIT || conn.count_encoders > LIMIT) goto out;
		conn.modes_ptr = PTR(modes); conn.encoders_ptr = PTR(encoders);
		conn.count_props = 0;
		if (call(fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn, "connector-modes")) goto out;
		if (conn.count_modes > LIMIT || conn.count_encoders > LIMIT) goto out;
		for (uint32_t m = 0; m < conn.count_modes; m++) {
			if (modes[m].hdisplay == 1080 && modes[m].vdisplay == 2400 && modes[m].vrefresh == 60) {
				mode = modes[m]; connector = conn.connector_id; break;
			}
		}
		if (connector) break;
	}
	if (!connector) { puts("DRMTEST blocked=no-1080x2400-60-DSI"); goto out; }
	for (uint32_t i = 0; i < conn.count_encoders && !crtc; i++) {
		struct drm_mode_get_encoder encoder = {.encoder_id = encoders[i]};
		if (call(fd, DRM_IOCTL_MODE_GETENCODER, &encoder, "encoder")) goto out;
		for (uint32_t c = 0; c < res.count_crtcs; c++)
			if (encoder.possible_crtcs & (1U << c)) { crtc = crtcs[c]; break; }
	}
	if (!crtc) goto out;
	for (int i = 0; i < 2; i++)
		if (alloc_buffer(fd, &buffers[i], mode.hdisplay, mode.vdisplay, i)) goto out;
	scanout.crtc_id = crtc; scanout.fb_id = buffers[0].fb; scanout.mode_valid = 1;
	scanout.mode = mode; scanout.set_connectors_ptr = PTR(&connector); scanout.count_connectors = 1;
	if (call(fd, DRM_IOCTL_MODE_SETCRTC, &scanout, "set-crtc")) goto out;
	active = 1;
	printf("DRMTEST modeset=PASS crtc=%u connector=%u mode=%ux%u clock=%u\n", crtc, connector, mode.hdisplay, mode.vdisplay, mode.clock);
	for (int i = 1; i <= 4; i++) {
		sleep(1);
		struct drm_mode_crtc_page_flip flip = {.crtc_id = crtc, .fb_id = buffers[i % 2].fb,
			.flags = DRM_MODE_PAGE_FLIP_EVENT, .user_data = (uint64_t)i};
		if (call(fd, DRM_IOCTL_MODE_PAGE_FLIP, &flip, "page-flip")) goto out;
		struct pollfd pfd = {.fd = fd, .events = POLLIN};
		if (poll(&pfd, 1, 1500) <= 0) { puts("DRMTEST failure=flip-event-timeout"); goto out; }
		struct drm_event_vblank event = {0};
		if (read(fd, &event, sizeof(event)) != sizeof(event) ||
		    event.base.type != DRM_EVENT_FLIP_COMPLETE || event.user_data != (uint64_t)i) goto out;
		printf("DRMTEST flip=%d sequence=%u time=%u.%06u\n", i, event.sequence, event.tv_sec, event.tv_usec);
		uint64_t event_us = (uint64_t)event.tv_sec * 1000000 + event.tv_usec;
		/* Timeout-generated completions can reuse stale vblank data. Trial 42
		 * returned four events with identical sequence/time while DSI failed. */
		if (i > 1 && ((int32_t)(event.sequence - last_sequence) <= 0 || event_us <= last_event_us)) {
			puts("DRMTEST failure=non-advancing-vblank"); goto out;
		}
		last_sequence = event.sequence; last_event_us = event_us;
	}
	puts("DRMTEST kms_events=PASS physical_observation=REQUIRED"); result = 0;
out:
	if (active) {
		struct drm_mode_crtc disable = {.crtc_id = crtc};
		if (call(fd, DRM_IOCTL_MODE_SETCRTC, &disable, "disable-crtc")) result = 1;
	}
	for (int i = 0; i < 2; i++) {
		if (buffers[i].map) munmap(buffers[i].map, buffers[i].dumb.size);
		if (buffers[i].fb) ioctl(fd, DRM_IOCTL_MODE_RMFB, &buffers[i].fb);
		if (buffers[i].dumb.handle) {
			struct drm_mode_destroy_dumb destroy = {.handle = buffers[i].dumb.handle};
			ioctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &destroy);
		}
	}
	close(fd);
	printf("DRMTEST exit=%d\n", result);
	return result;
}
