#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${RUNNER_TEMP:-/tmp}/android17-gki-618"
ARTIFACT_DIR="$ROOT_DIR/artifacts/sm8250-bootstrap"
mkdir -p "$ARTIFACT_DIR/dist"
GKI_SYNC_ONLY=1 bash "$ROOT_DIR/scripts/kernel_research/build_gki_618_kleaf.sh"
cp "$ROOT_DIR/artifacts/gki-6.18-kernel-build/resolved-manifest.xml" "$ARTIFACT_DIR/"
cp "$ROOT_DIR/artifacts/gki-6.18-kernel-build/build-metadata.txt" "$ARTIFACT_DIR/"
mkdir -p "$WORKSPACE/rmx2072/bootstrap"
cp -a "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/." "$WORKSPACE/rmx2072/bootstrap/"
cd "$WORKSPACE"
tools/bazel --output_user_root="${RUNNER_TEMP:-/tmp}/bazel-output-root" run \
  --jobs=2 --local_resources=cpu=2 --local_resources=memory=5500 --verbose_failures \
  //rmx2072/bootstrap:sm8250_bootstrap_dist -- --destdir="$ARTIFACT_DIR/dist" \
  2>&1 | tee "$ARTIFACT_DIR/build.log"
test -s "$ARTIFACT_DIR/dist/Image.gz"
python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
  --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
  --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_defconfig"
find "$ARTIFACT_DIR/dist" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/SHA256SUMS"
printf '%s\n' 'Platform compile candidate only; device DTS, boot packaging and physical boot remain untested.' > "$ARTIFACT_DIR/STATUS.txt"
