/* SPDX-License-Identifier: GPL-2.0-only */
/* Board-only lifetime test for the two listeners seen during F.20 key generation.
 * Included alongside the QSEECOM lock so registration and teardown are serialized
 * with the existing SCM callers. No secure memory is exposed to userspace.
 */
static int rmx2072_listener_change(u32 id, void *shared, struct qcom_scm_qseecom_resp *resp)
{
	struct qcom_scm_desc desc = {
		.owner = QSEECOM_TZ_OWNER_QSEE_OS, .svc = 2, .cmd = 2, .args = { id },
		.arginfo = QCOM_SCM_ARGS(1, QCOM_SCM_VAL),
	};
	int rc;

	if (!shared)
		return __qcom_scm_qseecom_call(&desc, resp);
	desc.cmd = 6;
	desc.arginfo = QCOM_SCM_ARGS(3, QCOM_SCM_VAL, QCOM_SCM_RW, QCOM_SCM_VAL);
	desc.args[1] = qcom_tzmem_to_phys(shared);
	desc.args[2] = SZ_16K + SZ_4K;
	rc = __qcom_scm_qseecom_call(&desc, resp);
	if (rc == -EIO) {
		desc.cmd = 1;
		rc = __qcom_scm_qseecom_call(&desc, resp);
	}
	return rc;
}

