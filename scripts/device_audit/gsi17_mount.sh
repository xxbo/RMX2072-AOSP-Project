#!/bin/busybox sh
# The USB-backed dm-user target represents the entire pinned GSI. The mount
# reads the ext4 data area through the signed SHA-256 hashtree.
set -eu
case "$(uname -r):$(cat /trial-id)" in 6.18.*:ufs-host-g3-gsi17-*) ;; *) exit 2 ;; esac
[ "$(cat /sys/class/udc/*/state)" = configured ]
[ "$(od -An -tx1 /sys/firmware/devicetree/base/oplus,dtsi_no | xargs)" = '00 00 50 7f' ]
base=/run/gsi17
tty=/dev/ttyGS0
raw=rmx-gsi17-source
verified=rmx-gsi17-verity
seeded=rmx-gsi17-seeded
dm() { /bin/lp/ld-musl-aarch64.so.1 --library-path /bin/lp /bin/lp/dmsetup --noudevsync --noudevrules "$@"; }
device() {
    for d in /sys/class/block/dm-*; do
        if [ -r "$d/dm/name" ] && [ "$(cat "$d/dm/name")" = "$1" ]; then echo "$d"; return 0; fi
    done
    return 1
}
make_node() {
    numbers=$(cat "$1")
    mknod "$2" "$3" "${numbers%:*}" "${numbers#*:}"
}

read -r image_bytes data_bytes block_size tree_start root_hash salt < /gsi17-table
mode=${1:-mount}
case "$mode" in
    mount|userspace|combined) ;;
    firststage) [ -x /bin/first-stage-mount ] ;;
    install) case "$(cat /trial-id)" in ufs-host-g3-gsi17-firststage-vendor-load-*) ;; *) exit 2 ;; esac ;;
    *) exit 2 ;;
