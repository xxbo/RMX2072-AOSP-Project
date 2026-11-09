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
    /sys/class/udc/*/state /sys/class/udc/*/current_speed; do
    capture "$path"
done
usb=/sys/bus/platform/devices/a600000.usb
group=$(/bin/busybox readlink -f "$usb/iommu_group")
if [ -d "$usb/iommu_group/devices" ]; then
    emit "usb-iommu-group=${group##*/}"
    for member in "$usb/iommu_group/devices/"*; do
        [ ! -e "$member" ] || emit "group-member=${member##*/}"
    done
else
    emit usb-iommu-group=unavailable
fi
for irq_pattern in 'dwc3|dwc_usb3|a600000|pwr_event|hs_phy_irq' smmu; do
    /bin/busybox grep -iE "$irq_pattern" /proc/interrupts | /bin/busybox head -n 8 |
        while IFS= read -r value; do emit "irq=$value"; done
done
/bin/busybox grep -E 'Kernel code|Kernel data' /proc/iomem | while IFS= read -r value; do
    emit "iomem=$value"
done
for pattern in /sys/bus/platform/devices/*scm* /sys/bus/platform/devices/*smem* \
    /sys/bus/platform/devices/*hwlock* /sys/bus/platform/devices/*watchdog* \
    /sys/bus/platform/devices/*rsc* /sys/bus/platform/devices/*clock-controller* \
    /sys/bus/platform/devices/*usb* /sys/bus/platform/devices/*phy* \
    /sys/bus/platform/devices/*smmu*; do
    [ -d "$pattern" ] || continue
    driver=$(/bin/busybox readlink "$pattern/driver")
    emit "device=${pattern##*/} driver=${driver:-unbound}"
done
emit phase=snapshot-end
