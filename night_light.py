#!/usr/bin/env python3
"""WarmSlider — display warmth and brightness controls."""

import json, math, os, re, shutil, subprocess, tkinter as tk, webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME, VERSION = "WarmSlider", "1.0.0"
DONATION_URL = "https://buymeacoffee.com/aadityabanwari"
CONFIG_HOME = Path(os.environ.get("SNAP_USER_DATA", Path.home() / ".config"))
CONFIG_FILE = CONFIG_HOME / "warmslider" / "settings.json"

def run(command):
    return subprocess.run(command, capture_output=True, text=True, check=True)

def connected_outputs():
    if not shutil.which("xrandr") or not os.environ.get("DISPLAY"):
        return []
    return re.findall(r"^([^ ]+) connected(?: primary)? ", run(["xrandr", "--query"]).stdout, re.MULTILINE)

def temperature_rgb(kelvin):
    temp = kelvin / 100.0
    red = 255.0 if temp <= 66 else 329.698727446 * ((temp - 60) ** -0.1332047592)
    green = (99.4708025861 * math.log(temp) - 161.1195681661 if temp <= 66
             else 288.1221695283 * ((temp - 60) ** -0.0755148492))
    blue = (255.0 if temp >= 66 else 0.0 if temp <= 19
            else 138.5177312231 * math.log(temp - 10) - 305.044792731)
    clamp = lambda value: max(0.05, min(1.0, value / 255.0))
    return clamp(red), clamp(green), clamp(blue)

class DisplayBackend:
    def __init__(self):
        self.outputs = connected_outputs()
        self.schema = "org.gnome.settings-daemon.plugins.color"

    @property
    def name(self):
        if self.outputs:
            return "X11 software controls"
        if shutil.which("gsettings"):
            return "GNOME native night light"
        return "No compatible display service"

    @property
    def brightness_available(self):
        return bool(self.outputs or shutil.which("brightnessctl"))

    def apply(self, enabled, kelvin, brightness):
        if self.outputs:
            gamma = ":".join(f"{v:.3f}" for v in temperature_rgb(kelvin if enabled else 6500))
            level = max(0.2, min(1.0, brightness / 100.0))
            for output in self.outputs:
                run(["xrandr", "--output", output, "--gamma", gamma, "--brightness", f"{level:.2f}"])
            return f"Applied to {', '.join(self.outputs)}"
        if shutil.which("gsettings"):
            run(["gsettings", "set", self.schema, "night-light-temperature", str(kelvin)])
            run(["gsettings", "set", self.schema, "night-light-enabled", str(enabled).lower()])
            if shutil.which("brightnessctl"):
                run(["brightnessctl", "set", f"{brightness}%"])
            return "Applied through GNOME"
        raise RuntimeError("This desktop does not expose a compatible colour service.")

class WarmSlider(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.resizable(False, False)
        self.pending = None
        self.backend = DisplayBackend()
        saved = self.load_settings()
        self.enabled = tk.BooleanVar(value=saved.get("enabled", False))
        self.kelvin = tk.IntVar(value=saved.get("kelvin", 4000))
        self.brightness = tk.IntVar(value=saved.get("brightness", 100))
        self.status = tk.StringVar(value=f"Backend: {self.backend.name}")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self.apply(show_error=False)

    @staticmethod
    def load_settings():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_settings(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps({
            "enabled": self.enabled.get(), "kelvin": self.kelvin.get(),
            "brightness": self.brightness.get()}, indent=2), encoding="utf-8")

    def build_ui(self):
        ttk.Style(self).configure("Title.TLabel", font=("Sans", 18, "bold"))
        frame = ttk.Frame(self, padding=22); frame.grid()
        ttk.Label(frame, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(frame, text="Night light", variable=self.enabled, command=self.apply).grid(
            row=0, column=1, sticky="e", padx=(80, 0))
        ttk.Label(frame, text="Color temperature").grid(row=1, column=0, sticky="w", pady=(22, 0))
        self.temp_value = ttk.Label(frame); self.temp_value.grid(row=1, column=1, sticky="e", pady=(22, 0))
        ttk.Label(frame, text="Warmer").grid(row=2, column=0, sticky="w")
        ttk.Label(frame, text="Neutral").grid(row=2, column=1, sticky="e")
        ttk.Scale(frame, from_=2500, to=6500, variable=self.kelvin, command=self.queue_apply,
                  length=380).grid(row=3, column=0, columnspan=2, pady=5)
        ttk.Label(frame, text="Brightness").grid(row=4, column=0, sticky="w", pady=(18, 0))
        self.brightness_value = ttk.Label(frame); self.brightness_value.grid(
            row=4, column=1, sticky="e", pady=(18, 0))
        self.brightness_scale = ttk.Scale(frame, from_=20, to=100, variable=self.brightness,
                                          command=self.queue_apply, length=380)
        self.brightness_scale.grid(row=5, column=0, columnspan=2, pady=5)
        if not self.backend.brightness_available:
            self.brightness_scale.state(["disabled"])
        ttk.Separator(frame).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(18, 10))
        ttk.Label(frame, textvariable=self.status, foreground="#666", wraplength=380).grid(
            row=7, column=0, columnspan=2)
        actions = ttk.Frame(frame); actions.grid(row=8, column=0, columnspan=2, pady=(16, 0), sticky="ew")
        ttk.Button(actions, text="Reset", command=self.reset).pack(side="left")
        ttk.Button(actions, text="About", command=self.about).pack(side="left", padx=8)
        if DONATION_URL:
            ttk.Button(actions, text="Donate ♥", command=lambda: webbrowser.open(DONATION_URL)).pack(side="right")
        self.update_labels()

    def update_labels(self):
        self.temp_value.config(text=f"{self.kelvin.get()} K")
        self.brightness_value.config(text=f"{self.brightness.get()}%")

    def queue_apply(self, _value=None):
        self.update_labels()
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(50, self.apply)

    def apply(self, show_error=True):
        self.pending = None; self.update_labels()
        try:
            self.status.set(self.backend.apply(self.enabled.get(), self.kelvin.get(), self.brightness.get()))
            self.save_settings()
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            self.status.set(f"Could not apply settings: {detail}")
            if show_error:
                messagebox.showerror(APP_NAME, self.status.get())

    def reset(self):
        self.kelvin.set(4000); self.brightness.set(100); self.enabled.set(False); self.apply()

    def about(self):
        messagebox.showinfo(f"About {APP_NAME}",
            f"{APP_NAME} {VERSION}\n\nA free display warmth and brightness controller.\nLicensed under the MIT License.")

    def close(self):
        self.save_settings(); self.destroy()

if __name__ == "__main__":
    WarmSlider().mainloop()
