/* M1 engineering watchdog: local ADB readiness or a bounded host test lease. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdlib.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <fcntl.h>
#include <linux/watchdog.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/system_properties.h>
#include <time.h>
#include <unistd.h>

static int journal = -1;
static char boot_id[40];
static void state(const char *value) {
    __system_property_set("vendor.rmx.m1.state", value);
    if (journal >= 0 && dprintf(journal, "RMX-M1-AUTO boot=%s state=%s\n", boot_id, value) < 0) {
        /* No feeding after losing the recovery marker. */
        _exit(1);
    }
    int fd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    if (fd >= 0) { dprintf(fd, "<6>RMX-M1-GUARD state=%s\n", value); close(fd); }
}
static int control(const char *mode, const char *boot) {
    if (strlen(boot) != 36 || (strcmp(mode, "--keep") && strcmp(mode, "--retain") && strcmp(mode, "--rollback") && strcmp(mode, "--expire-lease"))) return 2;
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    struct sockaddr_un addr = { .sun_family = AF_UNIX };
    strcpy(addr.sun_path, "/dev/socket/rmx_m1_guard");
    if (fd < 0 || connect(fd, (void *)&addr, sizeof(addr))) return 3;
    char command[80], reply[40] = {0};
    snprintf(command, sizeof(command), "%s:%s", mode+2, boot);
    if (write(fd, command, strlen(command)) != (ssize_t)strlen(command)) return 4;
    int n = read(fd, reply, sizeof(reply)-1); close(fd);
    if (n <= 0) return 5;
    puts(reply);
    return strcmp(reply, "lease") && strcmp(reply, "retained") && strcmp(reply, "rollback");
}
int main(int argc, char **argv) {
    if (argc == 3) return control(argv[1], argv[2]);
    if (argc != 1) return 2;
    const char *socket_env = getenv("ANDROID_SOCKET_rmx_m1_guard");
    if (!socket_env) { state("socket-missing"); return 1; }
    int server = atoi(socket_env);
    if (listen(server, 4)) { state("socket-listen-error"); return 1; }
    char boot[40] = {0}, keep[64], retain[64], rollback[64], expire[64];
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    if (fd < 0 || read(fd, boot, 37) != 37) { state("boot-id-error"); return 1; }
    close(fd); boot[36] = 0;
    strcpy(boot_id, boot);
    for (int attempt=0; attempt<10; attempt++) {
        journal = open("/dev/pmsg0", O_WRONLY | O_CLOEXEC);
        if (journal >= 0) break;
        sleep(1);
    }
    if (journal < 0) { state("journal-open-error"); return 1; }
    snprintf(retain, sizeof(retain), "retain:%s", boot);
    snprintf(keep, sizeof(keep), "keep:%s", boot);
    snprintf(rollback, sizeof(rollback), "rollback:%s", boot);
    snprintf(expire, sizeof(expire), "expire-lease:%s", boot);
    fd = -1;
    for (int attempt=0; attempt<10; attempt++) {
        fd = open("/dev/watchdog", O_WRONLY | O_CLOEXEC);
        if (fd >= 0) break;
        if (errno != ENOENT && errno != EBUSY) break;
        sleep(1);
    }
    if (fd < 0) { state("watchdog-open-error"); return 1; }
    int timeout = 30;
    if (ioctl(fd, WDIOC_SETTIMEOUT, &timeout) || timeout != 30) {
        state("watchdog-timeout-error"); close(fd); return 1;
    }
    __system_property_set("vendor.rmx.m1.timeout", "30");
    struct timespec start, now;
    clock_gettime(CLOCK_BOOTTIME, &start);
    int accepted = 0;
    time_t first_ack = 0, lease_end = 0, ready_since = 0, lost_since = 0, journal_at = 0;
    state("armed");
    for (;;) {
        clock_gettime(CLOCK_BOOTTIME, &now);
        char ready[PROP_VALUE_MAX] = {0};
        __system_property_get("vendor.rmx.m1.usb_ready", ready);
        if (!strcmp(ready, "1")) {
            lost_since = 0;
            if (!ready_since) ready_since = now.tv_sec;
        } else {
            ready_since = 0;
            if (!lost_since) lost_since = now.tv_sec;
        }
        if (!accepted && ready_since && now.tv_sec-ready_since >= 30) {
            accepted = 2; journal_at = now.tv_sec;
            __system_property_set("vendor.rmx.m1.accepted_by", "local-adbd");
            state("retained");
        }
        if (accepted == 2 && lost_since && now.tv_sec-lost_since >= 30) {
            state("usb-health-lost"); break;
        }
        if (accepted == 2 && now.tv_sec-journal_at >= 30) {
            state("retained"); journal_at = now.tv_sec;
        }
        if ((!accepted && now.tv_sec - start.tv_sec >= 150) || (accepted == 1 && now.tv_sec >= lease_end)) { state("expired"); break; }
        if (ioctl(fd, WDIOC_KEEPALIVE, 0)) { state("feed-error"); break; }
        struct pollfd pollfd = { .fd = server, .events = POLLIN };
        if (poll(&pollfd, 1, 1000) > 0 && (pollfd.revents & POLLIN)) {
            int client = accept4(server, NULL, NULL, SOCK_CLOEXEC);
            struct ucred cred; socklen_t bytes = sizeof(cred);
            struct timeval limit = { .tv_usec = 500000 };
            char command[80] = {0};
            if (client >= 0) {
                setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &limit, sizeof(limit));
                ssize_t n = read(client, command, sizeof(command)-1);
                const char *reply = "rejected";
                int returning = 0;
                if (n > 0 && !getsockopt(client, SOL_SOCKET, SO_PEERCRED, &cred, &bytes) && cred.uid == 2000) {
                    if (!strcmp(command, expire) && accepted == 2) {
                        accepted=1; first_ack=now.tv_sec; lease_end=now.tv_sec+45;
                        reply="lease"; state(reply);
                    }
                    if (!strcmp(command, keep)) {
                        if (accepted == 2) reply="retained";
                        else {
                            if (!accepted) first_ack = now.tv_sec;
                            accepted=1; lease_end=now.tv_sec+45; reply="lease"; state(reply);
                        }
                    }
                    if (!strcmp(command, retain) && accepted == 1 && now.tv_sec-first_ack >= 180) {
                        accepted=2; journal_at=now.tv_sec; reply="retained";
                        __system_property_set("vendor.rmx.m1.accepted_by", "host-soak");
                        state(reply);
                    }
                    if (!strcmp(command, retain) && accepted == 2) reply="retained";
                    if (!strcmp(command, rollback)) { returning=1; reply="rollback"; state(reply); }
                }
                send(client, reply, strlen(reply), MSG_NOSIGNAL); close(client);
                if (returning) break;
            }
        }
    }
    /* No magic close: leave watchdog armed. Init must not restart this oneshot. */
    close(fd);
    return 1;
}
