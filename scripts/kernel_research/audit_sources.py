#!/usr/bin/env python3
"""Read-only kernel source inventory and structural diff for pinned source trees."""

import argparse
import base64
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
SCAN_ROOTS = [
    "arch", "drivers", "techpack", "include", "kernel", "mm", "fs", "net",
    "block", "sound", "scripts", "security", "crypto", "init", "ipc", "virt",
]
DIFF_GROUPS = [
    "arch/arm64/configs",
    "drivers/gpu/msm",
    "drivers/gpu/drm",
    "drivers/soc/qcom",
    "drivers/clk/qcom",
    "drivers/thermal",
    "drivers/iommu",
    "drivers/input",
    "drivers/net/wireless",
    "drivers/usb",
    "techpack/display",
    "techpack/audio",
    "techpack/camera",
    "techpack/video",
    "mm",
    "kernel",
    "include/linux",
]
GKI_DIRS = [
    "arch", "arch/arm64", "arch/arm64/configs", "drivers", "drivers/gpu",
    "drivers/soc/qcom", "drivers/clk/qcom", "drivers/thermal", "drivers/iommu",
    "drivers/net/wireless", "drivers/usb", "drivers/input", "techpack",
    "mm", "kernel", "include", "include/linux", "block", "fs", "net", "security",
]
USER_AGENT = "RMX2072-Kernel-Source-Research/1.0"
JSON_CACHE = {}


def request_bytes(url, headers=None, timeout=90):
    merged = {"User-Agent": USER_AGENT}
    merged.update(headers or {})
    request = Request(url, headers=merged)
    last_error = None
    for attempt in range(5):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:1200]
            last_error = RuntimeError("HTTP %s for %s: %s" % (exc.code, url, body))
            retryable = exc.code in (429, 500, 502, 503, 504)
            if exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(exc.headers.get("X-RateLimit-Reset", "0") or "0")
                wait = max(1, min(60, reset - int(time.time())))
                if attempt < 4:
                    time.sleep(wait)
                    continue
            if not retryable or attempt == 4:
                raise last_error
        except (URLError, TimeoutError) as exc:
            last_error = RuntimeError("Network error for %s: %s" % (url, exc))
            if attempt == 4:
                raise last_error
        time.sleep(min(2 ** attempt, 12))
    raise last_error or RuntimeError("Request failed: " + url)


def github_json(repo, endpoint):
    url = API_ROOT + "/repos/" + repo
    if endpoint:
        url += "/" + endpoint.lstrip("/")
    if url not in JSON_CACHE:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = "Bearer " + token
        JSON_CACHE[url] = json.loads(request_bytes(url, headers).decode("utf-8"))
    return JSON_CACHE[url]


def github_raw(repo, commit, path):
    url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, commit, path)
    try:
        return request_bytes(url).decode("utf-8", "replace")
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def github_collect_tree(repo, tree_sha, prefix, output, depth=0):
    if depth > 12:
        raise RuntimeError("Tree recursion depth exceeded at " + prefix)
    recursive = github_json(repo, "git/trees/%s?recursive=1" % tree_sha)
    if not recursive.get("truncated", False):
        for item in recursive.get("tree", []):
            path = prefix + "/" + item["path"]
            output[path] = {
                "type": item.get("type"),
                "size": item.get("size"),
            }
        return
    shallow = github_json(repo, "git/trees/%s" % tree_sha)
    for item in shallow.get("tree", []):
        path = prefix + "/" + item["path"]
        output[path] = {"type": item.get("type"), "size": item.get("size")}
        if item.get("type") == "tree":
            github_collect_tree(repo, item["sha"], path, output, depth + 1)


def parse_kernel_version(makefile):
    if not makefile:
        return None
    values = {}
    for key in ("VERSION", "PATCHLEVEL", "SUBLEVEL", "EXTRAVERSION"):
        match = re.search(r"(?m)^%s\s*=\s*(.*?)\s*$" % key, makefile)
        if match:
            values[key] = match.group(1)
    if "VERSION" not in values or "PATCHLEVEL" not in values:
        return None
    version = values["VERSION"] + "." + values["PATCHLEVEL"]
    if "SUBLEVEL" in values:
        version += "." + values["SUBLEVEL"]
    version += values.get("EXTRAVERSION", "")
    return version


def extract_build_config(text):
    if not text:
        return []
    patterns = (
        r"^(BRANCH|KMI_GENERATION|LLVM|LLVM_IAS|CLANG_PREBUILT_BIN|"
        r"BUILD_CONFIG|DEFCONFIG|LTO|CONFIG_LOCALVERSION)\s*=.*$"
    )
    return [line.strip() for line in text.splitlines()
            if re.match(patterns, line.strip())]


