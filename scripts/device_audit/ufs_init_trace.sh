#!/bin/busybox sh
# Offsets verified from the exact 6.18.32 Image BTF. The inode numbers belong
# to CP3A.260905.010. Correlate the filesystem device with the PID 1 mounts.
set -eu
if [ "${1:-}" = layers ]; then
    case "$2" in system|vendor) ;; *) exit 2 ;; esac
    dm() { /bin/lp/ld-musl-aarch64.so.1 --library-path /bin/lp /bin/lp/dmsetup --noudevsync --noudevrules "$@"; }
    name=$2
    node=$3
    actual=$(cat "/sys/class/block/$node/dm/name")
    linear=$(dm table "$name")
    verity=$(dm table "$actual")
    status=$(dm status "$actual")
    echo "$linear" | sed "s/^/M1EVENT table=$name /" > /dev/ttyGS0
    echo "M1EVENT table=$actual $verity" > /dev/ttyGS0
    echo "M1EVENT status=$actual $status" > /dev/ttyGS0
    super=$(cat /sys/class/block/sda10/dev)
    echo "$linear" | awk -v backing="$super" '$3 != "linear" || $4 != backing { exit 1 }'
    set -- $verity
    [ "$3" = verity ]
    [ "$4" = 1 ]
    [ "$5" = "$6" ]
    [ "$(cat "/sys/dev/block/$5/dm/name")" = "$name" ]
    [ "${12}" = "$(cat "/$name.verity-root")" ]
    [ "$(cat "/sys/class/block/$node/ro")" = 1 ]
    echo "M1EVENT verified_ufs_mount=$name dev=$(cat "/sys/class/block/$node/dev")" > /dev/ttyGS0
    exit 0
fi
t=/sys/kernel/debug/tracing
mkdir -p /dev/mapper
ctl=$(cat /sys/class/misc/device-mapper/dev)
[ -c /dev/mapper/control ] || mknod /dev/mapper/control c "${ctl%:*}" "${ctl#*:}"
i=$t/instances/m1reads
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
echo 'M1EVENT read_trace=pid1 inode=659,757 sink=printk' > /dev/ttyGS0
