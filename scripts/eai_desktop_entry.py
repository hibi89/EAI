"""Frozen Windows entrypoint; only starts the local Tk event loop."""
from eai.desktop_app import main

if __name__ == "__main__":
    raise SystemExit(main())
