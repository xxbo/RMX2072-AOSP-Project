#!/bin/busybox sh
# Live F.20 vbmeta identity, dm-verity, read-only mounts and a wrong-root control.
set -eu
case "$(uname -r):$(cat /trial-id)" in 6.18.*:ufs-host-g3-super-verity-*|6.18.*:ufs-host-g3-gsi17-*) ;; *) exit 2 ;; esac
[ "$(cat /sys/class/udc/*/state)" = configured ]
[ "$(od -An -tx1 /sys/firmware/devicetree/base/oplus,dtsi_no | xargs)" = '00 00 50 7f' ]
base=/run/rmx-super
profile=/verity-profile
mkdir -p "$base"
dm() {
    /bin/lp/ld-musl-aarch64.so.1 --library-path /bin/lp /bin/lp/dmsetup --noudevsync --noudevrules "$@"
}
device() {
    for p in /sys/class/block/dm-*; do
        if [ -r "$p/dm/name" ] && [ "$(cat "$p/dm/name")" = "$1" ]; then echo "$p"; return 0; fi
    done
    return 1
}
blocknode() {
    nums=$(cat "$1/dev")
    mknod "$2" b "${nums%:*}" "${nums#*:}"
}
if [ "$1" = metadata ]; then
    while read -r label expected; do
        case "$label" in vbmeta) p=/sys/class/block/sde18 ;; vbmeta_system) p=/sys/class/block/sde16 ;;
            vbmeta_vendor) p=/sys/class/block/sde17 ;; *) exit 1 ;; esac
        [ "$(sed -n 's/^PARTNAME=//p' "$p/uevent")" = "$label" ]
        case "$(readlink -f "$p")" in */1d84000.ufs/*) ;; *) exit 1 ;; esac
        [ "$(cat "$p/size")" = 128 ]
        node="$base/avb-$label"
        [ ! -e "$node" ] || rm -f "$node"
        blocknode "$p" "$node"
        blockdev --setro "$node"
        readback=$(sha256sum "$node")
        [ "${readback%% *}" = "$expected" ]
        echo "vbmeta=$label sha256=$expected"
        rm -f "$node"
    done < "$profile/vbmeta-hashes"
    echo verified > "$base/vbmeta-checked"
    exit 0
fi

name=$1
case "$name" in system|vendor|product|odm) ;; *) exit 2 ;; esac
[ "$(cat "$base/vbmeta-checked")" = verified ]
lp=$(device "rmx-lp-$name")
[ "$(cat "$lp/ro")" = 1 ] && [ "$(cat "$lp/dev")" = "$3" ] && [ -b "$2" ]
backing=$3
if [ "$name" = odm ]; then
    read -r size footer page page_hash key < "$profile/odm-source"
    [ "$(cat "$lp/size")" -eq "$((size/512))" ]
    hash=$(sha256sum "$base/mnt-vendor/etc/oplus_avb.pubkey")
    [ "${hash%% *}" = "$key" ]
    for block in "$((size/4096-1)):$footer" "$page:$page_hash"; do
        dd if="$2" of="$base/odm-page" bs=4096 count=1 skip="${block%:*}"
        hash=$(sha256sum "$base/odm-page")
        [ "${hash%% *}" = "${block#*:}" ]
    done
    echo "odm_signer=$key"
fi
read -r sectors db hb blocks start alg root salt fec roots fs expected < "$profile/$name"
target=rmx-verity-$name
bad=rmx-verity-reject-$name
mnt="$base/mnt-$name"
node="$base/checked-$name"
badnode="$base/reject-$name"
for t in "$target" "$bad"; do if device "$t" >/dev/null; then exit 1; fi; done
mkdir "$mnt"
cleanup() {
    rc=$?
    trap - EXIT
    if awk -v m="$mnt" '$2==m {found=1} END {exit !found}' /proc/mounts; then umount "$mnt" || rc=1; fi
    for t in "$bad" "$target"; do
        if device "$t" >/dev/null; then dm remove "$t" || rc=1; fi
        if device "$t" >/dev/null; then rc=1; fi
    done
    rm -f "$badnode" "$node"
    rmdir "$mnt" || rc=1
    echo "verity_cleanup=$name rc=$rc"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

prefix="0 $sectors verity 1 $backing $backing $db $hb $blocks $start $alg"
dm create "$target" --readonly --table "$prefix $root $salt 8 use_fec_from_device $backing fec_blocks $fec fec_start $fec fec_roots $roots"
d=$(device "$target")
[ "$(cat "$d/ro")" = 1 ] && [ "$(cat "$d/size")" = "$sectors" ]
blocknode "$d" "$node"
echo "verity_table=$name $(dm table "$target")"
result=$(sha256sum "$node")
[ "${result%% *}" = "$expected" ]
echo "verified=$name sectors=$sectors sha256=$expected"
case "$fs" in ext4) opts=ro,noload,nodev,nosuid,noexec ;; erofs) opts=ro,nodev,nosuid,noexec ;; *) exit 2 ;; esac
mount -t "$fs" -o "$opts" "$node" "$mnt"
awk -v m="$mnt" -v dev="$(cat "$d/dev")" -v fs="$fs" '
    $5==m && $3==dev && $6 ~ /^ro(,|$)/ {
        for (i=7;i<NF;i++) if ($i=="-" && $(i+1)==fs) {print "mounted="m" fs="fs" dev="dev" options="$6; found=1}
    } END {exit !found}' /proc/self/mountinfo
while read -r wanted rel; do
    resolved=$(readlink -f "$mnt/$rel")
    case "$resolved" in "$mnt"/*) ;; *) exit 1 ;; esac
    [ -f "$resolved" ]
    actual=$(sha256sum "$resolved")
    [ "${actual%% *}" = "$wanted" ]
    echo "file=$name/$rel sha256=$wanted"
done < "$profile/$name.files"
if [ "${4:-}" = combined ]; then
    case "$name" in
    vendor) /bin/verity-readonly odm "$base/read-odm" "$(cat "$(device rmx-lp-odm)/dev")" combined ;;
    odm) /bin/verity-readonly system "$base/read-system" "$(cat "$(device rmx-lp-system)/dev")" combined ;;
    system) /bin/gsi17-policy ;;
    *) exit 2 ;;
    esac
fi
umount "$mnt"
health=$(dm status "$target")
[ "$(echo "$health" | awk '{print $4}')" = V ]
echo "health=$name $health"
if [ "$name" = product ]; then
    # Use a distinct fresh dm target and the default EIO policy. Only the
    # RAM-side root differs. O_DIRECT avoids the positive target's page cache.
    case "$root" in 0*) wrong=1${root#?} ;; *) wrong=0${root#?} ;; esac
    dm create "$bad" --readonly --table "$prefix $wrong $salt"
    d=$(device "$bad")
    [ "$(cat "$d/ro")" = 1 ]
    blocknode "$d" "$badnode"
    read_rc=0
    dd if="$badnode" of=/dev/null bs=4096 count=1 iflag=direct 2>"$base/reject-log" || read_rc=$?
    echo "reject_read_rc=$read_rc"
    grep -F -e 'I/O error' -e 'Input/output error' "$base/reject-log"
    health=$(dm status "$bad")
    echo "reject_status=$health"
    [ "$read_rc" -ne 0 ]
    [ "$(echo "$health" | awk '{print $4}')" = C ]
    echo "wrong_root=$name read=EIO health=C"
fi
