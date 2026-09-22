#!/usr/bin/env python3

import gi
import subprocess
import os
import shutil

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

# GTK DrawingArea passes a cairo.Context. That conversion needs
# python3-gi-cairo (gi._gi_cairo), not only python3-cairo.
gi.require_foreign("cairo")

import cairo
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
STATE_FILE = os.path.join(PROJECT_DIR, ".last_mode")

DEFAULT_MODE = "Record"


class ScreenshotOverlay(Gtk.Application):

    def __init__(self):
        super().__init__(application_id="com.shrawan.ScreenshotTool")

        self.mode = self.load_mode()

        self.window = None
        self.overlay = None
        self.toolbar = None
        self.top_container = None
        self.record_hint = None

        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_current_x = 0
        self.drag_current_y = 0
        self.dragging = False
        self.capturing = False
        self.window_hover_rect = None
        self._pending_geometry = None

    # --------------------------------------------------
    # Remember last mode
    # --------------------------------------------------

    def load_mode(self):
        try:
            with open(STATE_FILE, "r") as f:
                mode = f.read().strip()

            if mode in ["Record", "Rectangle", "Full Screen", "Window"]:
                return mode

        except:
            pass

        return DEFAULT_MODE

    def save_mode(self):
        os.makedirs(PROJECT_DIR, exist_ok=True)

        with open(STATE_FILE, "w") as f:
            f.write(self.mode)

    # --------------------------------------------------
    # Application
    # --------------------------------------------------

    def do_activate(self):

        # A second Print Screen must not stack another overlay.
        if self.window is not None:
            return

        self.window = Gtk.Window(application=self)

        self.window.set_decorated(False)
        self.window.set_title("Screenshot Tool")
        self.window.connect("destroy", self.on_window_destroy)

        # Wayland layer-shell
        Gtk4LayerShell.init_for_window(self.window)

        Gtk4LayerShell.set_layer(
            self.window,
            Gtk4LayerShell.Layer.OVERLAY
        )

        # Cover entire screen
        Gtk4LayerShell.set_anchor(
            self.window,
            Gtk4LayerShell.Edge.TOP,
            True
        )

        Gtk4LayerShell.set_anchor(
            self.window,
            Gtk4LayerShell.Edge.BOTTOM,
            True
        )

        Gtk4LayerShell.set_anchor(
            self.window,
            Gtk4LayerShell.Edge.LEFT,
            True
        )

        Gtk4LayerShell.set_anchor(
            self.window,
            Gtk4LayerShell.Edge.RIGHT,
            True
        )

        # Make sure this is above normal windows
        Gtk4LayerShell.set_exclusive_zone(
            self.window,
            -1
        )

        # Keyboard handling (Escape to cancel, Enter/Space to record Full Screen)
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.window.add_controller(key_ctrl)

        # Apply window transparency CSS before widgets realize.
        self.load_css()

        self.create_ui()

        self.window.present()

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        elif keyval in [Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space]:
            if self.mode == "Record":
                self.start_recording(geometry=None)
                return True
            elif self.mode == "Full Screen":
                self.take_fullscreen()
                return True
        return False

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def create_ui(self):

        root = Gtk.Overlay()
        root.add_css_class("capture-root")

        self.window.set_child(root)

        # Main transparent capture area
        self.overlay = Gtk.DrawingArea()
        self.overlay.set_hexpand(True)
        self.overlay.set_vexpand(True)

        self.overlay.set_draw_func(
            self.draw_overlay
        )

        root.set_child(self.overlay)

        # Mouse handling - clicks
        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect(
            "pressed",
            self.mouse_pressed
        )
        self.overlay.add_controller(click)

        # Mouse handling - drags
        drag = Gtk.GestureDrag()
        drag.set_button(1)

        drag.connect(
            "drag-begin",
            self.drag_begin
        )

        drag.connect(
            "drag-update",
            self.drag_update
        )

        drag.connect(
            "drag-end",
            self.drag_end
        )

        drag.connect(
            "cancel",
            self.drag_cancel
        )

        self.overlay.add_controller(drag)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.mouse_motion)
        motion.connect("leave", self.mouse_leave)
        self.overlay.add_controller(motion)

        # Toolbar
        self.create_toolbar(root)

    # --------------------------------------------------
    # Toolbar
    # --------------------------------------------------

    def create_toolbar(self, root):

        self.top_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8
        )
        self.top_container.set_halign(
            Gtk.Align.CENTER
        )
        self.top_container.set_valign(
            Gtk.Align.START
        )
        self.top_container.set_margin_top(15)

        self.toolbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )
        self.toolbar.add_css_class(
            "toolbar"
        )

        # 1. Rectangle Mode
        self.rect_btn = Gtk.Button(label="⬚ Rectangle")
        self.rect_btn.set_tooltip_text("Drag to crop a screenshot area")
        self.rect_btn.connect("clicked", self.select_rectangle)

        # 2. Full Screen Mode
        self.fullscreen_btn = Gtk.Button(label="🖥 Full Screen")
        self.fullscreen_btn.set_tooltip_text("Click anywhere on screen to capture full screen")
        self.fullscreen_btn.connect("clicked", self.select_fullscreen)

        # 3. Window Mode
        self.window_btn = Gtk.Button(label="🗔 Window")
        self.window_btn.set_tooltip_text("Click a window to capture")
        self.window_btn.connect("clicked", self.select_window)

        # 4. Record Mode
        self.record_btn = Gtk.Button(label="● Record")
        self.record_btn.add_css_class("btn-record")
        self.record_btn.set_tooltip_text("Record full screen or drag to select area")
        self.record_btn.connect("clicked", self.select_record)

        # 5. Close Button
        self.close_btn = Gtk.Button(label="✕")
        self.close_btn.set_tooltip_text("Cancel overlay (Esc)")
        self.close_btn.connect("clicked", self.cancel)

        self.toolbar.append(self.rect_btn)
        self.toolbar.append(self.fullscreen_btn)
        self.toolbar.append(self.window_btn)
        self.toolbar.append(self.record_btn)
        self.toolbar.append(self.close_btn)

        self.top_container.append(self.toolbar)

        self.record_hint = Gtk.Label(label="")
        self.record_hint.add_css_class("record-hint")
        self.top_container.append(self.record_hint)

        root.add_overlay(self.top_container)

        self.update_buttons()

    # --------------------------------------------------
    # Button highlighting
    # --------------------------------------------------

    def update_buttons(self):
        for btn in [self.rect_btn, self.fullscreen_btn, self.window_btn, self.record_btn]:
            btn.remove_css_class("selected")
            btn.remove_css_class("selected-red")

        if self.mode == "Rectangle":
            self.rect_btn.add_css_class("selected")
            self.record_hint.set_text("Drag to select area for cropped screenshot  •  Esc to cancel")
        elif self.mode == "Full Screen":
            self.fullscreen_btn.add_css_class("selected")
            self.record_hint.set_text("Click anywhere on screen to capture full screen  •  Esc to cancel")
        elif self.mode == "Window":
            self.window_btn.add_css_class("selected")
            self.record_hint.set_text("Click any window to capture  •  Esc to cancel")
        elif self.mode == "Record":
            self.record_btn.add_css_class("selected-red")
            self.record_hint.set_text("Click anywhere for full screen  •  Or drag to select area to record")

    # --------------------------------------------------
    # Mode selection
    # --------------------------------------------------

    def select_rectangle(self, button):
        self.mode = "Rectangle"
        self.save_mode()
        self.update_buttons()
        self.clear_window_hover()

    def select_fullscreen(self, button):
        self.mode = "Full Screen"
        self.save_mode()
        self.update_buttons()
        self.clear_window_hover()

    def select_window(self, button):
        self.mode = "Window"
        self.save_mode()
        self.update_buttons()

    def select_record(self, button):
        self.mode = "Record"
        self.save_mode()
        self.update_buttons()
        self.clear_window_hover()

    # --------------------------------------------------
    # Mouse Events
    # --------------------------------------------------

    def mouse_pressed(
        self,
        gesture,
        n_press,
        x,
        y
    ):
        if self.is_inside_toolbar(x, y):
            return

        if self.mode == "Full Screen":
            self.take_fullscreen()
        elif self.mode == "Window":
            self.take_window_at(x, y)
        elif self.mode == "Record":
            self.top_container.set_visible(False)

    def mouse_motion(self, controller, x, y):
        if self.mode != "Window":
            return

        if self.is_inside_toolbar(x, y):
            self.clear_window_hover()
            return

        width = self.overlay.get_width()
        height = self.overlay.get_height()
        rect = self.smallest_snap_rect(x, y, width, height)

        if rect != self.window_hover_rect:
            self.window_hover_rect = rect
            self.overlay.queue_draw()

    def mouse_leave(self, controller):
        self.clear_window_hover()

    def clear_window_hover(self):
        if self.window_hover_rect is None:
            return

        self.window_hover_rect = None

        if self.overlay:
            self.overlay.queue_draw()

    def snap_rects(self, screen_w, screen_h):
        rects = []

        def add(x, y, w, h):
            x = int(round(x))
            y = int(round(y))
            w = int(round(w))
            h = int(round(h))
            if w > 0 and h > 0:
                rects.append((x, y, w, h))

        add(0, 0, screen_w / 2, screen_h)
        add(screen_w / 2, 0, screen_w - screen_w / 2, screen_h)
        add(0, 0, screen_w, screen_h / 2)
        add(0, screen_h / 2, screen_w, screen_h - screen_h / 2)
        add(0, 0, screen_w, screen_h)

        return rects

    def smallest_snap_rect(self, x, y, screen_w, screen_h):
        best = None
        best_area = None
        best_dist = None

        for rx, ry, rw, rh in self.snap_rects(screen_w, screen_h):
            if rx <= x < rx + rw and ry <= y < ry + rh:
                area = rw * rh
                cx = rx + rw / 2
                cy = ry + rh / 2
                dist = (x - cx) ** 2 + (y - cy) ** 2

                better = False
                if best is None:
                    better = True
                elif area < best_area:
                    better = True
                elif area == best_area and dist < best_dist:
                    better = True

                if better:
                    best = (rx, ry, rw, rh)
                    best_area = area
                    best_dist = dist

        return best

    def take_window_at(self, x, y):
        if self.capturing:
            return

        width = self.overlay.get_width()
        height = self.overlay.get_height()
        rect = self.window_hover_rect or self.smallest_snap_rect(
            x, y, width, height
        )

        if rect is None:
            return

        rx, ry, rw, rh = rect
        self.take_geometry(rx, ry, rw, rh)

    # --------------------------------------------------
    # Drag & Rectangle / Region Selection
    # --------------------------------------------------

    def drag_begin(
        self,
        gesture,
        start_x,
        start_y
    ):
        if self.is_inside_toolbar(
            start_x,
            start_y
        ):
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        if self.mode in ["Full Screen", "Window"]:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        if self.mode == "Record":
            self.top_container.set_visible(False)

        self.dragging = True

        self.drag_start_x = start_x
        self.drag_start_y = start_y
        self.drag_current_x = start_x
        self.drag_current_y = start_y

        self.overlay.queue_draw()

    def drag_update(
        self,
        gesture,
        offset_x,
        offset_y
    ):
        if not self.dragging:
            return

        self.drag_current_x = self.drag_start_x + offset_x
        self.drag_current_y = self.drag_start_y + offset_y

        self.overlay.queue_draw()

    def selection_rect(self):
        x = min(self.drag_start_x, self.drag_current_x)
        y = min(self.drag_start_y, self.drag_current_y)
        width = abs(self.drag_current_x - self.drag_start_x)
        height = abs(self.drag_current_y - self.drag_start_y)

        return x, y, width, height

    def drag_cancel(self, gesture, sequence):
        if not self.dragging:
            return
        # If pointer crossed screen edge/corner, finish drag with current bounds
        self.drag_end(gesture, self.drag_current_x - self.drag_start_x, self.drag_current_y - self.drag_start_y)

    def drag_end(
        self,
        gesture,
        offset_x,
        offset_y
    ):
        if not self.dragging:
            return

        self.drag_current_x = self.drag_start_x + offset_x
        self.drag_current_y = self.drag_start_y + offset_y

        x, y, width, height = self.selection_rect()

        self.dragging = False
        self.overlay.queue_draw()

        screen_w = self.overlay.get_width() or 1920
        screen_h = self.overlay.get_height() or 1080

        if self.mode == "Record":
            # Tap / single click without dragging (< 10px) -> Record Full Screen!
            if width < 10 or height < 10:
                self.start_recording(geometry=None)
                return

            # User dragged from corner to corner covering most of screen -> Record Full Screen!
            if width >= (screen_w - 150) and height >= (screen_h - 150):
                self.start_recording(geometry=None)
                return

            # Clamped region strictly inside screen dimensions so wf-recorder never errors
            ix = max(0, min(screen_w - 10, int(x)))
            iy = max(0, min(screen_h - 10, int(y)))
            iw = max(10, min(int(width), screen_w - ix - 1))
            ih = max(10, min(int(height), screen_h - iy - 1))
            self.start_recording(geometry=f"{ix},{iy} {iw}x{ih}")
            return

        elif self.mode == "Rectangle":
            if width < 10 or height < 10:
                return

            if width >= (screen_w - 150) and height >= (screen_h - 150):
                self.take_fullscreen()
                return

            ix = max(0, min(screen_w - 10, int(x)))
            iy = max(0, min(screen_h - 10, int(y)))
            iw = max(10, min(int(width), screen_w - ix - 1))
            ih = max(10, min(int(height), screen_h - iy - 1))
            self.take_rectangle(ix, iy, iw, ih)
            return

    # --------------------------------------------------
    # Drawing
    # --------------------------------------------------

    def draw_overlay(
        self,
        area,
        cr,
        width,
        height
    ):
        # White translucent tint over the whole screen.
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(
            1.0,
            1.0,
            1.0,
            0.20
        )
        cr.paint()

        highlight = None

        if self.dragging:
            highlight = self.selection_rect()
        elif self.mode == "Window" and self.window_hover_rect:
            highlight = self.window_hover_rect

        if highlight is None:
            return

        x, y, sel_w, sel_h = highlight

        if sel_w < 1 or sel_h < 1:
            return

        # Punch a clear hole so the selected crop is un-tinted.
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.rectangle(x, y, sel_w, sel_h)
        cr.fill()

        # Visible crop border around the selection.
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.mode in ["Record", "RecordArea"]:
            cr.set_source_rgba(1.0, 0.25, 0.25, 0.95)
        else:
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        cr.set_line_width(2)
        cr.rectangle(x + 0.5, y + 0.5, sel_w, sel_h)
        cr.stroke()

    # --------------------------------------------------
    # Toolbar detection
    # --------------------------------------------------

    def is_inside_toolbar(
        self,
        x,
        y
    ):
        target = self.top_container if self.top_container is not None else self.toolbar
        if target is None or self.window is None or not target.get_visible():
            return False

        allocation = target.get_allocation()
        toolbar_width = allocation.width
        toolbar_height = allocation.height
        window_width = self.window.get_width()

        left = (window_width - toolbar_width) / 2
        top = 15

        return (
            left <= x <= left + toolbar_width
            and
            top <= y <= top + toolbar_height + 10
        )

    # --------------------------------------------------
    # Screenshot Operations
    # --------------------------------------------------

    def on_window_destroy(self, window):
        self.window = None

    def close_overlay(self):
        if self.window:
            self.window.close()

    def take_fullscreen(self):
        if self.capturing:
            return

        self.capturing = True

        if self.window:
            self.window.hide()

        GLib.timeout_add(80, self._capture_fullscreen)

    def take_geometry(self, x, y, width, height):
        if self.capturing:
            return

        self.capturing = True
        self._pending_geometry = (
            f"{int(x)},{int(y)} "
            f"{int(width)}x{int(height)}"
        )

        if self.window:
            self.window.hide()

        GLib.timeout_add(80, self._capture_geometry)

    def _capture_geometry(self):
        geometry = self._pending_geometry
        notify = " && notify-send 'Screenshot' 'Copied to clipboard'" if shutil.which("notify-send") else ""

        subprocess.run(
            [
                "bash",
                "-c",
                f"grim -g '{geometry}' - | wl-copy --type image/png{notify}"
            ]
        )

        self.quit()
        return False

    def _capture_fullscreen(self):
        notify = " && notify-send 'Screenshot' 'Full screen copied to clipboard'" if shutil.which("notify-send") else ""
        subprocess.run(
            [
                "bash",
                "-c",
                f"grim - | wl-copy --type image/png{notify}"
            ]
        )

        self.quit()
        return False

    def take_rectangle(
        self,
        x,
        y,
        width,
        height
    ):
        self.close_overlay()

        geometry = (
            f"{int(x)},{int(y)} "
            f"{int(width)}x{int(height)}"
        )
        notify = " && notify-send 'Screenshot' 'Cropped screenshot copied to clipboard'" if shutil.which("notify-send") else ""

        command = [
            "bash",
            "-c",
            f"grim -g '{geometry}' - | wl-copy --type image/png{notify}"
        ]

        subprocess.Popen(command)

    # --------------------------------------------------
    # Record Operation
    # --------------------------------------------------

    def start_recording(self, geometry=None):
        if self.capturing:
            return

        self.capturing = True

        if self.window:
            self.window.hide()

        recorder_script = os.path.join(PROJECT_DIR, "scripts", "screen-recorder")
        cmd = [recorder_script]
        if geometry:
            cmd.extend(["-g", geometry])

        def _do_launch():
            subprocess.Popen(cmd)
            self.quit()
            return False

        GLib.timeout_add(80, _do_launch)

    # --------------------------------------------------
    # Cancel
    # --------------------------------------------------

    def cancel(self, button=None):
        self.close_overlay()

    # --------------------------------------------------
    # CSS
    # --------------------------------------------------

    def load_css(self):

        css = Gtk.CssProvider()

        css.load_from_data(
            b"""
            window,
            window.background {
                background: transparent;
                background-color: transparent;
                background-image: none;
                box-shadow: none;
            }

            overlay,
            drawingarea,
            .capture-root {
                background: transparent;
                background-color: transparent;
                background-image: none;
                box-shadow: none;
            }

            .toolbar {
                background: rgba(14, 16, 22, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.16);
                padding: 6px 12px;
                border-radius: 16px;
                box-shadow: 0 4px 18px rgba(0, 0, 0, 0.45);
            }

            button {
                color: #e2e4ea;
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 13px;
                transition: all 0.15s ease;
            }

            button:hover {
                background: rgba(255, 255, 255, 0.18);
                color: #ffffff;
            }

            .btn-record {
                color: #ff6b6b;
            }

            .btn-record:hover {
                color: #ffffff;
                background: rgba(225, 45, 45, 0.40);
                border-color: rgba(255, 90, 90, 0.70);
            }

            .selected-red {
                background: rgba(225, 45, 45, 0.90);
                border-color: rgba(255, 90, 90, 0.95);
                color: #ffffff;
                font-weight: 700;
            }

            button.selected {
                background: rgba(60, 130, 255, 0.88);
                border-color: rgba(100, 160, 255, 0.95);
                color: #ffffff;
                font-weight: 700;
            }

            .record-hint {
                color: #ffffff;
                background: rgba(14, 18, 26, 0.90);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 16px;
                padding: 5px 18px;
                font-size: 13px;
                font-weight: 600;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
            }
            """
        )

        display = Gdk.Display.get_default()

        Gtk.StyleContext.add_provider_for_display(
            display,
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


app = ScreenshotOverlay()
app.run()
