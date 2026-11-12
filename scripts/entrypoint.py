"""Frozen builds use exactly the installed/module dispatcher."""
from yadinassi.launcher import main

if __name__ == '__main__':
    raise SystemExit(main())
