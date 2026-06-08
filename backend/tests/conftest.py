"""Test setup: keep tests offline and free of background threads.

Must run before app modules import (conftest is imported first), so the
scheduler never starts and TRADING_MODE stays paper during tests.
"""
import os

os.environ.setdefault("AUTO_SCHEDULE", "false")
os.environ.setdefault("TRADING_MODE", "paper")
