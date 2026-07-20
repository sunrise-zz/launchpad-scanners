"""Compatibility entrypoint for the on-chain Pons reputation collector.

The old implementation called pons.family's launches and graduations endpoints.
Those endpoints are dead; keep the familiar command while routing it to the
RPC-only collector.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from reputation import main  # noqa: E402


if __name__ == "__main__":
    main()
