#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${RUNNER_TEMP:?}/rmx2072-m2-aosp"
ARTIFACT_DIR="$ROOT_DIR/artifacts/m2-first-stage"
mkdir -p "$SOURCE_DIR" "$ARTIFACT_DIR"
python3 "$ROOT_DIR/scripts/build/prepare_m2_aosp_manifest.py" --output "$ARTIFACT_DIR/selected.xml"
cd "$SOURCE_DIR"
repo init -u https://android.googlesource.com/platform/manifest -b android-17.0.0_r1 --depth=1 --no-clone-bundle
cp "$ARTIFACT_DIR/selected.xml" .repo/manifests/rmx2072-minimal.xml
ln -sfn manifests/rmx2072-minimal.xml .repo/manifest.xml
repo sync -c -j4 --no-tags --no-clone-bundle 2>&1 | tee "$ARTIFACT_DIR/sync.log"
# This project supplies one owner declaration referenced by frameworks/native.
# Keep its actual pinned Git blob, without parsing unrelated framework targets.
git -C frameworks/base sparse-checkout set --no-cone /core/java/android/hardware/serial/Android.bp
git -C frameworks/base sparse-checkout list > "$ARTIFACT_DIR/frameworks-base-sparse.txt"
git -C packages/services/Car sparse-checkout set --no-cone /teams/Android.bp
git -C packages/services/Car sparse-checkout list > "$ARTIFACT_DIR/car-sparse.txt"
# APEX Java test payloads require the full Android framework and are unrelated
# to init's native libapexd_flags. Keep the implementation, omit only test data.
git -C system/apex sparse-checkout set --no-cone '/*' '!/apexd/apexd_testdata/'
git -C system/apex sparse-checkout list > "$ARTIFACT_DIR/apex-sparse.txt"
repo manifest -r -o "$ARTIFACT_DIR/resolved-manifest.xml"
test "$(git -C system/core rev-parse HEAD)" = 545d2487e38192a2ce25040897ced877cf6b4f53
mkdir -p device/realme/rmx2072_m2
cp "$ROOT_DIR/device/realme/bladerunner_48m/m2-init/"* device/realme/rmx2072_m2/
{
  git -C "$ROOT_DIR" rev-parse HEAD
  date -u +%FT%TZ
  df -h .
  free -h
} > "$ARTIFACT_DIR/build-host.txt"
# Unrelated modules in the selected source projects are not built. Missing
# dependencies of init_first_stage itself remain fatal Ninja build edges.
export ALLOW_MISSING_DEPENDENCIES=true
export SOONG_UI_NINJA_ARGS=-v
for attempt in $(seq 1 12); do
  # Run each attempt in a subshell so envsetup cannot retain a failed product.
  set +e
  bash -c 'set -eo pipefail; source build/envsetup.sh; lunch rmx2072_m2_init-aosp_current-user; m -j2 init_first_stage' \
    2>&1 | tee "$ARTIFACT_DIR/build-$attempt.log"
  result=${PIPESTATUS[0]}
  set -e
  if [[ "$result" == 0 ]]; then break; fi
  python3 "$ROOT_DIR/scripts/build/complete_m2_workspace.py" \
    --workspace "$SOURCE_DIR" --upstream "$ARTIFACT_DIR/selected.upstream.xml" \
    --log "$ARTIFACT_DIR/build-$attempt.log" --record "$ARTIFACT_DIR/dependency-additions.jsonl"
done
test "$result" == 0
repo manifest -r -o "$ARTIFACT_DIR/resolved-manifest.xml"
INIT=out/target/product/rmx2072_m2/ramdisk/init
test -s "$INIT"
cp "$INIT" "$ARTIFACT_DIR/init"
file "$INIT" > "$ARTIFACT_DIR/elf.txt"
readelf -h -l "$INIT" >> "$ARTIFACT_DIR/elf.txt"
! readelf -l "$INIT" | grep -q INTERP
grep -q AArch64 "$ARTIFACT_DIR/elf.txt"
cp "$ROOT_DIR/build/m2-first-stage-source.json" "$ARTIFACT_DIR/source.json"
cp device/realme/rmx2072_m2/*.mk "$ARTIFACT_DIR/"
sha256sum "$ARTIFACT_DIR/init" "$ARTIFACT_DIR/resolved-manifest.xml" > "$ARTIFACT_DIR/SHA256SUMS"
