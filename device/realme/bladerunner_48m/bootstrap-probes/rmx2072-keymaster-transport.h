/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef RMX2072_KEYMASTER_TRANSPORT_H
#define RMX2072_KEYMASTER_TRANSPORT_H

#include <linux/types.h>

#include <linux/ioctl.h>

/* Private ABI: bytes only, no caller-supplied app IDs, physical addresses or
 * listener responses. Response occupies the rest of the 40 KiB TA buffer. */
#define RMX2072_KM_CAPACITY 40960U
#define RMX2072_KM_MAX_REQUEST 16384U
struct rmx2072_km_xfer {
	__u32 version;
	__u32 flags;
	__u32 request_size;
	__u32 response_size;
	__aligned_u64 request;
	__aligned_u64 response;
};
#define RMX2072_KM_CALL _IOW('R', 0x4b, struct rmx2072_km_xfer)

#ifdef __KERNEL__
int rmx2072_keymaster_query(u32 app_id, u32 method, void *reply, size_t bytes);
int rmx2072_keymaster_transact(const void *request, size_t bytes, void *reply);
#endif

#endif
