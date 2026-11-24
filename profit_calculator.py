#!/usr/bin/env python3
"""
Profit Calculator
=================
Quickly work out profit when buying, crafting and selling items.
Starts with one item; add up to 5 side by side.

Runs on Windows, macOS and Linux (CachyOS/Arch) using only Python's
built-in Tkinter - nothing to pip install.

How to run
----------
Windows : install Python 3 from python.org (Tcl/Tk is included), then
          double-click this file or run:  python profit_calculator.py
          (rename to profit_calculator.pyw to hide the console window)
macOS   : install Python 3 from python.org (Homebrew users: brew install python-tk)
          python3 profit_calculator.py
CachyOS : sudo pacman -S python tk
          python profit_calculator.py

Tips
----
* Numbers accept commas and shorthand: 500k = 500,000, 1.5m = 1,500,000, 2b = 2,000,000,000.
* Pick which side of the sale you control: type the sale price and see the profit,
  or type the profit you want and see the sale price you need to list at.
* Ctrl+Z / Ctrl+Y (Cmd+Z / Cmd+Shift+Z on Mac) undo and redo, Ctrl+S (Cmd+S) saves.
* Saved entries are loaded automatically next time the app starts.
"""

import copy
import json
import math
import os
import sys
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

__version__ = "1.0.0"   # single source of truth - keep in sync with CHANGELOG.md

APP_NAME = "Profit Calculator"
MAX_ITEMS = 5
MAX_MATERIALS = 5
TAX_CHOICES = ("3%", "5%")
BASE_CARD_W = 340
HISTORY_LIMIT = 300
COMMIT_DELAY_MS = 450
MAX_VALUE = 1e15

BG_OK = "#ffffff"
BG_RO = "#eceff1"
BG_BAD = "#ffd9d9"
GREEN = "#1a7f37"
RED = "#c62828"
AMBER = "#b45309"
MUTED = "#777777"

DEFAULT_STATE = {
    "nickname": "",
    "base": "",
    "scrolls": "",
    "scroll_price": "",
    "materials": [],          # list of {"cost": str, "qty": str}
    "tax": "3%",
    "mode": "price",          # "price" = you enter sale price, "profit" = you enter target profit
    "sale_price": "",
    "target_profit": "",
}


# --------------------------------------------------------------------------- #
# Pure helpers (no GUI)
# --------------------------------------------------------------------------- #
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_num(text, allow_negative=False):
    """Blank -> 0.0, invalid -> None. Understands commas and k / m / b suffixes."""
    t = str(text).strip().replace(",", "").replace(" ", "").replace("_", "")
    if not t:
        return 0.0
    mult = 1.0
    if t[-1].lower() in _SUFFIX:
        mult = _SUFFIX[t[-1].lower()]
        t = t[:-1]
    try:
        v = float(t) * mult
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v) or abs(v) > MAX_VALUE:
        return None
    if v < 0 and not allow_negative:
        return None
    return v


def fmt_num(v):
    if v is None or math.isnan(v) or math.isinf(v):
        return "—"
    if abs(v - round(v)) < 0.005:
        return f"{int(round(v)):,}"
    return f"{v:,.2f}"


def compute(d):
    """All the math for one item. `d` is an item state dict."""
    def num(key):
        v = parse_num(d.get(key, ""), True)
        return 0.0 if v is None else v

    base = num("base")
    scroll_total = num("scrolls") * num("scroll_price")
    mat_total = 0.0
    for m in d.get("materials", []):
        c = parse_num(m.get("cost", ""), True) or 0.0
        q = parse_num(m.get("qty", ""), True) or 0.0
        mat_total += c * q
    cost = base + scroll_total + mat_total
    rate = 0.05 if d.get("tax") == "5%" else 0.03

    if d.get("mode") == "profit":
        # sale * (1 - rate) - cost = target  ->  round UP so the target is always met
        sale = max(0, math.ceil((cost + num("target_profit")) / (1 - rate) - 1e-9))
    else:
        sale = num("sale_price")

    tax = sale * rate
    net = sale - tax
    profit = net - cost
    roi = (profit / cost * 100.0) if cost > 0 else None
    return {"base": base, "scroll_total": scroll_total, "mat_total": mat_total,
            "cost": cost, "rate": rate, "sale": sale, "tax": tax, "net": net,
            "profit": profit, "roi": roi}


