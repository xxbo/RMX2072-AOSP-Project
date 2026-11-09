#!/bin/busybox sh
# Run inside the isolated RMX2072 6.18 diagnostic ramdisk.
set -eu

root=/sys/bus/platform
drivers=$root/drivers
base=/sys/firmware/devicetree/base/soc/ufs-phy-lab
case "$(uname -r):$(cat /trial-id)" in 6.18.*:ufs-phy-*) ;; *) exit 2 ;; esac
case " $(cat /proc/cmdline) " in *" initcall_blacklist=ufs_qcom_pltform_init "*) ;; *) exit 2 ;; esac
[ ! -d "$drivers/ufshcd-qcom" ]
[ -d "$root/devices/1d84000.ufshc" ]
[ ! -L "$root/devices/1d84000.ufshc/driver" ]

# Use OF paths because platform device names are generated from translated addresses.
device() {
    for path in "$root"/devices/*"$1"; do
        if [ -e "$path/of_node" ] && [ "$(readlink -f "$path/of_node")" = "$2" ]; then
            printf '%s\n' "$path"
            return 0
        fi
    done
    return 1
}

bind() {
    path=$1 driver=$2
    [ -d "$drivers/$driver" ] && [ ! -L "$path/driver" ] || return 1
    printf '%s\n' "$driver" > "$path/driver_override"
    printf '%s\n' "${path##*/}" > "$drivers/$driver/bind"
    [ "$(basename "$(readlink "$path/driver")")" = "$driver" ]
}

bus=$(device ufs-phy-lab "$base")
case "${1:-}" in
preflight)
    echo "lab=${bus##*/} compatible=$(tr -d '\000' < "$base/compatible")"
    for name in diag_pm8150_l5 diag_pm8150_l9; do
        found=0
        for r in /sys/class/regulator/regulator*; do
            [ "$(cat "$r/name")" = "$name" ] || continue
            echo "$name voltage=$(cat "$r/microvolts") state=$(cat "$r/state")"
            found=1
        done
        [ "$found" = 1 ] || { echo "$name is missing"; exit 1; }
    done
    echo "host_unbound=1 udc=$(cat /sys/class/udc/*/state)"
    ;;
probe)
    bind "$bus" rmx2072-ufs-phy-bus
    phy=$(device .phy "$base/phy@1d87000")
    [ "$(basename "$(readlink "$phy/driver")")" = qcom-qmp-ufs-phy ]
    echo "provider=${phy##*/} driver=qcom-qmp-ufs-phy"
    ;;
cycle)
    phy=$(device .phy "$base/phy@1d87000")
    [ "$(basename "$(readlink "$phy/driver")")" = qcom-qmp-ufs-phy ]
    testdev=$(device ufs-phy-exercise "$base/ufs-phy-exercise")
    bind "$testdev" rmx2072-ufs-phy-test
    printf '%s\n' "${testdev##*/}" > "$drivers/rmx2072-ufs-phy-test/unbind"
    echo "cycle_complete=1 uptime=$(cut -d' ' -f1 /proc/uptime) udc=$(cat /sys/class/udc/*/state)"
    ;;
*) echo 'Usage: ufs-phy-cycle preflight | probe | cycle' >&2; exit 2 ;;
esac
