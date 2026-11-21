// SPDX-License-Identifier: GPL-2.0-only
/* RMX2072 panel integration. Commands and power timings from the pinned
 * realme Android Q 20607 board sources; see rm19795-commands.h.
 * The filename in that tree says 2340; the actual selected mode is 2400.
 */
#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/regulator/consumer.h>
#include <linux/string.h>
#include <drm/display/drm_dsc.h>
#include <drm/display/drm_dsc_helper.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>
#include <drm/drm_probe_helper.h>
#include <video/mipi_display.h>

/* One bounded diagnostic before the first native frame; disabled by default. */
static bool readback;
module_param(readback, bool, 0400);
MODULE_PARM_DESC(readback, "RM19795 one-shot power and PPS readback diagnostic");

/* F.20 logs a standard PPS after its complete vendor on-sequence. Keep the
 * encoder and existing 0x9e payload unchanged to isolate that missing packet.
 */
static bool pps;
module_param(pps, bool, 0400);
MODULE_PARM_DESC(pps, "RM19795 standard PPS after vendor on-sequence isolation test");

struct rm19795_cmd {
	u8 type;
	u8 wait_ms;
	u8 len;
	u8 data[128];
};
#include "rm19795-commands.h"

struct rm19795 {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct drm_dsc_config dsc;
	struct gpio_desc *reset;
	struct regulator_bulk_data supplies[3];
	bool prepared;
	bool readback_done;
};

static void rm19795_log_bytes(struct rm19795 *ctx, const char *kind,
			     const u8 *data, size_t count)
{
	size_t offset;

	/* Kernel %ph is capped at 64 bytes. Keep every 88-byte PPS byte visible. */
	for (offset = 0; offset < count; offset += 32)
		dev_info(&ctx->dsi->dev, "RMXPPS %s offset=%zu bytes=%*phN\n",
			 kind, offset, (int)min_t(size_t, 32, count - offset), data + offset);
}

static int rm19795_send(struct rm19795 *ctx, const struct rm19795_cmd *cmd,
		       size_t count, bool lp)
{
	size_t i;

	for (i = 0; i < count; i++) {
		struct drm_dsc_picture_parameter_set pps;
		u8 pps_cmd[89];
		struct mipi_dsi_msg msg = {
			.channel = ctx->dsi->channel,
			.type = cmd[i].type,
			.flags = lp ? MIPI_DSI_MSG_USE_LPM : 0,
			.tx_len = cmd[i].len,
			.tx_buf = cmd[i].data,
		};
		ssize_t ret;

		/* The OEM 0x9e packet contains downstream DSC rate-control values.
		 * MSM 6.18 calculates different encoder values before panel prepare
		 * (prepare_prev_first). Send those same values to the decoder, using
		 * the panel's original vendor command and 88-byte DSC 1.1 payload.
		 * Keep the imported OEM table intact as the comparison reference.
		 */
		if (cmd[i].data[0] == 0x9e) {
			if (cmd[i].type != 0x39 || cmd[i].len != sizeof(pps_cmd) ||
			    ctx->dsc.dsc_version_major != 1 || ctx->dsc.dsc_version_minor != 1 ||
			    ctx->dsc.pic_width != 1080 || ctx->dsc.pic_height != 2400 ||
			    !ctx->dsc.rc_model_size || !ctx->dsc.slice_chunk_size)
				return dev_err_probe(&ctx->dsi->dev, -EINVAL,
						     "encoder DSC config not ready for panel PPS\n");
			drm_dsc_pps_payload_pack(&pps, &ctx->dsc);
			pps_cmd[0] = 0x9e;
			memcpy(pps_cmd + 1, &pps, sizeof(pps_cmd) - 1);
			msg.tx_buf = pps_cmd;
		}

		/* Preserve the OEM's long-write packets even for two-byte payloads. */
		ret = ctx->dsi->host->ops->transfer(ctx->dsi->host, &msg);
		if (ret < 0) {
			dev_err(&ctx->dsi->dev, "packet %zu DCS=%02x failed: %zd\n",
				i, cmd[i].data[0], ret);
			return ret;
		}
		/* MSM returns its padded DMA packet length, including the header. */
		if (ret < cmd[i].len)
			return -EIO;
		if (cmd[i].data[0] == 0x9e) {
			dev_info(&ctx->dsi->dev, "RMXPPS host-transfer ret=%zd payload=88\n", ret);
			rm19795_log_bytes(ctx, "tx", pps_cmd + 1, sizeof(pps_cmd) - 1);
		}
		if (cmd[i].wait_ms)
			msleep(cmd[i].wait_ms);
	}
	return 0;
}

