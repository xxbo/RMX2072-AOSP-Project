#!/bin/busybox sh
# Populate only the selected display stage, with a live pre-policy USB record.
set -eu
[ -f /m3-display-staged ]
stage=$1
case "$stage" in pins|fabric|core) ;; *) exit 2 ;; esac
boot=$(cat /proc/sys/kernel/random/boot_id)
[ "$(cat /run/m3-display-start)" = "$boot" ]
of=/sys/firmware/devicetree/base/soc/display-$stage-lab
dev=/sys/bus/platform/devices/soc:display-$stage-lab
driver=/sys/bus/platform/drivers/rmx2072-ufs-phy-bus
[ "$(readlink -f "$dev/of_node")" = "$of" ]
[ "$(tr -d '\000' < "$of/compatible")" = realme,rmx2072-diag-ufs-phy-bus ]
[ ! -L "$dev/driver" ]
mark() {
    line="M3BIND boot=$boot stage=$stage state=$1 uptime=$(cut -d' ' -f1 /proc/uptime)"
    echo "$line"
    echo "$line" > /dev/ttyGS0
    echo "$line" > /dev/kmsg
}
wlan_pins() {
    # Observe the inherited enable/reset state before the fabric creates the
    # PCIe and PMU devices. Debugfs GPIO reads do not request/change a GPIO.
    # Duplicate this small record to kmsg so a failed Android handoff cannot
    # hide it in the RAM-only display report.
    [ -d /sys/firmware/devicetree/base/soc/display-fabric-lab/qca6390-pmu ] || return 0
    echo "M3WLANSEQ boot=$boot stage=$stage boundary=$1 uptime=$(cut -d' ' -f1 /proc/uptime)" > /dev/kmsg
    # MSM's pinconf-pins contains labels only on this kernel; actual direction
    # and level come from its gpio debug show callback (verified in trial 93).
    wlan_levels=
    if [ -r /sys/kernel/debug/gpio ]; then
        wlan_levels=$(grep -E '^[[:space:]]*gpio(20|21|79|80|81)[[:space:]]*:' /sys/kernel/debug/gpio || true)
    fi
    if [ -n "$wlan_levels" ]; then
        printf '%s\n' "$wlan_levels" |
        while IFS= read -r line; do
            echo "M3WLANSEQ stage=$stage boundary=$1 $line"
            echo "M3WLANSEQ stage=$stage boundary=$1 $line" > /dev/kmsg
        done
    else
        echo "M3WLANSEQ stage=$stage boundary=$1 levels=unavailable" > /dev/kmsg
    fi
}
wlan_pins before || echo 'M3WLANSEQ read_failed=before'
mark begin
echo rmx2072-ufs-phy-bus > "$dev/driver_override"
echo "soc:display-$stage-lab" > "$driver/bind"
mark populated
# Registration can defer. Report the real child state without fabricating a pass.
sleep 2
wlan_pins after || echo 'M3WLANSEQ read_failed=after'
for child in "$dev"/*; do
    [ -L "$child/of_node" ] || continue
    echo "M3BIND child=${child##*/} driver=$(readlink "$child/driver" || true)"
done
cat /sys/kernel/debug/devices_deferred
case "$stage" in
    pins) expected=sm8250-pinctrl; child=f100000.pinctrl ;;
    fabric) expected=qnoc-sm8250; child=1740000.interconnect ;;
    core) mark inspected; exit 0 ;;
esac
[ "$(basename "$(readlink "$dev/$child/driver")")" = "$expected" ]
mark bound
