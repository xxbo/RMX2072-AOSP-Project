#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${RUNNER_TEMP:?}/rmx2072-m2-aosp"
ARTIFACT_DIR="$ROOT_DIR/artifacts/m3-graphics"
PHASE=${1:-all}
case "$PHASE" in prepare|build|all) ;; *) exit 2 ;; esac
mkdir -p "$ARTIFACT_DIR"
if [[ "$PHASE" != build ]]; then
  RMX2072_GRAPHICS=1 bash "$ROOT_DIR/scripts/build/build_m2_first_stage.sh" prepare
  cp "$ROOT_DIR/artifacts/m2-first-stage/selected"*.xml "$ARTIFACT_DIR/"
  mkdir -p "$SOURCE_DIR/device/realme/rmx2072_m3"
  cp "$ROOT_DIR/device/realme/bladerunner_48m/m3-graphics/"* "$SOURCE_DIR/device/realme/rmx2072_m3/"
fi
if [[ "$PHASE" == prepare ]]; then exit 0; fi
cd "$SOURCE_DIR"
# The generic DRM service defaults link this library, whose upstream visibility
# lists only upstream board packages. Admit this one project service package.
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
    targets=(libEGL_angle libGLESv1_CM_angle libGLESv2_angle vulkan.pastel
      android.hardware.graphics.allocator-service.minigbm mapper.minigbm gralloc.minigbm
      android.hardware.composer.hwc3-service.rmx2072)
    m --skip-ninja "${targets[@]}"
    python3 "$M3_RECIPE_ROOT/scripts/build/check_m2_ninja_deps.py" \
      --output "$M3_ARTIFACT_DIR/target-dependencies.json" \
      --graph out/combined-rmx2072_m3_graphics.ninja --targets "${targets[@]}"
    m -j2 "${targets[@]}"' 2>&1 | tee "$ARTIFACT_DIR/build-$attempt.log"
  result=${PIPESTATUS[0]}
  set -e
  if [[ "$result" == 0 ]]; then break; fi
  python3 "$ROOT_DIR/scripts/build/complete_m2_workspace.py" \
    --workspace "$SOURCE_DIR" --upstream "$ARTIFACT_DIR/selected.upstream.xml" \
    --log "$ARTIFACT_DIR/build-$attempt.log" --record "$ARTIFACT_DIR/dependency-additions.jsonl"
done
test "$result" == 0
repo manifest -r -o "$ARTIFACT_DIR/resolved-manifest.xml"
VENDOR=out/target/product/rmx2072_m3/vendor
test -s "$VENDOR/bin/hw/android.hardware.composer.hwc3-service.rmx2072"
test -s "$VENDOR/lib64/egl/libEGL_angle.so"
test -s "$VENDOR/lib64/hw/vulkan.pastel.so"
find "$VENDOR" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/vendor-files.sha256"
tar -C "$VENDOR" -czf "$ARTIFACT_DIR/graphics-vendor.tar.gz" .
sha256sum "$ARTIFACT_DIR/graphics-vendor.tar.gz" "$ARTIFACT_DIR/resolved-manifest.xml" > "$ARTIFACT_DIR/SHA256SUMS"
git -C "$ROOT_DIR" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
printf '%s\n' 'Source ARM64 graphics payload. CPU Vulkan rendering through SwiftShader/ANGLE; physical MSM DRM scanout. No Adreno acceleration claim. Device validation pending.' > "$ARTIFACT_DIR/STATUS.txt"
