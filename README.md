# Wayland Screenshot Tool

An interactive, high-performance screen capture overlay and toolbar designed for Wayland compositors (Labwc on Raspberry Pi OS, Sway, Hyprland, etc.).

---

## ⚡ Quick Installation

### Method 1: Terminal (Recommended - Single Command)
If you have the `ScreenshotTool.zip` archive, copy & paste this command:
```bash
unzip -o ScreenshotTool.zip && cd ScreenshotTool && ./install.sh
```

Or from inside the extracted folder:
```bash
./install.sh
```

### Method 2: One-Click GUI Install
1. Open the extracted **`ScreenshotTool`** folder in your file manager.
2. Double-click **`Install Screenshot Tool`** (`install.desktop`).

---

## 🎯 How to Use After Installing

| Shortcut / Command | Action |
| :--- | :--- |
| <kbd>Print Screen</kbd> | **Interactive Overlay**: Drag to crop any area, snap to windows, or capture full screen. |
| <kbd>Shift</kbd> + <kbd>Print Screen</kbd> | **Quick Toolbar Menu**: Horizontal menu with Rectangle, Full Screen, and Record options. |
| `screenshot-tool` | Terminal command to launch the interactive GTK4 overlay. |
| `screenshot-menu` | Terminal command to launch the Wofi toolbar menu. |
| `screen-recorder` | Terminal command to directly launch the floating screen recording controller. |

*Captured screenshots are automatically copied to your clipboard (`wl-copy`) ready to paste (<kbd>Ctrl</kbd>+<kbd>V</kbd>) anywhere. Screen recordings are saved to `~/Videos/Recordings/rec_*.mp4`.*

---

## ✨ Features
- **Instant Hardware Keybind**: Automatically binds <kbd>Print</kbd> and <kbd>Shift</kbd>+<kbd>Print</kbd>.
- **High-Performance Screen Recording (`wf-recorder`)**:
  - **Movable Floating Controller**: Draggable anywhere on the desktop via the grip handle `⠿`.
  - **Start, Stop, Pause & Resume**: Click `❚❚` to pause without splitting files; click `▶` to resume; click `■` to finalize the MP4.
  - **Live Duration Timer**: Precision digital timer (`MM:SS`) tracking elapsed recording time.
  - **Clean Recording Guarantee**: When recording a region, the toolbar positions itself outside the capture geometry. When recording full-screen, click `▲` to collapse the controller into a minimal edge pill.
  - **Pointer Capture**: The mouse cursor is rendered and tracked smoothly across the entire recording.
- **Interactive Overlay (`screenshot-tool`)**:
  - **Rectangle Drag**: Click and drag to crop any area with translucent guides and real-time pixel size indicator.
  - **Window Snapping**: Automatically detects and highlights window boundaries.
  - **Full Screen**: Instant one-click full monitor capture.
  - **Direct Clipboard Integration**: Copies clean PNG directly into Wayland clipboard.
- **Toolbar Menu Mode (`screenshot-menu`)**:
  - Compact Wofi toolbar with Rectangle, Full Screen, and Record options that remembers your last-used selection mode.
- **Robust Desktop Integration**:
  - Preserves your system's default Labwc theme and desktop preferences so Raspberry Pi OS appearance settings will never erase your keybinds.

---

## 📦 Supported Operating Systems & Dependencies
The installer automatically detects your package manager and installs all necessary libraries:
- **Debian / Ubuntu / Raspberry Pi OS**: `apt`
- **Arch Linux / Manjaro**: `pacman`
- **Fedora / RHEL**: `dnf`
- **openSUSE**: `zypper`

**Packages installed**: `grim`, `slurp`, `wl-clipboard`, `wofi`, `libgtk4-layer-shell`, `python3-gi`, `python3-cairo`.

---

## 🗑️ Uninstallation
To cleanly remove all commands, desktop shortcuts, and keybindings:
```bash
./uninstall.sh
```
