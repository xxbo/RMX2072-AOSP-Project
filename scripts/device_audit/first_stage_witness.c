/* Observe the first mount syscalls of the global Android init on an engineering boot. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/netlink.h>
#include <linux/watchdog.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/xattr.h>
#include <sys/mount.h>
#include <sys/ptrace.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <unistd.h>
#include "m1_autoboot_state.h"

#define ROOT "/run/m1/root"
#define PID_ONE 1

static int events = -1, kmsg = -1, kernel_log = -1;

static void publish_autoboot(void);


/* One write per record, on the same device-to-host stream as GSI17 READ. */
static void report(const char *fmt, ...) {
    char line[896] = "M1EVENT ";
    va_list args;
    va_start(args, fmt);
    vsnprintf(line + 8, sizeof(line) - 1 - 8, fmt, args);
    va_end(args);
    strcat(line, "\n");
    fputs(line + 8, stdout);
    if (events >= 0) (void)write(events, line, strlen(line));
    if (kmsg >= 0) (void)write(kmsg, line, strlen(line));
}

static void fail(const char *name) {
    perror(name);
    /* PID 1 exiting would panic the kernel. The recovery timer is a sibling. */
    if (getpid() == PID_ONE) for (;;) pause();
    exit(1);
}

/* Scope syscall auditing to the next execve of PID 1 on this diagnostic boot.
 * The kernel records EXECVE arguments and the syscall outcome across the
 * domain transition even when the userspace observer loses access to proc. */
static void audit_init_exec(void) {
    struct {
        struct nlmsghdr header;
        struct audit_rule_data rule;
    } request = {0};
    struct sockaddr_nl addr = { .nl_family = AF_NETLINK };
    struct timeval timeout = { .tv_sec = 1 };
    struct { struct nlmsghdr header; struct nlmsgerr ack; } reply = {0};
    int fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, NETLINK_AUDIT);
    if (fd < 0) { report("exec_audit_rc=%d", -errno); return; }
    request.header.nlmsg_len = NLMSG_LENGTH(sizeof(request.rule));
    request.header.nlmsg_type = AUDIT_ADD_RULE;
    request.header.nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
    request.header.nlmsg_seq = 1;
    request.rule.flags = AUDIT_FILTER_EXIT;
    request.rule.action = AUDIT_ALWAYS;
    request.rule.mask[__NR_execve / 32] = 1U << (__NR_execve % 32);
    request.rule.field_count = 1;
    request.rule.fields[0] = AUDIT_PID;
    request.rule.values[0] = PID_ONE;
    request.rule.fieldflags[0] = AUDIT_EQUAL;
    int rc = -EPROTO;
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0 ||
        sendto(fd, &request, request.header.nlmsg_len, 0, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
        recv(fd, &reply, sizeof(reply), 0) < 0) rc = -errno;
    else if (reply.header.nlmsg_type == NLMSG_ERROR && reply.header.nlmsg_seq == 1) rc = reply.ack.error;
    close(fd);
    report("exec_audit_rc=%d", rc);
}

/* Capture the mapped file offsets before init installs its production policy. */
static void start_fault_trace(void) {
    if (access("/m1-trace-fault", F_OK)) return;
    FILE *maps = fopen("/proc/1/maps", "r");
    if (!maps) fail("init mappings");
    char row[640];
    while (fgets(row, sizeof(row), maps)) {
        if (strstr(row, " /")) {
            row[strcspn(row, "\n")] = 0;
            report("map=%s", row);
        }
    }
    fclose(maps);
    int fd = open("/run/m1/trace/tracing_on", O_WRONLY | O_CLOEXEC);
    if (fd < 0 || write(fd, "1", 1) != 1) fail("start fault trace");
    close(fd);
    audit_init_exec();
    report("fault_trace=armed");
}

static void handoff(void) {
    if (getpid() != PID_ONE) exit(2);
    if (unshare(CLONE_NEWNS) || mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) ||
        chdir(ROOT) || mount(".", "/", NULL, MS_MOVE, NULL) || chroot(".") || chdir("/"))
        fail("first-stage root");
    execl("/init", "/init", (char *)NULL);
    fail("exec /init");
}

