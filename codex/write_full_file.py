#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Safely overwrite a file from stdin using a full-file write.'
    )
    parser.add_argument('target', help='Absolute or repo-relative target file path')
    parser.add_argument(
        '--py-compile',
        action='store_true',
        help='Validate Python syntax before replacing the target file',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()

    if not target.parent.exists():
        raise SystemExit(f'target parent does not exist: {target.parent}')

    content = sys.stdin.read()
    fd, temp_path = tempfile.mkstemp(
        prefix=target.stem + '.',
        suffix=target.suffix or '.tmp',
        dir=str(target.parent),
        text=True,
    )
    os.close(fd)
    temp_file = Path(temp_path)

    try:
        temp_file.write_text(content)
        if args.py_compile or target.suffix == '.py':
            subprocess.run(
                [sys.executable, '-m', 'py_compile', str(temp_file)],
                check=True,
            )
        temp_file.replace(target)
    finally:
        if temp_file.exists():
            temp_file.unlink()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
