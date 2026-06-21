#!/usr/bin/env python3
"""
Run the full parallax conformance suite — thin wrapper over `judge.py` (kept for
the documented entrypoint). judge.py runs all three layers (schema / interface /
behaviour) against a daemon and emits the pre-registered scorecard + gate verdict.

  python3 conformance/run.py [--daemon PATH] [--adapter DECL.json] [--home SYNC_HOME]
                             [--efficiency]

Point --daemon (+ --adapter) at a partner's implementation to verify it by
measurement, WITHOUT reading its code. Exit 0 iff the daemon is CONFORMANT (no
hard-check failure). --efficiency also runs the efficiency suite (M1-M4 →
_efficiency.json), so one command emits both _verdict.json and _efficiency.json.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--efficiency"]
    rc = subprocess.run([sys.executable, os.path.join(HERE, "judge.py"), *args]).returncode
    if "--efficiency" in sys.argv:
        subprocess.run([sys.executable, os.path.join(HERE, "efficiency.py")])
    sys.exit(rc)