def github_kernel_source(source):
    repo = source["repository"]
    commit_sha = source["commit"]
    commit = github_json(repo, "commits/" + commit_sha)
    if commit.get("sha") != commit_sha:
        raise RuntimeError("Commit SHA mismatch: expected %s, received %s" %
                           (commit_sha, commit.get("sha")))
    tree_sha = commit["commit"]["tree"]["sha"]
    metadata = github_json(repo, "")
    root_tree = github_json(repo, "git/trees/" + tree_sha)
    root_entries = root_tree.get("tree", [])
    root_map = {entry["path"]: entry for entry in root_entries}
    paths = {}
    for root in SCAN_ROOTS:
        entry = root_map.get(root)
        if entry and entry.get("type") == "tree":
            paths[root] = {"type": "tree", "size": None}
            github_collect_tree(repo, entry["sha"], root, paths)

    makefile = github_raw(repo, commit_sha, "Makefile")
    common = github_raw(repo, commit_sha, "build.config.common")
    gki = github_raw(repo, commit_sha, "build.config.gki.aarch64")
    arm64_config = github_raw(repo, commit_sha, "build.config.aarch64")
    oplus_config = github_raw(repo, commit_sha, "OplusKernelEnvConfig.mk")

    files = {path for path, item in paths.items() if item.get("type") == "blob"}
    dirs = {path for path, item in paths.items() if item.get("type") == "tree"}
    defconfigs = sorted(
        path for path in files
        if path.startswith("arch/arm64/configs/") and path.endswith("defconfig")
    )
    relevant_defconfigs = [
        path for path in defconfigs
        if re.search(r"kona|sm8250|qcom|vendor", path, re.IGNORECASE)
    ][:40]

    driver_modules = sorted(
        path.split("/", 1)[1] for path in dirs
        if path.startswith("drivers/") and path.count("/") == 1
    )
    techpack_modules = sorted(
        path.split("/", 1)[1] for path in dirs
        if path.startswith("techpack/") and path.count("/") == 1
    )

    module_counts = {}
    for prefix in DIFF_GROUPS:
        module_counts[prefix] = sum(
            1 for path in files if path.startswith(prefix.rstrip("/") + "/")
        )

    build_configs = {
        "build.config.common": extract_build_config(common),
        "build.config.gki.aarch64": extract_build_config(gki),
        "build.config.aarch64": extract_build_config(arm64_config),
        "OplusKernelEnvConfig.mk": extract_build_config(oplus_config),
    }
    return {
        "id": source["id"],
        "category": source["category"],
        "repository": repo,
        "url": source.get("url"),
        "ref": source.get("ref"),
        "expected_commit": commit_sha,
        "verified_commit": commit.get("sha"),
        "commit_date": commit.get("commit", {}).get("committer", {}).get("date"),
        "commit_message": commit.get("commit", {}).get("message", "").splitlines()[0],
        "kernel_version_expected": source.get("kernel_version"),
        "kernel_version_from_makefile": parse_kernel_version(makefile),
        "repository_size_kb": metadata.get("size"),
        "repository_pushed_at": metadata.get("pushed_at"),
        "repository_license_metadata": (metadata.get("license") or {}).get("spdx_id"),
        "root_directories": sorted(
            entry["path"] for entry in root_entries if entry.get("type") == "tree"
        ),
        "scanned_roots": [root for root in SCAN_ROOTS if root in root_map],
        "scanned_file_count": len(files),
        "scanned_directory_count": len(dirs),
        "arm64_defconfig_count": len(defconfigs),
        "relevant_arm64_defconfigs": relevant_defconfigs,
        "driver_modules": driver_modules,
        "techpack_modules": techpack_modules,
        "module_file_counts": module_counts,
        "build_config_evidence": build_configs,
        "scan_method": "GitHub Git Trees API; selected top-level source trees recursively enumerated",
        "_files": files,
    }


def gitiles_json(url):
    raw = request_bytes(url).decode("utf-8", "replace")
    raw = re.sub(r"^\)\]\}'\s*", "", raw)
    return json.loads(raw)


def gitiles_text(url):
    raw = request_bytes(url).decode("ascii", "replace")
    return base64.b64decode(raw).decode("utf-8", "replace")


