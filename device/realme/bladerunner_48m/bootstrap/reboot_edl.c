// SPDX-License-Identifier: GPL-2.0-only
// RAM-only diagnostic helper. Reboot requires an explicit "edl" argument.
#include <linux/reboot.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--check")) {
        puts("RMX2072 reboot-edl helper ready");
        return 0;
    }
    if (argc != 2 || strcmp(argv[1], "edl")) {
        fputs("Usage: reboot-edl --check | edl\n", stderr);
        return 2;
    }
    syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
            LINUX_REBOOT_CMD_RESTART2, "edl");
    perror("reboot(RESTART2, edl)");
    return 1;
}
