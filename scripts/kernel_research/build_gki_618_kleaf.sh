#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_FILE="$ROOT_DIR/sources/SOURCE_LOCK.json"
WORKSPACE="${RUNNER_TEMP:-/tmp}/android17-gki-618"
ARTIFACT_DIR="$ROOT_DIR/artifacts/gki-6.18-kernel-build"
DIST_DIR="$ARTIFACT_DIR/dist"
BUILD_LOG="$ARTIFACT_DIR/kleaf-build.log"
BAZEL_ROOT="${RUNNER_TEMP:-/tmp}/bazel-output-root"

GKI_REF="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["ref"] for s in d["sources"] if s["id"]=="android17-gki-618"))' "$LOCK_FILE")"
GKI_SHA="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["commit"] for s in d["sources"] if s["id"]=="android17-gki-618"))' "$LOCK_FILE")"
MANIFEST_REF="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["ref"] for s in d["sources"] if s["id"]=="android-kernel-manifest"))' "$LOCK_FILE")"
MANIFEST_SHA="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["commit"] for s in d["sources"] if s["id"]=="android-kernel-manifest"))' "$LOCK_FILE")"

mkdir -p "$WORKSPACE" "$ARTIFACT_DIR" "$DIST_DIR"

{
  echo "BUILD_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "GKI_REF=$GKI_REF"
  echo "GKI_SHA=$GKI_SHA"
  echo "MANIFEST_REF=$MANIFEST_REF"
  echo "MANIFEST_SHA=$MANIFEST_SHA"
  echo "HOST=$(uname -a)"
  echo
  df -h
} | tee "$ARTIFACT_DIR/build-metadata.txt"

mkdir -p "$HOME/.bin"
curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo -o "$HOME/.bin/repo"
chmod a+x "$HOME/.bin/repo"
export PATH="$HOME/.bin:$PATH"

cd "$WORKSPACE"
repo init -u https://android.googlesource.com/kernel/manifest -b "$MANIFEST_REF"

ACTUAL_MANIFEST_SHA="$(git -C .repo/manifests rev-parse HEAD)"
if [[ "$ACTUAL_MANIFEST_SHA" != "$MANIFEST_SHA" ]]; then
  echo "Kernel manifest SHA mismatch: expected $MANIFEST_SHA, got $ACTUAL_MANIFEST_SHA" >&2
  exit 1
fi

echo "Verified manifest: $ACTUAL_MANIFEST_SHA" | tee -a "$ARTIFACT_DIR/build-metadata.txt"

# The ddk groups contain Kleaf, the pinned Clang/Rust toolchains, build tools
# and bzlmod dependencies. The default group contains common/.
repo sync -c -j4 --fail-fast --groups=default,ddk,ddk-external

if [[ ! -d common/.git || ! -x tools/bazel ]]; then
  echo "Kleaf workspace is incomplete: expected common/ and tools/bazel" >&2
  exit 1
fi

git -C common fetch --depth=1 aosp \
  "refs/tags/$GKI_REF:refs/tags/$GKI_REF"
git -C common checkout --detach "refs/tags/$GKI_REF"
ACTUAL_GKI_SHA="$(git -C common rev-parse HEAD)"
if [[ "$ACTUAL_GKI_SHA" != "$GKI_SHA" ]]; then
  echo "Pinned GKI SHA mismatch: expected $GKI_SHA, got $ACTUAL_GKI_SHA" >&2
  exit 1
fi

echo "Verified GKI source: $ACTUAL_GKI_SHA" | tee -a "$ARTIFACT_DIR/build-metadata.txt"

if ! grep -q '^CONFIG_RUST=y$' common/arch/arm64/configs/gki_defconfig; then
  echo "Pinned GKI defconfig does not enable CONFIG_RUST=y" >&2
  exit 1
fi
grep -E '^(CONFIG_RUST=|CONFIG_MODULES=|CONFIG_MODVERSIONS=|CONFIG_GENDWARFKSYMS=)' \
  common/arch/arm64/configs/gki_defconfig \
  | tee "$ARTIFACT_DIR/gki-rust-config.txt"

if [[ ! -d prebuilts/rust-toolchain/linux-x86 ]]; then
  echo "Manifest did not sync the pinned Rust toolchain" >&2
  exit 1
fi
find prebuilts/rust-toolchain/linux-x86 -maxdepth 4 \
  \( -name rustc -o -name rustfmt -o -name rustdoc \) -print \
  | tee "$ARTIFACT_DIR/rust-toolchain-files.txt"

repo manifest -r -o "$ARTIFACT_DIR/resolved-manifest.xml"
git -C common rev-parse HEAD > "$ARTIFACT_DIR/gki-source-sha.txt"
git -C build/kernel rev-parse HEAD > "$ARTIFACT_DIR/kleaf-source-sha.txt"

tools/bazel --output_user_root="$BAZEL_ROOT" run \
  --jobs=2 \
  --local_cpu_resources=2 \
  --local_ram_resources=5500 \
  --verbose_failures \
  //common:kernel_aarch64_dist \
  -- --destdir="$DIST_DIR" \
  2>&1 | tee "$BUILD_LOG"

if ! find "$DIST_DIR" -type f \( -name Image -o -name Image.gz -o -name Image.lz4 \) \
  -print -quit | grep -q .; then
  echo "Kleaf completed but no ARM64 kernel Image was found in $DIST_DIR" >&2
  exit 1
fi

find "$DIST_DIR" -type f -printf '%P\t%s bytes\n' | sort \
  | tee "$ARTIFACT_DIR/dist-file-list.txt"

if find "$DIST_DIR" -type f -name vmlinux -print -quit | grep -q .; then
  echo "VMLINUX=present" >> "$ARTIFACT_DIR/build-metadata.txt"
else
  echo "VMLINUX=not-in-dist" >> "$ARTIFACT_DIR/build-metadata.txt"
fi

if find "$DIST_DIR" -type f -name Module.symvers -print -quit | grep -q .; then
  echo "MODULE_SYMVERS=present" >> "$ARTIFACT_DIR/build-metadata.txt"
fi

grep -Ei '(^|[[:space:]])RUSTC([[:space:]]|$)|rustc' "$BUILD_LOG" \
  > "$ARTIFACT_DIR/rust-build-log.txt" || true

find "$DIST_DIR" -type f -print0 \
  | sort -z \
  | xargs -0 -r sha256sum \
  > "$ARTIFACT_DIR/DIST_SHA256SUMS"

echo "Full Kleaf GKI 6.18 ARM64 distribution build completed."
