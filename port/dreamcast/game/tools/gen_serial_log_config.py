#!/usr/bin/env python3
"""Generate the serial diagnostic switch and source identity, without stale knobs."""
import argparse
from pathlib import Path
import re
import subprocess


def identity(root):
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            text=True, stderr=subprocess.DEVNULL).strip()
        if not re.fullmatch(r"[0-9a-f]{12,40}", revision):
            return "unknown"
        dirty = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            text=True, stderr=subprocess.DEVNULL)
        return revision + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enabled", choices=("0", "1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    build = identity(root) if args.enabled == "1" else "disabled"
    content = ('#define RE4DC_SERIAL_LOG ' + args.enabled + '\n' +
               '#define RE4DC_SERIAL_LOG_BUILD_ID "' + build + '"\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists() or args.output.read_text() != content:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(content)
        temporary.replace(args.output)


if __name__ == "__main__":
    main()
