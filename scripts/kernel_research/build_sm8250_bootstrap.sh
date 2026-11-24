#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${RUNNER_TEMP:-/tmp}/android17-gki-618"
ARTIFACT_DIR="$ROOT_DIR/artifacts/sm8250-bootstrap"
mkdir -p "$ARTIFACT_DIR/dist"
if [[ "${RMX2072_PON_POWER:-0}" == 1 && "${RMX2072_SOURCE_PON:-0}" == 1 ]]; then
  echo 'Select legacy PON or source-tree PON, never both' >&2
  exit 1
fi
GKI_SYNC_ONLY=1 bash "$ROOT_DIR/scripts/kernel_research/build_gki_618_kleaf.sh"
EDL_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-scm-edl.patch"
git -C "$WORKSPACE/common" apply --check "$EDL_PATCH"
git -C "$WORKSPACE/common" apply "$EDL_PATCH"
sha256sum "$EDL_PATCH" > "$ARTIFACT_DIR/board-patch.sha256"
TZMEM_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-tzmem-status.patch"
git -C "$WORKSPACE/common" apply --check "$TZMEM_PATCH"
git -C "$WORKSPACE/common" apply "$TZMEM_PATCH"
sha256sum "$TZMEM_PATCH" > "$ARTIFACT_DIR/tzmem-patch.sha256"
PHY_TEST="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-ufs-phy-test.c"
cp "$PHY_TEST" "$WORKSPACE/common/drivers/phy/qualcomm/"
printf '\nobj-$(CONFIG_PHY_QCOM_QMP_UFS) += rmx2072-ufs-phy-test.o\n' >> "$WORKSPACE/common/drivers/phy/qualcomm/Makefile"
sha256sum "$PHY_TEST" > "$ARTIFACT_DIR/phy-test.sha256"
KM_PROBE="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-keymaster-lookup.c"
cp "$KM_PROBE" "$WORKSPACE/common/drivers/firmware/qcom/"
printf '\nobj-$(CONFIG_QCOM_QSEECOM) += rmx2072-keymaster-lookup.o\n' >> "$WORKSPACE/common/drivers/firmware/qcom/Makefile"
sha256sum "$KM_PROBE" > "$ARTIFACT_DIR/keymaster-lookup.sha256"
KM_TRANSPORT="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-keymaster-transport.h"
cp "$KM_TRANSPORT" "$WORKSPACE/common/drivers/firmware/qcom/"
sha256sum "$KM_TRANSPORT" > "$ARTIFACT_DIR/keymaster-transport.sha256"
LISTENER="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-listener.inc"
cp "$LISTENER" "$WORKSPACE/common/drivers/firmware/qcom/"
python3 - "$WORKSPACE/common/drivers/firmware/qcom/qcom_scm.c" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
anchor = "/**\n * qcom_scm_qseecom_call()"
if s.count(anchor) != 1:
    raise ValueError("Pinned SCM listener insertion point changed")
p.write_text(s.replace(anchor, '#include "rmx2072-listener.inc"\n\n' + anchor))
PY
sha256sum "$LISTENER" > "$ARTIFACT_DIR/listener.sha256"
cp "$ROOT_DIR/artifacts/gki-6.18-kernel-build/resolved-manifest.xml" "$ARTIFACT_DIR/"
cp "$ROOT_DIR/artifacts/gki-6.18-kernel-build/build-metadata.txt" "$ARTIFACT_DIR/"
mkdir -p "$WORKSPACE/rmx2072/bootstrap"
cp -a "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/." "$WORKSPACE/rmx2072/bootstrap/"
if [[ "${RMX2072_PON_POWER:-0}" == 1 ]]; then
  PON_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-pon-power.patch"
  git -C "$WORKSPACE/common" apply --check "$PON_PATCH"
  git -C "$WORKSPACE/common" apply "$PON_PATCH"
  sha256sum "$PON_PATCH" > "$ARTIFACT_DIR/pon-power-patch.sha256"
  cat "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_pon.fragment" >> "$WORKSPACE/rmx2072/bootstrap/sm8250_defconfig"
fi
if [[ "${RMX2072_SOURCE_PON:-0}" == 1 ]]; then
  PON_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-source-pon.patch"
  git -C "$WORKSPACE/common" apply --check "$PON_PATCH"
  git -C "$WORKSPACE/common" apply "$PON_PATCH"
  sha256sum "$PON_PATCH" > "$ARTIFACT_DIR/source-pon-patch.sha256"
  cat "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_source_pon.fragment" >> "$WORKSPACE/rmx2072/bootstrap/sm8250_defconfig"
fi
if [[ "${RMX2072_DISPLAY:-0}" == 1 ]]; then
  test "${RMX2072_SOURCE_PON:-0}" == 1
  CLOCK_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-display-clock.patch"
  git -C "$WORKSPACE/common" apply --check "$CLOCK_PATCH"
  git -C "$WORKSPACE/common" apply "$CLOCK_PATCH"
  sha256sum "$CLOCK_PATCH" > "$ARTIFACT_DIR/display-clock-patch.sha256"
  for DSC_PATCH_NAME in upstream-dsi-dsc-all-slices-flag upstream-msm-dsi-dsc-slices-per-packet rmx2072-dsc-packet-trace rmx2072-dsc-route-test rmx2072-dpu-solid-fill-test rmx2072-stock-linkclock-test rmx2072-stock-dsc-test rmx2072-stock-phy-timing-test rmx2072-first-frame-trace; do
    DSC_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/$DSC_PATCH_NAME.patch"
    git -C "$WORKSPACE/common" apply --check "$DSC_PATCH"
    git -C "$WORKSPACE/common" apply "$DSC_PATCH"
    sha256sum "$DSC_PATCH" > "$ARTIFACT_DIR/$DSC_PATCH_NAME.sha256"
  done
  PANEL_DIR="$ROOT_DIR/device/realme/bladerunner_48m/display"
  cp "$PANEL_DIR/panel-samsung-rm19795.c" "$PANEL_DIR/rm19795-commands.h" "$PANEL_DIR/rm19795-commands-90.h" "$WORKSPACE/common/drivers/gpu/drm/panel/"
  cat >> "$WORKSPACE/common/drivers/gpu/drm/panel/Kconfig" <<'EOF'