def gitiles_kernel_source(source):
    base = source["url"].rstrip("/")
    commit_sha = source["commit"]
    root_url = "%s/+/%s/?format=JSON" % (base, commit_sha)
    root = gitiles_json(root_url)
    root_entries = root.get("entries", [])
    root_names = sorted(entry["name"] for entry in root_entries
                        if entry.get("type") == "tree")
    shallow = {}
    targets = []
    for path in GKI_DIRS:
        url = "%s/+/%s/%s/?format=JSON" % (base, commit_sha, path)
        try:
            data = gitiles_json(url)
            entries = data.get("entries", [])
            shallow[path] = {
                "entry_count": len(entries),
                "directories": sorted(e["name"] for e in entries
                                      if e.get("type") == "tree")[:80],
                "files": sorted(e["name"] for e in entries
                                if e.get("type") == "blob")[:80],
            }
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc):
                raise
            shallow[path] = {"missing": True}
    makefile = gitiles_text("%s/+/%s/Makefile?format=TEXT" % (base, commit_sha))
    return {
        "id": source["id"],
        "category": source["category"],
        "repository": source["repository"],
        "url": source.get("url"),
        "ref": source.get("ref"),
        "expected_commit": commit_sha,
        "verified_commit": commit_sha,
        "commit_date": source.get("commit_date"),
        "kernel_version_expected": source.get("kernel_version"),
        "kernel_version_from_makefile": parse_kernel_version(makefile),
        "root_directories": root_names,
        "gitiles_directory_inventory": shallow,
        "scan_method": "Gitiles immutable commit lookup; directory-level targeted inventory (not a full recursive file scan)",
        "_files": set(),
    }


def compare_sources(baseline, candidate):
    base_files = baseline["_files"]
    candidate_files = candidate["_files"]
    result = []
    for prefix in DIFF_GROUPS:
        prefix_slash = prefix.rstrip("/") + "/"
        left = {path for path in base_files if path.startswith(prefix_slash)}
        right = {path for path in candidate_files if path.startswith(prefix_slash)}
        added = sorted(right - left)
        removed = sorted(left - right)
        result.append({
            "group": prefix,
            "baseline_file_count": len(left),
            "candidate_file_count": len(right),
            "added_count": len(added),
            "removed_count": len(removed),
            "added_sample": added[:12],
            "removed_sample": removed[:12],
        })
    return {
        "baseline": baseline["id"],
        "candidate": candidate["id"],
        "groups": result,
    }


