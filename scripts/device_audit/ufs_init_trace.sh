#!/bin/busybox sh
# Offsets verified from the exact 6.18.32 Image BTF. The inode numbers belong
# to CP3A.260905.010. Correlate the filesystem device with the PID 1 mounts.
set -eu
event_sink=/dev/ttyGS0
[ ! -f /m1-autoboot ] || event_sink=/run/m1-autoboot.events
t=/sys/kernel/debug/tracing
i=$t/instances/m1reads
if [ "${1:-}" = layers ]; then
    case "$2" in system|vendor) ;; *) exit 2 ;; esac
    dm() { /bin/lp/ld-musl-aarch64.so.1 --library-path /bin/lp /bin/lp/dmsetup --noudevsync --noudevrules "$@"; }
    name=$2
    node=$3
    actual=$(cat "/sys/class/block/$node/dm/name")
    linear=$(dm table "$name")
    verity=$(dm table "$actual")
    status=$(dm status "$actual")
    echo "$linear" | sed "s/^/M1EVENT table=$name /" >> "$event_sink"
    echo "M1EVENT table=$actual $verity" >> "$event_sink"
    echo "M1EVENT status=$actual $status" >> "$event_sink"
    super=$(cat /sys/class/block/sda10/dev)
    echo "$linear" | awk -v backing="$super" '$3 != "linear" || $4 != backing { exit 1 }'
    set -- $verity
    [ "$3" = verity ]
    [ "$4" = 1 ]
    [ "$5" = "$6" ]
    [ "$(cat "/sys/dev/block/$5/dm/name")" = "$name" ]
    echo "M1EVENT linear_mapper=$name dev=$5" >> "$event_sink"
    [ "${12}" = "$(cat "/$name.verity-root")" ]
    [ "$(cat "/sys/class/block/$node/ro")" = 1 ]
    echo "M1EVENT verified_ufs_mount=$name dev=$(cat "/sys/class/block/$node/dev")" >> "$event_sink"
    if [ "$name" = vendor ]; then
        root=/proc/1/root
        filter='common_pid == 1 && (ino == 659 || ino == 757'
        for file in init.zygote64_32.rc init.zygote64.rc init.boringssl.zygote64_32.rc; do
            path="/system/etc/init/hw/$file"
            inode=$(stat -c %i "$root$path")
            echo "M1EVENT read_target=$path ino=$inode bytes=$(stat -c %s "$root$path")" >> "$event_sink"
            filter="$filter || ino == $inode"
        done
        dev=$(cat "/sys/class/block/$node/dev")
        inode=$(stat -c %i "$root/vendor/etc/fstab.qcom")
        bytes=$(stat -c %s "$root/vendor/etc/fstab.qcom")
        echo "M1EVENT read_target=/vendor/etc/fstab.qcom ino=$inode bytes=$bytes" >> "$event_sink"
        # Capture all readers of this specific vendor inode. Attribute the read
        # to vold using the PID logged by Android init on the same boot.
        echo "($filter)) || (dev == $(( (${dev%:*} << 20) | ${dev#*:} )) && ino == $inode)" > "$i/events/m1reads/m1_file_read/filter"
        if [ -x /bin/ufs-scratch ]; then /bin/busybox sh -x /bin/ufs-scratch >> "$event_sink" 2>&1; fi
    fi
    exit 0
fi
mkdir -p /dev/mapper
ctl=$(cat /sys/class/misc/device-mapper/dev)
[ -c /dev/mapper/control ] || mknod /dev/mapper/control c "${ctl%:*}" "${ctl#*:}"
mkdir "$i"
echo 'r:m1reads/m1_file_read vfs_read ino=+64(+32($arg1)):u64 dev=+16(+40(+32($arg1))):u32 count=$arg3:u64 result=$retval:s64' >> "$t/kprobe_events"
# Limit printk to these two files and to PID 1. Disable earlier UFS link
# startup probes before enabling trace-to-printk in this diagnostic boot.
echo 0 > "$t/instances/rmxlink/events/enable"
echo 'common_pid == 1 && (ino == 659 || ino == 757)' > "$i/events/m1reads/m1_file_read/filter"
echo 1 > "$i/events/m1reads/m1_file_read/enable"
echo 1 > "$i/tracing_on"
echo 1 > /proc/sys/kernel/tracepoint_printk
[ "$(cat /proc/sys/kernel/tracepoint_printk)" = 1 ]
echo 'M1EVENT read_trace=pid1 inode=659,757 sink=printk' >> "$event_sink"
