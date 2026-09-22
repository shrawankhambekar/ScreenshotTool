#!/bin/bash
set -e

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
REAL_HOME="${REAL_HOME:-$HOME}"

echo "=========================================="
echo "    Uninstalling Wayland Screenshot Tool   "
echo "=========================================="

# Remove symlinks and desktop entry
rm -f "$REAL_HOME/.local/bin/screenshot-tool"
rm -f "$REAL_HOME/.local/bin/screenshot-menu"
rm -f "$REAL_HOME/.local/share/applications/screenshot-tool.desktop"
echo "Removed launcher shortcuts."

# Remove keybind from labwc if present
LABWC_RC="$REAL_HOME/.config/labwc/rc.xml"
if [ -f "$LABWC_RC" ]; then
    python3 - << PYEOF
import xml.etree.ElementTree as ET
import os

rc_path = "$LABWC_RC"
try:
    tree = ET.parse(rc_path)
    root = tree.getroot()
    kb_elem = root.find("keyboard")
    if kb_elem is not None:
        to_remove = []
        for kb in kb_elem.findall("keybind"):
            if kb.get("key") == "Print":
                cmd = kb.find(".//command")
                if cmd is not None and "screenshot-overlay" in (cmd.text or ""):
                    to_remove.append(kb)
        for r in to_remove:
            kb_elem.remove(r)
        if hasattr(ET, "indent"):
            ET.indent(root, space="    ")
        tree.write(rc_path, encoding="utf-8", xml_declaration=True)
        print("Removed Print keybind from Labwc.")
except Exception as e:
    pass
PYEOF

    if pgrep -x labwc >/dev/null 2>&1; then
        labwc --reconfigure 2>/dev/null || true
    fi
fi

echo "Screenshot Tool uninstalled successfully."
