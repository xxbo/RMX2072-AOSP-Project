/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef RMX2072_KEYMASTER_TRANSPORT_H
#define RMX2072_KEYMASTER_TRANSPORT_H

#include <linux/types.h>

/* Board-private, fixed GET_VERSION / GET_HMAC_SHARING_PARAMETERS only. */
int rmx2072_keymaster_query(u32 app_id, u32 method, void *reply, size_t bytes);

#endif
