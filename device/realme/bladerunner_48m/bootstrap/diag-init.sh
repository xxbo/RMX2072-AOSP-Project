#!/bin/busybox sh
# SPDX-License-Identifier: GPL-2.0-only
export PATH=/bin:/sbin
# Do not depend on /proc/self/exe during BusyBox applet installation.
/bin/busybox mount -t proc proc /proc
/bin/busybox --install -s /bin
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev || mount -t tmpfs tmpfs /dev
mkdir -p /dev/pts /run /sys/kernel/config
[ -c /dev/console ] || mknod /dev/console c 5 1
[ -c /dev/null ] || mknod /dev/null c 1 3
[ -c /dev/kmsg ] || mknod /dev/kmsg c 1 11
mount -t devpts devpts /dev/pts
if [ ! -c /dev/pmsg0 ] && [ -r /sys/class/pmsg/pmsg0/dev ]; then
    device="$(cat /sys/class/pmsg/pmsg0/dev)"
    mknod /dev/pmsg0 c "${device%:*}" "${device#*:}"
fi
log_phase() {
    message="RMX2072-DIAG kernel=$(uname -r) phase=$1"
    echo "<6>$message" > /dev/kmsg
    # pmsg is reserved RAM; this does not write any handset filesystem.
    [ ! -c /dev/pmsg0 ] || printf '%s\n' "$message" > /dev/pmsg0
}
log_phase init
uname -a > /run/kernel.txt
dmesg > /run/boot-dmesg.txt
# No block filesystem is mounted. No firmware is written or updated.
mount -t configfs configfs /sys/kernel/config
mkdir -p /sys/kernel/config/usb_gadget/rmxdiag
if ! cd /sys/kernel/config/usb_gadget/rmxdiag; then
    log_phase gadget-directory-failed
    exit 1
fi
echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0200 > bcdUSB
mkdir -p strings/0x409 configs/c.1/strings/0x409 functions/acm.usb0
echo RMX2072-DIAG > strings/0x409/serialnumber
echo 'RMX2072 Project' > strings/0x409/manufacturer
echo 'Linux 6.18 USB diagnostic' > strings/0x409/product
echo 'Diagnostic serial console' > configs/c.1/strings/0x409/configuration
echo 100 > configs/c.1/MaxPower
ln -s functions/acm.usb0 configs/c.1/acm.usb0
count=0
while [ -z "$(ls /sys/class/udc 2>/dev/null)" ] && [ "$count" -lt 60 ]; do
    sleep 1
    count=$((count + 1))
done
controller="$(ls /sys/class/udc 2>/dev/null | head -n 1)"
if [ -n "$controller" ]; then
    log_phase udc-present
    if [ -e /defer-gadget-bind ]; then
        log_phase udc-bind-deferred
        while :; do sleep 10; done
    fi
    if echo "$controller" > UDC; then
        log_phase udc-bound
    else
        log_phase udc-bind-failed
    fi
    if [ ! -c /dev/ttyGS0 ] && [ -r /sys/class/tty/ttyGS0/dev ]; then
        device="$(cat /sys/class/tty/ttyGS0/dev)"
        mknod /dev/ttyGS0 c "${device%:*}" "${device#*:}"
    fi
    log_phase acm-shell-ready
    while :; do
        setsid sh -c 'exec < /dev/ttyGS0 > /dev/ttyGS0 2>&1; echo; echo RMX2072-DIAG; uname -a; echo "RAM-only diagnostic: no handset filesystems mounted"; exec sh -i'
        sleep 1
    done
fi
log_phase no-udc
while :; do sleep 10; done
