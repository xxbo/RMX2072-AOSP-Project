#!/bin/busybox sh
# SPDX-License-Identifier: GPL-2.0-only
# PID 1 must survive every diagnostic-child failure and closed console input.
export PATH=/bin:/sbin
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sysfs /sys
if [ -r /sys/class/pmsg/pmsg0/dev ]; then
    device="$(/bin/busybox cat /sys/class/pmsg/pmsg0/dev)"
    /bin/busybox mknod /dev/pmsg0 c "${device%:*}" "${device#*:}"
fi
record() {
    message="RMX2072-SUPERVISOR kernel=$(/bin/busybox uname -r) $*"
    printf '<0>%s\n' "$message" > /dev/kmsg
    [ ! -c /dev/pmsg0 ] || printf '%s\n' "$message" > /dev/pmsg0
}
record phase=start
if [ -r /control-return-seconds ]; then
    (
        /bin/busybox sleep "$(/bin/busybox cat /control-return-seconds)"
        record phase=control-return-edl
        /bin/reboot-edl edl > /dev/kmsg 2>&1
        record phase=control-return-failed
    ) &
fi
while :; do
    # Redirection failure affects this child, never replaces/exits PID 1.
    /bin/busybox sh -x /diag-init.sh < /dev/null > /dev/kmsg 2>&1
    result=$?
    record "phase=child-exit status=$result"
    /bin/busybox sleep 10
done
