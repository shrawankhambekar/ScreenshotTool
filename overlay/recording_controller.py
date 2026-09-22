#!/usr/bin/env python3
"""
recording_controller.py
Floating, movable Wayland screen recording toolbar for ScreenshotTool.
Ultra-minimalist HUD design:
- Vertical lines separating options (no funky complete boxes)
- Shrunk pill: < 50% opacity, pure text timer (no yellow block), small stop button
- Inactivity auto-shrink after 3 seconds
- Click timer to expand back to full panel
- Draggable anywhere, positioned in top bar area to prevent workspace obstruction
"""

import os
import sys
import time
import signal
import subprocess
import shutil
import argparse
import re
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_foreign("cairo")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell


class RecordingController(Gtk.Application):
    def __init__(self, geometry: Optional[str] = None, output_dir: Optional[str] = None, mic: bool = False, audio: bool = False):
        super().__init__(application_id="com.shrawan.CapturePiRecorder")
        self.geometry = geometry
        self.output_dir = output_dir or os.path.expanduser("~/Videos/Recordings")
        os.makedirs(self.output_dir, exist_ok=True)

        self.mic_enabled = mic
        self.audio_enabled = audio
        self.mic_muted = False
        self.audio_muted = False

        self.window = None
        self.proc: Optional[subprocess.Popen] = None
        self.output_file: Optional[str] = None

        # State tracking: "RECORDING", "PAUSED", "STOPPED"
        self.state = "RECORDING"
        self.start_time = 0.0
        self.last_resume_time = 0.0
        self.accumulated_duration = 0.0

        # Inactivity auto-shrink tracking (3 seconds threshold)
        self.last_interaction_time = time.time()
        self.inactivity_timeout = 3.0
        self.is_collapsed = False

        # UI elements - Full panel
        self.root_box = None
        self.main_box = None
        self.dot_label = None
        self.status_label = None
        self.timer_label = None
        self.pause_button = None
        self.stop_button = None
        self.collapse_button = None
        self.cancel_button = None

        # UI elements - Minimal Shrunk Pill (Only Timer & Small Stop Button)
        self.collapsed_box = None
        self.col_timer = None
        self.col_stop_button = None

        # Drag tracking
        self.drag_active = False
        self.drag_grab_x = 0.0
        self.drag_grab_y = 0.0

        # Blinking phase
        self.blink_phase = False

    def do_activate(self):
        if self.window is not None:
            return

        self.start_recording_process()

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_decorated(False)
        self.window.set_title("Screen Recorder")

        # Configure Wayland LayerShell
        Gtk4LayerShell.init_for_window(self.window)
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.LEFT, True)

        # Smart initial placement: in the top bar margin
        init_x, init_y = self.calculate_initial_position()
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.LEFT, init_x)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.TOP, init_y)

        # Build UI layout
        self.root_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.root_box.add_css_class("recorder-root")

        def make_sep():
            s = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
            s.add_css_class("bar-sep")
            return s

        # -------------------------------------------------------------
        # 1. Expanded Minimalist Full View (separated by vertical lines)
        # -------------------------------------------------------------
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.main_box.add_css_class("recorder-bar")

        # Drag Handle Grip
        drag_handle = Gtk.Label(label="⠿")
        drag_handle.add_css_class("drag-grip")
        drag_handle.set_tooltip_text("Click and drag to move anywhere")
        self.main_box.append(drag_handle)

        self.main_box.append(make_sep())

        # Recording Status & Pulsing Dot
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        status_box.add_css_class("status-box")
        self.dot_label = Gtk.Label(label="●")
        self.dot_label.add_css_class("rec-dot")
        self.status_label = Gtk.Label(label="REC")
        self.status_label.add_css_class("rec-status")
        status_box.append(self.dot_label)
        status_box.append(self.status_label)
        self.main_box.append(status_box)

        # Live Active Duration Timer
        self.timer_label = Gtk.Label(label="00:00")
        self.timer_label.add_css_class("timer-label")
        self.main_box.append(self.timer_label)
        self.main_box.append(make_sep())

        # Audio status / mute toggles
        self.mic_button = Gtk.Button(label="🎙 Mic")
        self.mic_button.add_css_class("flat-btn")
        self.mic_button.add_css_class("btn-audio-pill")
        self.mic_button.set_tooltip_text("External Microphone (Click to mute/unmute)")
        self.mic_button.connect("clicked", self.toggle_mic)
        self.main_box.append(self.mic_button)

        self.audio_button = Gtk.Button(label="🔊 Audio")
        self.audio_button.add_css_class("flat-btn")
        self.audio_button.add_css_class("btn-audio-pill")
        self.audio_button.set_tooltip_text("Internal System Audio Playback (Click to mute/unmute)")
        self.audio_button.connect("clicked", self.toggle_sys_audio)
        self.main_box.append(self.audio_button)

        self.update_audio_buttons()

        self.main_box.append(make_sep())

        # Action Buttons: Pause / Resume (flat, no box)
        self.pause_button = Gtk.Button(label="❚❚")
        self.pause_button.add_css_class("flat-btn")
        self.pause_button.add_css_class("btn-pause-flat")
        self.pause_button.set_tooltip_text("Pause recording")
        self.pause_button.connect("clicked", self.toggle_pause)
        self.main_box.append(self.pause_button)

        self.main_box.append(make_sep())

        # Action Button: Stop Recording (flat red icon, no box)
        self.stop_button = Gtk.Button(label="■")
        self.stop_button.add_css_class("flat-btn")
        self.stop_button.add_css_class("btn-stop-flat")
        self.stop_button.set_tooltip_text("Stop and save recording")
        self.stop_button.connect("clicked", self.stop_recording)
        self.main_box.append(self.stop_button)

        self.main_box.append(make_sep())

        # Action Button: Collapse / Shrink manually (flat icon, no box)
        self.collapse_button = Gtk.Button(label="▲")
        self.collapse_button.add_css_class("flat-btn")
        self.collapse_button.add_css_class("btn-collapse-flat")
        self.collapse_button.set_tooltip_text("Shrink to minimal pill")
        self.collapse_button.connect("clicked", lambda b: self.collapse_to_pill())
        self.main_box.append(self.collapse_button)

        self.main_box.append(make_sep())

        # Action Button: Discard / Cancel (flat icon, no box)
        self.cancel_button = Gtk.Button(label="✕")
        self.cancel_button.add_css_class("flat-btn")
        self.cancel_button.add_css_class("btn-cancel-flat")
        self.cancel_button.set_tooltip_text("Discard and cancel recording")
        self.cancel_button.connect("clicked", self.cancel_recording)
        self.main_box.append(self.cancel_button)

        self.root_box.append(self.main_box)

        # -------------------------------------------------------------
        # 2. Collapsed Minimal Pill View: ONLY Timer & Small Stop Button
        #    (No yellow block, < 50% opacity, pure minimalist pill)
        # -------------------------------------------------------------
        self.collapsed_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.collapsed_box.add_css_class("collapsed-pill")
        self.collapsed_box.set_visible(False)

        # Clickable Duration Time: clicking on time expands to full panel!
        self.col_timer = Gtk.Label(label="00:00")
        self.col_timer.add_css_class("col-timer-flat")
        self.col_timer.set_tooltip_text("Click time to expand full controls")
        self.collapsed_box.append(self.col_timer)

        # Subtle vertical separator line
        col_sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        col_sep.add_css_class("bar-sep-subtle")
        self.collapsed_box.append(col_sep)

        # Small Stop Button (flat red square icon, NOT pause button)
        self.col_stop_button = Gtk.Button(label="■")
        self.col_stop_button.add_css_class("flat-btn")
        self.col_stop_button.add_css_class("btn-col-stop")
        self.col_stop_button.set_tooltip_text("Stop and save recording")
        self.col_stop_button.connect("clicked", self.stop_recording)
        self.collapsed_box.append(self.col_stop_button)

        # Click gesture on timer: expands to full panel!
        click_expand = Gtk.GestureClick()
        click_expand.connect("pressed", lambda g, n, x, y: self.expand_to_full())
        self.col_timer.add_controller(click_expand)

        self.root_box.append(self.collapsed_box)

        # -------------------------------------------------------------
        # Event Controllers: Drag (excluding buttons) & Inactivity Reset
        # -------------------------------------------------------------
        click_ctrl = Gtk.GestureClick()
        click_ctrl.connect("pressed", self.on_box_pressed)
        click_ctrl.connect("released", self.on_box_released)
        self.root_box.add_controller(click_ctrl)

        motion_ctrl = Gtk.EventControllerMotion()
        motion_ctrl.connect("motion", self.on_box_motion)
        motion_ctrl.connect("enter", self.on_user_enter)
        self.root_box.add_controller(motion_ctrl)

        self.window.set_child(self.root_box)
        self.load_css()
        self.window.present()

        # Start timer loop (every 250ms for smooth updates and auto-shrink)
        GLib.timeout_add(250, self.on_timer_tick)

        # Handle Unix termination signals cleanly
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_sigint)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_sigint)

    def _on_sigint(self):
        self.stop_recording()
        return GLib.SOURCE_REMOVE

    def on_box_pressed(self, gesture, n_press, x, y):
        self.reset_interaction_timer()
        # Hit test: if user clicked on any button, ignore drag so buttons click cleanly!
        picked = self.root_box.pick(x, y, Gtk.PickFlags.DEFAULT)
        curr = picked
        while curr and curr != self.root_box:
            if isinstance(curr, Gtk.Button):
                return
            curr = curr.get_parent()

        self.drag_active = True
        self.drag_grab_x = x
        self.drag_grab_y = y

    def on_box_released(self, gesture, n_press, x, y):
        self.drag_active = False

    def on_box_motion(self, controller, x, y):
        self.reset_interaction_timer()
        if not self.drag_active:
            return

        dx = x - self.drag_grab_x
        dy = y - self.drag_grab_y
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return

        cur_x = Gtk4LayerShell.get_margin(self.window, Gtk4LayerShell.Edge.LEFT)
        cur_y = Gtk4LayerShell.get_margin(self.window, Gtk4LayerShell.Edge.TOP)
        new_x = max(0, int(cur_x + dx))
        new_y = max(0, int(cur_y + dy))
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.LEFT, new_x)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.TOP, new_y)

    def on_user_enter(self, controller, x, y):
        self.reset_interaction_timer()
        if self.is_collapsed and self.collapsed_box:
            self.collapsed_box.set_opacity(0.90)

    def reset_interaction_timer(self):
        self.last_interaction_time = time.time()

    def collapse_to_pill(self):
        if not self.is_collapsed:
            self.is_collapsed = True
            self.main_box.set_visible(False)
            self.collapsed_box.set_visible(True)
            self.reset_interaction_timer()

    def expand_to_full(self):
        if self.is_collapsed:
            self.is_collapsed = False
            self.collapsed_box.set_visible(False)
            self.main_box.set_visible(True)
            self.reset_interaction_timer()

    def calculate_initial_position(self) -> tuple[int, int]:
        if self.geometry:
            try:
                parts = self.geometry.replace("x", " ").replace(",", " ").split()
                if len(parts) >= 4:
                    gx, gy, gw, gh = [int(p) for p in parts[:4]]
                    # Position toolbar outside the recorded region, clamped to visible display
                    if gy >= 50:
                        pos_y = max(2, gy - 45)
                    else:
                        pos_y = min(1042, gy + gh + 10)
                    pos_x = max(10, min(1640, gx + (gw - 260) // 2))
                    return pos_x, pos_y
            except Exception:
                pass
        # Default full-screen placement: top panel bar (y=2) where it does not cover windows
        return 320, 2

    def get_sink_monitor(self) -> Optional[str]:
        try:
            out = subprocess.check_output(["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"], text=True)
            m = re.search(r'node\.name\s*=\s*\"([^\"]+)\"', out)
            if m:
                return m.group(1) + ".monitor"
        except Exception:
            pass
        return None

    def toggle_mic(self, button=None):
        self.reset_interaction_timer()
        self.mic_muted = not self.mic_muted
        try:
            val = 1 if self.mic_muted else 0
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", str(val)], check=False)
        except Exception:
            pass
        self.update_audio_buttons()

    def toggle_sys_audio(self, button=None):
        self.reset_interaction_timer()
        self.audio_muted = not self.audio_muted
        try:
            val = 1 if self.audio_muted else 0
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", str(val)], check=False)
        except Exception:
            pass
        self.update_audio_buttons()

    def update_audio_buttons(self):
        if not getattr(self, "mic_button", None) or not getattr(self, "audio_button", None):
            return

        if not self.mic_enabled:
            self.mic_button.set_label("🎙 Off")
            self.mic_button.remove_css_class("btn-audio-active")
            self.mic_button.remove_css_class("btn-audio-muted")
            self.mic_button.add_css_class("btn-audio-off")
        elif self.mic_muted:
            self.mic_button.set_label("🎙✕")
            self.mic_button.remove_css_class("btn-audio-active")
            self.mic_button.remove_css_class("btn-audio-off")
            self.mic_button.add_css_class("btn-audio-muted")
        else:
            self.mic_button.set_label("🎙 Mic")
            self.mic_button.remove_css_class("btn-audio-off")
            self.mic_button.remove_css_class("btn-audio-muted")
            self.mic_button.add_css_class("btn-audio-active")

        if not self.audio_enabled:
            self.audio_button.set_label("🔊 Off")
            self.audio_button.remove_css_class("btn-audio-active")
            self.audio_button.remove_css_class("btn-audio-muted")
            self.audio_button.add_css_class("btn-audio-off")
        elif self.audio_muted:
            self.audio_button.set_label("🔊✕")
            self.audio_button.remove_css_class("btn-audio-active")
            self.audio_button.remove_css_class("btn-audio-off")
            self.audio_button.add_css_class("btn-audio-muted")
        else:
            self.audio_button.set_label("🔊 Audio")
            self.audio_button.remove_css_class("btn-audio-off")
            self.audio_button.remove_css_class("btn-audio-muted")
            self.audio_button.add_css_class("btn-audio-active")

    def start_recording_process(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(self.output_dir, f"rec_{ts}.mp4")

        cmd = ["wf-recorder", "-f", self.output_file]
        if self.geometry:
            cmd.extend(["-g", self.geometry])

        if self.audio_enabled:
            sink_mon = self.get_sink_monitor()
            if sink_mon:
                cmd.extend(["-a", sink_mon])
            else:
                cmd.append("-a")
        elif self.mic_enabled:
            cmd.append("-a")

        print(f"[CAPTUREPI] Spawning: {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd)
        now = time.time()
        self.start_time = now
        self.last_resume_time = now
        self.accumulated_duration = 0.0
        self.last_interaction_time = now
        self.state = "RECORDING"

    def toggle_pause(self, button=None):
        self.reset_interaction_timer()

        if self.state == "RECORDING":
            if self.proc and self.proc.pid:
                try:
                    os.kill(self.proc.pid, signal.SIGSTOP)
                except Exception as e:
                    print(f"[RECORDER] Failed to send SIGSTOP: {e}")

            self.accumulated_duration += time.time() - self.last_resume_time
            self.state = "PAUSED"

            self.pause_button.set_label("▶")
            self.pause_button.set_tooltip_text("Resume recording")
            self.status_label.set_text("PAUSED")
            self.dot_label.remove_css_class("rec-dot")
            self.dot_label.add_css_class("pause-dot")
            self.status_label.add_css_class("paused-status")
            print("[RECORDER] Recording PAUSED.")

        elif self.state == "PAUSED":
            if self.proc and self.proc.pid:
                try:
                    os.kill(self.proc.pid, signal.SIGCONT)
                except Exception as e:
                    print(f"[RECORDER] Failed to send SIGCONT: {e}")

            self.last_resume_time = time.time()
            self.state = "RECORDING"

            self.pause_button.set_label("❚❚")
            self.pause_button.set_tooltip_text("Pause recording")
            self.status_label.set_text("REC")
            self.dot_label.remove_css_class("pause-dot")
            self.dot_label.add_css_class("rec-dot")
            self.status_label.remove_css_class("paused-status")
            print("[RECORDER] Recording RESUMED.")

    def on_timer_tick(self) -> bool:
        if self.state == "STOPPED":
            return False

        now = time.time()

        # Inactivity auto-shrink: if expanded and untouched for >= 3 seconds, shrink to pill!
        if not self.is_collapsed and (now - self.last_interaction_time) >= self.inactivity_timeout:
            self.collapse_to_pill()

        # Ghost fade: if collapsed and untouched for > 4 seconds, keep it very translucent (< 40%)
        if self.is_collapsed and self.collapsed_box:
            if (now - self.last_interaction_time) > 4.0:
                self.collapsed_box.set_opacity(0.35)
            else:
                self.collapsed_box.set_opacity(0.85)

        # Calculate duration
        if self.state == "RECORDING":
            dur = self.accumulated_duration + (now - self.last_resume_time)
            self.blink_phase = not self.blink_phase
            if self.blink_phase:
                self.dot_label.set_opacity(1.0)
            else:
                self.dot_label.set_opacity(0.2)
        else:
            dur = self.accumulated_duration
            self.dot_label.set_opacity(1.0)

        seconds = int(round(dur))
        mins, secs = divmod(seconds, 60)
        hrs, mins = divmod(mins, 60)
        time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

        if self.timer_label:
            self.timer_label.set_text(time_str)
        if self.col_timer:
            self.col_timer.set_text(time_str)

        return True

    def stop_recording(self, button=None):
        if self.state == "STOPPED":
            return
        self.state = "STOPPED"

        if self.proc and self.proc.pid:
            try:
                os.kill(self.proc.pid, signal.SIGCONT)
            except Exception:
                pass
            try:
                os.kill(self.proc.pid, signal.SIGINT)
                self.proc.wait(timeout=3.0)
            except Exception as e:
                print(f"[RECORDER] Waiting for wf-recorder exit: {e}")

        if self.output_file and os.path.exists(self.output_file):
            size_mb = os.path.getsize(self.output_file) / (1024 * 1024)
            dur_secs = int(round(self.accumulated_duration + (time.time() - self.last_resume_time)))
            mins, secs = divmod(dur_secs, 60)
            msg = f"Saved: {os.path.basename(self.output_file)} ({mins:02d}:{secs:02d}, {size_mb:.1f} MB)"
            print(f"[RECORDER] {msg}")

            if shutil.which("wl-copy"):
                try:
                    subprocess.run(
                        [
                            "bash",
                            "-c",
                            f"printf 'file://{self.output_file}\\r\\n' | wl-copy -t text/uri-list"
                        ],
                        timeout=2.0
                    )
                except Exception as e:
                    print(f"[RECORDER] Clipboard error: {e}")

            if shutil.which("notify-send"):
                try:
                    subprocess.Popen([
                        "notify-send",
                        "-i", "video-x-generic",
                        "Screen Recording Saved",
                        f"{msg}\nCopied to clipboard (ready to paste!)"
                    ])
                except Exception:
                    pass

        if self.window:
            self.window.close()
        self.quit()

    def cancel_recording(self, button=None):
        self.state = "STOPPED"
        if self.proc and self.proc.pid:
            try:
                os.kill(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=1.0)
            except Exception:
                pass
        if self.output_file and os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
            except Exception:
                pass

        if shutil.which("notify-send"):
            try:
                subprocess.Popen([
                    "notify-send",
                    "Screen Recording Cancelled",
                    "The recording was discarded."
                ])
            except Exception:
                pass

        if self.window:
            self.window.close()
        self.quit()

    def load_css(self):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        window, window.background {
            background: transparent;
            background-color: transparent;
        }

        .recorder-root {
            background: transparent;
            padding: 2px;
        }

        /* Minimalist Expanded Bar - Translucent Glass */
        .recorder-bar {
            background: rgba(12, 14, 20, 0.40);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 3px 10px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
            transition: background 0.2s ease, border-color 0.2s ease;
        }

        .recorder-bar:hover {
            background: rgba(12, 14, 20, 0.78);
            border-color: rgba(255, 255, 255, 0.25);
        }

        /* Minimal Shrunk Pill: LESS THAN 50% OPAQUE (< 38%), NO YELLOW BLOCK */
        .collapsed-pill {
            background: rgba(8, 10, 14, 0.22);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 14px;
            padding: 2px 7px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            opacity: 0.38;
            transition: opacity 0.2s ease, background 0.2s ease, border-color 0.2s ease;
        }

        .collapsed-pill:hover {
            opacity: 0.90;
            background: rgba(12, 14, 20, 0.78);
            border-color: rgba(255, 255, 255, 0.25);
        }

        /* Vertical Lines between options */
        .bar-sep {
            background: rgba(255, 255, 255, 0.16);
            min-width: 1px;
            margin: 4px 3px;
        }

        .bar-sep-subtle {
            background: rgba(255, 255, 255, 0.14);
            min-width: 1px;
            margin: 3px 2px;
        }

        /* Flat Minimalist Buttons - NO Chunky Boxes */
        .flat-btn {
            color: #d8dbe2;
            background: transparent;
            background-color: transparent;
            border: none;
            box-shadow: none;
            padding: 2px 6px;
            font-size: 13px;
            font-weight: 700;
            border-radius: 6px;
            min-height: 22px;
            min-width: 22px;
            transition: color 0.15s ease, background-color 0.15s ease;
        }

        .flat-btn:hover {
            background-color: rgba(255, 255, 255, 0.12);
            color: #ffffff;
        }

        .drag-grip {
            color: rgba(180, 185, 200, 0.65);
            font-size: 14px;
            padding: 0 3px;
        }

        .rec-dot {
            color: #ff3b30;
            font-size: 11px;
            font-weight: bold;
        }

        .pause-dot {
            color: #ff9500;
            font-size: 11px;
            font-weight: bold;
        }

        .rec-status {
            color: #ff453a;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }

        .paused-status {
            color: #ff9f0a;
            font-size: 11px;
            font-weight: 800;
        }

        .timer-label {
            color: #ffffff;
            font-family: monospace;
            font-size: 13px;
            font-weight: 700;
            padding: 0 4px;
            background: transparent;
        }

        /* In Shrunk Pill: Pure text with NO background block */
        .col-timer-flat {
            color: #ffffff;
            font-family: monospace;
            font-size: 12px;
            font-weight: 700;
            padding: 1px 4px;
            background: transparent;
        }

        .col-timer-flat:hover {
            color: #ffffff;
        }

        /* Small Stop Button in Shrunk Pill */
        .btn-col-stop {
            color: #ff3b30;
            font-size: 10px;
            padding: 1px 4px;
            min-width: 16px;
            min-height: 16px;
        }

        .btn-col-stop:hover {
            color: #ff5b52;
            background-color: rgba(255, 59, 48, 0.20);
        }

        .btn-pause-flat {
            color: #ff9f0a;
        }

        .btn-pause-flat:hover {
            color: #ffb340;
            background-color: rgba(255, 159, 10, 0.15);
        }

        .btn-stop-flat {
            color: #ff3b30;
        }

        .btn-stop-flat:hover {
            color: #ff5b52;
            background-color: rgba(255, 59, 48, 0.18);
        }

        .btn-collapse-flat {
            color: #98a0b0;
            font-size: 9px;
        }

        .btn-collapse-flat:hover {
            color: #ffffff;
        }

        .btn-cancel-flat {
            color: #788090;
            font-size: 12px;
        }

        .btn-cancel-flat:hover {
            color: #ff453a;
            background-color: rgba(255, 60, 60, 0.15);
        }

        /* Audio Pill Styles */
        .btn-audio-pill {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 6px;
        }

        .btn-audio-active {
            color: #38ef7d;
            background-color: rgba(56, 239, 125, 0.18);
        }

        .btn-audio-active:hover {
            color: #ffffff;
            background-color: rgba(56, 239, 125, 0.30);
        }

        .btn-audio-muted {
            color: #ff9500;
            background-color: rgba(255, 149, 0, 0.18);
        }

        .btn-audio-muted:hover {
            color: #ffffff;
            background-color: rgba(255, 149, 0, 0.30);
        }

        .btn-audio-off {
            color: rgba(255, 255, 255, 0.35);
        }

        .btn-audio-off:hover {
            color: rgba(255, 255, 255, 0.65);
        }
        """)

        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )


def main():
    parser = argparse.ArgumentParser(description="CapturePi Floating Wayland Screen Recording Controller")
    parser.add_argument("-g", "--geometry", type=str, default=None, help="Target screen geometry: 'X,Y WxH'")
    parser.add_argument("-o", "--output-dir", type=str, default=None, help="Output directory for recordings")
    parser.add_argument("--mic", action="store_true", help="Record external microphone input")
    parser.add_argument("--audio", action="store_true", help="Record internal system audio playback")
    args = parser.parse_args()

    app = RecordingController(geometry=args.geometry, output_dir=args.output_dir, mic=args.mic, audio=args.audio)
    app.run([])


if __name__ == "__main__":
    main()