static void marker(const char *path) {
    int fd = open(path, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    if (fd < 0) fail(path);
    close(fd);
}

/* PID 1 is stopped at syscall entry, so its string arguments are stable. */
static void argument(uint64_t address, char *dest, size_t size) {
    size_t pos = 0;
    if (!address) { snprintf(dest, size, "(null)"); return; }
    while (pos + sizeof(long) < size) {
        errno = 0;
        long value = ptrace(PTRACE_PEEKDATA, PID_ONE, (void *)(uintptr_t)(address + pos), NULL);
        if (errno) { snprintf(dest, size, "<unreadable>"); return; }
        memcpy(dest + pos, &value, sizeof(value));
        if (memchr(dest + pos, 0, sizeof(value))) return;
        pos += sizeof(value);
    }
    dest[pos] = 0;
}

static _Noreturn void hold(const char *reason) {
    report("trial_stop=%s", reason);
    marker("/run/m1/stopped");
    /* Keep the syscall stop while the host reads the trace and requests EDL. */
    for (;;) pause();
}

static int read_proc(const char *path, char *buf, size_t size) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -errno;
    int n = read(fd, buf, size);
    int error = errno;
    close(fd);
    return n < 0 ? -error : n;
}

static void android_log(void) {
    char record[8192];
    for (int i = 0; i < 128; i++) {
        int n = read(kernel_log, record, sizeof(record) - 1);
        if (n <= 0) break;
        record[n] = 0;
        char *message = strchr(record, ';');
        if (!message || strstr(message, "M1EVENT ")) continue;
        if (!strstr(message, "init:") && !strstr(message, "avc:") && !strstr(message, "SELinux:")) continue;
        message++;
        message[strcspn(message, "\n\r")] = 0;
        report("kernel=%s", message);
    }
}

static void post_install(void) {
    static const char stage[] = "/system/bin/init\0second_stage";
    int previous = -9999, second_stage = 0;
    for (int i = 0; i < 80; i++) {
        char buf[128];
        int n = read_proc("/proc/1/root/sys/fs/selinux/enforce", buf, 1);
        int state = n == 1 ? buf[0] : n;
        if (state != previous) {
            if (state == '0' || state == '1') report("enforcing=%c", state);
            else report("enforce_read_rc=%d", n);
            previous = state;
        }
        /* Enforcing can revoke this diagnostic process's proc/kmsg access.
         * Stop retrying after that transition so repeated audit denials do not
         * displace the Android service results in the persistent console. */
        if (n == -EACCES || n == -EPERM) break;
        n = read_proc("/proc/1/cmdline", buf, sizeof(buf));
        if (!second_stage && n == sizeof(stage) && !memcmp(buf, stage, n)) {
            report("exec_pid=1 path=/system/bin/init arg=second_stage");
            second_stage = 1;
        }
        android_log();
        if (second_stage && previous == '1') break;
        usleep(100000);
    }
    report("post_install_window=end");
    execl("/bin/reboot-edl", "reboot-edl", "edl", (char *)NULL);
    fail("software return");
}

/* The kernel may restrict proc after policy installation. Record the actual
 * layers while PID 1 is stopped just after a successful partition mount. */
static void mount_layers(const char *source, const char *target) {
    if (access("/ufs-fstab", F_OK) || strncmp(source, "/dev/block/dm-", 14) ||
        (strcmp(target, "/system") && strcmp(target, "/vendor"))) return;
    char line[256];
    const char *name = strrchr(source, '/') + 1;
    snprintf(line, sizeof(line), "/sys/class/block/%s/dm/name", name);
    char map[128];
    int n = read_proc(line, map, sizeof(map) - 1);
    if (n <= 0) return;
    map[n] = 0;
    map[strcspn(map, "\r\n")] = 0;
    report("mounted_mapper=%s node=%s target=%s", map, name, target);
    pid_t child = fork();
    if (child == 0) {
        execl("/bin/busybox", "busybox", "sh", "/bin/ufs-init-trace", "layers",
              target + 1, name, (char *)NULL);
        _exit(127);
    }
    if (child > 0) {
        int status = 0;
        pid_t waited;
        do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
        if (waited != child || !WIFEXITED(status) || WEXITSTATUS(status))
            hold("unexpected-ufs-mapping");
    }
    if (child < 0) hold("ufs-mapping-observer-failed");
}