static ssize_t rm19795_read(struct rm19795 *ctx, u8 command, u8 *data, size_t count)
{
	struct mipi_dsi_msg msg = {
		.channel = ctx->dsi->channel,
		.type = MIPI_DSI_DCS_READ,
		.flags = MIPI_DSI_MSG_USE_LPM,
		.tx_len = 1, .tx_buf = &command,
		.rx_len = count, .rx_buf = data,
	};
	ssize_t ret;

	memset(data, 0, count);
	ret = ctx->dsi->host->ops->transfer(ctx->dsi->host, &msg);
	dev_info(&ctx->dsi->dev, "RMXPANEL read command=%02x requested=%zu ret=%zd\n",
		 command, count, ret);
	if (ret > 0 && ret <= count)
		rm19795_log_bytes(ctx, command == 0x0a ? "power" : "rx", data, ret);
	return ret;
}

static void rm19795_readback_once(struct rm19795 *ctx)
{
	struct drm_dsc_picture_parameter_set pps;
	u8 data[88];
	ssize_t ret;
	int lock_ret;

	if (!readback || ctx->readback_done)
		return;
	ctx->readback_done = true;
	/* OEM ESD check documents LP GET_POWER_MODE and expected byte 0x9c. */
	ret = rm19795_read(ctx, 0x0a, data, 1);
	if (ret != 1 || data[0] != 0x9c) {
		dev_info(&ctx->dsi->dev, "RMXPANEL PPS-read skipped: power-mode unconfirmed\n");
		return;
	}
	/* Reuse only the panel's original 9f key pair. 9e is its documented PPS
	 * write address; whether this DDIC supports reading it is not established.
	 * A short/zero/unsupported response is not decoder PPS evidence.
	 */
	ret = rm19795_send(ctx, &rm19795_cmd_enable[0], 1, false);
	if (!ret) {
		ret = rm19795_read(ctx, 0x9e, data, 16);
		if (ret == 16 && data[0] == 0x11 && (data[3] >> 4) == 8) {
			ret = rm19795_read(ctx, 0x9e, data, sizeof(data));
			if (ret == sizeof(data)) {
				drm_dsc_pps_payload_pack(&pps, &ctx->dsc);
				dev_info(&ctx->dsi->dev, "RMXPANEL PPS-shaped-response match_tx=%d scope=unverified-register-semantics\n",
					 !memcmp(data, &pps, sizeof(data)));
			}
		} else {
			dev_info(&ctx->dsi->dev, "RMXPANEL PPS-read unsupported-or-unrecognized\n");
		}
	}
	/* Relock even when the read or unlock failed. Do not change the PPS. */
	lock_ret = rm19795_send(ctx, &rm19795_cmd_enable[ARRAY_SIZE(rm19795_cmd_enable) - 1], 1, false);
	dev_info(&ctx->dsi->dev, "RMXPANEL readback-end relock_ret=%d\n", lock_ret);
}

