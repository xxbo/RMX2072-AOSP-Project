/* SPDX-License-Identifier: GPL-2.0-only */
/* F.20 reference only. Build with the pinned downstream uapi/linux/qseecom.h. */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "qseecom.h"

int main(void)
{
    const char *const names[] = {"keymaster", "keymaster64"};
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        struct qseecom_qseos_app_load_query q = {0};
        int fd = open("/dev/qseecom", O_RDWR | O_CLOEXEC);
        if (fd < 0) {
            perror("open qseecom");
            return 1;
        }
        strcpy(q.app_name, names[i]);
        int rc = ioctl(fd, QSEECOM_IOCTL_APP_LOADED_QUERY_REQ, &q);
        int err = rc < 0 ? errno : 0;
        close(fd);
        if (rc == -1 && err == EEXIST && q.app_id)
            printf("%s=loaded\n", names[i]);
        else if (rc == 0 && !q.app_id)
            printf("%s=absent\n", names[i]);
        else {
            fprintf(stderr, "%s query rc=%d errno=%d\n", names[i], rc, err);
            return 1;
        }
    }
    return 0;
}
