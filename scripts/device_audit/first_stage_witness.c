/* Observe the first mount syscalls of the global Android init on an engineering boot. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define ROOT "/run/m1/root"
#define PID_ONE 1

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

static void hold(const char *reason) {
    printf("trial_stop=%s\n", reason);
    marker("/run/m1/stopped");
    /* Keep the syscall stop while the host reads the trace and requests EDL. */
    for (;;) pause();
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
                printf("exec_pid=1 path=/init staged_inode_match=1\n");
                active = 1;
            } else if (active) {
                if (!vendor_trial || policy_setup || !is_policy_setup()) hold("next-exec");
                printf("exec_pid=1 path=/system/bin/init arg=selinux_setup\n");
                policy_setup = 1;
            }
        } else if (active && sig == (SIGTRAP | 0x80)) {
            struct ptrace_syscall_info info = {0};
            if (ptrace(PTRACE_GET_SYSCALL_INFO, PID_ONE, (void *)sizeof(info), &info) < 0)
                fail("get syscall info");
            if (info.op == PTRACE_SYSCALL_INFO_ENTRY) {
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
                    if (!strcmp(path, "/sys/fs/selinux/load") || !strcmp(path, "/selinux/load"))
                        hold("policy-load-open");
                }
                if (info.entry.nr == __NR_reboot || info.entry.nr == __NR_exit_group)
                    hold(info.entry.nr == __NR_reboot ? "reboot-request" : "exit-request");
            } else if (info.op == PTRACE_SYSCALL_INFO_EXIT && in_mount) {
                printf("mount_pid=1 source=%s target=%s fs=%s flags=%#lx rc=%lld\n",
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
    else return 2;
    return 0;
}