static int rm19795_standard_pps(struct rm19795 *ctx)
{
	struct drm_dsc_picture_parameter_set payload;
	struct mipi_dsi_msg msg = {
		.channel = ctx->dsi->channel,
		.type = MIPI_DSI_PICTURE_PARAMETER_SET,
		.flags = MIPI_DSI_MSG_USE_LPM,
		.tx_len = sizeof(payload),
		.tx_buf = &payload,
	};
	ssize_t ret;

	drm_dsc_pps_payload_pack(&payload, &ctx->dsc);
	ret = ctx->dsi->host->ops->transfer(ctx->dsi->host, &msg);
	dev_info(&ctx->dsi->dev, "RMXPPS standard-transfer ret=%zd payload=%zu\n",
		 ret, sizeof(payload));
	if (ret < 0)
		return ret;
	/* MSM returns the padded DMA packet length, not just the payload size. */
	if (ret < sizeof(payload))
		return -EIO;
	rm19795_log_bytes(ctx, "standard-tx", (const u8 *)&payload, sizeof(payload));
	return 0;
}

static int rm19795_prepare(struct drm_panel *panel)
{
	struct rm19795 *ctx = container_of(panel, struct rm19795, panel);
	int i, ret;

	if (ctx->prepared)
		return 0;

	for (i = 0; i < ARRAY_SIZE(ctx->supplies); i++) {
		ret = regulator_enable(ctx->supplies[i].consumer);
		if (ret)
			goto disable;
		if (i != 1)
			usleep_range(5000, 6000);
	}
	/* Active-low reset: physical high 20 ms, low 10 ms, high 5 ms. */
	gpiod_set_value_cansleep(ctx->reset, 0);
	msleep(20);
	gpiod_set_value_cansleep(ctx->reset, 1);
	msleep(10);
	gpiod_set_value_cansleep(ctx->reset, 0);
	usleep_range(5000, 6000);
	ret = rm19795_send(ctx, rm19795_cmd_on, ARRAY_SIZE(rm19795_cmd_on), true);
	if (ret)
		goto disable;
	if (pps) {
		ret = rm19795_standard_pps(ctx);
		if (ret)
			goto disable;
	}
	ctx->prepared = true;
	dev_info(&ctx->dsi->dev, "RM19795 prepared 1080x2400@60 DSC 540x48\n");
	return 0;
disable:
	gpiod_set_value_cansleep(ctx->reset, 1);
	while (--i >= 0)
		regulator_disable(ctx->supplies[i].consumer);
	return ret;
}

static int rm19795_enable(struct drm_panel *panel)
{
	struct rm19795 *ctx = container_of(panel, struct rm19795, panel);
	int ret;

	if (!ctx->prepared)
		return -EPERM;
	ret = rm19795_send(ctx, rm19795_cmd_enable, ARRAY_SIZE(rm19795_cmd_enable), false);

	if (!ret) {
		dev_info(&ctx->dsi->dev, "RM19795 display-on commands accepted\n");
		rm19795_readback_once(ctx);
	}
	return ret;
}

static int rm19795_unprepare(struct drm_panel *panel)
{
	struct rm19795 *ctx = container_of(panel, struct rm19795, panel);
	int ret;

	if (!ctx->prepared)
		return 0;

	ret = rm19795_send(ctx, rm19795_cmd_off, ARRAY_SIZE(rm19795_cmd_off), false);
	ctx->prepared = false;
	gpiod_set_value_cansleep(ctx->reset, 1);
	regulator_bulk_disable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
	return ret;
}

