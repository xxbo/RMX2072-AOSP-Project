#!/bin/busybox sh
# $1 is the sysfs block device of the already verified, read-only GSI target.
set -eu
case "$(cat /trial-id)" in ufs-host-g3-gsi17-firststage-*) ;; *) exit 2 ;; esac
d=$1
[ "$(cat "$d/dm/name")" = rmx-gsi17-verity ] && [ "$(cat "$d/ro")" = 1 ]
base=/run/m1
root=$base/root
mkdir "$base"
mkdir "$root"
mount -t tmpfs -o mode=0755 tmpfs "$root"
for dir in dev proc sys metadata mnt debug_ramdisk second_stage_resources system first_stage_ramdisk; do
    mkdir "$root/$dir"
done
cp /android-first-stage "$root/init"
chmod 0755 "$root/init"
cmp /android-first-stage "$root/init"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)"
echo "init_sha256=$(sha256sum "$root/init" | cut -d' ' -f1)"
echo "gsi_device=$(basename "$d") dev=$(cat "$d/dev")"
# Android regenerates its own device nodes in its new /dev. fs_mgr consumes
# only the read-only dm-verity device created from the pinned GSI descriptor.
printf '/dev/block/%s /system ext4 ro,noload wait,first_stage_mount\n' "$(basename "$d")" > "$root/fstab.qcom"
cp "$root/fstab.qcom" "$root/fstab.default"
cp "$root/fstab.qcom" "$root/first_stage_ramdisk/fstab.qcom"
cp "$root/fstab.default" "$root/first_stage_ramdisk/fstab.default"
cat "$root/fstab.qcom"
for step in preflight fabric phy arm start; do /bin/ufs-host-test "$step" > "$base/ufs-$step" 2>&1; done
for i in $(seq 1 12); do [ ! -e /sys/class/block/sdf ] || break; sleep 1; done
[ -e /sys/class/block/sdf ]
/bin/ufs-host-test disks
# Cover individual partitions too. No writable UFS block device is required.
for part in /sys/class/block/sd*; do
    case "$(readlink -f "$part")" in */1d84000.ufs/*) ;; *) exit 1 ;; esac
    n=$(cat "$part/dev")
    mknod "$base/ro-node" b "${n%:*}" "${n#*:}"
    blockdev --setro "$base/ro-node"
    [ "$(cat "$part/ro")" = 1 ]
    rm "$base/ro-node"
done
/bin/first-stage-witness observe > "$base/witness" 2>&1 &
observer=$!
for i in $(seq 1 5); do [ ! -f "$base/ready" ] || break; sleep 1; done
if [ ! -f "$base/ready" ]; then cat "$base/witness"; exit 1; fi
touch "$base/go"
for i in $(seq 1 110); do
    [ ! -f "$base/stopped" ] && kill -0 "$observer" || break
    sleep 1
done
cat "$base/witness"
echo "pid1_exe=$(readlink /proc/1/exe)"
echo "pid1_sha256=$(sha256sum /proc/1/exe | cut -d' ' -f1)"
awk '$5=="/dev" || $5=="/system" {print "pid1_mountinfo=" $0}' /proc/1/mountinfo
dmesg | grep -E 'init: |libfs_mgr|EXT4-fs \(dm-' | tail -80
[ -f "$base/stopped" ]
