#!/usr/bin/env python3
"""Build a pinned legacy kernel candidate; never packages or flashes a boot image."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import time
import urllib.request


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=['config', 'kernel'], default='config')
    p.add_argument('--work', required=True, type=pathlib.Path)
    p.add_argument('--artifacts', required=True, type=pathlib.Path)
    p.add_argument('--jobs', type=int, default=4)
    args = p.parse_args()
    if not 1 <= args.jobs <= 32:
        p.error('--jobs must be between 1 and 32')
    project = pathlib.Path(__file__).resolve().parents[2]
    work, artifacts = args.work.resolve(), args.artifacts.resolve()
    if work == project or project in work.parents:
        p.error('--work must be outside the project checkout')
    work.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    profile = json.loads((project/'build/legacy-kernel.json').read_text())
    lock = json.loads((project/'sources/SOURCE_LOCK.json').read_text())
    source = next(x for x in lock['sources'] if x['id'] == profile['kernel_source_id'])
    clang = profile['clang']
    report = dict(profile=profile['profile'], stage=args.stage, status='running',
                  hardware_status='not-boot-tested-not-flashable', kernel_commit=source['commit'],
                  clang_commit=clang['commit'], clang_directory=clang['directory'], commands=[])
    env = os.environ.copy()
    log = (artifacts/'build.log').open('w', encoding='utf-8', buffering=1)
    def save():
        (artifacts/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    def run(cmd, cwd=None):
        report['commands'].append(cmd)
        save()
        print('+ '+' '.join(map(str, cmd)), flush=True)
        log.write('+ '+' '.join(map(str, cmd))+'\n')
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace')
        for line in proc.stdout:
            print(line, end='', flush=True)
            log.write(line)
        code = proc.wait()
        if code:
            raise RuntimeError(f'command exited {code}: {cmd[0]}')
    def download(url, dest):
        error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=180) as response, dest.open('wb') as f:
                    shutil.copyfileobj(response, f, 1024 * 1024)
                return
            except Exception as exc:
                error = exc
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        raise error
    def unpack(archive, dest, strip_root=False):
        dest.mkdir(parents=True, exist_ok=True)
        # Archives are fetched from immutable, explicitly selected upstream commits.
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if member.name.startswith('/') or '..' in pathlib.PurePosixPath(member.name).parts:
                    raise ValueError('unsafe archive member')
            tf.extractall(dest, filter='data')
        if strip_root:
            roots = list(dest.iterdir())
            if len(roots) != 1 or not roots[0].is_dir():
                raise ValueError('expected one source archive root')
            return roots[0]
        return dest
    try:
        save()
        free = shutil.disk_usage(work).free
        report['initial_free_bytes'] = free
        if free < 10 * 1024**3:
            raise RuntimeError('at least 10 GiB free workspace required for this experiment')
        kernel_archive, clang_archive = work/'kernel.tar.gz', work/'clang.tar.gz'
        download(f"https://codeload.github.com/{source['repository']}/tar.gz/{source['commit']}", kernel_archive)
        report['kernel_archive_sha256'] = sha256(kernel_archive)
        extracted = unpack(kernel_archive, work/'kernel', strip_root=True)
        # qcacld repeats source paths in its flags; long archive roots exceed
        # Linux's per-argument limit when make passes the recipe to /bin/sh.
        kernel = work/'k'
        extracted.rename(kernel)
        # Avoid retaining compressed and unpacked copies in the constrained runner.
        kernel_archive.unlink()
        report['patches'] = {}
        for name in profile.get('patches', []):
            patch = project/name
            run(['git', 'apply', '--check', str(patch)], cwd=kernel)
            run(['git', 'apply', str(patch)], cwd=kernel)
            report['patches'][name] = sha256(patch)
        download(f"{clang['repository']}/+archive/{clang['commit']}/{clang['directory']}.tar.gz", clang_archive)
        report['clang_archive_sha256'] = sha256(clang_archive)
        toolchain = unpack(clang_archive, work/'clang')
        clang_archive.unlink()
        env['PATH'] = str(toolchain/'bin')+os.pathsep+env['PATH']
        env.update(ARCH='arm64', SUBARCH='arm64', KBUILD_BUILD_USER='rmx2072-ci',
                   KBUILD_BUILD_HOST='github-actions', KBUILD_BUILD_TIMESTAMP='2026-11-06 00:00:00 +0000',
                   KBUILD_BUILD_VERSION='1', SOURCE_DATE_EPOCH='1793923200')
        run(['clang', '--version'])
        run(['make', '--version'])
        out = work/'out'
        out.mkdir(exist_ok=True)
        make = ['make', '-C', str(kernel), f'O={out}', 'ARCH=arm64', 'CC=clang',
                'LD=ld.lld', 'AR=llvm-ar', 'NM=llvm-nm', 'OBJCOPY=llvm-objcopy',
                'OBJDUMP=llvm-objdump', 'STRIP=llvm-strip', 'CLANG_TRIPLE=aarch64-linux-gnu-',
                'CROSS_COMPILE=aarch64-linux-gnu-', 'CROSS_COMPILE_ARM32=arm-linux-gnueabi-', 'LLVM_IAS=1']
        run(make+[profile['defconfig']])
        fragments = [kernel/'arch/arm64/configs'/f for f in profile['source_fragments']]
        fragments.append(project/profile['device_fragment'])
        run(['bash', str(kernel/'scripts/kconfig/merge_config.sh'), '-m', '-O', str(out),
             str(out/'.config')]+[str(f) for f in fragments], cwd=kernel)
        run(make+['olddefconfig'])
        config = (out/'.config').read_text()
        for key, value in profile['required_config'].items():
            if f'{key}={value}' not in config.splitlines():
                raise RuntimeError(f'required device config not selected: {key}={value}')
        shutil.copyfile(out/'.config', artifacts/'kernel.config')
        report['config_sha256'] = sha256(out/'.config')
        report['input_fragment_sha256'] = {str(f.relative_to(kernel) if kernel in f.parents else f.relative_to(project)): sha256(f) for f in fragments}
        if args.stage == 'kernel':
            run(make+[f'-j{args.jobs}', 'Image.gz', 'dtbs', 'modules'])
            image = out/'arch/arm64/boot/Image.gz'
            if not image.is_file() or not image.stat().st_size:
                raise RuntimeError('build produced no Image.gz')
            shutil.copyfile(image, artifacts/'Image.gz')
            with tarfile.open(artifacts/'dtbs.tar.gz', 'w:gz') as tf:
                for f in sorted((out/'arch/arm64/boot/dts').rglob('*.dtb')):
                    tf.add(f, arcname=f.relative_to(out/'arch/arm64/boot/dts'))
            modules = sorted(out.rglob('*.ko'))
            with tarfile.open(artifacts/'modules.tar.gz', 'w:gz') as tf:
                for f in modules:
                    tf.add(f, arcname=f.relative_to(out))
            report['module_count'] = len(modules)
            for name in ['Module.symvers', 'System.map', 'include/config/kernel.release']:
                if (out/name).is_file():
                    shutil.copyfile(out/name, artifacts/pathlib.Path(name).name)
        report['status'] = 'config-validated' if args.stage == 'config' else 'build-tested'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        log.close()
        report['artifacts'] = {f.name: dict(size_bytes=f.stat().st_size, sha256=sha256(f))
                               for f in artifacts.iterdir() if f.is_file() and f.name != 'provenance.json'}
        save()


if __name__ == '__main__':
    main()
