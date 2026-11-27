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
#include <sys/stat.h>
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

/* Read the existing MSM snapshot only with our CRTC enabled. The pinned
 * driver's kms reader owns display runtime-PM references and snapshots
 * DSI/DPU registers and atomic state. No debug register writes or GPU snapshot.
 * The enclosing initramfs caller bounds this probe to 50 s (75 s for solid fill).
 * Keep output below the witness's 2 MiB publication limit.
 */
static void kms_snapshot(const char *solid_label)
{
	static const struct { const char *name; size_t limit; } files[] = {
		{"kms", 512 * 1024}, {"state", 64 * 1024}, {"fb", 64 * 1024},
	};
	for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); i++) {
		if (solid_label && i) break;
		const char *label = solid_label ? solid_label : files[i].name;
		size_t limit = solid_label ? 256 * 1024 : files[i].limit;
		char path[128], buf[4096];
		size_t total = 0;
		int error = 0;
		snprintf(path, sizeof(path), "/sys/kernel/debug/dri/0/%s", files[i].name);
		printf("DRMSNAPSHOT begin=%s phase=after-flips\n", label);
		int fd = open(path, O_RDONLY | O_CLOEXEC);
		if (fd < 0) {
			printf("DRMSNAPSHOT end=%s open_errno=%d\n", label, errno);
			continue;
		}
		while (total < limit) {
			size_t count = limit - total;
			if (count > sizeof(buf)) count = sizeof(buf);
			ssize_t n = read(fd, buf, count);
			if (n < 0 && errno == EINTR) continue;
			if (n < 0) { error = errno; break; }
			if (!n) break;
			if (fwrite(buf, 1, (size_t)n, stdout) != (size_t)n) {
				error = EIO;
				break;
			}
			total += (size_t)n;
		}
		close(fd);
		printf("\nDRMSNAPSHOT end=%s bytes=%zu limit_reached=%d read_errno=%d\n",
		       label, total, total == limit, error);
	}
}

/* Read the CCF's own diagnostics while the modeset still owns the clocks.
 * Rates may be cached by CCF; counts are software references, not PLL-lock
 * or physical-output proof. Never write clock/debug registers from this test.
 */
static void clock_snapshot(const char *phase)
{
	static const char *const clocks[] = {
		"disp_cc_mdss_mdp_clk_src", "disp_cc_mdss_mdp_clk",
		"disp_cc_mdss_ahb_clk", "disp_cc_mdss_esc0_clk",
		"disp_cc_mdss_vsync_clk",
		"dsi0vco_clk", "dsi0_pll_out_div_clk", "dsi0_pll_bit_clk",
		"dsi0_pll_by_2_bit_clk", "dsi0_pclk_mux",
		"dsi0_phy_pll_out_byteclk", "dsi0_phy_pll_out_dsiclk",
		"disp_cc_mdss_byte0_clk_src", "disp_cc_mdss_byte0_clk",
		"disp_cc_mdss_pclk0_clk_src", "disp_cc_mdss_pclk0_clk",
	};
	static const char *const fields[] = {
		"clk_rate", "clk_parent", "clk_prepare_count", "clk_enable_count", "clk_flags",
	};
	for (size_t c = 0; c < sizeof(clocks) / sizeof(clocks[0]); c++) {
		for (size_t f = 0; f < sizeof(fields) / sizeof(fields[0]); f++) {
			char path[192], value[512];
			snprintf(path, sizeof(path), "/sys/kernel/debug/clk/%s/%s", clocks[c], fields[f]);
			int fd = open(path, O_RDONLY | O_CLOEXEC);
			if (fd < 0) {
				printf("DRMCLOCK phase=%s clock=%s field=%s open_errno=%d\n",
				       phase, clocks[c], fields[f], errno);
				continue;
			}
			ssize_t count;
			do { count = read(fd, value, sizeof(value) - 1); } while (count < 0 && errno == EINTR);
			int read_errno = errno;
			close(fd);
			if (count < 0) {
				printf("DRMCLOCK phase=%s clock=%s field=%s read_errno=%d\n",
				       phase, clocks[c], fields[f], read_errno);
				continue;
			}
			int truncated = count == sizeof(value) - 1;
			while (count && (value[count - 1] == '\n' || value[count - 1] == '\r')) count--;
			value[count] = '\0';
			for (ssize_t i = 0; i < count; i++)
				if (value[i] == '\n' || value[i] == '\r' || value[i] == '\t') value[i] = ',';
			printf("DRMCLOCK phase=%s clock=%s field=%s value=%s truncated=%d\n",
			       phase, clocks[c], fields[f], value, truncated);
		}
	}
}