def sanitize_item(d):
    """Make an item dict from untrusted data (e.g. a hand-edited save file)."""
    out = copy.deepcopy(DEFAULT_STATE)
    if not isinstance(d, dict):
        return out
    for k in ("nickname", "base", "scrolls", "scroll_price", "sale_price", "target_profit"):
        if isinstance(d.get(k), str):
            out[k] = d[k]
    if d.get("tax") in TAX_CHOICES:
        out["tax"] = d["tax"]
    if d.get("mode") in ("price", "profit"):
        out["mode"] = d["mode"]
    mats = []
    if isinstance(d.get("materials"), list):
        for m in d["materials"][:MAX_MATERIALS]:
            if isinstance(m, dict):
                c, q = m.get("cost"), m.get("qty")
                mats.append({"cost": c if isinstance(c, str) else "",
                             "qty": q if isinstance(q, str) else ""})
    out["materials"] = mats
    return out


def data_file():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "ProfitCalculator", "entries.json")


def default_app_state():
    return {"version": 1, "items": [copy.deepcopy(DEFAULT_STATE)]}


def _bumped(base_font, delta):
    f = base_font.copy()
    size = base_font.actual("size")
    f.configure(size=(size + delta) if size > 0 else (size - delta), weight="bold")
    return f


# --------------------------------------------------------------------------- #
# One item calculator
# --------------------------------------------------------------------------- #
class Card(ttk.Frame):
    def __init__(self, parent, app, index, state):
        super().__init__(parent, padding=(12, 10), relief="groove", borderwidth=2)
        self.app = app
        self.index = index
        self._updating = False
        self.entries = []        # (entry, var, kind) for fixed fields
        self.mat_entries = []    # same, for material rows (rebuilt often)
        self.mats = []           # list of (cost_var, qty_var)

        V = tk.StringVar
        self.nick, self.base, self.scrolls, self.sprice = V(), V(), V(), V()
        self.sale, self.target, self.total = V(), V(), V()
        self.tax, self.mode = V(value="3%"), V(value="price")
        for v in (self.nick, self.base, self.scrolls, self.sprice,
                  self.sale, self.target, self.tax, self.mode):
            v.trace_add("write", self._on_var)

        self._build()
        self.load_state(state)

    # ---- widgets ---------------------------------------------------------- #
    def _entry(self, parent, var, kind, width=14, store=None, bold=False):
        kw = {}
        if bold:
            kw["font"] = self.app.f_bold
        e = tk.Entry(parent, textvariable=var, width=width,
                     justify="left" if kind == "text" else "right",
                     relief="solid", bd=1, bg=BG_OK, fg="black",
                     readonlybackground=BG_RO, insertbackground="black",
                     disabledforeground="black", highlightthickness=1,
                     highlightbackground="#c8ccd0", highlightcolor="#3b82f6", **kw)
        if kind in ("cost", "signed"):
            e.bind("<FocusOut>", lambda ev, v=var, k=kind: self._reformat(v, k))
        (self.entries if store is None else store).append((e, var, kind))
        return e

    def _build(self):
        app = self.app
        self.columnconfigure(0, weight=1)

        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        self.title_lbl = ttk.Label(head, text="", font=app.f_title)
        self.title_lbl.grid(row=0, column=0, sticky="w")
        ttk.Button(head, text="Clear", width=7, command=self.clear).grid(row=0, column=1, padx=(6, 0))
        self.remove_btn = ttk.Button(head, text="Remove", width=8,
                                     command=lambda: self.app.remove_card(self))
        self.remove_btn.grid(row=0, column=2, padx=(4, 0))

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        body.columnconfigure(1, weight=1)
        r = 0

        def sep():
            nonlocal r
            ttk.Separator(body).grid(row=r, column=0, columnspan=2, sticky="ew", pady=8)
            r += 1

        def section(text):
            nonlocal r
            ttk.Label(body, text=text, style="Section.TLabel").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(0, 3))
            r += 1

        def field(text, var, kind, **kw):
            nonlocal r
            lbl = ttk.Label(body, text=text)
            lbl.grid(row=r, column=0, sticky="w", pady=2, padx=(0, 8))
            e = self._entry(body, var, kind, **kw)
            e.grid(row=r, column=1, sticky="ew", pady=2)
            r += 1
            return lbl, e

        def result(text, big=False):
            nonlocal r
            ttk.Label(body, text=text).grid(row=r, column=0, sticky="w", pady=1)
            lbl = ttk.Label(body, text="—", anchor="e", font=app.f_big if big else None)
            lbl.grid(row=r, column=1, sticky="e", pady=1)
            r += 1
            return lbl

        field("Nickname", self.nick, "text")
        sep()

        section("Costs")
        field("Base item price", self.base, "cost")
        field("Scrolls to use", self.scrolls, "cost")
        field("Scroll price (each)", self.sprice, "cost")

        self.mat_frame = ttk.Frame(body)
        self.mat_frame.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        r += 1

        ttk.Label(body, text="Total cost to create", font=app.f_bold).grid(
            row=r, column=0, sticky="w", pady=(6, 2), padx=(0, 8))
        total_e = self._entry(body, self.total, "ro", bold=True)
        total_e.config(state="readonly")
        total_e.grid(row=r, column=1, sticky="ew", pady=(6, 2))
        r += 1
        self.breakdown = ttk.Label(body, text="", style="Muted.TLabel", justify="left",
                                   wraplength=int(300 * app.scale))
        self.breakdown.grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        sep()

        section("Selling")
        ttk.Label(body, text="Tax rate").grid(row=r, column=0, sticky="w", pady=2)
        tax_f = ttk.Frame(body)
        tax_f.grid(row=r, column=1, sticky="e")
        for t in TAX_CHOICES:
            ttk.Radiobutton(tax_f, text=t, value=t, variable=self.tax).pack(side="left", padx=(8, 0))
        r += 1
        ttk.Label(body, text="I want to set:").grid(row=r, column=0, sticky="w", pady=(4, 0))
        mode_f = ttk.Frame(body)
        mode_f.grid(row=r, column=1, sticky="e", pady=(4, 0))
        ttk.Radiobutton(mode_f, text="Sale price", value="price", variable=self.mode).pack(side="left")
        ttk.Radiobutton(mode_f, text="Profit", value="profit", variable=self.mode).pack(side="left", padx=(8, 0))
        r += 1
        self.sale_lbl, self.sale_entry = field("Preferred sale price", self.sale, "cost")
        self.target_lbl, self.target_entry = field("Preferred profit", self.target, "signed")
        sep()

        section("Results")
        self.tax_lbl = result("Tax paid")
        self.net_lbl = result("You receive after tax")
        self.profit_lbl = result("Profit", big=True)
        self.roi_lbl = result("Return on cost")

    def _rebuild_mats(self, focus_last=False):
        f = self.mat_frame
        for w in f.winfo_children():
            w.destroy()
        self.mat_entries = []
        f.columnconfigure(1, weight=1)
        r = 0
        if self.mats:
            ttk.Label(f, text="Cost (each)", style="Muted.TLabel").grid(row=0, column=1, sticky="e")
            ttk.Label(f, text="Qty needed", style="Muted.TLabel").grid(row=0, column=3, sticky="e")
            r = 1
        for i, (cv, qv) in enumerate(self.mats):
            ttk.Label(f, text=f"Material {i + 1}").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
            ce = self._entry(f, cv, "cost", width=12, store=self.mat_entries)
            ce.grid(row=r, column=1, sticky="ew", pady=2)
            ttk.Label(f, text="×").grid(row=r, column=2, padx=4)
            qe = self._entry(f, qv, "cost", width=7, store=self.mat_entries)
            qe.grid(row=r, column=3, pady=2)
            ttk.Button(f, text="×", width=2,
                       command=lambda i=i: self.remove_material(i)).grid(row=r, column=4, padx=(6, 0))
            r += 1
        n = len(self.mats)
        btn = ttk.Button(f, text=f"+ Add material ({n}/{MAX_MATERIALS})", command=self.add_material)
        if n >= MAX_MATERIALS:
            btn.state(["disabled"])
        btn.grid(row=r, column=0, columnspan=5, sticky="w", pady=(4, 0))
        if focus_last and self.mat_entries:
            self.mat_entries[-2][0].focus_set()

    # ---- state ------------------------------------------------------------ #
    def get_state(self):
        return {
            "nickname": self.nick.get(),
            "base": self.base.get(),
            "scrolls": self.scrolls.get(),
            "scroll_price": self.sprice.get(),
            "materials": [{"cost": c.get(), "qty": q.get()} for c, q in self.mats],
            "tax": self.tax.get(),
            "mode": self.mode.get(),
            "sale_price": self.sale.get(),
            "target_profit": self.target.get(),
        }

    def load_state(self, d):
        d = sanitize_item(d)
        self._updating = True
        try:
            self.nick.set(d["nickname"])
            self.base.set(d["base"])
            self.scrolls.set(d["scrolls"])
            self.sprice.set(d["scroll_price"])
            self.sale.set(d["sale_price"])
            self.target.set(d["target_profit"])
            self.tax.set(d["tax"])
            self.mode.set(d["mode"])
            self.mats = []
            for m in d["materials"]:
                self._add_mat_vars(m["cost"], m["qty"])
        finally:
            self._updating = False
        self._rebuild_mats()
        self.recalc()

    def has_data(self):
        if any(v.get().strip() for v in (self.nick, self.base, self.scrolls, self.sprice)):
            return True
        if any(c.get().strip() for c, _ in self.mats):
            return True
        return bool((self.target if self.mode.get() == "profit" else self.sale).get().strip())

    def display_name(self):
        return self.nick.get().strip() or f"Item {self.index + 1}"

    def set_index(self, i, removable):
        self.index = i
        if removable:
            self.remove_btn.grid()
        else:
            self.remove_btn.grid_remove()
        self._update_title()

    def _update_title(self):
        nick = self.nick.get().strip()
        if len(nick) > 26:
            nick = nick[:25] + "…"
        self.title_lbl.config(text=f"Item {self.index + 1}" + (f" — {nick}" if nick else ""))

    # ---- events ----------------------------------------------------------- #
    def _on_var(self, *_):
        if self._updating or self.app.suspend:
            return
        self.recalc()
        self.app.changed()

    def _add_mat_vars(self, cost, qty):
        cv, qv = tk.StringVar(value=cost), tk.StringVar(value=qty)
        cv.trace_add("write", self._on_var)
        qv.trace_add("write", self._on_var)
        self.mats.append((cv, qv))

    def _reformat(self, var, kind):
        if self.app.suspend:
            return
        t = var.get().strip()
        if not t:
            return
        v = parse_num(t, allow_negative=(kind == "signed"))
        if v is None:
            return
        f = fmt_num(v)
        if f != var.get():
            var.set(f)

    def add_material(self):
        if len(self.mats) >= MAX_MATERIALS:
            return
        self.app.commit_now()
        self._add_mat_vars("", "1")
        self._rebuild_mats(focus_last=True)
        self.recalc()
        self.app.commit_now()

    def remove_material(self, i):
        self.app.commit_now()
        del self.mats[i]
        self._rebuild_mats()
        self.recalc()
        self.app.commit_now()

    def clear(self):
        ok = messagebox.askyesno(
            "Clear item",
            f"Reset “{self.display_name()}” and clear all of its entries?\n\n"
            "You can bring them back with Undo.",
            icon="warning", default="no", parent=self.winfo_toplevel())
        if not ok:
            return
        self.app.commit_now()
        self.load_state(copy.deepcopy(DEFAULT_STATE))
        self.app.commit_now()

    # ---- calculation ------------------------------------------------------ #
    def _validate(self):
        bad = False
        for e, var, kind in self.entries + self.mat_entries:
            if kind == "text":
                continue
            if str(e.cget("state")) == "readonly":
                e.config(bg=BG_RO)
                continue
            ok = parse_num(var.get(), kind == "signed") is not None
            e.config(bg=BG_OK if ok else BG_BAD)
            bad = bad or not ok
        return bad

    def recalc(self):
        st = self.get_state()
        profit_mode = st["mode"] == "profit"
        self.sale_entry.config(state="readonly" if profit_mode else "normal")
        self.target_entry.config(state="normal" if profit_mode else "readonly")
        self.sale_lbl.config(text="Preferred sale price" + ("  (auto)" if profit_mode else ""))
        self.target_lbl.config(text="Preferred profit" + ("" if profit_mode else "  (auto)"))
        self._update_title()

        if self._validate():
            self.total.set("—")
            self.breakdown.config(text="")
            for lbl in (self.tax_lbl, self.net_lbl, self.roi_lbl):
                lbl.config(text="—")
            self.profit_lbl.config(text="Check red fields", foreground=RED)
            return

        r = compute(st)
        self._updating = True
        try:
            self.total.set(fmt_num(r["cost"]))
            if profit_mode:
                self.sale.set(fmt_num(r["sale"]))
            else:
                self.target.set(fmt_num(r["profit"]))
        finally:
            self._updating = False

        parts = []
        if r["base"]:
            parts.append(f"Base {fmt_num(r['base'])}")
        if r["scroll_total"]:
            parts.append(f"Scrolls {fmt_num(r['scroll_total'])}")
        if r["mat_total"]:
            parts.append(f"Materials {fmt_num(r['mat_total'])}")
        self.breakdown.config(text="  ·  ".join(parts))

        self.tax_lbl.config(text=fmt_num(r["tax"]))
        self.net_lbl.config(text=fmt_num(r["net"]))
        p = r["profit"]
        color = GREEN if p > 0.005 else RED if p < -0.005 else self.app.default_fg
        self.profit_lbl.config(text=("+" if p > 0.005 else "") + fmt_num(p), foreground=color)
        self.roi_lbl.config(text="—" if r["roi"] is None else f"{r['roi']:,.1f}%")