static int rmx2072_probe_listener(u32 id, char *buf)
{
	static bool pinned[2];
	const size_t size = SZ_16K + SZ_4K;
	struct qcom_scm_qseecom_resp resp = {};
	unsigned int slot = id == 11 ? 0 : 1;
	u64 reg_result, unreg_result = U64_MAX;
	int reg_rc, unreg_rc = -ENODATA;
	void *shared;

	lockdep_assert_held(&qcom_scm_qseecom_call_lock);
	if (pinned[slot])
		return sysfs_emit(buf, "id=%u previous_teardown_uncertain\n", id);
	shared = qcom_tzmem_alloc(__scm->mempool, size, GFP_KERNEL);
	if (!shared)
		return -ENOMEM;
	memset(shared, 0, size);
	reg_rc = rmx2072_listener_change(id, shared, &resp);
	reg_result = resp.result;
	if (!reg_rc && reg_result == QSEECOM_RESULT_SUCCESS) {
		unreg_rc = rmx2072_listener_change(id, NULL, &resp);
		unreg_result = resp.result;
	}
	/* Keep the allocation for the rest of this boot if ownership is uncertain. */
	if ((!reg_rc && reg_result == QSEECOM_RESULT_FAILURE) ||
	    (!unreg_rc && unreg_result == QSEECOM_RESULT_SUCCESS))
		qcom_tzmem_free(shared);
	else
		pinned[slot] = true;
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

/* One engineering-boot control: create a disposable HMAC-SHA256 signing
 * key and delete the exact wrapped blob returned by this call. No client
 * supplies a command, key parameter, listener reply or blob.
 */
struct rmx2072_key_test {
	void *request, *reply, *listener, *sglist;
	u32 app_id, callbacks, last_listener, time_command;
	u64 first_result, final_result;
};

static int rmx2072_resume_time(struct rmx2072_key_test *test,
			       struct qcom_scm_qseecom_resp *resp)
{
	struct qcom_scm_desc desc = {
		.owner = QSEECOM_TZ_OWNER_QSEE_OS, .svc = 2, .cmd = 5,
		.arginfo = QCOM_SCM_ARGS(4, QCOM_SCM_VAL, QCOM_SCM_VAL, QCOM_SCM_RW, QCOM_SCM_VAL),
		.args = { 11, QSEECOM_RESULT_FAILURE, qcom_tzmem_to_phys(test->sglist), 32 },
	};
	/* Qualcomm time_msg.h: command, UTC seconds, nanoseconds, signed status. */
	__le32 *message = test->listener;
	struct timespec64 now;

	test->time_command = le32_to_cpu(message[0]);
	pr_info("rmx2072-temp-key: callback id=11 command=%u\n", test->time_command);
	ktime_get_real_ts64(&now);
	if (test->time_command == 770 && now.tv_sec >= 1577836800 && now.tv_sec <= U32_MAX) {
		message[1] = cpu_to_le32(now.tv_sec);
		message[2] = cpu_to_le32(now.tv_nsec);
		message[3] = 0;
		desc.args[1] = QSEECOM_RESULT_SUCCESS;
	}
	pr_info("rmx2072-temp-key: resuming callback status=%llu\n", desc.args[1]);
	return __qcom_scm_qseecom_call(&desc, resp);
}

static int rmx2072_key_call(struct rmx2072_key_test *test, size_t len, bool *terminal)
{
	/* F.20 places the response immediately after the serialized request in
	 * the same 40 KiB client buffer. Keep both addresses in one allocation. */
	void *reply = (u8 *)test->request + len;
	struct qcom_scm_desc desc = {
		.owner = QSEECOM_TZ_OWNER_TZ_APPS, .svc = QSEECOM_TZ_SVC_APP_ID_PLACEHOLDER,
		/* F.20 uses TZ_APP_QSAPP_SEND_DATA_WITH_WHITELIST_ID (0x70000006). */
		.cmd = 6,
		.arginfo = QCOM_SCM_ARGS(7, QCOM_SCM_VAL, QCOM_SCM_RW, QCOM_SCM_VAL,
					    QCOM_SCM_RW, QCOM_SCM_VAL, QCOM_SCM_RW, QCOM_SCM_VAL),
		.args = { test->app_id, qcom_tzmem_to_phys(test->request), len,
			  qcom_tzmem_to_phys(test->request) + len, SZ_32K + SZ_8K - len,
			  qcom_tzmem_to_phys(test->sglist), 32 },
	};
	struct qcom_scm_qseecom_resp resp = {};
	int rc;

	lockdep_assert_held(&qcom_scm_qseecom_call_lock);
	test->reply = reply;
	memset(reply, 0, SZ_32K + SZ_8K - len);
	*(__le32 *)reply = cpu_to_le32((u32)-1000);
	*terminal = false;
	pr_info("rmx2072-temp-key: send method=%u bytes=%zu\n",
		le32_to_cpu(*(__le32 *)test->request), len);
	rc = __qcom_scm_qseecom_call(&desc, &resp);
	pr_info("rmx2072-temp-key: send rc=%d result=%llu listener=%llu\n",
		rc, resp.result, resp.data);
	test->first_result = resp.result;
	while (!rc && resp.result == QSEECOM_RESULT_INCOMPLETE) {
		test->last_listener = resp.data;
		if (resp.data != 11 || ++test->callbacks > 8)
			return -EOPNOTSUPP;
		rc = rmx2072_resume_time(test, &resp);
		pr_info("rmx2072-temp-key: resumed rc=%d result=%llu listener=%llu\n",
			rc, resp.result, resp.data);
	}
	test->final_result = resp.result;
	if (rc)
		return rc;
	*terminal = resp.result == QSEECOM_RESULT_SUCCESS || resp.result == QSEECOM_RESULT_FAILURE;
	return resp.result == QSEECOM_RESULT_SUCCESS ? 0 : -EIO;
}

static int rmx2072_temp_key(char *buf, const struct kernel_param *kp)
{
	static bool attempted;
	/* The six scalar HIDL authorizations used by the F.20 reference client:
	 * HMAC, 256-bit, SIGN, SHA-256, 256-bit minimum MAC, no user auth. */
	static const u32 generate[] = {
		0x108, 12, 6, 0x10000002, 128, 0, 0x30000003, 256, 0,
		0x20000001, 2, 0, 0x20000005, 4, 0, 0x30000008, 256, 0, 0x700001f7, 1, 0,
	};
	/* Engineering control for the verified CP3A.260905.010 GSI only.
	 * Its build.prop specifies Android 17 and security patch 2026-09-05.
	 * The project vendor declares the engineering epoch patch date.
	 * F.20 CONFIGURE also serializes the daily VENDOR_PATCHLEVEL tag. */
	static const u32 configure[] = {
		0x116, 12, 3, 0x300002c1, 170000, 0, 0x300002c2, 202609, 0,
		0x300002ce, 19700101, 0,
	};
	const size_t capacity = SZ_32K + SZ_8K;
	struct qcom_scm_qseecom_resp resp = {};
	struct rmx2072_key_test t = {};
	s32 configure_status = -ENODATA, generate_status = -ENODATA, delete_status = -ENODATA;
	u32 board, offset, blob_len = 0, i;
	int rc, teardown = -ENODATA;
	u64 first = U64_MAX, final = U64_MAX;
	bool terminal = true, listener_owned = false;
	__le32 *req, *reply;

	if (!of_machine_is_compatible("qcom,kona-mtp") ||
	    of_property_read_u32(of_root, "oplus,dtsi_no", &board) || board != 20607 ||
	    !qcom_scm_is_available())
		return -ENODEV;
	pr_info("rmx2072-temp-key: lookup\n");
	rc = qcom_scm_qseecom_app_get_id("keymaster64", &t.app_id);
	if (rc)
		return rc;
	mutex_lock(&qcom_scm_qseecom_call_lock);
	if (attempted) {
		mutex_unlock(&qcom_scm_qseecom_call_lock);
		return -EALREADY;
	}
	attempted = true;
	pr_info("rmx2072-temp-key: allocating buffers\n");
	req = t.request = qcom_tzmem_alloc(__scm->mempool, capacity, GFP_KERNEL);
	t.listener = qcom_tzmem_alloc(__scm->mempool, SZ_16K + SZ_4K, GFP_KERNEL);
	t.sglist = qcom_tzmem_alloc(__scm->mempool, 32, GFP_KERNEL);
	rc = -ENOMEM;
	if (!req || !t.listener || !t.sglist)
		goto out;
	memset(t.listener, 0, SZ_16K + SZ_4K);
	memset(t.sglist, 0, 32);
	pr_info("rmx2072-temp-key: registering time listener\n");
	rc = rmx2072_listener_change(11, t.listener, &resp);
	pr_info("rmx2072-temp-key: registered rc=%d result=%llu\n", rc, resp.result);
	listener_owned = rc || resp.result != QSEECOM_RESULT_FAILURE;
	if (rc || resp.result != QSEECOM_RESULT_SUCCESS) {
		rc = rc ?: -EIO;
		goto out;
	}
	for (i = 0; i < ARRAY_SIZE(configure); ++i)
		req[i] = cpu_to_le32(configure[i]);
	rc = rmx2072_key_call(&t, sizeof(configure), &terminal);
	if (rc)
		goto unregister;
	reply = t.reply;
	configure_status = (s32)le32_to_cpu(reply[0]);
	pr_info("rmx2072-temp-key: configure status=%d os_version=170000 os_patchlevel=202609 vendor_patchlevel=19700101\n",
		configure_status);
	if (configure_status)
		goto unregister;
	for (i = 0; i < ARRAY_SIZE(generate); ++i)
		req[i] = cpu_to_le32(generate[i]);
	rc = rmx2072_key_call(&t, sizeof(generate), &terminal);
	first = t.first_result;
	final = t.final_result;
	if (rc)
		goto unregister;
	reply = t.reply;
	generate_status = (s32)le32_to_cpu(reply[0]);
	if (generate_status)
		goto unregister;
	offset = le32_to_cpu(reply[2]);
	blob_len = le32_to_cpu(reply[3]);
	if (offset < 16 || offset > capacity - sizeof(generate) || !blob_len ||
	    blob_len > capacity - sizeof(generate) - offset || blob_len > capacity - 16) {
		rc = -EPROTO;
		goto unregister;
	}
	memmove(req + 3, (u8 *)reply + offset, blob_len);
	req[0] = cpu_to_le32(0x10d);
	req[1] = cpu_to_le32(12);
	req[2] = cpu_to_le32(blob_len);
	rc = rmx2072_key_call(&t, 12 + blob_len, &terminal);
	if (!rc)
		delete_status = (s32)le32_to_cpu(*(__le32 *)t.reply);
unregister:
	if (terminal) {
		pr_info("rmx2072-temp-key: unregistering\n");
		teardown = rmx2072_listener_change(11, NULL, &resp);
		if (!teardown && resp.result != QSEECOM_RESULT_SUCCESS)
			teardown = -EIO;
		listener_owned = teardown != 0;
	}
out:
	/* Indeterminate ownership lasts until reboot. Never reuse a buffer
	 * referenced by a suspended app call or an ambiguous registration. */
	if (!listener_owned && t.listener)
		qcom_tzmem_free(t.listener);
	if (terminal) {
		if (t.sglist)
			qcom_tzmem_free(t.sglist);
		if (req) {
			memzero_explicit(req, capacity);
			qcom_tzmem_free(req);
		}
	}
	mutex_unlock(&qcom_scm_qseecom_call_lock);
	return sysfs_emit(buf, "rc=%d first=%llu listener=%u command=%u callbacks=%u final=%llu generate=%d blob_bytes=%u delete=%d unregister=%d configure=%d\n",
			  rc, first, t.last_listener, t.time_command, t.callbacks, final,
			  generate_status, blob_len, delete_status, teardown, configure_status);
}

static const struct kernel_param_ops rmx2072_temp_key_ops = { .get = rmx2072_temp_key };
module_param_cb(temp_hmac_key, &rmx2072_temp_key_ops, NULL, 0400);
