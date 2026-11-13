#!/bin/busybox sh
# $1 is the sysfs block device of the already verified, read-only GSI target.
set -eu
case "$(cat /trial-id)" in ufs-host-g3-gsi17-firststage-*) ;; *) exit 2 ;; esac
d=$1
if [ "$d" != ufs ]; then
    [ "$(cat "$d/dm/name")" = rmx-gsi17-verity ]
    [ "$(cat "$d/ro")" = 1 ]
fi
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
# Android regenerates its own device nodes in its new /dev. fs_mgr consumes
# only the read-only dm-verity device created from the pinned GSI descriptor.
mode=observe
if [ "$d" = ufs ]; then
    mkdir "$root/avb"
    cp /system.avbpubkey /vendor.avbpubkey "$root/avb/"
    cp /ufs-fstab "$root/fstab.qcom"
    mode=observe-vendor
else
    echo "gsi_device=$(basename "$d") dev=$(cat "$d/dev")"
    printf '/dev/block/%s /system ext4 ro,noload wait,first_stage_mount\n' "$(basename "$d")" > "$root/fstab.qcom"
fi
if [ -f /project-vendor.img ]; then
    [ "$(basename "$d")" = dm-1 ]
    loop=/sys/class/block/loop0
    [ "$(readlink -f "$loop")" = /sys/devices/virtual/block/loop0 ]
    [ ! -e "$loop/loop/backing_file" ]
    n=$(cat "$loop/dev")
    mknod "$base/vendor-loop" b "${n%:*}" "${n#*:}"
    losetup -r "$base/vendor-loop" /project-vendor.img
    [ "$(cat "$loop/ro")" = 1 ]
    hash=$(sha256sum "$base/vendor-loop" | cut -d' ' -f1)
    [ "$hash" = "$(cat /project-vendor.sha256)" ]
    echo "vendor_device=loop0 dev=$n image_sha256=$hash"
    cp /project-vendor.fstab "$root/fstab.qcom"
    mode=observe-vendor
fi
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
# Check that the trace sees the correct exec before permitting the handoff.
if [ "${2:-}" = install ]; then
    [ "$mode" = observe-vendor ]
    case "$(cat /trial-id)" in ufs-host-g3-gsi17-firststage-vendor-load-*|ufs-host-g3-gsi17-firststage-ufs-*) ;; *) exit 2 ;; esac
    wd=/sys/class/watchdog/watchdog0
    case "$(readlink -f "$wd/device")" in */17c10000.qcom,wdt) ;; *) exit 1 ;; esac
    n=$(cat "$wd/dev")
    mknod "$base/watchdog" c "${n%:*}" "${n#*:}"
    echo 8 > /proc/sys/kernel/printk
    if [ "$d" = ufs ]; then
        echo "M1EVENT ufs_super=$(readlink -f /sys/class/block/sda10) dev=$(cat /sys/class/block/sda10/dev) ro=$(cat /sys/class/block/sda10/ro)" > /dev/ttyGS0
        /bin/ufs-init-trace
    fi
    if [ -f /m1-trace-fault ]; then
        trace=/run/m1/trace
        mkdir "$trace"
        mount -t tracefs tracefs "$trace"
        echo 0 > "$trace/tracing_on"
        echo 4 > "$trace/buffer_size_kb"
        for pair in 'filemap/mm_filemap_fault:common_pid == 1' \
                    'signal/signal_generate:sig == 7' 'sched/sched_process_exec:pid == 1' \
                    'block/block_bio_complete:error != 0'; do
            event=${pair%%:*}
            printf '%s\n' "${pair#*:}" > "$trace/events/$event/filter"
            echo 1 > "$trace/events/$event/enable"
        done
        echo 1 > /proc/sys/kernel/ftrace_dump_on_oops
        [ ! -w /proc/sys/debug/exception-trace ] || echo 1 > /proc/sys/debug/exception-trace
        [ ! -w /proc/sys/kernel/print-fatal-signals ] || echo 1 > /proc/sys/kernel/print-fatal-signals
    fi
    grep -E '^(boot_id|init_sha256|gsi_device|vendor_device|source_table|verity_table|last_block_sha256|seed_backing)=' \
        /run/gsi17-run.log | sed 's/^/M1EVENT /' > /dev/ttyGS0
    for disk in /sys/class/block/sd?; do
        echo "M1EVENT disk=$(basename "$disk") ro=$(cat "$disk/ro")" > /dev/ttyGS0
    done
    mode=observe-install
