#!/bin/busybox sh
# Autonomous engineering boot. No cable, host time or writable UFS is required.
set -eu
export PATH=/bin:/sbin
/bin/busybox --install -s /bin
mount -t devtmpfs devtmpfs /dev || mount -t tmpfs tmpfs /dev
mkdir -p /run /dev/pts /sys/kernel/debug /sys/fs/pstore
for pair in null:1:3 kmsg:1:11; do
    name=${pair%%:*}; numbers=${pair#*:}
    [ -c /dev/$name ] || mknod /dev/$name c "${numbers%:*}" "${numbers#*:}"
done
mount -t debugfs debugfs /sys/kernel/debug || true
mount -t pstore pstore /sys/fs/pstore || true
device=$(cat /sys/class/pmsg/pmsg0/dev)
[ -c /dev/pmsg0 ] || mknod /dev/pmsg0 c "${device%:*}" "${device#*:}"
boot=$(cat /proc/sys/kernel/random/boot_id)
mark() { printf 'RMX-M1-AUTO boot=%s state=%s\n' "$boot" "$1" > /dev/pmsg0; }
# Preserve the newest complete guard marker from the previous boot. A pending
# attempt must enter recovery rather than repeatedly start the same Android.
previous=$(/bin/first-stage-witness autoboot-state /sys/fs/pstore/pmsg-ramoops-0) || previous=unreadable
printf 'M1AUTO boot=%s previous=%s\n' "$boot" "$previous" > /dev/kmsg
if [ "$previous" != none ] && [ "${previous##*state=}" != retained ]; then
    mark recovery
    # Allow the host to retrieve the failed boot's pstore. Without a host the
    # same image enters EDL on its own after this bounded capture window.
    /bin/busybox sh /diag-init.sh < /dev/null > /dev/kmsg 2>&1 &
    sleep 30
    printf 'M1RECOVERY boot=%s uptime=%s\n' "$boot" "$(cat /proc/uptime)" > /run/m1-recovery-watchdog.log
    /bin/first-stage-witness recovery-stop-watchdog >> /run/m1-recovery-watchdog.log 2>&1
    cat /run/m1-recovery-watchdog.log > /dev/kmsg
    mark edl-watchdog-disabled
    # Observe two full 30-second AP-watchdog periods without userspace feeding.
    sleep 60
    exec /bin/reboot-edl edl
fi
mark attempt
printf 'M1EVENT autonomous=1\nM1EVENT boot_id=%s\n' "$boot" > /run/m1-autoboot.events
printf 'M1EVENT previous_guard=%s\n' "$previous" >> /run/m1-autoboot.events
printf 'M1EVENT boot_usb_state=%s\n' "$(cat /sys/class/udc/*/state 2>/dev/null || echo unavailable)" >> /run/m1-autoboot.events
# A real RTC is not yet available. Do not supply invented UTC to the optional
# TIME listener key probe; the Android HAL path still runs normally.
printf 'M1EVENT clock_source=unavailable fixed_time_probe=skipped\n' >> /run/m1-autoboot.events
for attempt in $(seq 1 30); do
    if /bin/ufs-host-test preflight > /run/m1-preflight.log 2>&1; then break; fi
    sleep 1
done
# Read-only provider evidence for the PDC/SPMI power-control investigation.
{
    printf 'M1POWER boot=%s\n' "$boot"
    echo DEFERRED
    cat /sys/kernel/debug/devices_deferred
    echo SPMI
    ls -l /sys/bus/spmi/devices
    for device in /sys/bus/spmi/devices/*; do
        [ -e "$device" ] || continue
        printf 'DEVICE=%s DRIVER=%s\n' "${device##*/}" "$(readlink -f "$device/driver")"
        cat "$device/uevent"
    done
    echo POWER_LOG
    for device in /sys/bus/platform/devices/*power-on* /sys/bus/platform/devices/*restart*; do
        [ -e "$device" ] || continue
        printf 'PLATFORM=%s DRIVER=%s\n' "${device##*/}" "$(readlink -f "$device/driver")"
    done
    dmesg | grep -iE 'spmi|pmic|pdc|psci|power.?off|pon@|pwrkey' || true
} > /run/m1-power.txt 2>&1 || true
/bin/busybox sh /bin/first-stage-mount ufs install > /run/gsi17-run.log 2>&1
mark failed
exec /bin/reboot-edl edl