config DRM_PANEL_RMX2072_RM19795
	tristate "RMX2072 RM19795 Samsung command-mode DSC panel"
	depends on OF && DRM_MIPI_DSI && BACKLIGHT_CLASS_DEVICE
	select DRM_DISPLAY_DSC_HELPER
EOF
  printf '\nobj-$(CONFIG_DRM_PANEL_RMX2072_RM19795) += panel-samsung-rm19795.o\n' >> "$WORKSPACE/common/drivers/gpu/drm/panel/Makefile"
  sha256sum "$PANEL_DIR/panel-samsung-rm19795.c" "$PANEL_DIR/rm19795-commands.h" "$PANEL_DIR/rm19795-commands-90.h" > "$ARTIFACT_DIR/display-source.sha256"
  cat "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_display.fragment" >> "$WORKSPACE/rmx2072/bootstrap/sm8250_defconfig"
fi
if [[ "${RMX2072_INPUT:-0}" == 1 ]]; then
  test "${RMX2072_DISPLAY:-0}" == 1
  INPUT_DIR="$ROOT_DIR/device/realme/bladerunner_48m/input"
  cp "$INPUT_DIR/goodix_gtx8.c" "$INPUT_DIR/goodix_gtx8.h" "$WORKSPACE/common/drivers/input/touchscreen/"
  cat >> "$WORKSPACE/common/drivers/input/touchscreen/Kconfig" <<'EOF'

config TOUCHSCREEN_GOODIX_GTX8
	tristate "Goodix GTX8 touchscreen"
	depends on I2C
	select REGMAP_I2C
	help
	  Community GTX8 driver port for GT9886/GT9896 I2C touchscreens.
	  Requires pre-flashed controller firmware; does not flash firmware.
EOF
  printf '\nobj-$(CONFIG_TOUCHSCREEN_GOODIX_GTX8) += goodix_gtx8.o\n' >> "$WORKSPACE/common/drivers/input/touchscreen/Makefile"
  sha256sum "$INPUT_DIR/goodix_gtx8.c" > "$ARTIFACT_DIR/touch-source.sha256"
  sha256sum "$INPUT_DIR/goodix_gtx8.h" > "$ARTIFACT_DIR/touch-header.sha256"
  cat "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_input.fragment" >> "$WORKSPACE/rmx2072/bootstrap/sm8250_defconfig"
fi
if [[ "${RMX2072_BATTERY:-0}" == 1 ]]; then
  test "${RMX2072_INPUT:-0}" == 1
  cat "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_battery.fragment" >> "$WORKSPACE/rmx2072/bootstrap/sm8250_defconfig"
  sha256sum "$WORKSPACE/common/drivers/power/supply/bq27xxx_battery.c" \
    "$WORKSPACE/common/drivers/power/supply/bq27xxx_battery_i2c.c" > "$ARTIFACT_DIR/battery-source.sha256"
fi
if [[ "${RMX2072_PERFORMANCE:-0}" == 1 ]]; then
  test "${RMX2072_DISPLAY:-0}" == 1
  cat "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_performance.fragment" >> "$WORKSPACE/rmx2072/bootstrap/sm8250_defconfig"
  sha256sum "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_performance.fragment" > "$ARTIFACT_DIR/performance-fragment.sha256"
fi
cd "$WORKSPACE"
tools/bazel --output_user_root="${RUNNER_TEMP:-/tmp}/bazel-output-root" run \
  --jobs=2 --local_resources=cpu=2 --local_resources=memory=5500 --verbose_failures \
  //rmx2072/bootstrap:sm8250_bootstrap_dist -- --destdir="$ARTIFACT_DIR/dist" \
  2>&1 | tee "$ARTIFACT_DIR/build.log"
test -s "$ARTIFACT_DIR/dist/Image.gz"
python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
  --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
  --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_defconfig"
if [[ "${RMX2072_PON_POWER:-0}" == 1 ]]; then
  python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
    --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
    --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_pon.fragment"
fi
if [[ "${RMX2072_SOURCE_PON:-0}" == 1 ]]; then
  python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
    --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
    --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_source_pon.fragment"
fi
python3 "$ROOT_DIR/scripts/device_audit/audit_bootstrap_config.py" \
  --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
  --output "$ARTIFACT_DIR/platform-config-audit.json"
if [[ "${RMX2072_DISPLAY:-0}" == 1 ]]; then
  python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
    --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
    --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_display.fragment"
fi
if [[ "${RMX2072_INPUT:-0}" == 1 ]]; then
  python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
    --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
    --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_input.fragment"
fi
if [[ "${RMX2072_BATTERY:-0}" == 1 ]]; then
  python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
    --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
    --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_battery.fragment"
  grep -Fx '# CONFIG_BATTERY_BQ27XXX_DT_UPDATES_NVM is not set' "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config"
fi
if [[ "${RMX2072_PERFORMANCE:-0}" == 1 ]]; then
  python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
    --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
    --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_performance.fragment"
fi
find "$ARTIFACT_DIR/dist" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/SHA256SUMS"
printf '%s\n' 'Platform compile candidate: Qualcomm hardware mutex and APSS watchdog required built-in. Physical kernel execution is not established by this build.' > "$ARTIFACT_DIR/STATUS.txt"