static int is_policy_setup(void) {
    static const char args[] = "/system/bin/init\0selinux_setup";
    char cmdline[sizeof(args) + 1];
    int fd = open("/proc/1/cmdline", O_RDONLY | O_CLOEXEC);
    if (fd < 0) fail("PID 1 cmdline");
    ssize_t size = read(fd, cmdline, sizeof(cmdline));
    close(fd);
    return size == sizeof(args) && !memcmp(cmdline, args, sizeof(args));
}

static void observe(int vendor_trial) {
    int usb_guard = !access("/m1-usb-guard", F_OK);
    int autonomous = !access("/m1-autoboot", F_OK);
    struct stat expected;
    int policy_fd = -1, opening = 0, writing = 0, watchdog = -1;
    unsigned long long count = 0;
    if (vendor_trial == 2) {
        events = open(autonomous ? "/run/m1-autoboot.events" : "/dev/ttyGS0",
                      O_WRONLY | O_APPEND | O_NOCTTY | O_CLOEXEC);
        kmsg = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
        if (events < 0 || kmsg < 0) fail("live event sinks");
        kernel_log = open("/dev/kmsg", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (kernel_log < 0) fail("kernel log");
    }
    if (stat(ROOT "/init", &expected)) fail("staged init");
    if (ptrace(PTRACE_SEIZE, PID_ONE, NULL, (void *)(PTRACE_O_TRACEEXEC | PTRACE_O_TRACESYSGOOD)))
        fail("seize PID 1");
    marker("/run/m1/ready");
    int active = 0, in_mount = 0, policy_setup = 0;
    char source[256], target[256], fs[96];
    unsigned long flags = 0;
    for (;;) {
        int status;
        if (waitpid(PID_ONE, &status, __WALL) < 0) {
            if (errno == EINTR) continue;
            fail("waitpid");
        }
        if (!WIFSTOPPED(status)) fail("PID 1 exited");
        int sig = WSTOPSIG(status), deliver = 0;
        if ((status >> 16) == PTRACE_EVENT_EXEC) {
            struct stat actual;
            if (stat("/proc/1/exe", &actual)) fail("stat PID 1 executable");
            if (actual.st_dev == expected.st_dev && actual.st_ino == expected.st_ino) {
                report("exec_pid=1 path=/init staged_inode_match=1");
                active = 1;
            } else if (active) {
                if (!vendor_trial || policy_setup || !is_policy_setup()) hold("next-exec");
                report("exec_pid=1 path=/system/bin/init arg=selinux_setup");
                policy_setup = 1;
            }
        } else if (active && sig == (SIGTRAP | 0x80)) {
            struct ptrace_syscall_info info = {0};
            if (ptrace(PTRACE_GET_SYSCALL_INFO, PID_ONE, (void *)sizeof(info), &info) < 0)
                fail("get syscall info");
            if (info.op == PTRACE_SYSCALL_INFO_ENTRY) {
                opening = 0;
                writing = policy_fd >= 0 && info.entry.nr == __NR_write &&
                          (int)info.entry.args[0] == policy_fd;
                if (writing) {
                    count = info.entry.args[2];
                    report("policy_write_entry fd=%d count=%llu", policy_fd, count);
                }
                if (policy_fd >= 0 && info.entry.nr == __NR_close && (int)info.entry.args[0] == policy_fd)
                    policy_fd = -1;
                in_mount = info.entry.nr == __NR_mount;
                if (in_mount) {
                    argument(info.entry.args[0], source, sizeof(source));
                    argument(info.entry.args[1], target, sizeof(target));
                    argument(info.entry.args[2], fs, sizeof(fs));
                    flags = info.entry.args[3];
                }
                if (policy_setup && info.entry.nr == __NR_openat) {
                    char path[256];
                    argument(info.entry.args[1], path, sizeof(path));
                    if (!strcmp(path, "/sys/fs/selinux/load") || !strcmp(path, "/selinux/load")) {
                        if (vendor_trial != 2) hold("policy-load-open");
                        start_fault_trace();
                        int timeout;
                        watchdog = open("/run/m1/watchdog", O_WRONLY | O_CLOEXEC);
                        if (watchdog < 0 || ioctl(watchdog, WDIOC_GETTIMEOUT, &timeout) < 0)
                            hold("watchdog-open-failed");
                        if (usb_guard) {
                            timeout = 30;
                            int set_rc = ioctl(watchdog, WDIOC_SETTIMEOUT, &timeout);
                            report("usb_guard_timeout requested=30 actual=%d rc=%d errno=%d", timeout, set_rc, set_rc ? errno : 0);
                            if (set_rc || timeout != 30)
                                hold("guard-timeout-failed");
                            FILE *timer = fopen("/control-return-pid", "r");
                            int timer_pid = 0;
                            if (!timer || fscanf(timer, "%d", &timer_pid) != 1 || timer_pid <= 1)
                                hold("guard-timer-pid-failed");
                            fclose(timer);
                            if (kill(timer_pid, SIGTERM)) hold("guard-timer-cancel-failed");
                            report("usb_guard=handoff watchdog_seconds=%d old_timer_cancelled=1", timeout);
                            if (autonomous) {
                                publish_autoboot();
                                /* The parent shell only waits for this observer. Stop it
                                 * before enforcing, avoiding inherited diagnostic retries. */
                                if (getppid() > 1) kill(getppid(), SIGTERM);
                            }
                            /* Release ownership without magic close; hardware remains armed.
                             * Android's oneshot guard must reopen it within 30 seconds. */
                            close(watchdog); watchdog = -1;
                        }
                        if (lseek(kernel_log, 0, SEEK_END) < 0) fail("seek kernel log");
                        report("policy_open_entry path=%s watchdog_seconds=%d", path, timeout);
                        opening = 1;
                    }
                }
                if (info.entry.nr == __NR_reboot || info.entry.nr == __NR_exit_group)
                    hold(info.entry.nr == __NR_reboot ? "reboot-request" : "exit-request");
            } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && opening) {
                policy_fd = (int)info.exit.rval;
                report("policy_open_rc=%d", policy_fd);
                if (policy_fd < 0) hold("policy-open-error");
                opening = 0;
            } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && writing) {
                report("policy_write_rc=%lld count=%llu", (long long)info.exit.rval, count);
                if (info.exit.rval <= 0 || (unsigned long long)info.exit.rval != count)
                    hold("policy-write-error");
                if (ptrace(PTRACE_DETACH, PID_ONE, NULL, NULL)) fail("detach after policy write");
                if (usb_guard) _exit(0);
                post_install();
            } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && in_mount) {
                report("mount_pid=1 source=%s target=%s fs=%s flags=%#lx rc=%lld",
                       source, target, fs, flags, (long long)info.exit.rval);
                if (info.exit.rval == 0) mount_layers(source, target);
                in_mount = 0;
                if ((!vendor_trial || info.exit.rval < 0) &&
                    (!strcmp(target, "/system") || !strncmp(source, "/dev/block/", 11)))
                    hold("partition-mount");
            }
        } else if (!(status >> 16)) {
            if (active && (sig == SIGABRT || sig == SIGSEGV)) hold("fatal-signal");
            deliver = sig;
        }
        if (ptrace(active ? PTRACE_SYSCALL : PTRACE_CONT, PID_ONE, NULL, (void *)(intptr_t)deliver))
            fail("resume PID 1");
    }
}

