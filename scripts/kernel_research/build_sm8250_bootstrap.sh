#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${RUNNER_TEMP:-/tmp}/android17-gki-618"
ARTIFACT_DIR="$ROOT_DIR/artifacts/sm8250-bootstrap"
mkdir -p "$ARTIFACT_DIR/dist"
GKI_SYNC_ONLY=1 bash "$ROOT_DIR/scripts/kernel_research/build_gki_618_kleaf.sh"
EDL_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-scm-edl.patch"
git -C "$WORKSPACE/common" apply --check "$EDL_PATCH"
git -C "$WORKSPACE/common" apply "$EDL_PATCH"
sha256sum "$EDL_PATCH" > "$ARTIFACT_DIR/board-patch.sha256"
PHY_TEST="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-ufs-phy-test.c"
cp "$PHY_TEST" "$WORKSPACE/common/drivers/phy/qualcomm/"
printf '\nobj-$(CONFIG_PHY_QCOM_QMP_UFS) += rmx2072-ufs-phy-test.o\n' >> "$WORKSPACE/common/drivers/phy/qualcomm/Makefile"
sha256sum "$PHY_TEST" > "$ARTIFACT_DIR/phy-test.sha256"
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
python3 "$ROOT_DIR/scripts/device_audit/audit_bootstrap_config.py" \
  --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
  --output "$ARTIFACT_DIR/platform-config-audit.json"
find "$ARTIFACT_DIR/dist" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/SHA256SUMS"
printf '%s\n' 'Platform compile candidate: Qualcomm hardware mutex and APSS watchdog required built-in. Physical kernel execution is not established by this build.' > "$ARTIFACT_DIR/STATUS.txt"