# --------------------------------------------------------------------------- #
# Application window
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, root):
        self.root = root
        self.mac = sys.platform == "darwin"
        self.mod = "Command" if self.mac else "Control"
        self.mod_name = "Cmd" if self.mac else "Ctrl"
        self.scale = 1.0 if self.mac else max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.cw = int(BASE_CARD_W * self.scale)
        self.suspend = False
        self.pending = None
        self.cards = []
        self.history = []
        self.hidx = -1
        self.saved_json = None
        self.saved_text = "No unsaved changes"
        self._cols = 0

        self._setup_style()
        self._build_toolbar()
        self._build_canvas()
        self._bind_keys()

        state = self._read_disk() or default_app_state()
        self._rebuild(state)
        snap = self._snap()
        self.history = [snap]
        self.hidx = 0
        self.saved_json = snap
        self._size_window()
        self._refresh()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.mac:
            try:
                root.createcommand("tk::mac::Quit", self.on_close)
            except tk.TclError:
                pass

    # ---- setup ------------------------------------------------------------ #
    def _setup_style(self):
        style = ttk.Style(self.root)
        if sys.platform.startswith("linux") and "clam" in style.theme_names():
            style.theme_use("clam")
        base = tkfont.nametofont("TkDefaultFont")
        self.f_bold = _bumped(base, 0)
        self.f_title = _bumped(base, 2)
        self.f_big = _bumped(base, 5)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Section.TLabel", font=self.f_bold)
        self.default_fg = style.lookup("TLabel", "foreground") or "black"
        self.canvas_bg = style.lookup("TFrame", "background") or self.root.cget("bg")

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(side="top", fill="x")
        self.add_btn = ttk.Button(bar, text="+ Add Item", command=self.add_card)
        self.add_btn.pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.undo_btn = ttk.Button(bar, text=f"Undo ({self.mod_name}+Z)", command=self.undo)
        self.undo_btn.pack(side="left")
        redo_key = "Shift+Z" if self.mac else "Y"
        self.redo_btn = ttk.Button(bar, text=f"Redo ({self.mod_name}+{redo_key})", command=self.redo)
        self.redo_btn.pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.save_btn = ttk.Button(bar, text=f"Save ({self.mod_name}+S)", command=self.save)
        self.save_btn.pack(side="left")
        self.status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.status.pack(side="right")
        ttk.Separator(self.root).pack(side="top", fill="x")

    def _build_canvas(self):
        wrap = ttk.Frame(self.root)
        wrap.pack(side="top", fill="both", expand=True)
        vs = ttk.Scrollbar(wrap, orient="vertical")
        vs.pack(side="right", fill="y")
        self.canvas = tk.Canvas(wrap, highlightthickness=0, bg=self.canvas_bg,
                                yscrollincrement=int(20 * self.scale), yscrollcommand=vs.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vs.config(command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, self._on_wheel)

    def _bind_keys(self):
        m = self.mod

        def bind(seq, fn):
            try:
                self.root.bind_all(seq, lambda e, fn=fn: (fn(), "break")[1])
            except tk.TclError:
                pass

        bind(f"<{m}-z>", self.undo)
        bind(f"<{m}-Z>", self.redo)
        bind(f"<{m}-Shift-Z>", self.redo)
        if not self.mac:
            bind("<Control-y>", self.redo)
        bind(f"<{m}-s>", self.save)

    def _size_window(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        cols = min(len(self.cards), 3)
        w = min(sw - 40, cols * self.cw + int(50 * self.scale))
        h = min(sh - 120, int(820 * self.scale))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(min(sw, self.cw + int(50 * self.scale)), int(420 * self.scale))

    def _fit_width(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        need = min(sw - 40, min(len(self.cards), 3) * self.cw + int(50 * self.scale))
        if self.root.winfo_width() < need:
            self.root.geometry(f"{need}x{self.root.winfo_height()}")

    # ---- layout ----------------------------------------------------------- #
    def _measure(self):
        self.root.update_idletasks()
        if self.cards:
            widest = max(c.winfo_reqwidth() for c in self.cards)
            self.cw = max(int(BASE_CARD_W * self.scale), widest + int(20 * self.scale))

    def _layout_cards(self, force=False):
        if not self.cards:
            return
        width = self.canvas.winfo_width()
        cols = max(1, min(len(self.cards), width // self.cw))
        if cols == self._cols and not force:
            return
        self._cols = cols
        for c in range(MAX_ITEMS):
            self.inner.grid_columnconfigure(c, weight=1 if c < cols else 0,
                                            uniform="cards" if c < cols else "")
        for i, card in enumerate(self.cards):
            card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="nsew")

    def _on_canvas_configure(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)
        self._layout_cards()

    def _on_wheel(self, e):
        if self.canvas.yview() == (0.0, 1.0):
            return
        if e.num == 4:
            step = -3
        elif e.num == 5:
            step = 3
        elif self.mac:
            step = -int(e.delta)
        else:
            step = -3 if e.delta > 0 else 3
        self.canvas.yview_scroll(step, "units")

    def _scroll_to(self, card):
        self.root.update_idletasks()
        total = max(self.inner.winfo_height(), 1)
        self.canvas.yview_moveto(max(0.0, (card.winfo_y() - 8) / total))

    def _renumber(self):
        removable = len(self.cards) > 1
        for i, c in enumerate(self.cards):
            c.set_index(i, removable)

    # ---- state / history -------------------------------------------------- #
    def get_state(self):
        return {"version": 1, "items": [c.get_state() for c in self.cards]}

    def _snap(self):
        return json.dumps(self.get_state(), sort_keys=True)

    def _rebuild(self, state):
        """Replace all cards with the ones described by `state`."""
        try:
            y = self.canvas.yview()[0]
        except tk.TclError:
            y = 0.0
        self.suspend = True
        try:
            for c in self.cards:
                c.destroy()
            self.cards = []
            items = state.get("items") if isinstance(state, dict) else None
            if not isinstance(items, list) or not items:
                items = [copy.deepcopy(DEFAULT_STATE)]
            for i, it in enumerate(items[:MAX_ITEMS]):
                self.cards.append(Card(self.inner, self, i, sanitize_item(it)))
            self._renumber()
            self._measure()
            self._layout_cards(force=True)
        finally:
            self.suspend = False
        self.root.update_idletasks()
        self.canvas.yview_moveto(y)

    def changed(self):
        """Called after any user edit; history is committed after a short pause."""
        if self.suspend:
            return
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(COMMIT_DELAY_MS, self.commit_now)
        self._refresh()

    def commit_now(self):
        if self.pending:
            try:
                self.root.after_cancel(self.pending)
            except tk.TclError:
                pass
            self.pending = None
        if self.suspend or not self.history:
            return
        snap = self._snap()
        if snap != self.history[self.hidx]:
            del self.history[self.hidx + 1:]
            self.history.append(snap)
            self.hidx += 1
            if len(self.history) > HISTORY_LIMIT:
                drop = len(self.history) - HISTORY_LIMIT
                del self.history[:drop]
                self.hidx -= drop
        self._refresh()

    def undo(self):
        self.commit_now()
        if self.hidx > 0:
            self.hidx -= 1
            self._rebuild(json.loads(self.history[self.hidx]))
            self._refresh()

    def redo(self):
        self.commit_now()
        if self.hidx < len(self.history) - 1:
            self.hidx += 1
            self._rebuild(json.loads(self.history[self.hidx]))
            self._refresh()

    def _refresh(self):
        dirty = self._snap() != self.saved_json
        can_undo = self.hidx > 0 or bool(self.pending)
        can_redo = self.hidx < len(self.history) - 1 and not self.pending
        self.undo_btn.state(["!disabled" if can_undo else "disabled"])
        self.redo_btn.state(["!disabled" if can_redo else "disabled"])
        n = len(self.cards)
        self.add_btn.config(text=f"+ Add Item ({n}/{MAX_ITEMS})")
        self.add_btn.state(["disabled" if n >= MAX_ITEMS else "!disabled"])
        if dirty:
            self.status.config(text="● Unsaved changes", foreground=AMBER)
        else:
            self.status.config(text=self.saved_text, foreground=MUTED)

    # ---- items ------------------------------------------------------------ #
    def add_card(self):
        if len(self.cards) >= MAX_ITEMS:
            return
        self.commit_now()
        card = Card(self.inner, self, len(self.cards), copy.deepcopy(DEFAULT_STATE))
        self.cards.append(card)
        self._renumber()
        self._measure()
        self._layout_cards(force=True)
        self.commit_now()
        self._fit_width()
        self.root.after(60, lambda: self._scroll_to(card))

    def remove_card(self, card):
        if len(self.cards) <= 1:
            return
        self.commit_now()
        if card.has_data():
            ok = messagebox.askyesno(
                "Remove item",
                f"Remove “{card.display_name()}” and its entries?\n\n"
                "You can bring it back with Undo.",
                icon="warning", default="no", parent=self.root)
            if not ok:
                return
        self.cards.remove(card)
        card.destroy()
        self._renumber()
        self._layout_cards(force=True)
        self.commit_now()

    # ---- save / load ------------------------------------------------------ #
    def _read_disk(self):
        try:
            with open(data_file(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
            return None
        self.saved_text = "Loaded saved entries"
        return data

    def save(self):
        self.commit_now()
        path = data_file()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.get_state(), f, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not save your entries:\n\n{exc}", parent=self.root)
            return False
        self.saved_json = self._snap()
        self.saved_text = "Saved at " + time.strftime("%I:%M %p").lstrip("0")
        self._refresh()
        return True

    def on_close(self):
        self.commit_now()
        if self._snap() != self.saved_json:
            ans = messagebox.askyesnocancel(
                APP_NAME, "You have unsaved changes. Save before closing?", parent=self.root)
            if ans is None:
                return
            if ans and not self.save():
                return
        self.root.destroy()


def main():
    if any(a in ("--version", "-V") for a in sys.argv[1:]):
        print(f"{APP_NAME} {__version__}")
        return
    if sys.platform.startswith("win"):
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    root = tk.Tk()
    root.title(f"{APP_NAME} v{__version__}")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
