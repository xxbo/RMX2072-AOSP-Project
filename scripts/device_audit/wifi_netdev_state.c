// SPDX-License-Identifier: Apache-2.0
// Read-only socket ioctls; do not change addresses, flags, channels or firmware.
#include <errno.h>
#include <android/log.h>
#include <net/if.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

static void report(const char *format, ...) __attribute__((format(printf, 1, 2)));
static void report(const char *format, ...) {
    char text[256];
    va_list args;
    va_start(args, format);
    vsnprintf(text, sizeof(text), format, args);
    va_end(args);
    fputs(text, stdout);
    __android_log_write(ANDROID_LOG_INFO, "RmxWifiState", text);
}

static struct ifreq request(void) {
    struct ifreq value = {0};
    snprintf(value.ifr_name, sizeof(value.ifr_name), "wlan0");
    return value;
}

int main(void) {
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        report("socket_errno=%d\n", errno);
        return 1;
    }
    struct ifreq value = request();
    if (ioctl(fd, SIOCGIFINDEX, &value) == 0)
        report("ifindex=%d\n", value.ifr_ifindex);
    else
        report("ifindex_errno=%d\n", errno);
    value = request();
    if (ioctl(fd, SIOCGIFFLAGS, &value) == 0)
        report("flags=0x%x up=%d\n", (unsigned short)value.ifr_flags,
               !!(value.ifr_flags & IFF_UP));
    else
        report("flags_errno=%d\n", errno);
    value = request();
    if (ioctl(fd, SIOCGIFHWADDR, &value) == 0) {
        const unsigned char *mac = (const unsigned char *)value.ifr_hwaddr.sa_data;
        unsigned any = 0;
        for (unsigned i = 0; i < 6; ++i) any |= mac[i];
        // Keep identifiers out of ordinary/public logs.
        report("hw_family=%u all_zero=%d multicast=%d locally_administered=%d\n",
               value.ifr_hwaddr.sa_family, any == 0, !!(mac[0] & 1), !!(mac[0] & 2));
    } else {
        report("hwaddr_errno=%d\n", errno);
    }
    close(fd);
    return 0;
}
