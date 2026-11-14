/* SPDX-License-Identifier: GPL-2.0-only */
/* Board-only lifetime test for the two listeners seen during F.20 key generation.
 * Included alongside the QSEECOM lock so registration and teardown are serialized
 * with the existing SCM callers. No secure memory is exposed to userspace.
 */
static int rmx2072_probe_listener(u32 id, char *buf)
{
	static struct {
		bool pinned;
	} quarantine[2];
	const size_t size = SZ_16K + SZ_4K;
	struct qcom_scm_desc reg = {
		.owner = QSEECOM_TZ_OWNER_QSEE_OS, .svc = 2, .cmd = 6,
		.arginfo = QCOM_SCM_ARGS(3, QCOM_SCM_VAL, QCOM_SCM_RW, QCOM_SCM_VAL),
	};
	struct qcom_scm_desc unreg = {
		.owner = QSEECOM_TZ_OWNER_QSEE_OS, .svc = 2, .cmd = 2,
		.arginfo = QCOM_SCM_ARGS(1, QCOM_SCM_VAL),
	};
	struct qcom_scm_qseecom_resp resp = {};
	unsigned int slot = id == 11 ? 0 : 1;
	u64 reg_result, unreg_result = U64_MAX;
	int reg_rc, unreg_rc = -ENODATA;
	void *shared;

	lockdep_assert_held(&qcom_scm_qseecom_call_lock);
	if (quarantine[slot].pinned)
		return sysfs_emit(buf, "id=%u previous_teardown_uncertain\n", id);
	shared = qcom_tzmem_alloc(__scm->mempool, size, GFP_KERNEL);
	if (!shared)
		return -ENOMEM;
	memset(shared, 0, size);
	reg.args[0] = id;
	reg.args[1] = qcom_tzmem_to_phys(shared);
	reg.args[2] = size;
	reg_rc = __qcom_scm_qseecom_call(&reg, &resp);
	if (reg_rc == -EIO) {
		reg.cmd = 1; /* Downstream fallback for firmware without smcinvoke. */
		reg_rc = __qcom_scm_qseecom_call(&reg, &resp);
	}
	reg_result = resp.result;
	if (!reg_rc && reg_result == QSEECOM_RESULT_SUCCESS) {
		unreg.args[0] = id;
		unreg_rc = __qcom_scm_qseecom_call(&unreg, &resp);
		unreg_result = resp.result;
	}
	/* Keep the allocation for the rest of this boot if ownership is uncertain. */
	if ((!reg_rc && reg_result == QSEECOM_RESULT_FAILURE) ||
	    (!unreg_rc && unreg_result == QSEECOM_RESULT_SUCCESS))
		qcom_tzmem_free(shared);
	else
		quarantine[slot].pinned = true;
	return sysfs_emit(buf, "id=%u register_rc=%d register_result=%llu unregister_rc=%d unregister_result=%llu\n",
			  id, reg_rc, reg_result, unreg_rc, unreg_result);
}

static int rmx2072_listener_lifetime(char *buf, const struct kernel_param *kp)
{
	u32 board;
	int len;

	if (!of_machine_is_compatible("qcom,kona-mtp") ||
	    of_property_read_u32(of_root, "oplus,dtsi_no", &board) || board != 20607 ||
	    !qcom_scm_is_available())
		return -ENODEV;
	mutex_lock(&qcom_scm_qseecom_call_lock);
	len = rmx2072_probe_listener(*(const u32 *)kp->arg, buf);
	mutex_unlock(&qcom_scm_qseecom_call_lock);
	return len;
}

static const struct kernel_param_ops rmx2072_listener_ops = {
	.get = rmx2072_listener_lifetime,
};
static u32 rmx2072_time_id = 11;
static u32 rmx2072_cancel_id = 4352;
module_param_cb(listener_time_lifetime, &rmx2072_listener_ops, &rmx2072_time_id, 0400);
module_param_cb(listener_cancel_lifetime, &rmx2072_listener_ops, &rmx2072_cancel_id, 0400);
