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
    message="RMX2072-SUPERVISOR kernel=$(/bin/busybox uname -r) $* trial=$(/bin/busybox cat /trial-id 2>/dev/null) boot_id=$(/bin/busybox cat /proc/sys/kernel/random/boot_id)"
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
    echo $! > /control-return-pid
fi
if [ -x /bin/entry-carry ]; then
    /bin/busybox mkdir -p /sys/fs/pstore
    /bin/busybox mount -t pstore pstore /sys/fs/pstore
    /bin/entry-carry --capture > /dev/kmsg 2>&1
    record "phase=entry-carry status=$?"
fi
# Keep provider snapshots separate from both the gadget child and return timer.
# Missing USB must not prevent collecting driver binding / deferred-probe state.
if [ ! -f /m1-autoboot ]; then (
    delays="2 13 30 30"
    [ ! -r /snapshot-delays ] || delays="$(/bin/busybox cat /snapshot-delays)"
    for delay in $delays; do
        /bin/busybox sleep "$delay"
        /bin/busybox sh /diag-snapshot.sh < /dev/null > /dev/kmsg 2>&1
    done
) &
fi
if [ -x /bin/first-stage-witness ]; then
    if [ -f /m1-autoboot ]; then
        /bin/busybox sh /m1-autoboot.sh < /dev/null > /dev/kmsg 2>&1 &
    else
        /bin/busybox sh /diag-init.sh < /dev/null > /dev/kmsg 2>&1 &
    fi
    while [ ! -f /run/m1/go ]; do /bin/busybox sleep 1; done
    record phase=android-first-stage-handoff
    exec /bin/first-stage-witness handoff < /dev/null > /dev/kmsg 2>&1
fi
while :; do
    # Redirection failure affects this child, never replaces/exits PID 1.
    /bin/busybox sh -x /diag-init.sh < /dev/null > /dev/kmsg 2>&1
    result=$?
    record "phase=child-exit status=$result"
    /bin/busybox sleep 10
done
