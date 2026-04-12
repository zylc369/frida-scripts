"""Re-exports for backward compatibility during migration.

All frida operations are now in FridaClient (frida_client.py).
This module re-exports types for existing imports.
"""

from .frida_client import AppInfo, FridaServerError

__all__ = ["AppInfo", "FridaServerError"]
