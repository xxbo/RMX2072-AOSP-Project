#!/usr/bin/env python3
"""Require every explicit assignment in a platform fragment to survive Kconfig."""
import argparse
import pathlib


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=pathlib.Path)
    p.add_argument('--fragment', required=True, type=pathlib.Path)
    a = p.parse_args()
    wanted = [s for s in a.fragment.read_text().splitlines() if s.startswith('CONFIG_')]
    actual = set(a.config.read_text().splitlines())
    missing = [s for s in wanted if s not in actual]
    if missing:
        raise SystemExit('Required platform config missing: '+', '.join(missing))
    print(f'Verified {len(wanted)} required platform assignments')


if __name__ == '__main__':
    main()
