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
MIRROR_BRANCH="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["mirror_branch"] for s in d["sources"] if s["id"]=="android17-gki-618"))' "$LOCK_FILE")"
MANIFEST_REF="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["ref"] for s in d["sources"] if s["id"]=="android-kernel-manifest"))' "$LOCK_FILE")"
MANIFEST_SHA="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["commit"] for s in d["sources"] if s["id"]=="android-kernel-manifest"))' "$LOCK_FILE")"
GKI_MIRROR_COMMIT="${GKI_MIRROR_COMMIT:?GKI_MIRROR_COMMIT must be supplied by the mirror-source job}"

mkdir -p "$WORKSPACE" "$ARTIFACT_DIR" "$DIST_DIR"

{
  echo "BUILD_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "GKI_REF=$GKI_REF"
  echo "GKI_UPSTREAM_SHA=$GKI_SHA"
  echo "GKI_MIRROR_BRANCH=$MIRROR_BRANCH"
  echo "GKI_MIRROR_COMMIT=$GKI_MIRROR_COMMIT"
  echo "MANIFEST_REF=$MANIFEST_REF"
  echo "MANIFEST_SHA=$MANIFEST_SHA"
  echo "HOST=$(uname -a)"
  echo "CPU_COUNT=$(nproc)"
  echo
  echo "=== CPU ==="
  lscpu | grep -E '^(Architecture|CPU\\(s\\)|Model name|Thread\\(s\\) per core|Core\\(s\\) per socket|Socket\\(s\\)):' || true
  echo
  echo "=== MEMORY ==="
  free -h
  echo
  echo "=== STORAGE ==="
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

# Replace only kernel/common with the repository-owned pinned source snapshot.
# Kleaf, toolchains, build utilities and Bazel dependencies remain pinned by
# Google's official kernel/manifest repository.
mkdir -p .repo/local_manifests
cat > .repo/local_manifests/99-rmx2072-gki-mirror.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <remote name="rmx2072-github" fetch="https://github.com/xxbo" />
  <remove-project path="common" />
  <project
    name="RMX2072-AOSP-Project"
    path="common"
    remote="rmx2072-github"
    revision="$MIRROR_BRANCH"
    groups="default,ddk,ddk-external" />
</manifest>
XML

repo sync -c -j4 --fail-fast --groups=default,ddk,ddk-external

if [[ ! -d common/.git || ! -x tools/bazel ]]; then
  echo "Kleaf workspace is incomplete: expected common/ and tools/bazel" >&2
  exit 1
fi

ACTUAL_MIRROR_COMMIT="$(git -C common rev-parse HEAD)"
if [[ "$ACTUAL_MIRROR_COMMIT" != "$GKI_MIRROR_COMMIT" ]]; then
  echo "GKI mirror commit mismatch: expected $GKI_MIRROR_COMMIT, got $ACTUAL_MIRROR_COMMIT" >&2
  exit 1
fi

MIRRORED_UPSTREAM_SHA="$(git -C common log -1 --format=%B | sed -n 's/^Upstream-Commit: //p' | head -n 1)"
if [[ "$MIRRORED_UPSTREAM_SHA" != "$GKI_SHA" ]]; then
  echo "GKI mirror upstream SHA mismatch: expected $GKI_SHA, got $MIRRORED_UPSTREAM_SHA" >&2
  exit 1
fi

if ! grep -q '^VERSION = 6$' common/Makefile || ! grep -q '^PATCHLEVEL = 18$' common/Makefile; then
  echo "Repository-owned source snapshot is not Linux 6.18" >&2
  exit 1
fi

{
  echo "Verified GKI mirror commit: $ACTUAL_MIRROR_COMMIT"
  echo "Verified upstream GKI source: $MIRRORED_UPSTREAM_SHA"
} | tee -a "$ARTIFACT_DIR/build-metadata.txt"

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
git -C common rev-parse HEAD > "$ARTIFACT_DIR/gki-mirror-commit.txt"
printf '%s\n' "$GKI_SHA" > "$ARTIFACT_DIR/gki-upstream-source-sha.txt"
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

echo "Full Kleaf GKI 6.18 ARM64 distribution build completed from repository-owned kernel source."