esac
mkdir -p /dev/mapper "$base"
[ -c /dev/mapper/control ] || make_node /sys/class/misc/device-mapper/dev /dev/mapper/control c
for n in "$raw" "$verified"; do if device "$n" >/dev/null; then exit 1; fi; done
mkdir "$base/lock"
saved=$(stty -g < "$tty")
backend=
cleanup() {
    rc=$?
    trap - EXIT
    if awk -v m="$base/mnt/proc" '$2==m {ok=1} END {exit !ok}' /proc/mounts; then umount "$base/mnt/proc" || rc=1; fi
    if awk -v m="$base/mnt" '$2==m {ok=1} END {exit !ok}' /proc/mounts; then umount "$base/mnt" || rc=1; fi
    if device "$verified" >/dev/null; then dm remove "$verified" || rc=1; fi
    if device "$seeded" >/dev/null; then dm remove "$seeded" || rc=1; fi
    if [ -b "$base/seed-loop" ]; then losetup -d "$base/seed-loop" || rc=1; fi
    if [ -n "$backend" ]; then kill "$backend" 2>/dev/null || :; wait "$backend" 2>/dev/null || :; fi
    if device "$raw" >/dev/null; then dm remove "$raw" || rc=1; fi
    stty "$saved" < "$tty" || rc=1
    for n in "$raw" "$verified"; do if device "$n" >/dev/null; then rc=1; fi; done
    rm -f "$base/verified" "$base/channel" "$base/source" "$base/footer"
    rmdir "$base/lock" || rc=1
    echo "cleanup=$rc"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
mkdir -p "$base/mnt"
dm version
dm targets | awk '$1=="user" {print; found=1} END {exit !found}'
dm create "$raw" --readonly --table "0 $((image_bytes/512)) user 0 0 $raw"
source=$(device "$raw")
[ "$(cat "$source/ro")" = 1 ]
[ "$(cat "$source/size")" = "$((image_bytes/512))" ]
echo 0 > "$source/queue/read_ahead_kb"
if [ -c "/dev/dm-user/$raw" ]; then
    channel="/dev/dm-user/$raw"
else
    channel="$base/channel"
    make_node "/sys/class/misc/dm-user!$raw/dev" "$channel" c
fi
stty raw -echo min 1 time 0 < "$tty"
# READ requests and optional M1EVENT records each occupy one complete line.
( exec /bin/gsi-usb-reader "$channel" "$tty" "$image_bytes" ) > "$base/backend.log" 2>&1 &
backend=$!
dev=$(cat "$source/dev")
make_node "$source/dev" "$base/source" b
dd if="$base/source" of="$base/footer" bs=4096 skip=$((image_bytes/4096-1)) count=1 iflag=direct
footer=$(sha256sum "$base/footer")
echo "last_block_sha256=${footer%% *}"
if [ -f /gsi-seed.blocks ]; then
    [ "$mode" = install ]
    loop=/sys/class/block/loop1
    [ ! -e "$loop/loop/backing_file" ]
    make_node "$loop/dev" "$base/seed-loop" b
    losetup -r "$base/seed-loop" /gsi-seed.blocks
    [ "$(cat "$loop/ro")" = 1 ]
    # Uncached sectors still use the original USB backend. The original GSI
    # verity descriptor checks both sources above this read-only linear table.
    awk -v src="$dev" -v ram="$(cat "$loop/dev")" -v size="$((image_bytes/512))" '
        BEGIN { end=0; used=0 }
        { first=$1*8; len=$2*8; if (first>end) print end,first-end,"linear",src,end;
          print first,len,"linear",ram,used+0; end=first+len; used+=len }
        END { if (end<size) print end,size-end,"linear",src,end }' /gsi-seed.ranges > "$base/seed.table"
    dm_major=${dev%:*}
    dm create "$seeded" --major "$dm_major" --minor 2 --readonly < "$base/seed.table"
    seeddev=$(device "$seeded")
    [ "$(cat "$seeddev/ro")" = 1 ]
    [ "$(cat "$seeddev/size")" = "$((image_bytes/512))" ]
    dev=$(cat "$seeddev/dev")
    echo "seed_backing=$dev ram=$(cat "$loop/dev") sectors=$(cat "$loop/size") ranges_sha256=$(sha256sum /gsi-seed.ranges | cut -d' ' -f1)"
fi
blocks=$((data_bytes/block_size))
if [ -w /sys/module/dm_verity/parameters/prefetch_cluster ]; then
    echo 4096 > /sys/module/dm_verity/parameters/prefetch_cluster
fi
set --
if [ -f /gsi-seed.blocks ]; then set -- --major "$dm_major" --minor 1; fi
dm create "$verified" "$@" --readonly --table "0 $((data_bytes/512)) verity 1 $dev $dev $block_size $block_size $blocks $tree_start sha256 $root_hash $salt"
d=$(device "$verified")
[ "$(cat "$d/ro")" = 1 ]
echo 0 > "$d/queue/read_ahead_kb"
make_node "$d/dev" "$base/verified" b
echo "source_table=$(dm table "$raw")"
echo "verity_table=$(dm table "$verified")"
if [ "$mode" = firststage ] || [ "$mode" = install ]; then
    # Android owns any resulting mount. Leave the verified map pinned until EDL.
    /bin/first-stage-mount "$d" "$mode" || result=$?
    status=$(dm status "$verified")
    echo "verity_status=$status"
    if [ -f /run/m1/go ]; then
        trap - EXIT
        kill "$backend" 2>/dev/null || :
        stty "$saved" < "$tty"
    fi
    exit "${result:-0}"
fi
opts=ro,noload,nodev,nosuid
[ "$mode" != mount ] || opts="$opts,noexec"
mount -t ext4 -o "$opts" "$base/verified" "$base/mnt"
awk -v m="$base/mnt" -v dev="$(cat "$d/dev")" '$5==m && $3==dev && $6 ~ /^ro(,|$)/ {
    for (i=7;i<NF;i++) if ($i=="-" && $(i+1)=="ext4") {print "mounted="m" fs=ext4 options="$6; found=1}
} END {exit !found}' /proc/self/mountinfo
while read -r expected path; do
    resolved=$(readlink -f "$base/mnt/$path")
    case "$resolved" in "$base"/mnt/*) ;; *) exit 1 ;; esac
    hash=$(sha256sum "$resolved")
    [ "${hash%% *}" = "$expected" ]
    echo "file=$path sha256=$expected"
done < /gsi17-files
prop="$base/mnt/system/build.prop"
for value in ro.system.build.version.release=17 ro.system.build.version.sdk=37 ro.system.build.id=CP3A.260905.010; do
    grep -Fx "$value" "$prop"
done
grep '^ro.system.build.fingerprint=' "$prop"
if [ "$mode" = combined ]; then
    for step in preflight fabric phy arm start; do /bin/ufs-host-test "$step"; done
    for attempt in 1 2 3 4 5 6 7 8 9 10; do [ -e /sys/class/block/sdf ] && break; sleep 1; done
    [ -e /sys/class/block/sdf ]
    /bin/ufs-host-test disks
    /bin/super-readonly metadata > "$base/lp.log"
    /bin/verity-readonly metadata
    /bin/super-readonly combined
elif [ "$mode" = userspace ]; then
    # Bionic's bootstrap linker uses /proc/self/exe. Binder, Android properties,
    # vendor and writable storage are outside this isolated root.
    mount -t proc -o ro,nodev,nosuid,noexec proc "$base/mnt/proc"
    run_gsi() {
        /bin/busybox env -i PATH=/system/bin LD_LIBRARY_PATH=/system/lib64/bootstrap:/system/lib64 \
            /bin/busybox chroot "$base/mnt" /system/bin/bootstrap/linker64 "$@" </dev/null
    }
    release=$(run_gsi /system/bin/toybox uname -r)
    [ "$release" = "$(uname -r)" ]
    echo "android_toybox_uname=$release"
    run_gsi /system/bin/toybox cat /system/build.prop > "$base/android-build.prop"
    cmp "$base/android-build.prop" "$prop"
    echo "android_toybox_read=match"
    init_rc=0
    run_gsi --list /system/bin/init > "$base/init-libraries" 2>&1 || init_rc=$?
    echo "init_link_list_rc=$init_rc"
    cat "$base/init-libraries"
    umount "$base/mnt/proc"
fi
status=$(dm status "$verified")
[ "$(echo "$status" | awk '{print $4}')" = V ]
echo "verity_status=$status"
