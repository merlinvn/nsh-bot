"""Pytest configuration for nsh-mcp tests."""

import sys
from pathlib import Path

# Ensure src/ is on path so nsh_mcp imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))