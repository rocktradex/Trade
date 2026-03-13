"""
what changed:
- Replaced the legacy single-file launcher with a thin wrapper around main.py.

why:
- This keeps old startup commands working while the real logic now lives in modular files.
"""

from main import main

if __name__ == "__main__":
    main()
