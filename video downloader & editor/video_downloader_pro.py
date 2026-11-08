""""
Video Downloader Pro — Studio Edition v4.1

Install:
    py -m pip install -U yt-dlp customtkinter
    winget install Gyan.FFmpeg

Run:
    py Video_Downloader_Pro_Studio_v4_1.py

Use only for videos you own or have permission to download.
This app does not bypass DRM, paywalls, private-account restrictions,
or other access controls.
"""

import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp
from yt_dlp.version import __version__ as YTDLP_VERSION


APP_NAME = "VIDEO DOWNLOADER PRO"
APP_VERSION = "4.1 STUDIO"

BASE_DIR = os.path.dirname(
    sys.executable
    if getattr(sys, "frozen", False)
    else os.path.abspath(__file__)
)

CONFIG_FILE = os.path.join(BASE_DIR, "settings.json")

VIDEO_EXT = (
    ".mp4", ".mkv", ".webm", ".mov",
    ".m4v", ".avi", ".flv"
)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

QUALITIES = {
    "Best available": None,
    "8K · 4320p": 4320,
    "4K · 2160p": 2160,
    "2K · 1440p": 1440,
    "Full HD · 1080p": 1080,
    "HD · 720p": 720,
    "SD · 480p": 480,
}

CROPS = {
    "Original · no crop": None,
    "Vertical · 9:16": (9, 16),
    "Square · 1:1": (1, 1),
    "Portrait · 4:5": (4, 5),
    "Landscape · 16:9": (16, 9),
}

