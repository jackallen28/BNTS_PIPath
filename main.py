#!/usr/bin/env python3
"""Start PiPath.   python3 main.py   (add --scale 1.2 for bigger text on a large screen)"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.version_info < (3, 11):
    sys.exit("PiPath needs Python 3.11 or newer (Raspberry Pi OS Bookworm or later).")



def main():
    ap = argparse.ArgumentParser(description="PiPath: a Python coding tutor for Raspberry Pi")
    ap.add_argument("--scale", type=float, default=1.0, help="text size multiplier, e.g. 1.25")
    ap.add_argument("--no-update", action="store_true", help="open the installed version without checking for updates")
    args = ap.parse_args()
    from pipath.updater import launch_update_check
    if not launch_update_check(Path(__file__).resolve().parent, enabled=not args.no_update):
        return
    from pipath.app import PiPathApp
    PiPathApp(scale=args.scale).mainloop()


if __name__ == "__main__":
    main()
