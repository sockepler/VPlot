"""
VPlot — Analog Circuit Waveform Viewer
CSV / VCSV / PSF ASCII  —  IEEE-style publication-quality output
Features: SI-prefix axes, editable labels, CJK legend, split/merge subplots,
          zoom back/forward, SVG/PDF/EPS/PNG export.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.ticker import Formatter

from .parsers import load_file, WaveformData, infer_unit, get_label

# ── CJK / Japanese font ───────────────────────────────────────────
# Priority: broad-coverage fonts first so Simplified Chinese + Japanese both render.
# Microsoft YaHei covers Simplified Chinese + Japanese kanji; Yu Gothic covers Japanese.
_CJK_PRIORITY = [
    "Microsoft YaHei",     # Simplified Chinese + Japanese kanji (Windows standard)
    "Noto Sans CJK SC",    # Google's full CJK coverage
    "SimHei",              # Simplified Chinese
    "Yu Gothic",           # Japanese (limited Simplified Chinese coverage)
    "Meiryo",              # Japanese
    "BIZ UDGothic",        # Japanese
    "MS Gothic",           # Japanese
]
_all_font_names = {f.name for f in fm.fontManager.ttflist}
_cjk_available = [f for f in _CJK_PRIORITY if f in _all_font_names]
if _cjk_available:
    # Build a fallback chain: our CJK fonts first, then the default Latin fallback
    matplotlib.rcParams["font.sans-serif"] = _cjk_available + ["DejaVu Sans", "Arial"]
    matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["svg.fonttype"] = "path"

# ── Light academic theme ──────────────────────────────────────────
THEME = {
    "bg":         "#F4F4F4",
    "bg2":        "#EBEBEB",
    "fg":         "#1A1A1A",
    "fg_dim":     "#777777",
    "accent":     "#1565C0",
    "accent2":    "#C62828",
    "border":     "#C8C8C8",
    "plot_bg":    "#FFFFFF",
    "grid":       "#E0E0E0",
    "toolbar_bg": "#DCDCDC",
    "range_bg":   "#E8E8E8",
    "entry_bg":   "#FFFFFF",
}

SIGNAL_COLORS = [
    "#0072BD", "#D95319", "#EDB120", "#7E2F8E",
    "#77AC30", "#4DBEEE", "#A2142F", "#005C1A",
    "#8B4513", "#4B0082", "#E64A19", "#00695C",
]
LINE_STYLES = ["-", "--", "-.", ":", (0,(3,1,1,1)), (0,(5,2))]

SI_PREFIXES = [
    (1e-15,"f"),(1e-12,"p"),(1e-9,"n"),(1e-6,"u"),
    (1e-3,"m"),(1,""),(1e3,"k"),(1e6,"M"),(1e9,"G"),
]


def si_format(value: float, unit: str = "") -> str:
    if value == 0:
        return f"0 {unit}"
    av = abs(value)
    for scale, prefix in SI_PREFIXES:
        if av < scale * 1000:
            return f"{value/scale:.4g} {prefix}{unit}"
    return f"{value:.4g} {unit}"


def _parse_float(s: str):
    """Parse user-entered float, supporting SI suffixes (1n, 2.5u, 3M …)."""
    s = s.strip()
    suffix_map = {"f":1e-15,"p":1e-12,"n":1e-9,"u":1e-6,"m":1e-3,
                  "k":1e3,"K":1e3,"M":1e6,"G":1e9,"T":1e12}
    if s and s[-1] in suffix_map:
        return float(s[:-1]) * suffix_map[s[-1]]
    return float(s)


def _best_si(vmin, vmax):
    """Return (scale, prefix) that best covers the range [vmin, vmax]."""
    max_abs = max(abs(vmin), abs(vmax))
    if max_abs == 0:
        return 1.0, ""
    for s, p in SI_PREFIXES:
        if max_abs < s * 1000:
            return s, p
    return 1.0, ""


class SIAxisFormatter(Formatter):
    """Divide every tick by a single *scale* — axis shows plain numbers only."""
    def __init__(self, scale=1.0):
        self.scale = scale

    def __call__(self, value, pos=None):
        num = value / self.scale
        if num == 0:
            return "0"
        if abs(num - round(num)) < max(abs(num) * 1e-9, 1e-12):
            return f"{int(round(num))}"
        return f"{num:.4g}"


def _si_range_str(value: float) -> str:
    """Format a value with SI prefix for the range toolbar entries."""
    if value == 0:
        return "0"
    av = abs(value)
    for scale, prefix in SI_PREFIXES:
        if av < scale * 1000:
            num = value / scale
            return f"{num:.6g}{prefix}"
    return f"{value:.6g}"


# ══════════════════════════════════════════════════════════════════
class WaveformViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VPlot")
        self.geometry("1500x920")
        self.minsize(1000, 640)

        self.data: WaveformData | None = None
        self.checked_signals: dict[str, tk.BooleanVar] = {}
        self.signal_color_map: dict[str, str] = {}
        self.signal_style_map: dict[str, str] = {}
        self._label_vars: dict[str, tk.StringVar] = {}

        # subplot grouping (Virtuoso-style split/merge)
        self._signal_group: dict[str, int] = {}
        self._next_gid = 0

        # axis label overrides
        self._xlabel_var  = tk.StringVar(value="time [s]")
        self._ylabel_vars: dict[int, tk.StringVar] = {}   # gid → label

        # range toolbar vars
        self._xmin_var = tk.StringVar()
        self._xmax_var = tk.StringVar()
        self._ymin_var = tk.StringVar()
        self._ymax_var = tk.StringVar()
        self._active_ax_idx = 0
        self._range_updating = False   # prevent feedback loop

        # style
        self._font_size   = tk.IntVar(value=10)
        self._font_bold   = tk.BooleanVar(value=False)
        self._line_width  = tk.DoubleVar(value=1.5)
        self._use_lstyles = tk.BooleanVar(value=False)
        self._show_grid   = True
        self._show_legend = True

        self.mode = "navigate"
        self.cursor_markers: list[dict] = []
        self.crosshair_lines: list = []
        self.axes: list[plt.Axes] = []
        self.recent_files: list[str] = []

        self._apply_theme()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Theme ──────────────────────────────────────────────────────
    def _apply_theme(self):
        self.configure(bg=THEME["bg"])
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=THEME["bg"], foreground=THEME["fg"],
                    bordercolor=THEME["border"], focuscolor=THEME["accent"])
        s.configure("TFrame",      background=THEME["bg"])
        s.configure("TLabel",      background=THEME["bg"], foreground=THEME["fg"])
        s.configure("TButton",     background=THEME["bg2"], foreground=THEME["fg"],
                    borderwidth=1, relief="flat", padding=(8,4))
        s.map("TButton",
              background=[("active",THEME["border"]),("pressed",THEME["accent"])],
              foreground=[("active",THEME["fg"])])
        s.configure("TCheckbutton", background=THEME["bg2"], foreground=THEME["fg"],
                    indicatorbackground="white", indicatorforeground=THEME["accent"])
        s.map("TCheckbutton", background=[("active",THEME["bg2"])],
              indicatorbackground=[("selected",THEME["accent"])])
        s.configure("Toolbar.TFrame",  background=THEME["toolbar_bg"])
        s.configure("Range.TFrame",    background=THEME["range_bg"])
        s.configure("Toolbar.TButton", background=THEME["toolbar_bg"],
                    foreground=THEME["fg"], padding=(10,5), borderwidth=0)
        s.map("Toolbar.TButton",
              background=[("active",THEME["border"])], relief=[("active","flat")])
        s.configure("Active.Toolbar.TButton",
                    background=THEME["accent"], foreground="white")
        s.configure("Range.TButton",  background=THEME["range_bg"],
                    foreground=THEME["fg"], padding=(6,3), borderwidth=1)
        s.map("Range.TButton", background=[("active",THEME["border"])])
        s.configure("Panel.TFrame",    background=THEME["bg2"])
        s.configure("Panel.TLabel",    background=THEME["bg2"], foreground=THEME["fg"])
        s.configure("PanelDim.TLabel", background=THEME["bg2"], foreground=THEME["fg_dim"])
        s.configure("Measure.TLabel",  background=THEME["bg2"], foreground=THEME["accent"],
                    font=("Consolas",9))
        s.configure("Status.TLabel",   background=THEME["toolbar_bg"],
                    foreground=THEME["fg_dim"], font=("Consolas",9))
        s.configure("RangeStatus.TLabel", background=THEME["range_bg"],
                    foreground=THEME["fg_dim"], font=("Consolas",9))
        s.configure("Title.TLabel",    background=THEME["bg2"], foreground=THEME["accent"],
                    font=("Segoe UI",9,"bold"))

    # ── UI Build ───────────────────────────────────────────────────
    def _build_ui(self):
        self._build_menu()
        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._build_signal_panel(main)
        self._build_plot_area(main)
        self._build_toolbar()
        self._build_range_toolbar()
        main.pack(fill=tk.BOTH, expand=True)
        self._build_status_bar()

    # ── Menu ───────────────────────────────────────────────────────
    def _build_menu(self):
        mb = tk.Menu(self, bg=THEME["bg2"], fg=THEME["fg"],
                     activebackground=THEME["accent"], activeforeground="white",
                     borderwidth=0)
        fm_ = tk.Menu(mb, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"],
                      activebackground=THEME["accent"], activeforeground="white")
        fm_.add_command(label="Open File…", accelerator="Ctrl+O",
                        command=self._open_file)
        fm_.add_separator()
        for fmt in ["PNG","PDF","SVG","EPS"]:
            fm_.add_command(label=f"Export {fmt}…",
                            command=lambda f=fmt.lower(): self._export(f))
        fm_.add_separator()
        fm_.add_command(label="Exit", command=self._on_close)
        mb.add_cascade(label="File", menu=fm_)

        vm = tk.Menu(mb, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"],
                     activebackground=THEME["accent"], activeforeground="white")
        vm.add_command(label="Toggle Grid",   command=self._toggle_grid)
        vm.add_command(label="Toggle Legend", command=self._toggle_legend)
        vm.add_command(label="Auto Scale",    accelerator="Home",
                       command=self._auto_scale)
        vm.add_separator()
        vm.add_command(label="Select All",    command=self._select_all)
        vm.add_command(label="Deselect All",  command=self._deselect_all)
        vm.add_separator()
        vm.add_command(label="Reset Subplot Layout", command=self._reset_groups)
        mb.add_cascade(label="View", menu=vm)

        self.config(menu=mb)
        self.bind("<Control-o>", lambda e: self._open_file())
        self.bind("<Home>",      lambda e: self._auto_scale())

    # ── Main toolbar ───────────────────────────────────────────────
    def _build_toolbar(self):
        tb = ttk.Frame(self, style="Toolbar.TFrame")
        tb.pack(fill=tk.X)
        ttk.Button(tb, text="Open", style="Toolbar.TButton",
                   command=self._open_file).pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=4)

        self._mode_buttons: dict[str, ttk.Button] = {}
        for mn, ml in [("navigate","Select"),("pan","Pan"),
                       ("zoom","Zoom"),("cursor","Cursor")]:
            btn = ttk.Button(tb, text=ml, style="Toolbar.TButton",
                             command=lambda m=mn: self._set_mode(m))
            btn.pack(side=tk.LEFT, padx=2, pady=3)
            self._mode_buttons[mn] = btn

        ttk.Separator(tb, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=4)
        ttk.Button(tb, text="Home", style="Toolbar.TButton",
                   command=self._auto_scale).pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Button(tb, text="Back", style="Toolbar.TButton",
                   command=self._nav_back).pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Button(tb, text="Fwd",  style="Toolbar.TButton",
                   command=self._nav_forward).pack(side=tk.LEFT, padx=2, pady=3)

        ttk.Separator(tb, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=4)
        for fmt in ["PNG","PDF","SVG","EPS"]:
            ttk.Button(tb, text=fmt, style="Toolbar.TButton",
                       command=lambda f=fmt.lower(): self._export(f)
                       ).pack(side=tk.LEFT, padx=2, pady=3)

        self._file_label = ttk.Label(tb, text="  No file loaded",
                                     style="Status.TLabel")
        self._file_label.pack(side=tk.RIGHT, padx=10)
        self._set_mode("navigate")

    # ── Range toolbar ──────────────────────────────────────────────
    def _build_range_toolbar(self):
        rt = ttk.Frame(self, style="Range.TFrame")
        rt.pack(fill=tk.X)

        def _entry(parent, var, w=11):
            e = tk.Entry(parent, textvariable=var, width=w,
                         bg=THEME["entry_bg"], fg=THEME["fg"],
                         font=("Consolas",9), relief="solid", bd=1,
                         insertbackground=THEME["fg"])
            return e

        # ── X ──────────────────────────────────────────────────────
        ttk.Label(rt, text=" X label:", style="RangeStatus.TLabel").pack(
            side=tk.LEFT, padx=(8,2), pady=3)
        self._xlabel_entry = _entry(rt, self._xlabel_var, w=14)
        self._xlabel_entry.pack(side=tk.LEFT, padx=2, pady=3)
        self._xlabel_entry.bind("<Return>",   lambda e: self._replot())
        self._xlabel_entry.bind("<FocusOut>", lambda e: self._replot())

        ttk.Separator(rt, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=4)

        ttk.Label(rt, text="X range:", style="RangeStatus.TLabel").pack(
            side=tk.LEFT, padx=(2,2), pady=3)
        self._xmin_entry = _entry(rt, self._xmin_var)
        self._xmin_entry.pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Label(rt, text="~", style="RangeStatus.TLabel").pack(side=tk.LEFT)
        self._xmax_entry = _entry(rt, self._xmax_var)
        self._xmax_entry.pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Button(rt, text="Apply", style="Range.TButton",
                   command=self._apply_xrange).pack(side=tk.LEFT, padx=2)
        ttk.Button(rt, text="Auto",  style="Range.TButton",
                   command=self._auto_xrange).pack(side=tk.LEFT, padx=2)
        for e in (self._xmin_entry, self._xmax_entry):
            e.bind("<Return>", lambda ev: self._apply_xrange())

        ttk.Separator(rt, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        # ── Y ──────────────────────────────────────────────────────
        ttk.Label(rt, text="Y label:", style="RangeStatus.TLabel").pack(
            side=tk.LEFT, padx=(2,2), pady=3)
        self._ylabel_active_var = tk.StringVar(value="[V]")
        self._ylabel_entry = _entry(rt, self._ylabel_active_var, w=10)
        self._ylabel_entry.pack(side=tk.LEFT, padx=2, pady=3)
        self._ylabel_entry.bind("<Return>",   lambda e: self._apply_ylabel())
        self._ylabel_entry.bind("<FocusOut>", lambda e: self._apply_ylabel())

        ttk.Separator(rt, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=4, pady=4)

        ttk.Label(rt, text="Y range:", style="RangeStatus.TLabel").pack(
            side=tk.LEFT, padx=(2,2), pady=3)
        self._ymin_entry = _entry(rt, self._ymin_var)
        self._ymin_entry.pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Label(rt, text="~", style="RangeStatus.TLabel").pack(side=tk.LEFT)
        self._ymax_entry = _entry(rt, self._ymax_var)
        self._ymax_entry.pack(side=tk.LEFT, padx=2, pady=3)
        ttk.Button(rt, text="Apply", style="Range.TButton",
                   command=self._apply_yrange).pack(side=tk.LEFT, padx=2)
        ttk.Button(rt, text="Auto",  style="Range.TButton",
                   command=self._auto_yrange).pack(side=tk.LEFT, padx=2)
        for e in (self._ymin_entry, self._ymax_entry):
            e.bind("<Return>", lambda ev: self._apply_yrange())

        # subplot indicator with prev/next
        ttk.Separator(rt, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=4)
        ttk.Button(rt, text="◄", style="Range.TButton",
                   command=self._prev_subplot).pack(side=tk.LEFT, padx=1)
        self._subplot_label = ttk.Label(rt, text="—", style="RangeStatus.TLabel",
                                        width=7, anchor="center")
        self._subplot_label.pack(side=tk.LEFT)
        ttk.Button(rt, text="►", style="Range.TButton",
                   command=self._next_subplot).pack(side=tk.LEFT, padx=1)

    # ── Signal panel ───────────────────────────────────────────────
    def _build_signal_panel(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", width=260)
        parent.add(panel, weight=0)

        ttk.Label(panel, text="SIGNALS", style="Title.TLabel").pack(
            fill=tk.X, padx=10, pady=(10,4))

        sig_cv = tk.Canvas(panel, bg=THEME["bg2"], highlightthickness=0, width=240)
        sig_sb = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=sig_cv.yview)
        self._signal_inner = ttk.Frame(sig_cv, style="Panel.TFrame")
        self._signal_inner.bind(
            "<Configure>",
            lambda e: sig_cv.configure(scrollregion=sig_cv.bbox("all")))
        sig_cv.create_window((0,0), window=self._signal_inner, anchor="nw")
        sig_cv.configure(yscrollcommand=sig_sb.set)
        sig_sb.pack(side=tk.RIGHT, fill=tk.Y)
        sig_cv.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5)
        sig_cv.bind("<Enter>", lambda e: sig_cv.bind_all(
            "<MouseWheel>",
            lambda ev: sig_cv.yview_scroll(-1*(ev.delta//120),"units")))
        sig_cv.bind("<Leave>", lambda e: sig_cv.unbind_all("<MouseWheel>"))

        # Measurements
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(panel, text="MEASUREMENTS", style="Title.TLabel").pack(
            fill=tk.X, padx=10, pady=(4,4))
        mf = ttk.Frame(panel, style="Panel.TFrame")
        mf.pack(fill=tk.X, padx=10)
        self._measure_labels: dict[str, ttk.Label] = {}
        for key in ["Signal","Min","Max","Vpp","RMS","Freq","Mean"]:
            row = ttk.Frame(mf, style="Panel.TFrame"); row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"{key}:", style="PanelDim.TLabel",
                      width=8).pack(side=tk.LEFT)
            lbl = ttk.Label(row, text="--", style="Measure.TLabel")
            lbl.pack(side=tk.LEFT, padx=4)
            self._measure_labels[key] = lbl

        # Style
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(panel, text="STYLE", style="Title.TLabel").pack(
            fill=tk.X, padx=10, pady=(4,4))
        sf = ttk.Frame(panel, style="Panel.TFrame")
        sf.pack(fill=tk.X, padx=10, pady=(0,6))

        r1 = ttk.Frame(sf, style="Panel.TFrame"); r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Font size:", style="PanelDim.TLabel", width=10).pack(side=tk.LEFT)
        self._fs_lbl = ttk.Label(r1, text="10", style="Measure.TLabel", width=3)
        self._fs_lbl.pack(side=tk.RIGHT)
        tk.Scale(r1, from_=7, to=20, orient=tk.HORIZONTAL,
                 variable=self._font_size, showvalue=False,
                 bg=THEME["bg2"], fg=THEME["fg"], troughcolor=THEME["border"],
                 highlightthickness=0, relief="flat",
                 command=lambda v: (self._fs_lbl.configure(text=str(int(float(v)))),
                                    self._replot())
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        r2 = ttk.Frame(sf, style="Panel.TFrame"); r2.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(r2, text="Bold font", variable=self._font_bold,
                        command=self._replot, style="TCheckbutton").pack(side=tk.LEFT)

        r3 = ttk.Frame(sf, style="Panel.TFrame"); r3.pack(fill=tk.X, pady=2)
        ttk.Label(r3, text="Line width:", style="PanelDim.TLabel", width=10).pack(side=tk.LEFT)
        self._lw_lbl = ttk.Label(r3, text="1.5", style="Measure.TLabel", width=4)
        self._lw_lbl.pack(side=tk.RIGHT)
        tk.Scale(r3, from_=0.5, to=6.0, resolution=0.5, orient=tk.HORIZONTAL,
                 variable=self._line_width, showvalue=False,
                 bg=THEME["bg2"], fg=THEME["fg"], troughcolor=THEME["border"],
                 highlightthickness=0, relief="flat",
                 command=lambda v: (self._lw_lbl.configure(text=f"{float(v):.1f}"),
                                    self._replot())
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        r4 = ttk.Frame(sf, style="Panel.TFrame"); r4.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(r4, text="Vary line styles (B&W)",
                        variable=self._use_lstyles,
                        command=self._replot, style="TCheckbutton").pack(side=tk.LEFT)

    # ── Plot area ──────────────────────────────────────────────────
    def _build_plot_area(self, parent):
        pf = ttk.Frame(parent)
        parent.add(pf, weight=1)
        self.fig = Figure(facecolor="white", dpi=100)
        self.fig.subplots_adjust(left=0.09, right=0.97, top=0.96,
                                  bottom=0.08, hspace=0.30)
        self.canvas = FigureCanvasTkAgg(self.fig, master=pf)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._hidden_tb_frame = ttk.Frame(pf)
        self.nav_toolbar = NavigationToolbar2Tk(self.canvas, self._hidden_tb_frame)
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.canvas.mpl_connect("button_press_event", self._on_click)

    def _build_status_bar(self):
        sb = ttk.Frame(self, style="Toolbar.TFrame")
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_label = ttk.Label(sb, text="Ready", style="Status.TLabel")
        self._status_label.pack(side=tk.LEFT, padx=10, pady=3)
        self._cursor_label = ttk.Label(sb, text="", style="Status.TLabel")
        self._cursor_label.pack(side=tk.RIGHT, padx=10, pady=3)

    # ── File operations ────────────────────────────────────────────
    def _open_file(self):
        fp = filedialog.askopenfilename(
            title="Open Waveform File",
            filetypes=[("All Supported","*.csv *.vcsv *.psf *.txt *.dat *.tsv"),
                       ("CSV","*.csv"),("VCSV","*.vcsv"),("PSF","*.psf"),
                       ("Text","*.txt *.dat *.tsv"),("All","*.*")],
        )
        if not fp: return
        try:
            self.data = load_file(fp)
        except Exception as e:
            messagebox.showerror("Parse Error", str(e)); return
        self._file_label.configure(text=f"  {Path(fp).name}")
        self.title(f"VPlot — {Path(fp).name}")
        self._assign_default_groups()
        self._init_axis_label_vars()
        self._populate_signals()
        self._replot()
        if fp not in self.recent_files:
            self.recent_files = ([fp] + self.recent_files)[:10]

    def _export(self, fmt: str):
        if not self.data:
            messagebox.showwarning("No Data", "Load a file first."); return
        ext = f".{fmt}"
        fp = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[(fmt.upper(), f"*{ext}"),("All","*.*")],
            initialfile=f"waveform{ext}",
        )
        if not fp: return
        kw: dict = dict(facecolor="white", edgecolor="none", bbox_inches="tight")
        if fmt == "png": kw["dpi"] = 300
        self.fig.savefig(fp, **kw)
        self._status_label.configure(text=f"Exported: {Path(fp).name}")

    # ── Group / subplot management ─────────────────────────────────
    def _assign_default_groups(self):
        """Group signals by unit (like initial Virtuoso layout)."""
        if not self.data: return
        unit_to_gid: dict[str, int] = {}
        self._signal_group.clear()
        gid = 0
        for name in self.data.signals:
            unit = self.data.signal_units.get(name, "")
            if unit not in unit_to_gid:
                unit_to_gid[unit] = gid; gid += 1
            self._signal_group[name] = unit_to_gid[unit]
        self._next_gid = gid

    def _split_signal(self, name: str):
        """Give the signal its own subplot (Virtuoso 'New Subwindow')."""
        new_gid = self._next_gid
        self._signal_group[name] = new_gid
        self._next_gid += 1
        # create a proper ylabel var for the new group
        if self.data:
            unit = self.data.signal_units.get(name, "")
            lbl = f"[{unit}]" if unit else "Value"
            self._ylabel_vars[new_gid] = tk.StringVar(value=lbl)
        self._replot()

    def _merge_signal(self, name: str, target_gid: int):
        """Move a signal into an existing group."""
        self._signal_group[name] = target_gid
        self._replot()

    def _reset_groups(self):
        self._assign_default_groups()
        self._replot()

    def _delete_signal(self, name: str):
        """Remove a signal from the view (Virtuoso-style delete)."""
        if name in self.checked_signals:
            self.checked_signals[name].set(False)
        # remove from data so it doesn't show in the panel
        if name in self.checked_signals:
            del self.checked_signals[name]
        if name in self._signal_group:
            del self._signal_group[name]
        if name in self.signal_color_map:
            del self.signal_color_map[name]
        if name in self.signal_style_map:
            del self.signal_style_map[name]
        if name in self._label_vars:
            del self._label_vars[name]
        # rebuild signal panel and replot
        self._populate_signals_keep()
        self._replot()

    def _populate_signals_keep(self):
        """Rebuild signal panel keeping only the signals still in checked_signals."""
        for w in self._signal_inner.winfo_children():
            w.destroy()
        if not self.data:
            return

        by_group: dict[int, list[str]] = defaultdict(list)
        for name in self.data.signals:
            if name in self.checked_signals or name in self._signal_group:
                by_group[self._signal_group.get(name, 0)].append(name)

        ci = 0
        for gid in sorted(by_group):
            names = by_group[gid]
            if not names:
                continue
            unit = self.data.signal_units.get(names[0], "")
            header = f"── Subplot {gid+1}  [{unit}]" if unit else f"── Subplot {gid+1}"
            ttk.Label(self._signal_inner, text=header,
                      style="PanelDim.TLabel").pack(
                fill=tk.X, pady=(8, 2), padx=6)
            for name in names:
                if name not in self._signal_group:
                    continue
                color = self.signal_color_map.get(
                    name, SIGNAL_COLORS[ci % len(SIGNAL_COLORS)])
                self._make_signal_row(name, color)
                ci += 1

        ttk.Label(self._signal_inner,
                  text="  ✎ Double-click label to edit\n  ⊞ Right-click to split/merge",
                  style="PanelDim.TLabel",
                  font=("Segoe UI", 8, "italic")).pack(pady=(6, 2), padx=6)

    # ── Axis label vars ────────────────────────────────────────────
    def _init_axis_label_vars(self):
        if not self.data: return
        # X label
        xu = self.data.x_unit
        xl = self.data.x_label
        self._xlabel_var.set(f"{xl} [{xu}]")
        # Y labels per group (default: unit)
        gid_to_unit: dict[int, str] = {}
        for name, gid in self._signal_group.items():
            if gid not in gid_to_unit:
                gid_to_unit[gid] = self.data.signal_units.get(name, "")
        self._ylabel_vars = {}
        for gid, unit in gid_to_unit.items():
            lbl = f"[{unit}]" if unit else "Value"
            self._ylabel_vars[gid] = tk.StringVar(value=lbl)
        # update range toolbar Y entry
        if 0 in self._ylabel_vars:
            self._ylabel_active_var.set(self._ylabel_vars[0].get())

    def _apply_ylabel(self):
        """Write the active Y label entry back to the active subplot's var."""
        if not self.axes or self._active_ax_idx >= len(self.axes): return
        new_lbl = self._ylabel_active_var.get()
        # find which gid corresponds to the active axis
        active_groups = self._active_groups()
        if self._active_ax_idx < len(active_groups):
            gid = active_groups[self._active_ax_idx]
            if gid in self._ylabel_vars:
                self._ylabel_vars[gid].set(new_lbl)
        self._replot()

    def _active_groups(self) -> list[int]:
        """Return sorted list of group ids that have at least one visible signal."""
        gids: set[int] = set()
        for name, var in self.checked_signals.items():
            if var.get():
                gids.add(self._signal_group.get(name, 0))
        return sorted(gids)

    # ── Populate signal panel ──────────────────────────────────────
    def _populate_signals(self):
        for w in self._signal_inner.winfo_children(): w.destroy()
        self.checked_signals.clear()
        self.signal_color_map.clear()
        self.signal_style_map.clear()
        self._label_vars.clear()
        if not self.data: return

        # Sort by group then name
        by_group: dict[int, list[str]] = defaultdict(list)
        for name in self.data.signals:
            by_group[self._signal_group.get(name, 0)].append(name)

        ci = 0
        for gid in sorted(by_group):
            unit = self.data.signal_units.get(by_group[gid][0], "")
            header = f"── Subplot {gid+1}  [{unit}]" if unit else f"── Subplot {gid+1}"
            ttk.Label(self._signal_inner, text=header,
                      style="PanelDim.TLabel").pack(
                fill=tk.X, pady=(8,2), padx=6)
            for name in by_group[gid]:
                color  = SIGNAL_COLORS[ci % len(SIGNAL_COLORS)]
                lstyle = LINE_STYLES[ci % len(LINE_STYLES)]
                self.signal_color_map[name] = color
                self.signal_style_map[name] = lstyle
                self._make_signal_row(name, color)
                ci += 1

        ttk.Label(self._signal_inner,
                  text="  ✎ Double-click label to edit\n  ⊞ Right-click to split/merge",
                  style="PanelDim.TLabel",
                  font=("Segoe UI",8,"italic")).pack(pady=(6,2), padx=6)

    def _make_signal_row(self, name: str, color: str):
        frame = ttk.Frame(self._signal_inner, style="Panel.TFrame")
        frame.pack(fill=tk.X, padx=6, pady=2)

        if name in self.checked_signals:
            var = self.checked_signals[name]
        else:
            var = tk.BooleanVar(value=True)
            self.checked_signals[name] = var
        ttk.Checkbutton(frame, variable=var, command=self._replot,
                        style="TCheckbutton").pack(side=tk.LEFT)

        swatch = tk.Canvas(frame, width=22, height=14,
                           bg=THEME["bg2"], highlightthickness=0)
        swatch.pack(side=tk.LEFT, padx=(2,5))
        swatch.create_line(1, 7, 21, 7, fill=color, width=2)

        if name in self._label_vars:
            sv = self._label_vars[name]
        else:
            display = self.data.signal_labels.get(name, name) if self.data else name
            sv = tk.StringVar(value=display)
            self._label_vars[name] = sv

        lbl = tk.Label(frame, textvariable=sv, fg=color, bg=THEME["bg2"],
                       font=("Consolas",9), cursor="hand2", anchor="w")
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        lbl.bind("<Button-1>",
                 lambda e, n=name: self._select_measure_signal(n))
        lbl.bind("<Double-Button-1>",
                 lambda e, n=name, f=frame, l=lbl, s=sv:
                 self._start_edit_label(n, f, l, s))
        lbl.bind("<Button-3>",
                 lambda e, n=name: self._show_signal_ctx_menu(e, n))
        frame.bind("<Button-3>",
                   lambda e, n=name: self._show_signal_ctx_menu(e, n))

    def _start_edit_label(self, name, frame, lbl_widget, sv: tk.StringVar):
        lbl_widget.pack_forget()
        entry = tk.Entry(frame, textvariable=sv, bg="white", fg=THEME["fg"],
                         font=("Consolas",9), relief="solid", bd=1,
                         insertbackground=THEME["fg"], width=18)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.focus_set(); entry.select_range(0, tk.END)

        def _commit(ev=None):
            if not sv.get().strip(): sv.set(name)
            if self.data: self.data.signal_labels[name] = sv.get()
            entry.pack_forget()
            lbl_widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._replot()
        def _cancel(ev=None):
            entry.pack_forget()
            lbl_widget.pack(side=tk.LEFT, fill=tk.X, expand=True)

        entry.bind("<Return>", _commit)
        entry.bind("<FocusOut>", _commit)
        entry.bind("<Escape>", _cancel)

    # ── Context menu for split / merge ─────────────────────────────
    def _show_signal_ctx_menu(self, event, name: str):
        if not self.data: return
        menu = tk.Menu(self, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"],
                       activebackground=THEME["accent"], activeforeground="white")
        menu.add_command(
            label="⊞  Split to own subplot",
            command=lambda: self._split_signal(name))

        # build per-group merge options
        by_group: dict[int, list[str]] = defaultdict(list)
        for n, g in self._signal_group.items():
            if n in self.data.signals:
                by_group[g].append(n)

        cur_gid = self._signal_group.get(name, 0)
        for gid in sorted(by_group):
            if gid == cur_gid: continue
            members = by_group[gid]
            preview = ", ".join(
                self._label_vars[m].get() if m in self._label_vars else m
                for m in members[:2])
            if len(members) > 2: preview += f" +{len(members)-2}"
            menu.add_command(
                label=f"⊟  Merge into: {preview}",
                command=lambda g=gid: self._merge_signal(name, g))

        menu.add_separator()
        menu.add_command(label="✕  Delete this signal",
                         command=lambda: self._delete_signal(name))
        menu.add_separator()
        menu.add_command(label="↺  Reset all subplots",
                         command=self._reset_groups)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _select_all(self):
        for v in self.checked_signals.values(): v.set(True)
        self._replot()

    def _deselect_all(self):
        for v in self.checked_signals.values(): v.set(False)
        self._replot()

    def _select_measure_signal(self, name: str):
        self.selected_measure_signal = name
        self._update_measurements()

    # ── Plotting ───────────────────────────────────────────────────
    def _replot(self):
        if not self.data: return

        # ── Save current view limits so style changes don't reset zoom ──
        _saved_xlim = self.axes[0].get_xlim() if self.axes else None
        _saved_ylims: dict[int, tuple] = {}
        if self.axes:
            old_active = self._active_groups()
            for i, gid in enumerate(old_active):
                if i < len(self.axes):
                    _saved_ylims[gid] = self.axes[i].get_ylim()

        self.fig.clear()
        self.axes.clear()
        self.cursor_markers.clear()
        self.crosshair_lines.clear()
        self._y_base_units: dict[int, str] = {}

        # group checked signals by their assigned group id
        active_groups: dict[int, list[str]] = defaultdict(list)
        for name, var in self.checked_signals.items():
            if var.get():
                active_groups[self._signal_group.get(name,0)].append(name)
        if not active_groups:
            self.canvas.draw_idle(); return

        fsize  = self._font_size.get()
        fwt    = "bold" if self._font_bold.get() else "normal"
        lwidth = self._line_width.get()
        use_ls = self._use_lstyles.get()
        sorted_gids = sorted(active_groups.keys())
        n = len(sorted_gids)

        for idx, gid in enumerate(sorted_gids):
            ax = (self.fig.add_subplot(n,1,idx+1) if idx == 0
                  else self.fig.add_subplot(n,1,idx+1, sharex=self.axes[0]))

            ax.set_facecolor("white")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            for sp in ("left","bottom"):
                ax.spines[sp].set_color("#444444")
                ax.spines[sp].set_linewidth(0.8)
            ax.tick_params(axis="both", colors="#333333", labelsize=fsize-1,
                           direction="in", length=4, width=0.7)

            if self._show_grid:
                ax.grid(True, color=THEME["grid"], linewidth=0.5,
                        linestyle="--", alpha=0.8, zorder=0)
                ax.set_axisbelow(True)

            for name in active_groups[gid]:
                color  = self.signal_color_map.get(name, SIGNAL_COLORS[0])
                ls     = self.signal_style_map.get(name,"-") if use_ls else "-"
                x, y   = self.data.x_data, self.data.signals[name]
                ml     = min(len(x), len(y))
                dlabel = (self._label_vars[name].get()
                          if name in self._label_vars
                          else get_label(self.data, name))
                ax.plot(x[:ml], y[:ml], color=color, linewidth=lwidth,
                        linestyle=ls, label=dlabel, antialiased=True, zorder=2)

            # Y axis: unified SI scale — ticks show plain numbers, prefix in label
            base_unit = self.data.signal_units.get(
                active_groups[gid][0], "") if active_groups[gid] else ""
            self._y_base_units[gid] = base_unit
            ymin, ymax = ax.get_ylim()
            y_scale, y_prefix = _best_si(ymin, ymax)
            ax.yaxis.set_major_formatter(SIAxisFormatter(y_scale))
            ylabel_text = f"[{y_prefix}{base_unit}]" if base_unit else "Value"
            if gid in self._ylabel_vars:
                self._ylabel_vars[gid].set(ylabel_text)
            ax.set_ylabel(ylabel_text, fontsize=fsize, fontweight=fwt,
                          color="#222222", labelpad=6)

            if self._show_legend and active_groups[gid]:
                leg = ax.legend(loc="upper right", fontsize=fsize, frameon=True,
                                framealpha=0.92, facecolor="white",
                                edgecolor="#AAAAAA", handlelength=2.2,
                                handleheight=1.0, handletextpad=0.5,
                                borderpad=0.5, labelspacing=0.35)
                for txt in leg.get_texts():
                    txt.set_color("#1A1A1A"); txt.set_fontweight(fwt)
                leg.get_frame().set_linewidth(0.6)
                for h in leg.legend_handles:
                    try: h.set_linewidth(max(lwidth, 2.0))
                    except AttributeError: pass

            # Show X tick labels on every subplot (IEEE multi-panel style)
            ax.tick_params(labelbottom=True)
            self.axes.append(ax)

        # X axis: unified SI scale — ticks show plain numbers, prefix in label
        if self.axes:
            xmin, xmax = self.axes[0].get_xlim()
            x_scale, x_prefix = _best_si(xmin, xmax)
            x_fmt = SIAxisFormatter(x_scale)
            for ax in self.axes:
                ax.xaxis.set_major_formatter(SIAxisFormatter(x_scale))
            xlabel = f"{self.data.x_label} [{x_prefix}{self.data.x_unit}]"
            self._xlabel_var.set(xlabel)
            self.axes[-1].set_xlabel(xlabel, fontsize=fsize, fontweight=fwt,
                                     color="#222222", labelpad=6)

        # ── Restore saved view limits ──
        if _saved_xlim and self.axes:
            self._range_updating = True
            for ax in self.axes:
                ax.set_xlim(_saved_xlim)
            new_active = self._active_groups()
            for i, gid in enumerate(new_active):
                if gid in _saved_ylims and i < len(self.axes):
                    self.axes[i].set_ylim(_saved_ylims[gid])
            self._range_updating = False

        # connect xlim_changed to update range toolbar
        if self.axes:
            self.axes[0].callbacks.connect(
                "xlim_changed", self._on_xlim_changed)
            for ax in self.axes:
                ax.callbacks.connect("ylim_changed", self._on_ylim_changed)

        self.canvas.draw_idle()
        self._update_range_display()
        self._update_measurements()
        self._update_subplot_indicator()

    # ── Range toolbar logic ────────────────────────────────────────
    def _on_xlim_changed(self, ax):
        if not self._range_updating:
            self._range_updating = True
            xmin, xmax = ax.get_xlim()
            self._xmin_var.set(_si_range_str(xmin))
            self._xmax_var.set(_si_range_str(xmax))
            # Update X SI prefix / label dynamically on zoom
            self._refresh_x_si()
            self._range_updating = False

    def _on_ylim_changed(self, ax):
        if not self._range_updating:
            if ax in self.axes:
                idx = self.axes.index(ax)
                self._refresh_y_si(idx)
                if idx == self._active_ax_idx:
                    self._update_yrange_display()

    def _update_range_display(self):
        if not self.axes: return
        xmin, xmax = self.axes[0].get_xlim()
        self._xmin_var.set(_si_range_str(xmin))
        self._xmax_var.set(_si_range_str(xmax))
        self._update_yrange_display()

    def _update_yrange_display(self):
        if not self.axes or self._active_ax_idx >= len(self.axes): return
        ax = self.axes[self._active_ax_idx]
        ymin, ymax = ax.get_ylim()
        self._ymin_var.set(_si_range_str(ymin))
        self._ymax_var.set(_si_range_str(ymax))
        # sync Y label entry
        active_gids = self._active_groups()
        if self._active_ax_idx < len(active_gids):
            gid = active_gids[self._active_ax_idx]
            if gid in self._ylabel_vars:
                self._ylabel_active_var.set(self._ylabel_vars[gid].get())

    def _refresh_x_si(self):
        """Recompute SI prefix for X axis after zoom and update label."""
        if not self.axes or not self.data:
            return
        xmin, xmax = self.axes[0].get_xlim()
        scale, prefix = _best_si(xmin, xmax)
        for ax in self.axes:
            ax.xaxis.set_major_formatter(SIAxisFormatter(scale))
        xlabel = f"{self.data.x_label} [{prefix}{self.data.x_unit}]"
        self._xlabel_var.set(xlabel)
        fsize = self._font_size.get()
        fwt = "bold" if self._font_bold.get() else "normal"
        self.axes[-1].set_xlabel(xlabel, fontsize=fsize, fontweight=fwt,
                                  color="#222222", labelpad=6)

    def _refresh_y_si(self, ax_idx):
        """Recompute SI prefix for Y axis *ax_idx* after zoom and update label."""
        if not self.axes or ax_idx >= len(self.axes) or not self.data:
            return
        ax = self.axes[ax_idx]
        ymin, ymax = ax.get_ylim()
        scale, prefix = _best_si(ymin, ymax)
        ax.yaxis.set_major_formatter(SIAxisFormatter(scale))
        active_gids = self._active_groups()
        if ax_idx < len(active_gids):
            gid = active_gids[ax_idx]
            base_unit = self._y_base_units.get(gid, "")
            ylabel = f"[{prefix}{base_unit}]" if base_unit else "Value"
            if gid in self._ylabel_vars:
                self._ylabel_vars[gid].set(ylabel)
            fsize = self._font_size.get()
            fwt = "bold" if self._font_bold.get() else "normal"
            ax.set_ylabel(ylabel, fontsize=fsize, fontweight=fwt,
                          color="#222222", labelpad=6)

    def _push_view(self):
        """Save current view to matplotlib's nav stack so Back/Fwd work."""
        if hasattr(self, "nav_toolbar"):
            self.nav_toolbar.push_current()

    def _apply_xrange(self):
        if not self.axes: return
        try:
            xmin = _parse_float(self._xmin_var.get())
            xmax = _parse_float(self._xmax_var.get())
            if xmin >= xmax: raise ValueError
        except (ValueError, TypeError):
            self._status_label.configure(text="Invalid X range")
            return
        self._range_updating = True
        for ax in self.axes:
            ax.set_xlim(xmin, xmax)
        self._push_view()
        self.canvas.draw_idle()
        self._range_updating = False

    def _apply_yrange(self):
        if not self.axes or self._active_ax_idx >= len(self.axes): return
        try:
            ymin = _parse_float(self._ymin_var.get())
            ymax = _parse_float(self._ymax_var.get())
            if ymin >= ymax: raise ValueError
        except (ValueError, TypeError):
            self._status_label.configure(text="Invalid Y range")
            return
        self._range_updating = True
        self.axes[self._active_ax_idx].set_ylim(ymin, ymax)
        self._push_view()
        self.canvas.draw_idle()
        self._range_updating = False

    def _auto_xrange(self):
        if not self.axes: return
        self.axes[0].autoscale(axis="x")
        self._push_view()
        self.canvas.draw_idle()

    def _auto_yrange(self):
        if not self.axes or self._active_ax_idx >= len(self.axes): return
        self.axes[self._active_ax_idx].autoscale(axis="y")
        self._push_view()
        self.canvas.draw_idle()

    def _prev_subplot(self):
        if self.axes:
            self._active_ax_idx = (self._active_ax_idx - 1) % len(self.axes)
            self._update_yrange_display()
            self._update_subplot_indicator()

    def _next_subplot(self):
        if self.axes:
            self._active_ax_idx = (self._active_ax_idx + 1) % len(self.axes)
            self._update_yrange_display()
            self._update_subplot_indicator()

    def _update_subplot_indicator(self):
        if self.axes:
            self._subplot_label.configure(
                text=f"sub {self._active_ax_idx+1}/{len(self.axes)}")
        else:
            self._subplot_label.configure(text="—")

    # ── Navigation ─────────────────────────────────────────────────
    def _toggle_grid(self):
        self._show_grid = not self._show_grid; self._replot()
    def _toggle_legend(self):
        self._show_legend = not self._show_legend; self._replot()
    def _auto_scale(self):
        for ax in self.axes: ax.autoscale()
        self._push_view()
        self.canvas.draw_idle()

    def _set_mode(self, mode: str):
        self.mode = mode
        for m, btn in self._mode_buttons.items():
            btn.configure(style="Active.Toolbar.TButton"
                          if m == mode else "Toolbar.TButton")
        if not hasattr(self, "nav_toolbar"): return
        tb_mode = getattr(self.nav_toolbar, "mode", "")
        if mode == "pan":
            self.nav_toolbar.pan()
        elif mode == "zoom":
            self.nav_toolbar.zoom()
        elif mode in ("navigate","cursor"):
            if tb_mode == "pan/zoom":   self.nav_toolbar.pan()
            elif tb_mode == "zoom rect": self.nav_toolbar.zoom()
        if hasattr(self,"_status_label"):
            self._status_label.configure(text=f"Mode: {mode.capitalize()}")

    def _nav_back(self):
        self.nav_toolbar.back()
        self._update_range_display()

    def _nav_forward(self):
        self.nav_toolbar.forward()
        self._update_range_display()

    # ── Mouse events ───────────────────────────────────────────────
    def _on_mouse_move(self, event):
        if not event.inaxes or not self.data:
            self._cursor_label.configure(text=""); return
        # track active subplot
        if event.inaxes in self.axes:
            idx = self.axes.index(event.inaxes)
            if idx != self._active_ax_idx:
                self._active_ax_idx = idx
                self._update_yrange_display()
                self._update_subplot_indicator()
        xstr = si_format(event.xdata, self.data.x_unit) if event.xdata is not None else "--"
        ystr = f"{event.ydata:.5g}" if event.ydata is not None else "--"
        self._cursor_label.configure(text=f"x = {xstr}    y = {ystr}")
        if self.mode == "cursor":
            self._draw_crosshair(event)

    def _draw_crosshair(self, event):
        for ln in self.crosshair_lines:
            try: ln.remove()
            except ValueError: pass
        self.crosshair_lines.clear()
        for ax in self.axes:
            vl = ax.axvline(x=event.xdata, color="#888888",
                            linewidth=0.7, alpha=0.8, linestyle="--")
            hl = ax.axhline(y=event.ydata if event.inaxes==ax else 0,
                            color="#888888", linewidth=0.7, alpha=0.6,
                            linestyle="--")
            if event.inaxes != ax: hl.set_visible(False)
            self.crosshair_lines.extend([vl, hl])
        self.canvas.draw_idle()

    def _on_click(self, event):
        if self.mode != "cursor" or not event.inaxes or not self.data: return
        if event.button != 1: return
        if len(self.cursor_markers) >= 2:
            for m in self.cursor_markers:
                for art in m["artists"]:
                    try: art.remove()
                    except ValueError: pass
            self.cursor_markers.clear()
        marker = {"x":event.xdata,"y":event.ydata,"ax":event.inaxes,"artists":[]}
        for ax in self.axes:
            vl = ax.axvline(x=event.xdata, color=THEME["accent2"],
                            linewidth=1.0, linestyle="--", alpha=0.9)
            marker["artists"].append(vl)
        fsize = self._font_size.get()
        ann = event.inaxes.annotate(
            si_format(event.xdata, self.data.x_unit),
            xy=(event.xdata, event.ydata),
            xytext=(8,12), textcoords="offset points",
            fontsize=fsize, color=THEME["accent2"],
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=THEME["accent2"], alpha=0.9))
        marker["artists"].append(ann)
        self.cursor_markers.append(marker)
        if len(self.cursor_markers) == 2:
            dx = self.cursor_markers[1]["x"] - self.cursor_markers[0]["x"]
            dy = self.cursor_markers[1]["y"] - self.cursor_markers[0]["y"]
            freq = 1.0/abs(dx) if dx else float("inf")
            self._status_label.configure(
                text=(f"Δx={si_format(dx,self.data.x_unit)}   "
                      f"Δy={dy:.4g}   1/Δx={si_format(freq,'Hz')}"))
        self.canvas.draw_idle()

    # ── Measurements ───────────────────────────────────────────────
    def _update_measurements(self):
        if not self.data or not self.axes: return
        sig = getattr(self, "selected_measure_signal", None)
        if not sig or sig not in self.data.signals:
            checked = [n for n,v in self.checked_signals.items() if v.get()]
            sig = checked[0] if checked else None
        if not sig:
            for l in self._measure_labels.values(): l.configure(text="--")
            return
        y = self.data.signals[sig]; x = self.data.x_data
        ml = min(len(x),len(y)); x,y = x[:ml],y[:ml]
        if self.axes:
            xlim = self.axes[0].get_xlim()
            mask = (x>=xlim[0])&(x<=xlim[1])
            if np.any(mask): x,y = x[mask],y[mask]
        unit = self.data.signal_units.get(sig,"")
        y_min,y_max = np.nanmin(y),np.nanmax(y)
        y_rms = np.sqrt(np.nanmean(y**2))
        y_mean = np.nanmean(y)
        freq_str = "--"
        if len(y)>4:
            try:
                dx = np.mean(np.diff(x))
                if dx>0:
                    mag = np.abs(np.fft.rfft(y-y_mean))
                    if len(mag)>1:
                        freqs = np.fft.rfftfreq(len(y),d=dx)
                        peak = np.argmax(mag[1:])+1
                        freq_str = si_format(freqs[peak],"Hz")
            except Exception: pass
        dlbl = self._label_vars[sig].get() if sig in self._label_vars else sig
        self._measure_labels["Signal"].configure(text=dlbl)
        self._measure_labels["Min"].configure(text=si_format(y_min,unit))
        self._measure_labels["Max"].configure(text=si_format(y_max,unit))
        self._measure_labels["Vpp"].configure(text=si_format(y_max-y_min,unit))
        self._measure_labels["RMS"].configure(text=si_format(y_rms,unit))
        self._measure_labels["Mean"].configure(text=si_format(y_mean,unit))
        self._measure_labels["Freq"].configure(text=freq_str)

    def _on_close(self):
        plt.close("all"); self.destroy()


def main():
    app = WaveformViewer()
    app.mainloop()

if __name__ == "__main__":
    main()
