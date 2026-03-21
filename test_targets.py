"""Verify that propose_targets can find Dock items via the AX API."""
from src.tool_runtime.tools.targets import (
    _collect_dock_ax_targets,
    _collect_frontmost_ax_targets,
    propose_targets,
)

print("=== Dock AX targets ===")
dock = _collect_dock_ax_targets()
for t in dock:
    print(f"  {t['label']:30s}  center={t['center']}")

print(f"\n=== Frontmost app AX targets (first 5) ===")
frontmost = _collect_frontmost_ax_targets()
for t in frontmost[:5]:
    print(f"  {t['label']:30s}  role={t['role']}  center={t['center']}")

print(f"\n=== propose_targets('Slack') ===")
result = propose_targets("Slack", limit=3)
print(result)
