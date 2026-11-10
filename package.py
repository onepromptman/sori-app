#!/usr/bin/env python3
"""Build browser and plugin ZIPs; --windows-exe adds the optional EXE. See public_release.py."""

from public_release import main

if __name__ == "__main__":
    raise SystemExit(main())
