// SPDX-License-Identifier: GPL-2.0-only
/* Query the two application names present in the F.20 Keymaster client. */
#include <linux/firmware/qcom/qcom_scm.h>
#include <linux/firmware/qcom/qcom_tzmem.h>
#include <linux/moduleparam.h>
#include <linux/kobject.h>
#include <linux/of.h>
#include <linux/sysfs.h>
#include "qcom_scm.h"

static bool rmx2072_keymaster_board(void)
{
	u32 board;

	return of_machine_is_compatible("qcom,kona-mtp") &&
	       !of_property_read_u32(of_root, "oplus,dtsi_no", &board) &&
	       board == 20607;
}

static int rmx2072_keymaster_apps(char *buf, const struct kernel_param *param)
{
	u32 id;
	int km, km64;

	if (!rmx2072_keymaster_board())
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

/* Wire layout from the Qualcomm PFK GET_VERSION client in security/pfe/pfk_ice.h. */
struct km_version_response {
	__le32 status, api_major, api_minor, ta_major, ta_minor;
};

static int rmx2072_keymaster_version(char *buf, const struct kernel_param *param)
{
	struct qcom_tzmem_pool *pool;
	struct km_version_response *rsp __free(qcom_tzmem) = NULL;
	__le32 *req __free(qcom_tzmem) = NULL;
	u32 id;
	int ret;

	if (!rmx2072_keymaster_board())
		return -ENODEV;
	pool = qcom_scm_get_tzmem_pool();
	if (!pool)
		return -EAGAIN;
	ret = qcom_scm_qseecom_app_get_id("keymaster64", &id);
	if (ret)
		return sysfs_emit(buf, "lookup_rc=%d\n", ret);
	req = qcom_tzmem_alloc(pool, sizeof(*req), GFP_KERNEL);
	rsp = qcom_tzmem_alloc(pool, sizeof(*rsp), GFP_KERNEL);
	if (!req || !rsp)
		return -ENOMEM;
	*req = cpu_to_le32(0x200); /* KEYMASTER_GET_VERSION */
	memset(rsp, 0xff, sizeof(*rsp));
	ret = qcom_scm_qseecom_app_send(id, req, sizeof(*req), rsp, sizeof(*rsp));
	if (ret)
		return sysfs_emit(buf, "transport_rc=%d\n", ret);
	if (rsp->status || !rsp->ta_major || rsp->ta_major == cpu_to_le32(U32_MAX))
		return sysfs_emit(buf, "transport_rc=0 invalid_reply status=%d\n",
				  (s32)le32_to_cpu(rsp->status));
	return sysfs_emit(buf, "transport_rc=0 status=0 api=%u.%u ta=%u.%u\n",
			  le32_to_cpu(rsp->api_major), le32_to_cpu(rsp->api_minor),
			  le32_to_cpu(rsp->ta_major), le32_to_cpu(rsp->ta_minor));
}

static const struct kernel_param_ops rmx2072_version_ops = {
	.get = rmx2072_keymaster_version,
};
module_param_cb(version_info, &rmx2072_version_ops, NULL, 0400);

/* F.20 Keymaster 4.0/default uses its legacy get-sharing-parameters ABI.
 * Only the fixed HIDL result crosses this read-only board interface.
 */
struct rmx2072_hmac_reply {
	__le32 status;
	u8 seed[32];
	u8 nonce[32];
};

static ssize_t rmx2072_hmac_read(struct file *file, struct kobject *kobj,
				 const struct bin_attribute *attr, char *buf,
				 loff_t off, size_t count)
{
	const size_t rsp_bytes = 40956; /* Capacity passed by the F.20 client. */
	struct rmx2072_hmac_reply *rsp __free(qcom_tzmem) = NULL;
	__le32 *req __free(qcom_tzmem) = NULL;
	struct qcom_tzmem_pool *pool;
	u32 id;
	int ret;

	if (off || count != sizeof(*rsp))
		return -EINVAL;
	pool = qcom_scm_get_tzmem_pool();
	if (!pool)
		return -EAGAIN;
	ret = qcom_scm_qseecom_app_get_id("keymaster64", &id);
	if (ret)
		return ret;
	req = qcom_tzmem_alloc(pool, sizeof(*req), GFP_KERNEL);
	rsp = qcom_tzmem_alloc(pool, rsp_bytes, GFP_KERNEL);
	if (!req || !rsp)
		return -ENOMEM;
	*req = cpu_to_le32(0x20e);
	memset(rsp, 0, rsp_bytes);
	rsp->status = cpu_to_le32((u32)-1000);
	ret = qcom_scm_qseecom_app_send(id, req, sizeof(*req), rsp, rsp_bytes);
	if (!ret) {
		memset(buf, 0, sizeof(*rsp));
		memcpy(buf, rsp, rsp->status ? sizeof(rsp->status) : sizeof(*rsp));
	}
	memzero_explicit(rsp, rsp_bytes);
	return ret ? ret : sizeof(*rsp);
}

static const struct bin_attribute rmx2072_hmac_attr = {
	.attr = { .name = "rmx2072_hmac_parameters", .mode = 0400 },
	.size = sizeof(struct rmx2072_hmac_reply),
	.read = rmx2072_hmac_read,
};

static int __init rmx2072_hmac_init(void)
{
	if (!rmx2072_keymaster_board())
		return 0;
	return sysfs_create_bin_file(firmware_kobj, &rmx2072_hmac_attr);
}
late_initcall(rmx2072_hmac_init);
