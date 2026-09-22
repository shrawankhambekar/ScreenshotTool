#!/bin/bash
set -e

# ==============================================================================
# CapturePi Installer
# Works on Debian/Ubuntu/Raspberry Pi OS, Arch, Fedora, and openSUSE
# ==============================================================================

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
REAL_HOME="${REAL_HOME:-$HOME}"

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
export OVERLAY_LAUNCHER="$INSTALL_DIR/scripts/capturepi"
export MENU_LAUNCHER="$INSTALL_DIR/scripts/capturepi-menu"
export RECORDER_LAUNCHER="$INSTALL_DIR/scripts/capturepi-recorder"

echo "=========================================="
echo "          Installing CapturePi            "
echo "  Raspberry Pi & Wayland Screen Recorder  "
echo "=========================================="
echo "Directory:   $INSTALL_DIR"
echo "Target User: $REAL_USER ($REAL_HOME)"
echo ""

# 1. Install system dependencies
echo "[1/4] Checking system dependencies..."

check_deps() {
    for cmd in grim slurp wl-copy wofi wf-recorder python3; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            return 1
        fi
    done
    if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Gtk4LayerShell', '1.0'); import cairo" >/dev/null 2>&1; then
        return 1
    fi
    return 0
}

run_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        "$@"
    fi
}

if check_deps; then
    echo "  -> All required dependencies are already present. Skipping package manager installation."
else
    echo "  -> Missing dependencies detected. Installing via package manager..."
    if command -v apt-get >/dev/null 2>&1; then
        run_sudo apt-get update -y
        run_sudo apt-get install -y \
            grim \
            slurp \
            wl-clipboard \
            wf-recorder \
            wofi \
            python3-gi \
            gir1.2-gtk-4.0 \
            gir1.2-gtk4layershell-1.0 \
            libgtk4-layer-shell0 \
            python3-cairo \
            python3-gi-cairo
    elif command -v pacman >/dev/null 2>&1; then
        run_sudo pacman -S --needed --noconfirm \
            grim \
            slurp \
            wl-clipboard \
            wf-recorder \
            wofi \
            python-gobject \
            gtk4-layer-shell \
            python-cairo
    elif command -v dnf >/dev/null 2>&1; then
        run_sudo dnf install -y \
            grim \
            slurp \
            wl-clipboard \
            wf-recorder \
            wofi \
            python3-gobject \
            gtk4-layer-shell \
            python3-cairo
    elif command -v zypper >/dev/null 2>&1; then
        run_sudo zypper install -y \
            grim \
            slurp \
            wl-clipboard \
            wf-recorder \
            wofi \
            python3-gobject \
            gtk4-layer-shell \
            python3-cairo
    else
        echo "Notice: Package manager not recognized. Please ensure grim, slurp, wl-clipboard, wf-recorder, wofi, and libgtk4-layer-shell are installed."
    fi
fi

