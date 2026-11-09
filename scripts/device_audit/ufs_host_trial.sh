#!/bin/busybox sh
# One stage per invocation so the USB observer can preserve partial evidence.
set -eu
dev=/sys/bus/platform/devices
drv=/sys/bus/platform/drivers
of=/sys/firmware/devicetree/base/soc
hba=$dev/1d84000.ufs
trace=/sys/kernel/debug/tracing
inst=$trace/instances/rmxlink
stage=$1
case "$(uname -r):$(cat /trial-id)" in 6.18.*:ufs-host-*) ;; *) exit 2 ;; esac
[ "$(od -An -tx1 "$of/../oplus,dtsi_no" | xargs)" = '00 00 50 7f' ]
[ "$(cat /sys/class/udc/*/state)" = configured ]
[ "$(tr -d '\000' < "$of/ufshc@1d84000/compatible")" = realme,rmx2072-parked-ufs-host ]
[ ! -L "$dev/1d84000.ufshc/driver" ]
[ -d "$drv/ufshcd-qcom" ]
bind_bus() {
    target="$dev/soc:$1"
    [ "$(readlink -f "$target/of_node")" = "$of/$1" ]
    if [ ! -L "$target/driver" ]; then
        echo rmx2072-ufs-phy-bus > "$target/driver_override"
        basename "$target" > "$drv/rmx2072-ufs-phy-bus/bind"
    fi
    [ "$(basename "$(readlink "$target/driver")")" = rmx2072-ufs-phy-bus ]
}
case "$stage" in
preflight)
    [ ! -e "$hba" ]
    for wanted in l5 l6 l9 l17 s4; do
        seen=0
        for r in /sys/class/regulator/regulator*; do
            if [ "$(cat "$r/name")" = "diag_pm8150_$wanted" ]; then
                echo "$wanted $(cat "$r/microvolts") $(cat "$r/state")"
                seen=1
            fi
        done
        [ "$seen" = 1 ]
    done
    ls -d "$drv"/bcm_voter/*ufs-bcm-voter
    ;;
fabric)
    bind_bus ufs-fabric-lab
    for addr in 1500000 1620000 163d000 16e0000 9100000; do
        p="$dev/$addr.interconnect"
        [ "$(basename "$(readlink "$p/driver")")" = qnoc-sm8250 ] || { echo "missing=$p"; exit 1; }
        echo "$addr qnoc-sm8250"
    done
    ;;
phy)
    bind_bus ufs-phy-lab
    [ "$(basename "$(readlink "$dev/1d87000.phy/driver")")" = qcom-qmp-ufs-phy ]
    echo '1d87000.phy qcom-qmp-ufs-phy'
    ;;
arm)
    mkdir -p "$inst"
    echo 1024 > "$inst/buffer_size_kb"
    echo 'cmd == 22' > "$inst/events/ufs/ufshcd_uic_command/filter"
    echo 1 > "$inst/events/ufs/ufshcd_uic_command/enable"
    echo 'r:rmxlink/link_return ufshcd_link_startup rc=$retval:s32' >> "$trace/kprobe_events"
    echo 1 > "$inst/events/rmxlink/link_return/enable"
    echo 1 > "$inst/tracing_on"
    cat "$inst/events/ufs/ufshcd_uic_command/format" | tail -n 10
    ;;
start)
    [ "$(cat "$inst/events/ufs/ufshcd_uic_command/enable")" = 1 ]
    bind_bus ufs-host-lab
    echo "host_driver=$(readlink "$hba/driver") iommu=$(readlink "$hba/iommu_group")"
    ;;
info)
    for f in "$hba"/power_info/*; do
        [ -f "$f" ] || continue
        echo "$(basename "$f")=$(cat "$f")"
    done
    ;;
descriptor)
    [ -e /sys/class/block/sda ]
    for f in number_of_luns specification_version; do
        [ ! -f "$hba/device_descriptor/$f" ] || echo "$f=$(cat "$hba/device_descriptor/$f")"
    done
    ;;
trace)
    grep -e 'link_return:' -e 'ufshcd_uic_command:' "$inst/trace" | tail -n 36
    ;;
disks)
    for d in /sys/class/block/sd?; do
        [ -e "$d" ] || { echo 'no SCSI disks'; exit 1; }
        real=$(readlink -f "$d")
        case "$real" in */1d84000.ufs/*) ;; *) exit 1 ;; esac
        name=$(basename "$d")
        node=/run/ufs-ro-$name
        if [ ! -b "$node" ]; then
            nums=$(cat "$d/dev")
            mknod "$node" b "$(echo "$nums" | cut -d: -f1)" "$(echo "$nums" | cut -d: -f2)"
        fi
        blockdev --setro "$node"
        [ "$(cat "$d/ro")" = 1 ]
        dd if="$node" of=/dev/null bs=4096 count=1
        echo "disk=$name scsi=$(basename "$(readlink -f "$d/device")") sectors=$(cat "$d/size") ro=$(cat "$d/ro")"
    done
    ;;
*) exit 2 ;;
esac
