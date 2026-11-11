#!/bin/busybox sh
# Called while the three verified filesystems are live. Keep logs in the ramdisk.
set -eu
base=/run/gsi17
root=$base/mnt
cleanup() {
    rc=$?
    trap - EXIT
    for part in system/etc/selinux/mapping system/bin/secilc sys dev proc odm vendor; do
        if awk -v m="$root/$part" '$2==m {ok=1} END {exit !ok}' /proc/mounts; then
            umount "$root/$part" || rc=1
        fi
    done
    echo "policy_cleanup=$rc"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
for part in vendor odm; do
    [ -d "$root/$part" ] && [ ! -L "$root/$part" ]
    mount -o bind "/run/rmx-super/mnt-$part" "$root/$part"
    awk -v m="$root/$part" '$2==m && $3=="erofs" && $4 ~ /^ro(,|$)/ {print "combined_mount="m" fs="$3" options="$4; ok=1} END {exit !ok}' /proc/mounts
done
mount -t proc -o ro,nodev,nosuid,noexec proc "$root/proc"
mount -t tmpfs -o nosuid,noexec,mode=1777,size=16m tmpfs "$root/dev"
mknod -m 666 "$root/dev/null" c 1 3
# Android init directs the compiler's file_contexts output to this null
# device. Expose only the sink, without mounting the global SELinux filesystem.
mount -t tmpfs -o nosuid,noexec,size=64k tmpfs "$root/sys"
mkdir -p "$root/sys/fs/selinux"
mknod -m 666 "$root/sys/fs/selinux/null" c 1 3
touch "$root/dev/kmsg"
chmod 666 "$root/dev/kmsg"
version=$(cat "$root/vendor/etc/selinux/plat_sepolicy_vers.txt")
[ "$version" = 30.0 ]
echo "vendor_policy_version=$version"
mapping="/system/etc/selinux/mapping/$version.cil"
if [ -e "$root$mapping" ]; then echo "mapping=present"; else echo "mapping=absent path=$mapping"; fi
for item in system/etc/selinux/plat_sepolicy_and_mapping.sha256 odm/etc/selinux/precompiled_sepolicy.plat_sepolicy_and_mapping.sha256; do
    printf 'policy_id=%s %s\n' "$item" "$(cat "$root/$item")"
done
gsi() {
    /bin/busybox env -i PATH=/system/bin LD_LIBRARY_PATH=/system/lib64/bootstrap:/system/lib64 \
        /bin/busybox chroot "$root" /system/bin/bootstrap/linker64 "$@" </dev/null
}
gsi /system/bin/toybox cat /vendor/etc/selinux/plat_sepolicy_vers.txt > "$base/android-vendor-version"
cmp "$base/android-vendor-version" "$root/vendor/etc/selinux/plat_sepolicy_vers.txt"
gsi /system/bin/toybox cat /odm/build.prop > "$base/android-odm.prop"
cmp "$base/android-odm.prop" "$root/odm/build.prop"
echo "android_read_vendor_odm=match"
# The original 0700 secilc is executable only by root. A byte-identical RAM
# copy lets the restricted init process exec the compiler at its normal path.
cp "$root/system/bin/secilc" "$base/probe-secilc"
cmp "$base/probe-secilc" "$root/system/bin/secilc"
chmod 0555 "$base/probe-secilc"
mount -o bind "$base/probe-secilc" "$root/system/bin/secilc"
mount -o remount,bind,ro,nosuid,nodev "$root/system/bin/secilc"
echo "probe_compiler_sha256=$(sha256sum "$base/probe-secilc" | cut -d' ' -f1)"
run_init() {
    : > "$root/dev/kmsg"
    rc=0
    timeout -s KILL 45 /bin/gsi-init-probe </dev/null > "$base/init-stderr" 2>&1 || rc=$?
    echo "$1_rc=$rc"
    cat "$base/init-stderr"
    head -c 32000 "$root/dev/kmsg"
    echo
}
run_init init_selinux_setup
rc=0
gsi /system/bin/secilc -m -M true -G -c 30 /system/etc/selinux/plat_sepolicy.cil "$mapping" \
    /vendor/etc/selinux/plat_pub_versioned.cil /vendor/etc/selinux/vendor_sepolicy.cil \
    -o /dev/probe.policy -f /dev/null > "$base/compiler" 2>&1 || rc=$?
echo "secilc_rc=$rc"
cat "$base/compiler"

# Test whether F.20's original platform mappings alone can bridge this GSI.
# The underlying ext4 mount and two signed images remain read-only.
dir=system/etc/selinux/mapping
mkdir -p "$base/test-mapping"
cp -R "$root/$dir/." "$base/test-mapping/"
for file in 30.0.cil 30.0.compat.cil; do
    cp "/run/rmx-super/mnt-system/$dir/$file" "$base/test-mapping/$file"
    echo "f20_mapping=$file sha256=$(sha256sum "$base/test-mapping/$file" | cut -d' ' -f1)"
done
mount -o bind "$base/test-mapping" "$root/$dir"
mount -o remount,bind,ro,nosuid,nodev,noexec "$root/$dir"
run_init init_with_f20_mapping
rc=0
gsi /system/bin/secilc -m -M true -G -c 30 /system/etc/selinux/plat_sepolicy.cil "$mapping" \
    /system/etc/selinux/mapping/30.0.compat.cil /system_ext/etc/selinux/system_ext_sepolicy.cil \
    /product/etc/selinux/product_sepolicy.cil /vendor/etc/selinux/plat_pub_versioned.cil \
    /vendor/etc/selinux/vendor_sepolicy.cil -o /dev/comparison.policy -f /dev/null \
    > "$base/comparison-compiler" 2>&1 || rc=$?
echo "comparison_compiler_rc=$rc"
# Preserve one location per reported neverallow plus its first matching allow.
# Large raw CIL expressions add little to the diagnostic console transcript.
awk '
    /^neverallow check failed at / {where=$NF; count++; next}
    where && /^    allow at / {print "conflict="where" allow="$3" source="$NF; where=""}
    END {print "neverallow_reports="count+0}
' "$base/comparison-compiler"
if ! grep -q '^neverallow check failed at ' "$base/comparison-compiler"; then
    head -c 2000 "$base/comparison-compiler"
    echo
fi
if [ "$rc" = 0 ]; then
    [ -s "$root/dev/comparison.policy" ]
    echo "comparison_policy_sha256=$(sha256sum "$root/dev/comparison.policy" | cut -d' ' -f1)"
fi
