#!/usr/bin/env bash
# Build the project capability-only Power HAL against pinned AOSP AIDL V7.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${RUNNER_TEMP:?}/rmx2072-m2-aosp"
ARTIFACT_DIR="$ROOT_DIR/artifacts/m3-power"
PHASE=${1:-all}
case "$PHASE" in prepare|build|all) ;; *) exit 2 ;; esac
mkdir -p "$ARTIFACT_DIR"
if [[ "$PHASE" != build ]]; then
  bash "$ROOT_DIR/scripts/build/build_m3_graphics.sh" prepare
  cp "$ROOT_DIR/artifacts/m3-graphics/selected"*.xml "$ARTIFACT_DIR/"
  cp "$ROOT_DIR/artifacts/m3-graphics/hardwarebuffer-source.json" "$ARTIFACT_DIR/"
  mkdir -p "$SOURCE_DIR/device/realme/rmx2072_m3/power"
  cp "$ROOT_DIR/device/realme/bladerunner_48m/m3-power/"* "$SOURCE_DIR/device/realme/rmx2072_m3/power/"
fi
if [[ "$PHASE" == prepare ]]; then exit 0; fi
cd "$SOURCE_DIR"
# Soong analyzes the existing product's composer declaration even when only
# Power is requested. Apply the same narrow visibility admission as graphics.
python3 - <<'PY'
from pathlib import Path
p = Path('external/libdisplay-info/Android.bp')
text = p.read_text()
anchor = '        "//external/drm_hwcomposer:__subpackages__",\n'
entry = '        "//device/realme/rmx2072_m3",\n'
if text.count(anchor) != 1:
    raise ValueError('Pinned libdisplay_info visibility changed')
if entry not in text:
    p.write_text(text.replace(anchor, anchor + entry))
PY
export ALLOW_MISSING_DEPENDENCIES=true SOONG_UI_NINJA_ARGS=-v
export M3_RECIPE_ROOT="$ROOT_DIR" M3_ARTIFACT_DIR="$ARTIFACT_DIR"
for attempt in $(seq 1 12); do
  set +e
  bash -c 'set -eo pipefail
    source build/envsetup.sh
    lunch rmx2072_m3_graphics-aosp_current-user
    target=android.hardware.power-service.rmx2072
    m --skip-ninja "$target"
    python3 "$M3_RECIPE_ROOT/scripts/build/check_m2_ninja_deps.py" \
      --output "$M3_ARTIFACT_DIR/target-dependencies.json" \
      --graph out/combined-rmx2072_m3_graphics.ninja --targets "$target"
    m -j2 "$target"' 2>&1 | tee "$ARTIFACT_DIR/build-$attempt.log"
  result=${PIPESTATUS[0]}
  set -e
  if [[ "$result" == 0 ]]; then break; fi
  python3 "$ROOT_DIR/scripts/build/complete_m2_workspace.py" \
    --workspace "$SOURCE_DIR" --upstream "$ARTIFACT_DIR/selected.upstream.xml" \
    --log "$ARTIFACT_DIR/build-$attempt.log" --record "$ARTIFACT_DIR/dependency-additions.jsonl"
done
test "$result" == 0
repo manifest -r -o "$ARTIFACT_DIR/resolved-manifest.xml"
VENDOR=$(bash -c 'source build/envsetup.sh >&2
  lunch rmx2072_m3_graphics-aosp_current-user >&2
  get_build_var TARGET_OUT_VENDOR')
case "$VENDOR" in
  out/target/product/rmx2072_m3/vendor|out/target/product/rmx2072_m3/system/vendor) ;;
  *) echo "Unexpected vendor output: $VENDOR" >&2; exit 1 ;;
esac
printf '%s\n' "$VENDOR" > "$ARTIFACT_DIR/vendor-output-path.txt"
test -s "$VENDOR/bin/hw/android.hardware.power-service.rmx2072"
find "$VENDOR" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/vendor-files.sha256"
tar -C "$VENDOR" -czf "$ARTIFACT_DIR/power-vendor.tar.gz" .
sha256sum "$ARTIFACT_DIR/power-vendor.tar.gz" "$ARTIFACT_DIR/resolved-manifest.xml" "$ARTIFACT_DIR/vendor-output-path.txt" > "$ARTIFACT_DIR/SHA256SUMS"
sha256sum hardware/interfaces/power/aidl/Android.bp \
  hardware/interfaces/power/aidl/android/hardware/power/IPower.aidl \
  hardware/interfaces/power/aidl/android/hardware/power/SupportInfo.aidl \
  hardware/interfaces/power/aidl/aidl_api/android.hardware.power/7/android/hardware/power/IPower.aidl \
  hardware/interfaces/power/aidl/aidl_api/android.hardware.power/7/android/hardware/power/SupportInfo.aidl \
  hardware/interfaces/power/aidl/aidl_api/android.hardware.power/7/.hash > "$ARTIFACT_DIR/power-source.sha256"
(cd "$ROOT_DIR"; sha256sum device/realme/bladerunner_48m/m3-power/*) > "$ARTIFACT_DIR/project-power-source.sha256"
git -C "$ROOT_DIR" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
printf '%s\n' 'Project Power HAL with pinned AOSP AIDL V7. All unimplemented capabilities report unsupported; no performance driver or hardware writes. Device integration pending.' > "$ARTIFACT_DIR/STATUS.txt"