fi
/bin/first-stage-witness "$mode" > "$base/witness" 2>&1 &
observer=$!
for i in $(seq 1 5); do [ ! -f "$base/ready" ] || break; sleep 1; done
if [ ! -f "$base/ready" ]; then cat "$base/witness"; exit 1; fi
touch "$base/go"
for i in $(seq 1 240); do
    [ ! -f "$base/stopped" ] && kill -0 "$observer" || break
    sleep 1
done
cat "$base/witness"
echo "pid1_exe=$(readlink /proc/1/exe)"
echo "pid1_sha256=$(sha256sum /proc/1/exe | cut -d' ' -f1)"
awk '$5=="/" || $5=="/dev" || $5=="/vendor" || $5=="/system" {print "pid1_mountinfo=" $0}' /proc/1/mountinfo
if [ "$mode" = observe-vendor ] && [ -f /proc/1/root/vendor/etc/fstab.qcom ]; then
    [ -r /proc/1/root/vendor/etc/fstab.qcom ]
    hash=$(sha256sum /proc/1/root/vendor/etc/fstab.qcom | cut -d' ' -f1)
    [ "$hash" = "$(cat /project-vendor-fstab.sha256)" ]
    echo "mounted_vendor_fstab=match"
    echo "mounted_vendor_policy_version=$(cat /proc/1/root/vendor/etc/selinux/plat_sepolicy_vers.txt)"
    echo "pid1_cmdline=$(tr '\000' ' ' < /proc/1/cmdline)"
    if grep -qx 'trial_stop=policy-load-open' "$base/witness"; then
        # Recompile the mounted split policy with neverallow checks enabled.
        # Both outputs are inside the stopped init's /dev tmpfs.
        android=/proc/1/root
        version=$(cat "$android/vendor/etc/selinux/plat_sepolicy_vers.txt")
        genfs=$(cat "$android/vendor/etc/selinux/genfs_labels_version.txt")
        [ "$version" = 202604 ]
        [ "$genfs" = 202604 ]
        set -- /system/etc/selinux/plat_sepolicy.cil "/system/etc/selinux/mapping/$version.cil"
        for file in "/system/etc/selinux/mapping/$version.compat.cil" \
                /system_ext/etc/selinux/system_ext_sepolicy.cil "/system_ext/etc/selinux/mapping/$version.cil" \
                "/system_ext/etc/selinux/mapping/$version.compat.cil" /product/etc/selinux/product_sepolicy.cil \
                "/product/etc/selinux/mapping/$version.cil"; do
            [ ! -f "$android$file" ] || set -- "$@" "$file"
        done
        set -- "$@" /vendor/etc/selinux/plat_pub_versioned.cil /vendor/etc/selinux/vendor_sepolicy.cil \
            "/system/etc/selinux/plat_sepolicy_genfs_$genfs.cil"
        echo "strict_inputs=$*"
        mkdir "$android/dev/rmx-strict"
        rc=0
        env -i PATH=/system/bin LD_LIBRARY_PATH=/system/lib64/bootstrap:/system/lib64 \
            /bin/busybox chroot "$android" /system/bin/bootstrap/linker64 /system/bin/secilc \
            -m -M true -G -c 30 "$@" -o /dev/rmx-strict/policy -f /dev/rmx-strict/contexts \
            > "$base/strict.log" 2>&1 || rc=$?
        echo "strict_compile_rc=$rc"
        if [ "$rc" = 0 ]; then
            [ -s "$android/dev/rmx-strict/policy" ]
            echo "strict_policy_sha256=$(sha256sum "$android/dev/rmx-strict/policy" | cut -d' ' -f1)"
        else
            head -c 2000 "$base/strict.log"
        fi
        rm -f "$android/dev/rmx-strict/policy" "$android/dev/rmx-strict/contexts"
        rmdir "$android/dev/rmx-strict"
    fi
fi
dmesg | grep -E 'init: |libfs_mgr|EXT4-fs \((loop|dm-)|linker: |CANNOT LINK|libc: ' | tail -100
[ -f "$base/stopped" ]