P = {
    "bg": "#090b10",
    "panel": "#111620",
    "panel2": "#171e2b",
    "field": "#0c111a",
    "edge": "#283348",
    "text": "#edf3ff",
    "muted": "#92a0b8",
    "dim": "#5e6b82",
    "blue": "#5b8cff",
    "blue2": "#3974f6",
    "cyan": "#48d9e8",
    "green": "#35d49a",
    "red": "#ff667d",
    "amber": "#ffc46b",
    "purple": "#a88bff",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ================================================================
# HELPERS
# ================================================================

def font(size=12, weight="normal"):
    return ctk.CTkFont(
        family="Segoe UI",
        size=size,
        weight=weight
    )


def mono(size=11):
    return ctk.CTkFont(
        family="Consolas",
        size=size
    )


def find_tool(name):
    exe = name + (".exe" if os.name == "nt" else "")

    found = shutil.which(name)
    if found:
        return found

    candidates = [
        os.path.join(BASE_DIR, exe),
        os.path.join(BASE_DIR, "ffmpeg", exe),
        os.path.join(BASE_DIR, "ffmpeg", "bin", exe),
        os.path.join("C:\\", "ffmpeg", "bin", exe),
    ]

    local = os.environ.get("LOCALAPPDATA")

    if local:
        candidates.append(
            os.path.join(
                local, "Microsoft", "WinGet", "Links", exe
            )
        )

        candidates.extend(
            glob.glob(
                os.path.join(
                    local,
                    "Microsoft",
                    "WinGet",
                    "Packages",
                    "*FFmpeg*",
                    "**",
                    exe,
                ),
                recursive=True,
            )
        )

    return next(
        (p for p in candidates if os.path.isfile(p)),
        None
    )


def safe_name(value):
    value = re.sub(
        r'[\\/:*?"<>|%#\x00-\x1f]+',
        " ",
        value or ""
    )

    return (
        re.sub(r"\s+", " ", value)
        .strip(" .")[:120]
        or "video"
    )


def extract_url(value):
    match = re.search(
        r"https?://[^\s<>\"']+",
        value or ""
    )

    return (
        match.group(0).rstrip(".,);]")
        if match else None
    )


def fmt_time(sec):
    sec = max(0, int(round(float(sec or 0))))

    hours, remainder = divmod(sec, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def friendly_error(error):
    msg = re.sub(
        r"\x1b\[[0-9;]*[A-Za-z]",
        "",
        str(error)
    ).strip()

    low = msg.lower()

    if "unsupported url" in low:
        return (
            "Unsupported link. Try a direct video/post URL."
        )

    if "429" in low or "too many requests" in low:
        return (
            "The site is rate-limiting requests. "
            "Wait a while and retry."
        )

    if "403" in low:
        return (
            "Access denied by the site. "
            "Update yt-dlp and retry."
        )

    if any(
        term in low
        for term in (
            "sign in",
            "login",
            "cookies",
            "age-restricted",
            "age restricted",
        )
    ):
        return (
            "This video requires sign-in or age verification. "
            "This app does not bypass access restrictions."
        )

    if any(
        term in low
        for term in (
            "timed out",
            "connection",
            "network",
            "getaddrinfo",
        )
    ):
        return (
            "Network failed. Check internet and retry."
        )

    if "private" in low:
        return (
            "This video is private. "
            "Only accessible videos can be downloaded."
        )

    return msg[-600:] or "Unknown error."


class Cancelled(Exception):
    pass


# ================================================================
# MAIN APPLICATION
# ================================================================

class VideoDownloader(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME}  |  {APP_VERSION}")
        self.configure(fg_color=P["bg"])

        self.fit_window()

        self.cancel_event = threading.Event()
        self.running = False
        self.process = None

        self.completed = 0
        self.duration = 0.0
        self.src_dims = None
        self.meta = {}
        self.playhead = 0.0

        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")

        cfg = self.load_config()

        self.out_dir = tk.StringVar(
            value=cfg.get(
                "out_dir",
                str(Path.home() / "Videos")
            )
        )

        self.quality = tk.StringVar(
            value=cfg.get("quality", "Best available")
        )

        self.crop = tk.StringVar(
            value=cfg.get(
                "crop",
                "Vertical · 9:16"
            )
        )

        if self.quality.get() not in QUALITIES:
            self.quality.set("Best available")

        if self.crop.get() not in CROPS:
            self.crop.set("Original · no crop")

        self.split_default = tk.BooleanVar(
            value=cfg.get("split", True)
        )

        self.part_seconds = tk.StringVar(
            value=str(cfg.get("part_seconds", 34))
        )

        self.part_seconds.trace_add(
            "write",
            lambda *_: self.redraw()
        )

        self.build_ui()
        self.update_tool_status()

        self.protocol(
            "WM_DELETE_WINDOW",
            self.close_app
        )

        self.bind(
            "<Return>",
            lambda _event: self.start_download()
        )

        self.after(300, self.try_maximize)
        self.after(450, self.redraw)

    # ------------------------------------------------------------
    # WINDOW
    # ------------------------------------------------------------

    def fit_window(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        width = min(1480, sw - 24)
        height = min(900, sh - 70)

        self.geometry(
            f"{width}x{height}+"
            f"{max(0, (sw - width) // 2)}+"
            f"{max(0, (sh - height) // 2 - 15)}"
        )

        self.minsize(
            min(1050, width),
            min(680, height)
        )

    def try_maximize(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    # ------------------------------------------------------------
    # SETTINGS
    # ------------------------------------------------------------

    def load_config(self):
        try:
            with open(
                CONFIG_FILE,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            return data if isinstance(data, dict) else {}

        except (OSError, ValueError):
            return {}

    def save_config(self):
        data = {
            "out_dir": self.out_dir.get(),
            "quality": self.quality.get(),
            "crop": self.crop.get(),
            "split": self.split_default.get(),
            "part_seconds": self.part_seconds.get(),
        }

        try:
            with open(
                CONFIG_FILE,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(data, file, indent=2)

        except OSError:
            pass

    # ------------------------------------------------------------
    # UI BUILDING BLOCKS
    # ------------------------------------------------------------

    def section(self, parent, title, tag=None):
        outer = ctk.CTkFrame(
            parent,
            fg_color=P["panel"],
            corner_radius=13,
            border_width=1,
            border_color=P["edge"],
        )

        head = ctk.CTkFrame(
            outer,
            fg_color=P["panel2"],
            corner_radius=10,
            height=37,
        )

        head.pack(
            fill="x",
            padx=4,
            pady=(4, 0)
        )

        head.pack_propagate(False)

        ctk.CTkLabel(
            head,
            text="◆",
            font=font(10, "bold"),
            text_color=P["cyan"],
        ).pack(side="left", padx=(12, 8))

        ctk.CTkLabel(
            head,
            text=title.upper(),
            font=font(11, "bold"),
            text_color=P["text"],
        ).pack(side="left")

        if tag:
            ctk.CTkLabel(
                head,
                text=tag,
                font=font(9, "bold"),
                text_color=P["muted"],
            ).pack(side="right", padx=12)

        body = ctk.CTkFrame(
            outer,
            fg_color="transparent"
        )

        body.pack(
            fill="both",
            expand=True,
            padx=3,
            pady=3
        )

        return outer, body

    def label(self, parent, text):
        return ctk.CTkLabel(
            parent,
            text=text,
            font=font(11, "bold"),
            text_color=P["muted"],
            anchor="w",
        )

    def ghost(self, parent, text, command, width=80):
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=35,
            corner_radius=9,
            font=font(11, "bold"),
            fg_color=P["field"],
            hover_color=P["edge"],
            text_color=P["text"],
            border_width=1,
            border_color=P["edge"],
            command=command,
        )

    # ------------------------------------------------------------
    # MAIN UI
    # ------------------------------------------------------------

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(
            self,
            fg_color="#0d121b",
            corner_radius=0,
            height=64,
        )

        top.grid(
            row=0,
            column=0,
            sticky="ew"
        )

        top.grid_propagate(False)
        top.grid_columnconfigure(2, weight=1)

        logo = ctk.CTkFrame(
            top,
            fg_color=P["blue2"],
            corner_radius=11,
            width=40,
            height=40,
        )

        logo.grid(
            row=0,
            column=0,
            padx=(18, 12),
            pady=11
        )

        logo.grid_propagate(False)

        ctk.CTkLabel(
            logo,
            text="▶",
            font=font(18, "bold"),
            text_color="white",
        ).place(
            relx=0.5,
            rely=0.5,
            anchor="center"
        )

        ctk.CTkLabel(
            top,
            text="VIDEO DOWNLOADER",
            font=font(16, "bold"),
            text_color=P["text"],
        ).grid(
            row=0,
            column=1,
            sticky="w"
        )

        ctk.CTkLabel(
            top,
            text="PRO  /  STUDIO EDITION",
            font=font(10, "bold"),
            text_color=P["cyan"],
        ).grid(
            row=0,
            column=2,
            sticky="w",
            padx=14
        )

        self.tool_badge = ctk.CTkLabel(
            top,
            text="Checking media engine…",
            font=font(10, "bold"),
            corner_radius=9,
            padx=12,
            height=29,
            fg_color=P["panel2"],
            text_color=P["muted"],
        )

        self.tool_badge.grid(
            row=0,
            column=3,
            padx=18
        )

        ctk.CTkFrame(
            self,
            fg_color=P["blue2"],
            height=2,
            corner_radius=0,
        ).grid(
            row=0,
            column=0,
            sticky="sew"
        )

        main = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )

        main.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=12
        )

        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(
            main,
            width=285,
            fg_color="transparent",
            corner_radius=0,
        )

        left.grid(
            row=0,
            column=0,
            sticky="ns",
            padx=(0, 10)
        )

        center = ctk.CTkFrame(
            main,
            fg_color="transparent"
        )

        center.grid(
            row=0,
            column=1,
            sticky="nsew"
        )

        right = ctk.CTkScrollableFrame(
            main,
            width=285,
            fg_color="transparent",
            corner_radius=0,
        )

        right.grid(
            row=0,
            column=2,
            sticky="ns",
            padx=(10, 0)
        )

        self.build_left(left)
        self.build_center(center)
        self.build_right(right)

        log_outer, log_body = self.section(
            main,
            "Console / Activity",
            f"YT-DLP {YTDLP_VERSION}",
        )

        log_outer.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0)
        )

        self.log_box = ctk.CTkTextbox(
            log_body,
            height=94,
            font=mono(10),
            fg_color="#080b10",
            text_color="#c8d5eb",
            corner_radius=9,
            wrap="word",
        )

        self.log_box.pack(
            fill="both",
            expand=True,
            padx=9,
            pady=9
        )

        for tag, color in (
            ("ok", P["green"]),
            ("err", P["red"]),
            ("warn", P["amber"]),
            ("info", P["muted"]),
        ):
            try:
                self.log_box.tag_config(
                    tag,
                    foreground=color
                )
            except Exception:
                pass

        self.log_box.configure(state="disabled")

        bar = ctk.CTkFrame(
            self,
            fg_color="#101a2b",
            corner_radius=0,
            height=27,
        )

        bar.grid(
            row=2,
            column=0,
            sticky="ew"
        )

        bar.grid_propagate(False)

        self.status_left = ctk.CTkLabel(
            bar,
            text="●  READY",
            font=font(10, "bold"),
            text_color=P["cyan"],
        )

        self.status_left.pack(
            side="left",
            padx=14
        )

        self.status_right = ctk.CTkLabel(
            bar,
            text="Jobs completed: 0   •   MP4 pipeline",
            font=font(10),
            text_color=P["muted"],
        )

        self.status_right.pack(
            side="right",
            padx=14
        )

    # ------------------------------------------------------------
    # LEFT PANEL
    # ------------------------------------------------------------

    def build_left(self, parent):
        src, body = self.section(
            parent,
            "Source ingest",
            "01 / INPUT"
        )

        src.pack(
            fill="x",
            pady=(0, 10)
        )

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=12
        )

        self.label(
            pad,
            "VIDEO / POST URL"
        ).pack(fill="x")

        self.url_entry = ctk.CTkEntry(
            pad,
            height=41,
            font=font(12),
            fg_color=P["field"],
            border_color=P["edge"],
            corner_radius=9,
            placeholder_text="Paste a public video URL…",
        )

        self.url_entry.pack(
            fill="x",
            pady=(7, 9)
        )

        row = ctk.CTkFrame(
            pad,
            fg_color="transparent"
        )

        row.pack(fill="x")
        row.grid_columnconfigure((0, 1), weight=1)

        self.ghost(
            row,
            "▣  Paste",
            self.paste
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4)
        )

        self.ghost(
            row,
            "×  Clear",
            self.clear
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0)
        )

        ctk.CTkLabel(
            pad,
            text=(
                "YouTube  ·  TikTok  ·  Instagram\n"
                "Facebook  ·  X  ·  other yt-dlp sites"
            ),
            font=font(10),
            text_color=P["dim"],
            justify="left",
        ).pack(
            anchor="w",
            pady=(10, 0)
        )

        out, body = self.section(
            parent,
            "Export destination",
            "02 / OUTPUT"
        )

        out.pack(
            fill="x",
            pady=(0, 10)
        )

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=12
        )

        self.label(
            pad,
            "SAVE LOCATION"
        ).pack(fill="x")

        ctk.CTkEntry(
            pad,
            textvariable=self.out_dir,
            height=37,
            font=font(10),
            fg_color=P["field"],
            border_color=P["edge"],
            corner_radius=8,
        ).pack(
            fill="x",
            pady=(7, 8)
        )

        row = ctk.CTkFrame(
            pad,
            fg_color="transparent"
        )

        row.pack(fill="x")
        row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            row,
            text="▣  Browse",
            height=34,
            corner_radius=8,
            font=font(11, "bold"),
            fg_color=P["blue2"],
            hover_color=P["blue"],
            command=self.pick_folder,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4)
        )

        self.ghost(
            row,
            "Open folder",
            self.open_folder
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0)
        )

        info, body = self.section(
            parent,
            "Asset metadata",
            "AUTO DETECT"
        )

        info.pack(fill="x")

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=10
        )

        pad.grid_columnconfigure(1, weight=1)

        self.info_labels = {}

        for i, key in enumerate(
            (
                "Title",
                "Duration",
                "Resolution",
                "Uploader",
                "Export plan",
            )
        ):
            ctk.CTkLabel(
                pad,
                text=key.upper(),
                font=font(9, "bold"),
                text_color=P["dim"],
                anchor="w",
                width=76,
            ).grid(
                row=i,
                column=0,
                sticky="w",
                pady=4
            )

            label = ctk.CTkLabel(
                pad,
                text="—",
                font=font(10),
                text_color=P["text"],
                anchor="w",
                justify="left",
                wraplength=160,
            )

            label.grid(
                row=i,
                column=1,
                sticky="w",
                pady=4
            )

            self.info_labels[key] = label

    # ------------------------------------------------------------
    # CENTER PANEL
    # ------------------------------------------------------------

    def build_center(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        preview_section, body = self.section(
            parent,
            "Program monitor",
            "LIVE CROP GUIDE"
        )

        preview_section.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, 10)
        )

        self.preview = tk.Canvas(
            body,
            bg="#080b10",
            highlightthickness=0,
            height=230,
        )

        self.preview.pack(
            fill="both",
            expand=True,
            padx=9,
            pady=9
        )

        self.preview.bind(
            "<Configure>",
            lambda _event: self.draw_preview()
        )

        timeline_section, body = self.section(
            parent,
            "Edit timeline",
            "SPLIT MAP"
        )

        timeline_section.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        self.timeline = tk.Canvas(
            body,
            bg="#080b10",
            highlightthickness=0,
            height=112,
        )

        self.timeline.pack(
            fill="x",
            padx=9,
            pady=(9, 3)
        )

        self.timeline.bind(
            "<Configure>",
            lambda _event: self.draw_timeline()
        )

        self.timeline_note = ctk.CTkLabel(
            body,
            text=(
                "Download a video to inspect its duration "
                "and plan parts."
            ),
            font=font(10),
            text_color=P["muted"],
            anchor="w",
        )

        self.timeline_note.pack(
            fill="x",
            padx=12,
            pady=(0, 8)
        )

        render_section, body = self.section(
            parent,
            "Render queue",
            "DOWNLOAD → PLAN → EXPORT"
        )

        render_section.grid(
            row=2,
            column=0,
            sticky="ew"
        )

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=12
        )

        pad.grid_columnconfigure(0, weight=1)

        self.start_btn = ctk.CTkButton(
            pad,
            text="↓   DOWNLOAD VIDEO",
            height=46,
            corner_radius=10,
            font=font(13, "bold"),
            fg_color=P["blue2"],
            hover_color=P["blue"],
            command=self.start_download,
        )

        self.start_btn.grid(
            row=0,
            column=0,
            sticky="ew"
        )

        self.cancel_btn = ctk.CTkButton(
            pad,
            text="Cancel",
            width=86,
            height=46,
            corner_radius=10,
            font=font(11, "bold"),
            fg_color="#542130",
            hover_color="#79283d",
            state="disabled",
            command=self.cancel,
        )

        self.cancel_btn.grid(
            row=0,
            column=1,
            padx=(8, 0)
        )

        row = ctk.CTkFrame(
            pad,
            fg_color="transparent"
        )

        row.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(11, 5)
        )

        self.status = ctk.CTkLabel(
            row,
            text="Ready · paste a link to begin",
            font=font(11),
            text_color=P["muted"],
            anchor="w",
        )

        self.status.pack(side="left")

        self.percent = ctk.CTkLabel(
            row,
            text="0%",
            font=font(11, "bold"),
            text_color=P["cyan"],
        )

        self.percent.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            pad,
            height=8,
            corner_radius=5,
            progress_color=P["cyan"],
            fg_color=P["field"],
        )

        self.progress_bar.set(0)

        self.progress_bar.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew"
        )

    # ------------------------------------------------------------
    # RIGHT PANEL
    # ------------------------------------------------------------

    def build_right(self, parent):
        inspector, body = self.section(
            parent,
            "Render inspector",
            "03 / SETTINGS"
        )

        inspector.pack(
            fill="x",
            pady=(0, 10)
        )

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=12
        )

        self.label(
            pad,
            "DOWNLOAD QUALITY"
        ).pack(fill="x")

        self.menu(
            pad,
            list(QUALITIES),
            self.quality
        ).pack(
            fill="x",
            pady=(6, 13)
        )

        self.label(
            pad,
            "FRAME / ASPECT RATIO"
        ).pack(fill="x")

        self.menu(
            pad,
            list(CROPS),
            self.crop,
            lambda _value: self.redraw()
        ).pack(
            fill="x",
            pady=(6, 0)
        )

        split_section, body = self.section(
            parent,
            "Split planner",
            "CUSTOM TIMECODES"
        )

        split_section.pack(
            fill="x",
            pady=(0, 10)
        )

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=12
        )

        ctk.CTkLabel(
            pad,
            text=(
                "After download, the split planner opens. "
                "Choose the number of parts and the exact "
                "duration of every part."
            ),
            font=font(10),
            text_color=P["muted"],
            wraplength=230,
            justify="left",
        ).pack(anchor="w")

        self.label(
            pad,
            "DEFAULT PART LENGTH (SECONDS)"
        ).pack(
            fill="x",
            pady=(13, 0)
        )

        row = ctk.CTkFrame(
            pad,
            fg_color="transparent"
        )

        row.pack(
            fill="x",
            pady=(6, 0)
        )

        self.part_entry = ctk.CTkEntry(
            row,
            textvariable=self.part_seconds,
            width=94,
            height=36,
            font=font(13, "bold"),
            justify="center",
            fg_color=P["field"],
            border_color=P["edge"],
            corner_radius=8,
        )

        self.part_entry.pack(side="left")

        ctk.CTkLabel(
            row,
            text="seconds",
            font=font(10),
            text_color=P["muted"],
        ).pack(
            side="left",
            padx=8
        )

        chiprow = ctk.CTkFrame(
            pad,
            fg_color="transparent"
        )

        chiprow.pack(
            fill="x",
            pady=(9, 0)
        )

        for i, seconds in enumerate(
            (15, 30, 34, 60, 120, 300)
        ):
            ctk.CTkButton(
                chiprow,
                text=str(seconds),
                width=37,
                height=27,
                corner_radius=7,
                font=font(10, "bold"),
                fg_color=P["field"],
                hover_color=P["edge"],
                text_color=P["text"],
                border_width=1,
                border_color=P["edge"],
                command=lambda value=seconds: (
                    self.part_seconds.set(str(value))
                ),
            ).grid(
                row=i // 3,
                column=i % 3,
                padx=2,
                pady=2,
                sticky="ew"
            )

        for j in range(3):
            chiprow.grid_columnconfigure(
                j,
                weight=1
            )

        behaviour, body = self.section(
            parent,
            "Workflow",
            "SAFE EXPORT"
        )

        behaviour.pack(fill="x")

        pad = ctk.CTkFrame(
            body,
            fg_color="transparent"
        )

        pad.pack(
            fill="x",
            padx=12,
            pady=12
        )

        ctk.CTkSwitch(
            pad,
            text="Split by custom durations",
            variable=self.split_default,
            font=font(11),
            progress_color=P["blue"],
            command=self.redraw,
        ).pack(anchor="w")

        ctk.CTkLabel(
            pad,
            text=(
                "The planner appears after the download "
                "finishes and before files are exported."
            ),
            font=font(10),
            text_color=P["dim"],
            wraplength=230,
            justify="left",
        ).pack(
            anchor="w",
            pady=(9, 0)
        )

    def menu(self, parent, values, variable, command=None):
        return ctk.CTkOptionMenu(
            parent,
            values=values,
            variable=variable,
            height=37,
            font=font(11),
            dropdown_font=font(11),
            corner_radius=8,
            fg_color=P["field"],
            button_color=P["edge"],
            button_hover_color=P["blue2"],
            dynamic_resizing=False,
            anchor="w",
            command=command,
        )

    # ------------------------------------------------------------
    # PREVIEW AND TIMELINE
    # ------------------------------------------------------------

    def get_default_seconds(self):
        try:
            value = int(
                float(self.part_seconds.get().strip())
            )

            return value if value >= 1 else 34

        except ValueError:
            return 34

    def redraw(self):
        try:
            self.draw_preview()
            self.draw_timeline()
            self.update_output_info()

        except (tk.TclError, AttributeError):
            pass

    def draw_preview(self):
        if not hasattr(self, "preview"):
            return

        canvas = self.preview
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 60 or height < 60:
            return

        sw, sh = self.src_dims or (1920, 1080)

        margin = 24

        scale = min(
            (width - 2 * margin) / sw,
            (height - 2 * margin) / sh,
        )

        fw, fh = sw * scale, sh * scale

        x0 = (width - fw) / 2
        y0 = (height - fh) / 2

        canvas.create_rectangle(
            x0,
            y0,
            x0 + fw,
            y0 + fh,
            fill="#111722",
            outline=P["edge"],
        )

        for i in range(1, 12):
            canvas.create_line(
                x0 + fw * i / 12,
                y0,
                x0 + fw * i / 12,
                y0 + fh,
                fill="#1b2433",
            )

        for i in range(1, 7):
            canvas.create_line(
                x0,
                y0 + fh * i / 7,
                x0 + fw,
                y0 + fh * i / 7,
                fill="#1b2433",
            )

        ratio = CROPS.get(self.crop.get())

        if ratio:
            rw, rh = ratio

            cw = min(
                sw,
                sh * rw / rh
            )

            ch = min(
                sh,
                sw * rh / rw
            )

        else:
            cw, ch = sw, sh

        ax = x0 + (fw - cw * scale) / 2
        ay = y0 + (fh - ch * scale) / 2

        bx = ax + cw * scale
        by = ay + ch * scale

        if ratio:
            boxes = (
                (x0, y0, ax, y0 + fh),
                (bx, y0, x0 + fw, y0 + fh),
                (ax, y0, bx, ay),
                (ax, by, bx, y0 + fh),
            )

            for box in boxes:
                if (
                    box[2] - box[0] > 0.5
                    and box[3] - box[1] > 0.5
                ):
                    canvas.create_rectangle(
                        *box,
                        fill="#000000",
                        stipple="gray50",
                        outline="",
                    )

        canvas.create_rectangle(
            ax,
            ay,
            bx,
            by,
            outline=P["cyan"],
            width=2,
        )

        for i in (1, 2):
            canvas.create_line(
                ax + (bx - ax) * i / 3,
                ay,
                ax + (bx - ax) * i / 3,
                by,
                fill=P["blue"],
                dash=(3, 5),
            )

            canvas.create_line(
                ax,
                ay + (by - ay) * i / 3,
                bx,
                ay + (by - ay) * i / 3,
                fill=P["blue"],
                dash=(3, 5),
            )

        canvas.create_text(
            ax + 9,
            ay + 12,
            text=(
                f"{self.crop.get().split('·')[-1].strip() if ratio else 'ORIGINAL'}"
                f"  |  {int(cw) // 2 * 2} × {int(ch) // 2 * 2}"
            ),
            anchor="w",
            fill=P["cyan"],
            font=("Segoe UI", 9, "bold"),
        )

        canvas.create_text(
            x0 + 4,
            y0 - 11,
            text=f"SOURCE  {sw} × {sh}",
            anchor="w",
            fill=P["muted"],
            font=("Segoe UI", 8, "bold"),
        )

        if not self.meta:
            canvas.create_text(
                width / 2,
                height / 2,
                text="STUDIO MONITOR",
                fill=P["muted"],
                font=("Segoe UI", 13, "bold"),
            )

            canvas.create_text(
                width / 2,
                height / 2 + 22,
                text="Media metadata and crop guide appear here",
                fill=P["dim"],
                font=("Segoe UI", 9),
            )

    def draw_timeline(self):
        if not hasattr(self, "timeline"):
            return

        canvas = self.timeline
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 120:
            return

        x0 = 55
        x1 = width - 12
        track = x1 - x0
        top = 26

        canvas.create_rectangle(
            0, 0, width, 20,
            fill="#0d121b",
            outline=""
        )

        canvas.create_text(
            9, 10,
            text="TIME",
            anchor="w",
            fill=P["dim"],
            font=("Segoe UI", 8, "bold"),
        )

        canvas.create_text(
            42, top + 19,
            text="V1",
            fill=P["muted"],
            font=("Segoe UI", 9, "bold"),
        )

        canvas.create_text(
            42, top + 62,
            text="A1",
            fill=P["muted"],
            font=("Segoe UI", 9, "bold"),
        )

        canvas.create_rectangle(
            x0, top, x1, top + 34,
            fill="#111927",
            outline=P["edge"],
        )

        canvas.create_rectangle(
            x0, top + 43, x1, top + 65,
            fill="#111927",
            outline=P["edge"],
        )

        if not self.duration:
            canvas.create_text(
                (x0 + x1) / 2,
                top + 17,
                text="TIMELINE AWAITS MEDIA ANALYSIS",
                fill=P["dim"],
                font=("Segoe UI", 9),
            )

            self.timeline_note.configure(
                text=(
                    "Download a video to inspect duration "
                    "and customize each part."
                )
            )

            return

        duration = self.duration

        steps = (
            1, 2, 5, 10, 15, 30, 60,
            120, 300, 600, 900, 1800, 3600
        )

        step = next(
            (
                value
                for value in steps
                if value * track / duration >= 70
            ),
            3600,
        )

        current = 0

        while current <= duration:
            x = x0 + current / duration * track

            canvas.create_line(
                x, 17, x, 23,
                fill=P["dim"]
            )

            canvas.create_text(
                x + 2,
                10,
                text=fmt_time(current),
                anchor="w",
                fill=P["muted"],
                font=("Consolas", 8),
            )

            current += step

        part = (
            self.get_default_seconds()
            if self.split_default.get()
            else None
        )

        count = (
            math.ceil(duration / part)
            if part else 1
        )

        for i in range(min(count, 300)):
            start = i * part if part else 0
            end = min(duration, start + part) if part else duration

            xa = x0 + start / duration * track + 1
            xb = x0 + end / duration * track - 1

            canvas.create_rectangle(
                xa,
                top + 2,
                xb,
                top + 32,
                fill="#2855a7" if i % 2 == 0 else "#176d78",
                outline="#080b10",
            )

            canvas.create_rectangle(
                xa,
                top + 45,
                xb,
                top + 63,
                fill="#246548",
                outline="#080b10",
            )

            if xb - xa > 28:
                canvas.create_text(
                    xa + 5,
                    top + 17,
                    text=f"P{i + 1}",
                    anchor="w",
                    fill="white",
                    font=("Segoe UI", 8, "bold"),
                )

        if count > 300:
            canvas.create_text(
                (x0 + x1) / 2,
                top + 17,
                text=f"{count} PARTS",
                fill="white",
                font=("Segoe UI", 9, "bold"),
            )

        play_x = x0 + max(
            0,
            min(1, self.playhead)
        ) * track

        canvas.create_line(
            play_x,
            16,
            play_x,
            top + 66,
            fill=P["red"],
            width=2,
        )

        self.timeline_note.configure(
            text=(
                f"{fmt_time(duration)} total  •  "
                f"estimated {count} part(s)  •  "
                "final durations confirmed after download"
            )
        )

    def update_output_info(self):
        if not hasattr(self, "info_labels"):
            return

        if self.duration:
            count = (
                math.ceil(
                    self.duration / self.get_default_seconds()
                )
                if self.split_default.get()
                else 1
            )

            text = f"Planner · ~{count} part(s)"

        else:
            text = "MP4 · custom split planner"

        self.info_labels["Export plan"].configure(
            text=text
        )

    # ------------------------------------------------------------
    # THREAD-SAFE UI HELPERS
    # ------------------------------------------------------------

    def ui(self, function):
        try:
            self.after(0, function)
        except Exception:
            pass

    def log(self, message, tag="info"):
        stamp = time.strftime("%H:%M:%S")

        def update():
            self.log_box.configure(state="normal")

            self.log_box.insert(
                "end",
                f"[{stamp}]  {message}\n",
                tag
            )

            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.ui(update)

    def set_progress(self, fraction, status=None):
        fraction = max(
            0,
            min(1, float(fraction))
        )

        def update():
            self.progress_bar.set(fraction)

            self.percent.configure(
                text=f"{fraction * 100:.0f}%"
            )

            if status is not None:
                self.status.configure(text=status)

                self.status_left.configure(
                    text="●  " + status[:52]
                )

        self.ui(update)

    def set_meta(self, info):
        title = info.get("title") or info.get("id") or "—"
        duration = float(info.get("duration") or 0)

        width = info.get("width")
        height = info.get("height")

        def update():
            self.meta = {"title": title}
            self.duration = duration

            self.src_dims = (
                (int(width), int(height))
                if width and height else None
            )

            self.info_labels["Title"].configure(
                text=title[:72]
            )

            self.info_labels["Duration"].configure(
                text=fmt_time(duration) if duration else "—"
            )

            self.info_labels["Resolution"].configure(
                text=(
                    f"{width} × {height}"
                    if width and height else "—"
                )
            )

            self.info_labels["Uploader"].configure(
                text=str(
                    info.get("uploader")
                    or info.get("channel")
                    or "—"
                )[:35]
            )

            self.playhead = 0
            self.redraw()

        self.ui(update)

    # ------------------------------------------------------------
    # TOOL STATUS AND FILE PICKERS
    # ------------------------------------------------------------

    def update_tool_status(self):
        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")

        if self.ffmpeg and self.ffprobe:
            self.tool_badge.configure(
                text="●  FFMPEG + FFPROBE READY",
                fg_color="#12362d",
                text_color=P["green"],
            )

        elif self.ffmpeg:
            self.tool_badge.configure(
                text="●  FFPROBE MISSING",
                fg_color="#40321a",
                text_color=P["amber"],
            )

        else:
            self.tool_badge.configure(
                text="●  FFMPEG MISSING",
                fg_color="#451e2a",
                text_color=P["red"],
            )

    def paste(self):
        if self.running:
            return

        try:
            text = self.clipboard_get()
        except tk.TclError:
            return

        self.url_entry.delete(0, "end")

        self.url_entry.insert(
            0,
            extract_url(text) or text.strip()
        )

        self.url_entry.focus_set()

    def clear(self):
        if not self.running:
            self.url_entry.delete(0, "end")
            self.url_entry.focus_set()

    def pick_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self.out_dir.get() or str(Path.home())
        )

        if folder:
            self.out_dir.set(folder)
            self.save_config()

    def open_folder(self):
        folder = self.out_dir.get().strip()

        try:
            os.makedirs(folder, exist_ok=True)

            if os.name == "nt":
                os.startfile(folder)

            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])

            else:
                subprocess.Popen(["xdg-open", folder])

        except Exception as error:
            messagebox.showerror(
                "Open folder",
                str(error)
            )

    # ------------------------------------------------------------
    # DOWNLOAD CONTROL
    # ------------------------------------------------------------

    def start_download(self):
        if self.running:
            return

        url = extract_url(
            self.url_entry.get().strip()
        )

        if not url:
            messagebox.showwarning(
                "Link required",
                "Paste a valid video URL first."
            )
            return

        self.update_tool_status()

        if not self.ffmpeg:
            messagebox.showerror(
                "FFmpeg required",
                "Install FFmpeg from Command Prompt:\n"
                "winget install Gyan.FFmpeg\n\n"
                "Then restart the app."
            )
            return

        folder = self.out_dir.get().strip()

        if not folder:
            messagebox.showwarning(
                "Save location",
                "Choose a save folder."
            )
            return

        try:
            os.makedirs(folder, exist_ok=True)

        except OSError as error:
            messagebox.showerror(
                "Save location",
                str(error)
            )
            return

        self.save_config()

        settings = {
            "url": url,
            "out": folder,
            "height": QUALITIES.get(self.quality.get()),
            "crop": CROPS.get(self.crop.get()),
            "default_split": self.split_default.get(),
            "part_seconds": self.get_default_seconds(),
            "clear_after": False,
        }

        self.cancel_event.clear()
        self.running = True
        self.playhead = 0

        self.start_btn.configure(
            state="disabled",
            text="DOWNLOADING…"
        )

        self.cancel_btn.configure(
            state="normal"
        )

        self.url_entry.configure(
            state="disabled"
        )

        self.log(f"Queued source: {url}")

        self.set_progress(
            0,
            "Analysing source metadata…"
        )

        threading.Thread(
            target=self.worker,
            args=(settings,),
            daemon=True,
        ).start()

    def cancel(self):
        self.cancel_event.set()

        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

        self.set_progress(
            self.progress_bar.get(),
            "Cancelling task…"
        )

    def finish(self, ok):
        self.running = False

        self.start_btn.configure(
            state="normal",
            text="↓   DOWNLOAD VIDEO"
        )

        self.cancel_btn.configure(
            state="disabled"
        )

        self.url_entry.configure(
            state="normal"
        )

        self.status_right.configure(
            text=(
                f"Jobs completed: {self.completed}   "
                "•   MP4 pipeline"
            )
        )

        self.url_entry.focus_set()

    def close_app(self):
        if self.running:
            if not messagebox.askyesno(
                "Exit Studio",
                "A task is running. Cancel it and exit?"
            ):
                return

            self.cancel()

        self.save_config()
        self.destroy()

    # ------------------------------------------------------------
    # DOWNLOAD -> SPLIT PLANNER -> EXPORT
    # ------------------------------------------------------------

    def worker(self, settings):
        temp_dir = os.path.join(
            settings["out"],
            f".vdp_tmp_{int(time.time())}"
        )

        ok = False
        outputs = []

        try:
            os.makedirs(
                temp_dir,
                exist_ok=True
            )

            files, title = self.download(
                settings,
                temp_dir
            )

            if not files:
                raise RuntimeError(
                    "Download completed but no video file was found."
                )

            if self.cancel_event.is_set():
                raise Cancelled()

            # Show the planner after download and before export.
            plan = self.ask_split_plan(
                title,
                files[0],
                settings
            )

            if plan is None:
                raise Cancelled()

            if plan.get("split"):
                count = len(plan.get("part_durations", []))
                self.log(
                    f"Export plan: split into {count} part(s)",
                    "info"
                )
            else:
                self.log(
                    "Export plan: single file (no split)",
                    "info"
                )

            for index, source in enumerate(files, 1):
                if self.cancel_event.is_set():
                    raise Cancelled()

                stem = safe_name(title)

                if len(files) > 1:
                    stem += f"_{index}"

                base = self.unique_base(
                    settings["out"],
                    stem
                )

                outputs.append(base)

                self.process_video(
                    source,
                    base,
                    {**settings, **plan}
                )

                self.log(
                    f"Export complete: {base}",
                    "ok"
                )

            ok = True
            self.completed += 1

            self.set_progress(
                1,
                "Export complete · ready for next video"
            )

        except Exception as error:
            cancelled = (
                self.cancel_event.is_set()
                or isinstance(error, Cancelled)
            )

            message = (
                "Cancelled."
                if cancelled
                else friendly_error(error)
            )

            for base in outputs:
                for path in self.list_outputs(
                    settings["out"],
                    base
                ):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

            self.log(
                message,
                "warn" if cancelled else "err"
            )

            self.set_progress(0, message)

        finally:
            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

            self.process = None

            self.ui(
                lambda: self.finish(ok)
            )

    # ------------------------------------------------------------
    # SPLIT PLANNER DIALOG
    # ------------------------------------------------------------

    def ask_split_plan(self, title, source, settings):
        """Open the split planner from the worker thread and wait
        synchronously for the user's decision.

        Buttons are packed with side='bottom' FIRST so they are
        always visible regardless of content height or screen size.
        """
        done = threading.Event()
        result = {"value": None}

        def open_dialog():
            if self.cancel_event.is_set():
                result["value"] = None
                done.set()
                return

            try:
                duration = (
                    self.get_duration(source)
                    or self.duration
                )
            except Exception:
                duration = self.duration or 0

            whole = max(1, int(round(duration)))

            dlg = ctk.CTkToplevel(self)
            dlg.title("Split Planner — confirm export")
            dlg.configure(fg_color=P["bg"])
            dlg.transient(self)
            dlg.resizable(False, False)

            # ----- size: keep buttons visible on smaller screens -----
            sw = dlg.winfo_screenwidth()
            sh = dlg.winfo_screenheight()

            width_d = 640
            height_d = min(820, sh - 120)

            dlg.update_idletasks()

            x = (
                self.winfo_rootx()
                + (self.winfo_width() - width_d) // 2
            )

            y = (
                self.winfo_rooty()
                + (self.winfo_height() - height_d) // 2
            )

            dlg.geometry(
                f"{width_d}x{height_d}+"
                f"{max(0, x)}+{max(20, y)}"
            )

            # =========================================================
            # BUTTONS FIRST (packed to bottom) — always visible
            # =========================================================
            buttons = ctk.CTkFrame(
                dlg,
                fg_color=P["bg"],
                corner_radius=0,
                height=72,
            )
            buttons.pack(
                side="bottom",
                fill="x",
                padx=22,
                pady=(6, 16)
            )
            buttons.pack_propagate(False)

            def finish(value):
                result["value"] = value

                try:
                    dlg.grab_release()
                except tk.TclError:
                    pass

                try:
                    dlg.destroy()
                except tk.TclError:
                    pass

                done.set()

            ctk.CTkButton(
                buttons,
                text="Cancel export",
                width=140,
                height=42,
                corner_radius=9,
                fg_color=P["field"],
                hover_color=P["edge"],
                text_color=P["text"],
                command=lambda: finish(None),
            ).pack(side="left", pady=15)

            confirm_btn = ctk.CTkButton(
                buttons,
                text="CONFIRM & EXPORT  →",
                width=200,
                height=42,
                corner_radius=9,
                font=font(12, "bold"),
                fg_color=P["blue2"],
                hover_color=P["blue"],
            )
            confirm_btn.pack(side="right", pady=15)

            # =========================================================
            # HEADER
            # =========================================================
            header = ctk.CTkFrame(dlg, fg_color="transparent")
            header.pack(side="top", fill="x", padx=24, pady=(20, 4))

            ctk.CTkLabel(
                header,
                text="CUSTOM SPLIT PLANNER",
                font=font(19, "bold"),
                text_color=P["text"],
            ).pack(anchor="w")

            ctk.CTkLabel(
                header,
                text=(
                    "Download complete · review the timeline "
                    "before files are exported"
                ),
                font=font(11),
                text_color=P["muted"],
            ).pack(anchor="w", pady=(2, 0))

            # =========================================================
            # SUMMARY CARD
            # =========================================================
            summary = ctk.CTkFrame(
                dlg,
                fg_color=P["panel"],
                corner_radius=12,
                border_width=1,
                border_color=P["edge"],
            )
            summary.pack(fill="x", padx=22, pady=(10, 10))

            ctk.CTkLabel(
                summary,
                text=title[:70] or "Downloaded video",
                font=font(12, "bold"),
                text_color=P["text"],
                wraplength=560,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(12, 4))

            ctk.CTkLabel(
                summary,
                text=(
                    f"DETECTED DURATION   {fmt_time(duration)} "
                    f"({whole} sec)"
                ),
                font=font(11, "bold"),
                text_color=P["cyan"],
            ).pack(anchor="w", padx=14, pady=(0, 12))

            # =========================================================
            # SPLIT TOGGLE
            # =========================================================
            split_var = tk.BooleanVar(
                value=bool(settings["default_split"])
            )

            ctk.CTkSwitch(
                dlg,
                text="Split this video into multiple parts",
                variable=split_var,
                font=font(12, "bold"),
                progress_color=P["blue"],
            ).pack(anchor="w", padx=25, pady=(0, 10))

            # =========================================================
            # CONTROLS (fills remaining space)
            # =========================================================
            controls = ctk.CTkFrame(
                dlg,
                fg_color=P["panel"],
                corner_radius=12,
            )
            controls.pack(
                side="top",
                fill="both",
                expand=True,
                padx=22,
                pady=(0, 8)
            )

            top = ctk.CTkFrame(controls, fg_color="transparent")
            top.pack(fill="x", padx=13, pady=(12, 0))

            ctk.CTkLabel(
                top,
                text="NUMBER OF PARTS",
                font=font(10, "bold"),
                text_color=P["muted"],
            ).pack(side="left")

            count_var = tk.StringVar(
                value=str(
                    max(
                        1,
                        math.ceil(
                            whole / max(
                                1,
                                int(settings["part_seconds"])
                            )
                        )
                    )
                )
            )

            ctk.CTkEntry(
                top,
                textvariable=count_var,
                width=88,
                height=34,
                justify="center",
                font=font(13, "bold"),
                fg_color=P["field"],
                border_color=P["edge"],
            ).pack(side="right")

            ctk.CTkLabel(
                controls,
                text=(
                    "Set each part length in seconds. "
                    "Total must match video duration."
                ),
                font=font(10),
                text_color=P["muted"],
                wraplength=560,
                justify="left",
            ).pack(anchor="w", padx=13, pady=(6, 8))

            sc = ctk.CTkScrollableFrame(
                controls,
                height=160,
                fg_color=P["field"],
                corner_radius=9,
            )
            sc.pack(
                side="top",
                fill="both",
                expand=True,
                padx=12,
                pady=(0, 10)
            )

            rows = []

            def update_total(*_):
                try:
                    values = [int(v.get()) for v in rows]
                    total = sum(values)
                    valid = all(v > 0 for v in values)
                except ValueError:
                    values = []
                    total = 0
                    valid = False

                delta = whole - total
                valid_total = valid and abs(delta) <= 1

                if valid_total:
                    status_text = "MATCH"
                elif delta > 0:
                    status_text = f"{abs(delta)} sec too short"
                else:
                    status_text = f"{abs(delta)} sec too long"

                try:
                    total_label.configure(
                        text=(
                            f"TOTAL  {total} sec / {whole} sec"
                            f"   ·   {status_text}"
                        ),
                        text_color=(
                            P["green"] if valid_total else P["amber"]
                        ),
                    )
                except Exception:
                    pass

                return valid_total, values

            def populate(*_):
                try:
                    count = int(count_var.get())
                except ValueError:
                    return

                if count < 1 or count > 100:
                    return

                old_values = []
                for v in rows:
                    try:
                        old_values.append(max(1, int(v.get())))
                    except ValueError:
                        old_values.append(1)

                for child in sc.winfo_children():
                    child.destroy()
                rows.clear()

                base_seconds = whole // count
                remainder = whole % count

                for i in range(count):
                    if i < len(old_values):
                        default = old_values[i]
                    else:
                        default = base_seconds + (1 if i < remainder else 0)

                    row = ctk.CTkFrame(
                        sc, fg_color=P["panel"], corner_radius=7
                    )
                    row.pack(fill="x", padx=4, pady=3)

                    ctk.CTkLabel(
                        row,
                        text=f"PART {i + 1:02d}",
                        font=font(10, "bold"),
                        text_color=P["cyan"],
                        width=90,
                        anchor="w",
                    ).pack(side="left", padx=10, pady=7)

                    variable = tk.StringVar(value=str(max(1, default)))
                    rows.append(variable)
                    variable.trace_add(
                        "write", lambda *_: update_total()
                    )

                    ctk.CTkEntry(
                        row,
                        textvariable=variable,
                        width=95,
                        height=30,
                        justify="center",
                        font=font(11, "bold"),
                        fg_color=P["field"],
                        border_color=P["edge"],
                    ).pack(side="right", padx=10, pady=5)

                    ctk.CTkLabel(
                        row,
                        text="seconds",
                        font=font(10),
                        text_color=P["muted"],
                    ).pack(side="right")

                update_total()

            total_label = ctk.CTkLabel(
                controls,
                text="",
                font=font(11, "bold"),
                text_color=P["amber"],
            )
            total_label.pack(anchor="w", padx=14, pady=(0, 12))

            count_var.trace_add("write", populate)
            populate()

            # =========================================================
            # CONFIRM HANDLER (needs update_total defined above)
            # =========================================================
            def confirm():
                if not split_var.get():
                    finish({
                        "split": False,
                        "part_durations": [],
                    })
                    return

                valid, values = update_total()

                try:
                    count = int(count_var.get())
                except ValueError:
                    count = 0

                if not valid or count != len(values) or not values:
                    messagebox.showwarning(
                        "Check part lengths",
                        (
                            "Part lengths must be positive whole "
                            f"seconds and total about {whole} seconds. "
                            "Adjust the fields before exporting."
                        ),
                        parent=dlg,
                    )
                    return

                values[-1] += whole - sum(values)

                finish({
                    "split": count > 1,
                    "part_durations": values,
                })

            confirm_btn.configure(command=confirm)

            dlg.protocol(
                "WM_DELETE_WINDOW",
                lambda: finish(None)
            )

            try:
                dlg.grab_set()
            except tk.TclError:
                pass

            dlg.lift()
            dlg.focus_force()

            try:
                dlg.after(50, lambda: dlg.focus_force())
            except tk.TclError:
                pass

        self.ui(open_dialog)

        while not done.wait(0.1):
            if self.cancel_event.is_set():
                return None

        return result["value"]

    # ------------------------------------------------------------
    # VIDEO DOWNLOAD
    # ------------------------------------------------------------

    def download(self, settings, temp_dir):
        height = settings["height"]

        if height:
            fmt = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        else:
            fmt = "bestvideo+bestaudio/best"

        def hook(data):
            if self.cancel_event.is_set():
                raise yt_dlp.utils.DownloadError(
                    "Download cancelled."
                )

            if data.get("status") == "downloading":
                total = (
                    data.get("total_bytes")
                    or data.get("total_bytes_estimate")
                    or 0
                )

                downloaded = data.get("downloaded_bytes") or 0

                fraction = (
                    downloaded / total
                    if total else 0
                )

                speed = data.get("speed")

                suffix = (
                    f" · {speed / 1024 / 1024:.1f} MB/s"
                    if speed else ""
                )

                self.set_progress(
                    fraction * 0.58,
                    f"Downloading · {fraction * 100:.0f}%{suffix}",
                )

            elif data.get("status") == "finished":
                self.set_progress(
                    0.58,
                    "Download complete · opening split planner…"
                )

        options = {
            "format": fmt,
            "outtmpl": os.path.join(
                temp_dir,
                "%(id)s.%(ext)s"
            ),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [hook],
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 3,
            "ffmpeg_location": os.path.dirname(self.ffmpeg),
            "windowsfilenames": True,
            "overwrites": False,
            "continuedl": True,
        }

        self.log(
            "Using public/accessible video mode — no login bypass."
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                settings["url"],
                download=False
            )

            if isinstance(info, dict):
                self.set_meta(info)

                self.log(
                    f"Source found: {info.get('title') or info.get('id')}"
                )

            self.set_progress(
                0.03,
                "Downloading source media…"
            )

            info = ydl.process_ie_result(
                info,
                download=True
            )

        title = (
            (info or {}).get("title")
            or (info or {}).get("id")
            or "video"
        )

        files = sorted(
            str(path)
            for path in Path(temp_dir).glob("*")
            if (
                path.is_file()
                and path.suffix.lower() in VIDEO_EXT
            )
        )

        return files, title

    # ------------------------------------------------------------
    # OUTPUT FILES AND MEDIA TOOLS
    # ------------------------------------------------------------

    def list_outputs(self, folder, base):
        try:
            return sorted(
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if (
                    name == base + ".mp4"
                    or (
                        name.startswith(base + "_part")
                        and name.endswith(".mp4")
                    )
                )
            )

        except OSError:
            return []

    def unique_base(self, folder, stem):
        candidate = stem
        index = 2

        while (
            any(
                os.path.exists(
                    os.path.join(folder, candidate + ext)
                )
                for ext in (".mp4", ".mkv", ".webm")
            )
            or any(
                name.startswith(candidate + "_part")
                for name in os.listdir(folder)
            )
        ):
            candidate = f"{stem} ({index})"
            index += 1

        return candidate

    def get_duration(self, path):
        if not self.ffprobe:
            return 0.0

        try:
            result = subprocess.run(
                [
                    self.ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=NO_WINDOW,
            )

            return float(result.stdout.strip())

        except (
            ValueError,
            OSError,
            subprocess.SubprocessError,
        ):
            return 0.0

    # ------------------------------------------------------------
    # CROP, SPLIT AND EXPORT
    # ------------------------------------------------------------

    def process_video(self, source, base, settings):
        duration = (
            self.get_duration(source)
            or self.duration
        )

        if duration and abs(duration - self.duration) > 0.5:
            self.duration = duration
            self.ui(self.redraw)

        cmd = [
            self.ffmpeg,
            "-y",
            "-hide_banner",
            "-progress", "pipe:1",
            "-nostats",
            "-loglevel", "error",
            "-i", source,
        ]

        crop = settings["crop"]

        if crop:
            width, height = crop

            crop_filter = (
                f"crop=w=trunc(min(iw\\,ih*{width}/{height})/2)*2:"
                f"h=trunc(min(ih\\,iw*{height}/{width})/2)*2,"
                "setsar=1"
            )

            cmd += [
                "-vf",
                crop_filter,
            ]

        cmd += [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ]

        if settings["split"]:
            lengths = settings.get("part_durations") or []

            boundaries = []
            accumulated = 0

            for seconds in lengths[:-1]:
                accumulated += seconds
                boundaries.append(accumulated)

            if boundaries:
                keyframes = ",".join(
                    (
                        f"{value // 3600:02d}:"
                        f"{(value % 3600) // 60:02d}:"
                        f"{value % 60:02d}.000"
                    )
                    for value in boundaries
                )

                segment_times = ",".join(
                    str(value)
                    for value in boundaries
                )

                output_pattern = os.path.join(
                    settings["out"],
                    f"{base}_part%03d.mp4"
                )

                cmd += [
                    "-force_key_frames",
                    keyframes,
                    "-f", "segment",
                    "-segment_times", segment_times,
                    "-segment_format", "mp4",
                    "-segment_format_options",
                    "movflags=+faststart",
                    "-reset_timestamps", "1",
                    output_pattern,
                ]

            else:
                cmd += [
                    "-movflags", "+faststart",
                    os.path.join(
                        settings["out"],
                        base + ".mp4"
                    ),
                ]

        else:
            cmd += [
                "-movflags", "+faststart",
                os.path.join(
                    settings["out"],
                    base + ".mp4"
                ),
            ]

        label = (
            "Cropping + splitting"
            if settings["crop"] and settings["split"]
            else "Cropping"
            if settings["crop"]
            else "Splitting"
            if settings["split"]
            else "Encoding / export"
        )

        self.set_progress(
            0.60,
            f"{label}…"
        )

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=NO_WINDOW,
        )

        tail = []

        for line in self.process.stdout:
            line = line.strip()

            if (
                line.startswith(
                    ("out_time_ms=", "out_time_us=")
                )
                and duration
            ):
                try:
                    fraction = min(
                        int(line.split("=")[1])
                        / 1_000_000
                        / duration,
                        1.0,
                    )

                except ValueError:
                    continue

                self.playhead = fraction

                self.set_progress(
                    0.60 + 0.40 * fraction,
                    f"{label} · {fraction * 100:.0f}%",
                )

                self.ui(self.draw_timeline)

            elif line and "=" not in line:
                tail = (tail + [line])[-5:]

        self.process.wait()

        if self.cancel_event.is_set():
            raise Cancelled()

        if self.process.returncode != 0:
            raise RuntimeError(
                "FFmpeg failed: " + " ".join(tail)[-500:]
            )

        if settings["split"]:
            parts = self.list_outputs(
                settings["out"],
                base
            )

            if (
                len(parts) == 1
                and parts[0].endswith("_part001.mp4")
            ):
                os.replace(
                    parts[0],
                    os.path.join(
                        settings["out"],
                        base + ".mp4"
                    )
                )


# ================================================================
# APP ENTRY POINT
# ================================================================

if __name__ == "__main__":
    VideoDownloader().mainloop()