static void publish_file(const char *source, const char *name, int optional) {
    const char label[] = "u:object_r:shell_data_file:s0";
    char target[160];
    snprintf(target, sizeof(target), "/proc/1/root/data/local/tmp/%s", name);
    int in = open(source, O_RDONLY | O_CLOEXEC);
    if (in < 0 && optional && errno == ENOENT) return;
    if (in < 0) hold("autoboot-log-input");
    int out = open(target, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0444);
    if (out < 0) hold("autoboot-log-output");
    char buf[4096]; ssize_t n; size_t size = 0;
    while ((n = read(in, buf, sizeof(buf))) > 0) {
        size += (size_t)n;
        if (size > 2U*1024U*1024U+4096U || write(out, buf, n) != n) hold("autoboot-log-write");
    }
    if (n < 0 || fsetxattr(out, "security.selinux", label, sizeof(label), 0) || fsync(out))
        hold("autoboot-log-sync");
    close(in); close(out);
}

/* Snapshot mount/verity evidence while init is stopped before loading policy.
 * Android shell can read this file on the disposable data volume after boot. */
static void publish_autoboot(void) {
    const char *dirs[] = {"/proc/1/root/data/local", "/proc/1/root/data/local/tmp"};
    const char label[] = "u:object_r:shell_data_file:s0";
    for (unsigned i = 0; i < sizeof(dirs)/sizeof(dirs[0]); i++) {
        if (mkdir(dirs[i], 0771) && errno != EEXIST) hold("autoboot-log-directory");
        if (chown(dirs[i], 2000, 2000) || setxattr(dirs[i], "security.selinux", label, sizeof(label), 0))
            hold("autoboot-log-directory-label");
    }
    publish_file("/run/m1-autoboot.events", "rmx-m1-boot.txt", 0);
    publish_file("/run/m1-power.txt", "rmx-m1-power.txt", 1);
    publish_file("/sys/fs/pstore/console-ramoops-0", "rmx-m1-previous-console", 1);
    publish_file("/sys/fs/pstore/pmsg-ramoops-0", "rmx-m1-previous-pmsg", 1);
}

