/* Observe the first mount syscalls of the global Android init on an engineering boot. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/watchdog.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define ROOT "/run/m1/root"
#define PID_ONE 1

static int events = -1, kmsg = -1, kernel_log = -1;

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
    struct stat expected;
    int policy_fd = -1, opening = 0, writing = 0, watchdog = -1;
    unsigned long long count = 0;
    if (vendor_trial == 2) {
        events = open("/dev/ttyGS0", O_WRONLY | O_NOCTTY | O_CLOEXEC);
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
                        int timeout;
                        watchdog = open("/run/m1/watchdog", O_WRONLY | O_CLOEXEC);
                        if (watchdog < 0 || ioctl(watchdog, WDIOC_GETTIMEOUT, &timeout) < 0)
                            hold("watchdog-open-failed");
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
                post_install();
            } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && in_mount) {
                report("mount_pid=1 source=%s target=%s fs=%s flags=%#lx rc=%lld",
                       source, target, fs, flags, (long long)info.exit.rval);
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

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 2 && !strcmp(argv[1], "handoff")) handoff();
    else if (argc == 2 && !strcmp(argv[1], "observe")) observe(0);
    else if (argc == 2 && !strcmp(argv[1], "observe-vendor")) observe(1);
    else if (argc == 2 && !strcmp(argv[1], "observe-install")) observe(2);
    else return 2;
    return 0;
}
