/* SPDX-License-Identifier: Apache-2.0
 * Bounded same-UID diagnostic of the fixed GSI screencap child. No root,
 * arbitrary command, device writes, or policy changes. AArch64 only.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t child;
static void expire(int sig) {
    (void)sig;
    if (child > 0) kill(child, SIGKILL);
    _exit(124);
}

static void copy_file(const char *path) {
    FILE *f = fopen(path, "r");
    char line[1024];
    printf("FILE %s\n", path);
    if (!f) { perror(path); return; }
    while (fgets(line, sizeof(line), f)) fputs(line, stdout);
    fclose(f);
}

static void sample(pid_t tid) {
    uint64_t regs[34]; /* x0..x30, sp, pc, pstate */
    struct iovec io = { regs, sizeof(regs) };
    int status;
    printf("THREAD %d\n", tid);
    if (ptrace(PTRACE_ATTACH, tid, 0, 0)) { perror("attach"); return; }
    if (waitpid(tid, &status, __WALL) < 0) { perror("waitpid"); goto detach; }
    if (!WIFSTOPPED(status)) goto detach;
    if (ptrace(PTRACE_GETREGSET, tid, (void *)NT_PRSTATUS, &io)) {
        perror("getregset"); goto detach;
    }
    printf("pc=%016" PRIx64 " lr=%016" PRIx64 " sp=%016" PRIx64 " fp=%016" PRIx64 " syscall=%" PRIu64 "\n",
           regs[32], regs[30], regs[31], regs[29], regs[8]);
    for (unsigned i=0; i<6; ++i) printf("x%u=%016" PRIx64 "\n",i,regs[i]);
    uint64_t fp = regs[29];
    for (unsigned i=0; i<24 && fp && !(fp & 15); ++i) {
        errno=0;
        uint64_t next=(uint64_t)ptrace(PTRACE_PEEKDATA,tid,(void *)(uintptr_t)fp,0);
        if (errno) break;
        uint64_t lr=(uint64_t)ptrace(PTRACE_PEEKDATA,tid,(void *)(uintptr_t)(fp+8),0);
        if (errno) break;
        printf("FRAME %u fp=%016" PRIx64 " lr=%016" PRIx64 "\n",i,fp,lr);
        if (next <= fp || next-fp > 1024*1024) break;
        fp=next;
    }
detach:
    if (ptrace(PTRACE_DETACH,tid,0,0)) perror("detach");
}

int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    signal(SIGALRM,expire);
    alarm(15);
    printf("uid=%d gid=%d\n",getuid(),getgid());
    copy_file("/proc/sys/kernel/random/boot_id");
    child=fork();
    if (child<0) { perror("fork"); return 1; }
    if (!child) {
        int fd=open("/dev/null",O_WRONLY);
        if (fd<0 || dup2(fd,STDOUT_FILENO)<0) _exit(125);
        close(fd);
        execl("/system/bin/screencap","screencap","-p",(char *)NULL);
        _exit(127);
    }
    sleep(3);
    int status;
    if (waitpid(child,&status,WNOHANG)==child) {
        printf("child_finished status=%d\n",status); return 0;
    }
    char path[96];
    snprintf(path,sizeof(path),"/proc/%d/maps",child);
    copy_file(path);
    snprintf(path,sizeof(path),"/proc/%d/task",child);
    DIR *d=opendir(path);
    if (d) {
        struct dirent *e;
        while ((e=readdir(d))) {
            char *end;
            long tid=strtol(e->d_name,&end,10);
            if (tid>0 && !*end) sample((pid_t)tid);
        }
        closedir(d);
    } else perror("task directory");
    kill(child,SIGKILL);
    waitpid(child,&status,0);
    alarm(0);
    puts("probe_complete child_reaped=1");
    return 0;
}