static int alloc_buffer(int fd, struct buffer *b, uint32_t width, uint32_t height)
{
	struct drm_mode_map_dumb map = {0};
	struct drm_mode_fb_cmd fb = {0};
	b->dumb.width = width; b->dumb.height = height; b->dumb.bpp = 32;
	if (call(fd, DRM_IOCTL_MODE_CREATE_DUMB, &b->dumb, "create-dumb")) return -1;
	if (b->dumb.size > 64 * 1024 * 1024 || b->dumb.pitch < width * 4 ||
	    b->dumb.size < (uint64_t)b->dumb.pitch * height || width != 1080 || height != 2400) return -1;
	map.handle = b->dumb.handle;
	if (call(fd, DRM_IOCTL_MODE_MAP_DUMB, &map, "map-dumb")) return -1;
	b->map = mmap(NULL, b->dumb.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
	if (b->map == MAP_FAILED) { b->map = NULL; perror("mmap"); return -1; }
	int input = open("/m3-pattern.rgb", O_RDONLY | O_CLOEXEC);
	struct stat st;
	if (input < 0) { perror("pattern open"); return -1; }
	if (fstat(input, &st) || !S_ISREG(st.st_mode) || st.st_size != (off_t)width * height * 3) {
		close(input); puts("DRMTEST failure=pattern-size"); return -1;
	}
	memset(b->map, 0, b->dumb.size);
	for (uint32_t y = 0; y < height; y++) {
		unsigned char rgb[1080 * 3];
		size_t have = 0;
		while (have < sizeof(rgb)) {
			ssize_t n = read(input, rgb + have, sizeof(rgb) - have);
			if (n < 0 && errno == EINTR) continue;
			if (n <= 0) { close(input); puts("DRMTEST failure=pattern-read"); return -1; }
			have += (size_t)n;
		}
		uint32_t *line = (uint32_t *)((char *)b->map + y * b->dumb.pitch);
		for (uint32_t x = 0; x < width; x++)
			/* Explicit RGB888 -> XRGB8888; padding follows the returned pitch. */
			line[x] = ((uint32_t)rgb[x*3] << 16) | ((uint32_t)rgb[x*3+1] << 8) | rgb[x*3+2];
	}
	close(input);
	fb.width = width; fb.height = height; fb.pitch = b->dumb.pitch;
	fb.bpp = 32; fb.depth = 24; fb.handle = b->dumb.handle;
	if (call(fd, DRM_IOCTL_MODE_ADDFB, &fb, "add-fb")) return -1;
	b->fb = fb.fb_id;
	printf("DRMTEST buffer=%u size=%llu pitch=%u\n", b->fb, (unsigned long long)b->dumb.size, b->dumb.pitch);
	return 0;
}

static const char *fill_control = "/sys/module/msm/parameters/rmx2072_solid_fill";

static int get_fill(uint32_t *value)
{
	FILE *file = fopen(fill_control, "r");
	if (!file) return -1;
	int matched = fscanf(file, "%u", value);
	int error = fclose(file);
	return matched == 1 && !error ? 0 : -1;
}

static int set_fill(uint32_t value)
{
	char text[32];
	int len = snprintf(text, sizeof(text), "%u\n", value);
	int fd = open(fill_control, O_WRONLY | O_CLOEXEC);
	if (fd < 0) return -1;
	ssize_t written = write(fd, text, (size_t)len);
	int error = close(fd);
	uint32_t observed;
	if (written != len || error || get_fill(&observed) || observed != value) return -1;
	return 0;
}

static int solid_flip(int fd, uint32_t crtc, uint32_t fb, uint64_t cookie,
		      uint32_t *last_sequence, uint64_t *last_us)
{
	struct drm_mode_crtc_page_flip flip = {.crtc_id = crtc, .fb_id = fb,
		.flags = DRM_MODE_PAGE_FLIP_EVENT, .user_data = cookie};
	if (call(fd, DRM_IOCTL_MODE_PAGE_FLIP, &flip, "solid-page-flip")) return -1;
	struct pollfd pfd = {.fd = fd, .events = POLLIN};
	if (poll(&pfd, 1, 1500) <= 0) return -1;
	struct drm_event_vblank event = {0};
	if (read(fd, &event, sizeof(event)) != sizeof(event) ||
	    event.base.type != DRM_EVENT_FLIP_COMPLETE || event.user_data != cookie) return -1;
	uint64_t us = (uint64_t)event.tv_sec * 1000000 + event.tv_usec;
	if ((int32_t)(event.sequence - *last_sequence) <= 0 || us <= *last_us) return -1;
	*last_sequence = event.sequence; *last_us = us;
	printf("DRMSOLID flip=%llu sequence=%u time=%u.%06u\n",
	       (unsigned long long)cookie, event.sequence, event.tv_sec, event.tv_usec);
	return 0;
}

static void phase_marker(const char *text)
{
	int fd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
	if (fd >= 0) { (void)write(fd, text, strlen(text)); close(fd); }
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
	int solid_test = access("/m3-solid-fill-test", F_OK) == 0;
	setvbuf(stdout, NULL, _IONBF, 0);
	if (solid_test) {
		uint32_t value;
		if (get_fill(&value) || value) {
			puts("DRMSOLID failure=missing-or-nonzero-control");
			goto out;
		}
	}
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
			if (modes[m].hdisplay == 1080 && modes[m].vdisplay == 2400 &&
			    (modes[m].vrefresh == 60 || modes[m].vrefresh == 90)) {
				mode = modes[m]; connector = conn.connector_id; break;
			}
		}
		if (connector) break;
	}
	if (!connector) { puts("DRMTEST blocked=no-1080x2400-supported-DSI"); goto out; }
	for (uint32_t i = 0; i < conn.count_encoders && !crtc; i++) {
		struct drm_mode_get_encoder encoder = {.encoder_id = encoders[i]};
		if (call(fd, DRM_IOCTL_MODE_GETENCODER, &encoder, "encoder")) goto out;
		for (uint32_t c = 0; c < res.count_crtcs; c++)
			if (encoder.possible_crtcs & (1U << c)) { crtc = crtcs[c]; break; }
	}
	if (!crtc) goto out;
	for (int i = 0; i < 2; i++)
		if (alloc_buffer(fd, &buffers[i], mode.hdisplay, mode.vdisplay)) goto out;
	scanout.crtc_id = crtc; scanout.fb_id = buffers[0].fb; scanout.mode_valid = 1;
	scanout.mode = mode; scanout.set_connectors_ptr = PTR(&connector); scanout.count_connectors = 1;
	clock_snapshot("before-modeset");
	if (call(fd, DRM_IOCTL_MODE_SETCRTC, &scanout, "set-crtc")) goto out;
	active = 1;
	clock_snapshot("after-modeset");
	printf("DRMTEST modeset=PASS crtc=%u connector=%u mode=%ux%u clock=%u\n", crtc, connector, mode.hdisplay, mode.vdisplay, mode.clock);
	printf("DRMTEST requested_refresh_hz=%u\n", mode.vrefresh);
	/* Keep flips continuous. One-second idle gaps let DRM disable its vblank
	 * reference, so counter delta / wall time is not a panel-rate measurement.
	 * These are scanout completions, not GPU rendering or Android frame times. */
	uint64_t first_event_us = 0;
	uint32_t first_sequence = 0;
	for (int i = 1; i <= 61; i++) {
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
		if (i == 1) { first_event_us = event_us; first_sequence = event.sequence; }
		last_sequence = event.sequence; last_event_us = event_us;
	}
	printf("DRMTEST continuous_intervals=60 elapsed_us=%llu presents_millihz=%llu vblank_counter_millihz=%llu\n",
	       (unsigned long long)(last_event_us - first_event_us),
	       60000000000ULL / (last_event_us - first_event_us),
	       (unsigned long long)(last_sequence - first_sequence) * 1000000000ULL /
	       (last_event_us - first_event_us));
	clock_snapshot("after-flips");
	if (solid_test) {
		static const struct { const char *name, *snapshot; uint32_t value; } colors[] = {
			{"red", "kms-solid-red", 0x800000ffU},
			{"green", "kms-solid-green", 0x8000ff00U},
			{"blue", "kms-solid-blue", 0x80ff0000U},
		};
		for (int i = 0; i < 3; i++) {
			if (set_fill(colors[i].value) ||
			    solid_flip(fd, crtc, buffers[(i+1)%2].fb, 0x6300U+(unsigned)i,
				       &last_sequence, &last_event_us)) {
				puts("DRMSOLID failure=color-update"); goto out;
			}
			kms_snapshot(colors[i].snapshot);
			printf("DRMSOLID color=%s value=%#x hold_seconds=8\n", colors[i].name, colors[i].value);
			char event[128];
			snprintf(event, sizeof(event), "<6>RMX2072-SOLID-PATTERN color=%s hold_seconds=8\n", colors[i].name);
			phase_marker(event);
			sleep(8);
		}
		/* Buffer 1 is currently on the plane (hardware blue). Fill only the
		 * inactive buffer 0 with the same RGB red as the first hardware fill.
		 * Buffer 1 retains the original row pattern for the final comparison.
		 */
		for (uint32_t y = 0; y < mode.vdisplay; y++) {
			uint32_t *line = (uint32_t *)((char *)buffers[0].map + y * buffers[0].dumb.pitch);
			for (uint32_t x = 0; x < mode.hdisplay; x++) line[x] = 0x00ff0000;
		}
		if (set_fill(0) || solid_flip(fd, crtc, buffers[0].fb, 0x63fe,
					    &last_sequence, &last_event_us)) {
			puts("DRMSOLID failure=memory-red"); goto out;
		}
		kms_snapshot("kms-memory-red");
		printf("DRMSOLID memory_color=red format=XRGB8888 value=0x00ff0000 fb=%u pitch=%u size=%llu hold_seconds=8\n",
		       buffers[0].fb, buffers[0].dumb.pitch, (unsigned long long)buffers[0].dumb.size);
		phase_marker("<6>RMX2072-MEMORY-PATTERN color=red hold_seconds=8\n");
		sleep(8);
		if (solid_flip(fd, crtc, buffers[1].fb, 0x63ff,
					    &last_sequence, &last_event_us)) {
			puts("DRMSOLID failure=restore-pattern"); goto out;
		}
		puts("DRMSOLID restored=framebuffer parameter=0");
	}
	kms_snapshot(NULL);
	unsigned int hold = solid_test ? 10 : 30;
	printf("DRMPATTERN version=m3-row-grid-v2 input=RGB888 output=XRGB8888 hold_seconds=%u\n", hold);
	char event[96];
	snprintf(event, sizeof(event), "<6>RMX2072-NATIVE-PATTERN hold_seconds=%u\n", hold);
	phase_marker(event);
	sleep(hold);
	puts("DRMTEST kms_events=PASS physical_observation=REQUIRED"); result = 0;
out:
	if (solid_test) {
		if (set_fill(0)) { puts("DRMSOLID cleanup=FAILED"); result = 1; }
		else puts("DRMSOLID cleanup=ok parameter=0");
	}
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