/* Pin the checked loop node and init's current root before entering its
 * namespace. setns resets the caller's root to the namespace root. */
static void scratch_mount(const char *name) {
    if (strcmp(name, "data") && strcmp(name, "metadata")) exit(2);
    char source[64], target[64];
    snprintf(source, sizeof(source), "/run/m1-scratch/%s-loop", name);
    snprintf(target, sizeof(target), "/%s", name);
    char key[768] = {0};
    int key_bytes = 0;
    if (!strcmp(name, "data") && !access("/m1-usb-guard", F_OK)) {
        key_bytes = read_proc("/m1-adb-public-key", key, sizeof(key));
        if (key_bytes <= 0 || key_bytes >= (int)sizeof(key)) fail("authorized public key");
    }
    int loop = open(source, O_PATH | O_CLOEXEC);
    int root = open("/proc/1/root", O_DIRECTORY | O_RDONLY | O_CLOEXEC);
    if (loop < 0 || root < 0) fail("pin scratch device and Android root");
    struct stat device, volume;
    if (fstat(loop, &device) || !S_ISBLK(device.st_mode)) fail("check scratch block node");
    int ns = open("/proc/1/ns/mnt", O_RDONLY | O_CLOEXEC);
    if (ns < 0 || setns(ns, CLONE_NEWNS)) fail("enter Android mount namespace");
    close(ns);
    if (fchdir(root) || chroot(".") || chdir("/")) fail("enter Android root");
    close(root);
    snprintf(source, sizeof(source), "/proc/self/fd/%d", loop);
    if (mount(source, target, "ext4", MS_NOSUID | MS_NODEV, NULL)) fail("mount RAM ext4");
    close(loop);
    if (stat(target, &volume) || device.st_rdev != volume.st_dev)
        fail("verify RAM ext4 mount");
    char sentinel[128];
    snprintf(sentinel, sizeof(sentinel), "%s/.m1-write-test", target);
    int fd = open(sentinel, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, "M1", 2) != 2 || fsync(fd) || close(fd) || unlink(sentinel))
        fail("verify RAM ext4 write");
    if (key_bytes) {
        static const char label[] = "u:object_r:adb_keys_file:s0";
        if (mkdir("/data/misc/adb", 02750) || chown("/data/misc/adb", 1000, 2000) ||
            chmod("/data/misc/adb", 02750) ||
            setxattr("/data/misc/adb", "security.selinux", label, sizeof(label), 0))
            fail("label adb directory");
        fd = open("/data/misc/adb/adb_keys", O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0640);
        if (fd < 0 || write(fd, key, key_bytes) != key_bytes || fchown(fd, 1000, 2000) ||
            fsetxattr(fd, "security.selinux", label, sizeof(label), 0) || fsync(fd) || close(fd))
            fail("install authorized public key");
    }
}

