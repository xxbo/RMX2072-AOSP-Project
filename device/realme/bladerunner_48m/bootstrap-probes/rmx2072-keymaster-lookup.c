// SPDX-License-Identifier: GPL-2.0-only
/* Query the two application names present in the F.20 Keymaster client. */
#include <linux/firmware/qcom/qcom_scm.h>
#include <linux/moduleparam.h>
#include <linux/of.h>
#include <linux/sysfs.h>

static int rmx2072_keymaster_apps(char *buf, const struct kernel_param *param)
{
	u32 board, id;
	int km, km64;

	if (!of_machine_is_compatible("qcom,kona-mtp") ||
	    of_property_read_u32(of_root, "oplus,dtsi_no", &board) ||
	    board != 20607)
		return -ENODEV;
	if (!qcom_scm_is_available())
		return -EAGAIN;

	km = qcom_scm_qseecom_app_get_id("keymaster", &id);
	km64 = qcom_scm_qseecom_app_get_id("keymaster64", &id);
	return sysfs_emit(buf, "keymaster=%d keymaster64=%d\n", km, km64);
}

static const struct kernel_param_ops rmx2072_keymaster_ops = {
	.get = rmx2072_keymaster_apps,
};
module_param_cb(apps, &rmx2072_keymaster_ops, NULL, 0400);