def markdown_report(report):
    lines = [
        "# Kernel Source Research — Automated Inventory",
        "",
        "Generated by GitHub Actions from immutable source pins.",
        "",
        "- Snapshot: " + report["generated_at_utc"],
        "- Project target: " + report["project_target"],
        "- Source lock: " + report["source_lock_path"],
        "- Research mode: read-only metadata and tree inspection; no kernel build or device flashing.",
        "",
        "## Source verification",
        "",
        "| Source | Expected kernel | Makefile version | Commit verification | Scanned files |",
        "|---|---:|---:|---|---:|",
    ]
    for source in report["sources"]:
        lines.append("| %s | %s | %s | %s | %s |" % (
            source.get("id"),
            source.get("kernel_version_expected") or "n/a",
            source.get("kernel_version_from_makefile") or "n/a",
            "PASS" if source.get("verified_commit") == source.get("expected_commit") else "CHECK",
            source.get("scanned_file_count", "targeted"),
        ))
    lines.extend(["", "## Per-source details", ""])
    for source in report["sources"]:
        lines.extend([
            "### " + source.get("id", "unknown"),
            "",
            "- Repository: " + str(source.get("repository")),
            "- Pinned ref: " + str(source.get("ref")),
            "- Commit: " + str(source.get("expected_commit")),
            "- Commit date: " + str(source.get("commit_date") or "not supplied"),
            "- Kernel version: expected " + str(source.get("kernel_version_expected") or "unknown") +
              "; Makefile " + str(source.get("kernel_version_from_makefile") or "not parsed"),
            "- Scan method: " + str(source.get("scan_method")),
        ])
        if "scanned_file_count" in source:
            lines.extend([
                "- Files scanned: %s; directories scanned: %s" %
                  (source["scanned_file_count"], source["scanned_directory_count"]),
                "- ARM64 defconfigs: %s" % source["arm64_defconfig_count"],
                "- Relevant defconfigs: " + (", ".join(source["relevant_arm64_defconfigs"]) or "none found"),
                "- Driver subsystems: " + (", ".join(source["driver_modules"]) or "none found"),
                "- Techpack subsystems: " + (", ".join(source["techpack_modules"]) or "none found"),
                "",
                "| Module path | File count |",
                "|---|---:|",
            ])
            for path, count in source["module_file_counts"].items():
                lines.append("| %s | %s |" % (path, count))
            lines.extend(["", "Build configuration evidence:"])
            evidence_found = False
            for filename, evidence in source["build_config_evidence"].items():
                if evidence:
                    evidence_found = True
                    lines.append("- " + filename + ": " + "; ".join(evidence))
            if not evidence_found:
                lines.append("- No recognized build variables found in the inspected config files.")
        else:
            lines.extend(["", "Targeted GKI directory inventory:"])
            for path, data in source.get("gitiles_directory_inventory", {}).items():
                if data.get("missing"):
                    lines.append("- " + path + ": absent")
                else:
                    lines.append("- " + path + ": %s immediate entries" % data["entry_count"])
        lines.append("")
    lines.extend(["## Structural comparison", ""])
    lines.append("File-path additions/removals are compared against the official RMX2072 Android Q 4.19.81 tree. They are structural signals, not proof of source-code behavior changes or driver compatibility.")
    lines.append("")
    for comparison in report["comparisons"]:
        lines.extend([
            "### %s → %s" % (comparison["baseline"], comparison["candidate"]),
            "",
            "| Group | Baseline files | Candidate files | Added paths | Removed paths |",
            "|---|---:|---:|---:|---:|",
        ])
        for group in comparison["groups"]:
            lines.append("| %s | %s | %s | %s | %s |" % (
                group["group"], group["baseline_file_count"],
                group["candidate_file_count"], group["added_count"],
                group["removed_count"]))
        lines.append("")
        for group in comparison["groups"]:
            if group["added_sample"] or group["removed_sample"]:
                lines.append("**" + group["group"] + "**")
                if group["added_sample"]:
                    lines.append("- Added examples: " + ", ".join(group["added_sample"]))
                if group["removed_sample"]:
                    lines.append("- Removed examples: " + ", ".join(group["removed_sample"]))
                lines.append("")
    lines.extend([
        "## Limitations and interpretation",
        "",
        "- The GitHub scan recursively enumerates selected top-level trees. It is not a byte-for-byte source diff.",
        "- The Android Common Kernel 6.18 entry is inspected through Gitiles directory listings; it is not included in full file-path diff counts.",
        "- Identical paths can contain substantially different code. A later source-analysis phase must inspect content diffs for selected subsystems.",
        "- A path absent from a candidate tree may have moved, been renamed, generated at build time, or be supplied by another repository.",
        "- No kernel was compiled, booted or flashed by this workflow.",
        "- Vendor binaries and device dumps are never downloaded by this workflow.",
        "",
        "## Errors",
        "",
    ])
    if report["errors"]:
        for error in report["errors"]:
            lines.append("- " + error)
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default="sources/SOURCE_LOCK.json")
    parser.add_argument("--out", default="reports/kernel-source-research")
    args = parser.parse_args()

    with open(args.lock, "r", encoding="utf-8") as handle:
        lock = json.load(handle)

    os.makedirs(args.out, exist_ok=True)
    sources = [
        source for source in lock.get("sources", [])
        if source.get("category") in ("official-kernel", "community-kernel", "official-ack-gki")
    ]
    report_sources = []
    errors = []
    internal_sources = []

    for source in sources:
        try:
            if (source.get("category") == "official-ack-gki" or
                    "googlesource.com" in source.get("url", "")):
                result = gitiles_kernel_source(source)
            else:
                result = github_kernel_source(source)
            report_sources.append(result)
            internal_sources.append(result)
            print("[OK] %s %s" % (source["id"], source.get("commit")))
        except Exception as exc:
            message = "%s: %s" % (source.get("id"), exc)
            errors.append(message)
            print("[ERROR] " + message, file=sys.stderr)

    baseline = next((item for item in internal_sources
                     if item["id"] == "realme-player-android-q-kernel"), None)
    comparisons = []
    if baseline:
        for candidate in internal_sources:
            if candidate is baseline or not candidate.get("_files"):
                continue
            comparisons.append(compare_sources(baseline, candidate))
    else:
        errors.append("Official Android Q baseline was not available; structural comparisons were skipped.")

    for item in report_sources:
        item.pop("_files", None)

    report = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_target": lock.get("target", {}).get("model", "unknown") + " / " +
                         lock.get("target", {}).get("codename", "unknown"),
        "source_lock_path": args.lock,
        "sources": report_sources,
        "comparisons": comparisons,
        "errors": errors,
        "workflow_scope": "read-only source inventory and structural path comparison",
    }

    json_path = os.path.join(args.out, "kernel-source-research.json")
    markdown_path = os.path.join(args.out, "kernel-source-research.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    with open(markdown_path, "w", encoding="utf-8") as handle:
        handle.write(markdown_report(report))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("# Kernel Source Research\n\n")
            handle.write("- Sources inspected: %s\n" % len(report_sources))
            handle.write("- Structural comparisons: %s\n" % len(comparisons))
            handle.write("- Errors: %s\n\n" % len(errors))
            handle.write("Full Markdown and JSON reports are uploaded as workflow artifacts.\n")

    print("Reports written:")
    print(" - " + markdown_path)
    print(" - " + json_path)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