/* Only the diagnostic recovery boot may relinquish the AP watchdog immediately
 * before EDL. The Android guard must never disarm its failed trial watchdog. */
static int recovery_stop_watchdog(void) {
    char device[256];
    if (access("/m1-autoboot", F_OK) ||
        !realpath("/sys/class/watchdog/watchdog0/device", device) ||
        strcmp(device, "/sys/devices/platform/soc/17c10000.qcom,wdt")) {
        fputs("M1RECOVERY watchdog scope mismatch\n", stderr); return 1;
    }
    /* Diagnostic /dev can be tmpfs: unlike Android, it has no ueventd. */
    unsigned int major_number = 0, minor_number = 0;
    FILE *devfile = fopen("/sys/class/watchdog/watchdog0/dev", "r");
    if (!devfile) { perror("recovery watchdog dev"); return 1; }
    int fields = fscanf(devfile, "%u:%u", &major_number, &minor_number);
    fclose(devfile);
    if (fields != 2 || !major_number || major_number > 4095 || minor_number) {
        fputs("M1RECOVERY watchdog device number mismatch\n", stderr); return 1;
    }
    dev_t number = makedev(major_number, minor_number);
    if (mknod("/dev/watchdog0", S_IFCHR | 0600, number) && errno != EEXIST) {
        perror("recovery watchdog mknod"); return 1;
    }
    struct stat node;
    if (lstat("/dev/watchdog0", &node) || !S_ISCHR(node.st_mode) || node.st_rdev != number) {
        fputs("M1RECOVERY watchdog node mismatch\n", stderr); return 1;
    }
    int fd = open("/dev/watchdog0", O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    int option = WDIOS_DISABLECARD;
    struct watchdog_info info = {0};
    if (fd < 0) { perror("recovery watchdog open"); return 1; }
    if (ioctl(fd, WDIOC_GETSUPPORT, &info) ||
        strncmp((const char *)info.identity, "qcom_wdt", sizeof(info.identity)) ||
        !(info.options & WDIOF_MAGICCLOSE)) {
        fputs("M1RECOVERY unexpected watchdog identity/options\n", stderr); close(fd); return 1;
    }
    /* The current kernel has WATCHDOG_SYSFS disabled. SETOPTIONS is the
     * authoritative stop operation and rejects a driver enforcing nowayout. */
    if (ioctl(fd, WDIOC_SETOPTIONS, &option)) {
        perror("recovery watchdog disable"); close(fd); return 1;
    }
    close(fd);
    puts("M1RECOVERY AP watchdog disable ioctl rc=0 identity=qcom_wdt");
    return 0;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 3 && !strcmp(argv[1], "autoboot-state")) return autoboot_state(argv[2]);
    if (argc == 2 && !strcmp(argv[1], "recovery-stop-watchdog")) return recovery_stop_watchdog();
    if (argc == 3 && !strcmp(argv[1], "scratch-mount")) scratch_mount(argv[2]);
    else if (argc == 2 && !strcmp(argv[1], "handoff")) handoff();
    else if (argc == 2 && !strcmp(argv[1], "observe")) observe(0);
    else if (argc == 2 && !strcmp(argv[1], "observe-vendor")) observe(1);
    else if (argc == 2 && !strcmp(argv[1], "observe-install")) observe(2);
    else return 2;
    return 0;
}
