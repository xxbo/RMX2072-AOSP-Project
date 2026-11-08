#!/bin/busybox sh
# SPDX-License-Identifier: GPL-2.0-only
# Bounded runtime evidence in reserved RAM, independent of a working USB UDC.
export PATH=/bin:/sbin
emit() {
    line="RMX2072-RUNTIME kernel=$(/bin/busybox uname -r) $*"
    printf '<0>%s\n' "$line" > /dev/kmsg
    [ ! -c /dev/pmsg0 ] || printf '%s\n' "$line" > /dev/pmsg0
}
capture() {
    emit "read=$1"
    if [ -r "$1" ]; then
        /bin/busybox head -n 32 "$1" | while IFS= read -r value; do
            emit "value=$value"
        done
    else
        emit unavailable
    fi
}
# debugfs is a virtual filesystem. Never mount block devices or open watchdog.
/bin/busybox mkdir -p /sys/kernel/debug
/bin/busybox mount -t debugfs debugfs /sys/kernel/debug
emit phase=snapshot-begin
for path in /proc/uptime /proc/sys/kernel/random/boot_id /sys/devices/system/cpu/online /proc/mounts \
    /sys/devices/system/clocksource/clocksource0/current_clocksource \
    /sys/kernel/debug/devices_deferred \
    /sys/class/watchdog/watchdog*/identity \
    /sys/class/watchdog/watchdog*/state \
    /sys/class/udc/*/state; do
    capture "$path"
done
/bin/busybox grep -E 'Kernel code|Kernel data' /proc/iomem | while IFS= read -r value; do
    emit "iomem=$value"
done
for pattern in /sys/bus/platform/devices/*scm* /sys/bus/platform/devices/*smem* \
    /sys/bus/platform/devices/*hwlock* /sys/bus/platform/devices/*watchdog* \
    /sys/bus/platform/devices/*rsc* /sys/bus/platform/devices/*clock-controller* \
    /sys/bus/platform/devices/*usb* /sys/bus/platform/devices/*phy*; do
    [ -d "$pattern" ] || continue
    driver=$(/bin/busybox readlink "$pattern/driver")
    emit "device=${pattern##*/} driver=${driver:-unbound}"
done
emit phase=snapshot-end
