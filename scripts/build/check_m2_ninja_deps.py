"""Inspect all commands in init's generated Ninja closure without executing them."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def inspect_commands(commands):
    # With ALLOW_MISSING_DEPENDENCIES, Soong emits fatal error edges. Looking at
    # the whole requested closure reports every such edge before compilation.
    return sorted(set(line.strip() for line in commands.splitlines()
                      if 'missing dependencies:' in line))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    graph = Path('out/combined-rmx2072_m2_init.ninja')
    if not graph.is_file():
        raise ValueError('Expected product Ninja graph was not generated')
    result = subprocess.run(['prebuilts/build-tools/linux-x86/bin/ninja',
                             '-f', str(graph), '-t', 'commands', 'init_first_stage'],
                            check=True, capture_output=True, text=True)
    if not result.stdout.strip():
        raise ValueError('Requested init target has an empty command closure')
    missing = inspect_commands(result.stdout)
    report = dict(target='init_first_stage', graph=str(graph),
                  method='ninja -t commands (read only)',
                  command_count=len(result.stdout.splitlines()),
                  commands_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
                  missing_dependency_commands=missing)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('init_first_stage command closure:', report['command_count'],
          'commands;', len(missing), 'missing-dependency edges')
    for command in missing:
        print(command)
    if missing:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