static const struct drm_display_mode rm19795_mode = {
	.clock = (1080 + 48 + 24 + 48) * (2400 + 16 + 4 + 20) * 60 / 1000,
	.hdisplay = 1080, .hsync_start = 1080 + 48,
	.hsync_end = 1080 + 48 + 24, .htotal = 1080 + 48 + 24 + 48,
	.vdisplay = 2400, .vsync_start = 2400 + 16,
	.vsync_end = 2400 + 16 + 4, .vtotal = 2400 + 16 + 4 + 20,
	.width_mm = 67, .height_mm = 149,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int rm19795_get_modes(struct drm_panel *panel, struct drm_connector *connector)
{
	return drm_connector_helper_get_modes_fixed(connector, &rm19795_mode);
}

static const struct drm_panel_funcs rm19795_funcs = {
	.prepare = rm19795_prepare, .enable = rm19795_enable,
	.unprepare = rm19795_unprepare, .get_modes = rm19795_get_modes,
};

static int rm19795_backlight_update(struct backlight_device *bl)
{
	struct rm19795 *ctx = bl_get_data(bl);

	if (!ctx->prepared)
		return 0;
	return mipi_dsi_dcs_set_display_brightness_large(ctx->dsi, backlight_get_brightness(bl));
}

static const struct backlight_ops rm19795_backlight_ops = {
	.update_status = rm19795_backlight_update,
};

static int rm19795_probe(struct mipi_dsi_device *dsi)
{
	const struct backlight_properties props = {
		.type = BACKLIGHT_RAW, .brightness = 400, .max_brightness = 1023,
	};
	struct rm19795 *ctx;
	int ret;

	ctx = devm_drm_panel_alloc(&dsi->dev, struct rm19795, panel, &rm19795_funcs,
				   DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);
	ctx->dsi = dsi;
	ctx->supplies[0].supply = "vddio";
	ctx->supplies[1].supply = "vout";
	ctx->supplies[2].supply = "vdd";
	ret = devm_regulator_bulk_get(&dsi->dev, ARRAY_SIZE(ctx->supplies), ctx->supplies);
	if (ret)
		return dev_err_probe(&dsi->dev, ret, "panel supplies unavailable\n");
	ctx->reset = devm_gpiod_get(&dsi->dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset))
		return dev_err_probe(&dsi->dev, PTR_ERR(ctx->reset), "panel reset unavailable\n");
	mipi_dsi_set_drvdata(dsi, ctx);
	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	/* Command mode; on commands explicitly use LP, off/brightness use HS. */
	/* OEM qcom,mdss-dsc-slice-per-pkt = <2>: both 540-pixel slices. */
	dsi->mode_flags = MIPI_DSI_CLOCK_NON_CONTINUOUS |
			  MIPI_DSI_MODE_DSC_ALL_SLICES_IN_PKT;
	dsi->dsc = &ctx->dsc;
	ctx->dsc.dsc_version_major = 1;
	ctx->dsc.dsc_version_minor = 1;
	ctx->dsc.slice_width = 540;
	ctx->dsc.slice_height = 48;
	ctx->dsc.slice_count = 2;
	ctx->dsc.bits_per_component = 8;
	ctx->dsc.bits_per_pixel = 8 << 4;
	ctx->dsc.block_pred_enable = true;
	ctx->panel.prepare_prev_first = true;
	ctx->panel.backlight = devm_backlight_device_register(&dsi->dev, "rm19795",
				&dsi->dev, ctx, &rm19795_backlight_ops, &props);
	if (IS_ERR(ctx->panel.backlight))
		return PTR_ERR(ctx->panel.backlight);
	drm_panel_add(&ctx->panel);
	ret = devm_mipi_dsi_attach(&dsi->dev, dsi);
	if (ret) {
		drm_panel_remove(&ctx->panel);
		return dev_err_probe(&dsi->dev, ret, "DSI attach failed\n");
	}
	dev_info(&dsi->dev, "RMX2072 RM19795 source panel attached\n");
	return 0;
}

static void rm19795_remove(struct mipi_dsi_device *dsi)
{
	struct rm19795 *ctx = mipi_dsi_get_drvdata(dsi);
	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id rm19795_of_match[] = {
	{ .compatible = "realme,rmx2072-rm19795-panel" }, {}
};
MODULE_DEVICE_TABLE(of, rm19795_of_match);
static struct mipi_dsi_driver rm19795_driver = {
	.probe = rm19795_probe, .remove = rm19795_remove,
	.driver = { .name = "panel-samsung-rm19795", .of_match_table = rm19795_of_match },
};
module_mipi_dsi_driver(rm19795_driver);
MODULE_DESCRIPTION("RMX2072 RM19795 Samsung command-mode DSC panel");
MODULE_LICENSE("GPL");
