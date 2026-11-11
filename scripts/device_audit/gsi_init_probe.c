// Run the GSI's SELinux setup as an unprivileged child of the RAM diagnostic.
#include <grp.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <unistd.h>

int main(void)
{
    if (chroot("/run/gsi17/mnt") || chdir("/") || setgroups(0, NULL) ||
        setgid(65534) || setuid(65534) || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) {
        perror("prepare init probe");
        return 1;
    }
    char *const args[] = {"/system/bin/init", "selinux_setup", NULL};
    char *const env[] = {"PATH=/system/bin", "LD_LIBRARY_PATH=/system/lib64/bootstrap:/system/lib64", NULL};
    execve(args[0], args, env);
    perror("exec Android init");
    return 1;
}