# 2. Make scripts executable
echo "[2/4] Setting file permissions..."
chmod +x "$INSTALL_DIR"/scripts/* 2>/dev/null || true
chmod +x "$INSTALL_DIR"/overlay/*.py 2>/dev/null || true
chmod +x "$INSTALL_DIR"/*.sh 2>/dev/null || true

# 3. Create CLI symlinks, Icons, and Desktop shortcuts
echo "[3/4] Setting up launcher shortcuts & icon..."
BIN_DIR="$REAL_HOME/.local/bin"
mkdir -p "$BIN_DIR"

# Install CapturePi primary commands
ln -sf "$INSTALL_DIR/scripts/capturepi" "$BIN_DIR/capturepi"
ln -sf "$INSTALL_DIR/scripts/capturepi-menu" "$BIN_DIR/capturepi-menu"
ln -sf "$INSTALL_DIR/scripts/capturepi-recorder" "$BIN_DIR/capturepi-recorder"

# Install backward-compatibility aliases
ln -sf "$INSTALL_DIR/scripts/screenshot-overlay" "$BIN_DIR/screenshot-tool"
ln -sf "$INSTALL_DIR/scripts/screenshot-menu" "$BIN_DIR/screenshot-menu"
ln -sf "$INSTALL_DIR/scripts/screen-recorder" "$BIN_DIR/screen-recorder"

chown -h "$REAL_USER":"$REAL_USER" "$BIN_DIR/capturepi" "$BIN_DIR/capturepi-menu" "$BIN_DIR/capturepi-recorder" \
    "$BIN_DIR/screenshot-tool" "$BIN_DIR/screenshot-menu" "$BIN_DIR/screen-recorder" 2>/dev/null || true
echo "  -> Created ~/.local/bin/capturepi, capturepi-menu, and capturepi-recorder"

# Install Icon
ICON_DIR="$REAL_HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$ICON_DIR"
if [ -f "$INSTALL_DIR/assets/icon.png" ]; then
    cp "$INSTALL_DIR/assets/icon.png" "$ICON_DIR/capturepi.png"
    chown "$REAL_USER":"$REAL_USER" "$ICON_DIR/capturepi.png" 2>/dev/null || true
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$REAL_HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
    echo "  -> Installed CapturePi icon to ~/.local/share/icons/hicolor/256x256/apps/capturepi.png"
fi

# Install Desktop Entry
APP_DIR="$REAL_HOME/.local/share/applications"
mkdir -p "$APP_DIR"
if [ -f "$INSTALL_DIR/CapturePi.desktop" ]; then
    cp "$INSTALL_DIR/CapturePi.desktop" "$APP_DIR/CapturePi.desktop"
    sed -i "s|^Exec=.*|Exec=$OVERLAY_LAUNCHER|g" "$APP_DIR/CapturePi.desktop"
else
    cat << DESKTOPEOF > "$APP_DIR/CapturePi.desktop"
[Desktop Entry]
Type=Application
Name=CapturePi
GenericName=Screen Capture & Recording Tool
Comment=Interactive Wayland screenshot overlay and screen recorder with dual audio
Exec=$OVERLAY_LAUNCHER
Icon=capturepi
Terminal=false
Categories=Graphics;Utility;AudioVideo;
Keywords=screenshot;screen;capture;record;video;wayland;grim;wf-recorder;audio;
DESKTOPEOF
fi

# Backward-compatibility desktop link
ln -sf "$APP_DIR/CapturePi.desktop" "$APP_DIR/screenshot-tool.desktop"

chown "$REAL_USER":"$REAL_USER" "$APP_DIR/CapturePi.desktop" 2>/dev/null || true
chown -h "$REAL_USER":"$REAL_USER" "$APP_DIR/screenshot-tool.desktop" 2>/dev/null || true
echo "  -> Created desktop entry in ~/.local/share/applications/CapturePi.desktop"

# 4. Configure Print Screen keybinding
echo "[4/4] Configuring Print Screen keybind..."

# 4A. Labwc (Raspberry Pi OS Desktop, labwc compositors)
LABWC_DIR="$REAL_HOME/.config/labwc"
export LABWC_RC="$LABWC_DIR/rc.xml"

mkdir -p "$LABWC_DIR"
chown "$REAL_USER":"$REAL_USER" "$LABWC_DIR" 2>/dev/null || true

python3 - << 'PYEOF'
import os
import shutil
import xml.etree.ElementTree as ET

rc_path = os.environ.get("LABWC_RC", "")
launcher = os.environ.get("OVERLAY_LAUNCHER", "")
menu_launcher = os.environ.get("MENU_LAUNCHER", "")

if not rc_path or not launcher:
    exit(0)

# If rc.xml does not exist or is smaller than 200 bytes, copy system default if available
sys_rc = "/etc/xdg/labwc/rc.xml"
if (not os.path.exists(rc_path) or os.path.getsize(rc_path) < 200) and os.path.exists(sys_rc):
    try:
        shutil.copyfile(sys_rc, rc_path)
    except Exception:
        pass

try:
    tree = ET.parse(rc_path)
    root = tree.getroot()
except Exception:
    root = ET.Element("openbox_config", {"xmlns": "http://openbox.org/3.4/rc"})
    tree = ET.ElementTree(root)

# Handle namespace if present
ns = ""
if root.tag.startswith("{"):
    ns = root.tag.split("}")[0] + "}"
    ET.register_namespace("", "http://openbox.org/3.4/rc")

kb_elem = root.find(f"{ns}keyboard")
if kb_elem is None:
    kb_elem = root.find("keyboard")
if kb_elem is None:
    kb_elem = ET.SubElement(root, f"{ns}keyboard")

# Update Print keybind
found = False
for kb in kb_elem.findall(f"{ns}keybind") + kb_elem.findall("keybind"):
    if kb.get("key") == "Print":
        action = kb.find(f"{ns}action")
        if action is None:
            action = kb.find("action")
        if action is None:
            action = ET.SubElement(kb, f"{ns}action", {"name": "Execute"})
        cmd = action.find(f"{ns}command")
        if cmd is None:
            cmd = action.find("command")
        if cmd is None:
            cmd = ET.SubElement(action, f"{ns}command")
        cmd.text = launcher
        found = True
        break

if not found:
    new_kb = ET.SubElement(kb_elem, f"{ns}keybind", {"key": "Print"})
    action = ET.SubElement(new_kb, f"{ns}action", {"name": "Execute"})
    cmd = ET.SubElement(action, f"{ns}command")
    cmd.text = launcher

# Also ensure Shift+Print for menu
if menu_launcher:
    found_menu = False
    for kb in kb_elem.findall(f"{ns}keybind") + kb_elem.findall("keybind"):
        if kb.get("key") in ["S-Print", "Shift-Print"]:
            action = kb.find(f"{ns}action")
            if action is None:
                action = kb.find("action")
            if action is None:
                action = ET.SubElement(kb, f"{ns}action", {"name": "Execute"})
            cmd = action.find(f"{ns}command")
            if cmd is None:
                cmd = action.find("command")
            if cmd is None:
                cmd = ET.SubElement(action, f"{ns}command")
            cmd.text = menu_launcher
            found_menu = True
            break
    if not found_menu:
        new_kb = ET.SubElement(kb_elem, f"{ns}keybind", {"key": "S-Print"})
        action = ET.SubElement(new_kb, f"{ns}action", {"name": "Execute"})
        cmd = ET.SubElement(action, f"{ns}command")
        cmd.text = menu_launcher

if hasattr(ET, "indent"):
    ET.indent(root, space="  ")

tree.write(rc_path, encoding="utf-8", xml_declaration=True)
print(f"  -> Successfully verified/updated Labwc keybind in {rc_path}")
PYEOF

chown "$REAL_USER":"$REAL_USER" "$LABWC_RC" 2>/dev/null || true

# Reload labwc if running
if pgrep -x labwc >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
        su - "$REAL_USER" -c "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0} labwc --reconfigure" 2>/dev/null || true
    else
        labwc --reconfigure 2>/dev/null || true
    fi
    echo "  -> Reloaded labwc configuration."
fi

# 4B. Sway
SWAY_CONFIG="$REAL_HOME/.config/sway/config"
if [ -f "$SWAY_CONFIG" ]; then
    if ! grep -q "capturepi" "$SWAY_CONFIG"; then
        echo "" >> "$SWAY_CONFIG"
        echo "# CapturePi" >> "$SWAY_CONFIG"
        echo "bindsym Print exec $OVERLAY_LAUNCHER" >> "$SWAY_CONFIG"
        echo "  -> Added Print keybind to Sway config ($SWAY_CONFIG)"
    fi
fi

# 4C. Hyprland
HYPR_CONFIG="$REAL_HOME/.config/hypr/hyprland.conf"
if [ -f "$HYPR_CONFIG" ]; then
    if ! grep -q "capturepi" "$HYPR_CONFIG"; then
        echo "" >> "$HYPR_CONFIG"
        echo "# CapturePi" >> "$HYPR_CONFIG"
        echo "bind = , Print, exec, $OVERLAY_LAUNCHER" >> "$HYPR_CONFIG"
        echo "  -> Added Print keybind to Hyprland config ($HYPR_CONFIG)"
    fi
fi

echo ""
echo "=========================================="
echo "     CapturePi Installation Complete!     "
echo "=========================================="
echo "You can now:"
echo "  1. Press 'Print Screen' on your keyboard"
echo "  2. Or run 'capturepi' from anywhere"
echo "  3. Or run 'capturepi-menu' for the quick toolbar menu"
echo "  4. Or run 'capturepi-recorder' to open the recording controller"
echo "=========================================="
