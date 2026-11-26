#!/usr/bin/env python3
"""
Profit Calculator
=================
Quickly work out profit when buying, crafting and selling items.
Starts with one item; add up to 10.

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
* Pick what you want to type: the sale price (see the profit), the profit you want, or the
  profit % you want - the other two are worked out for you.
* The picture under the results shows how good the profit is (return on cost).
* Reorder items with the < > buttons or by dragging an item's title onto another item.
* Resize the window and the whole app scales to fit it.
* Ctrl+Z / Ctrl+Y (Cmd+Z / Cmd+Shift+Z on Mac) undo and redo, Ctrl+S (Cmd+S) saves.
* Saved entries are loaded automatically next time the app starts.
"""

import copy
import json
import math
import os
import sys
import time
import types
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

try:  # the embedded pictures are optional - the app still works without them
    import icons_data
except Exception:  # pragma: no cover
    icons_data = None
ICON_PX = getattr(icons_data, "SMALL_SIZE", 32)   # size of the profit picture beside the percentage

__version__ = "1.4.0"   # single source of truth - keep in sync with CHANGELOG.md

APP_NAME = "Profit Calculator"
MAX_ITEMS = 10
MAX_MATERIALS = 5
TAX_CHOICES = ("3%", "5%")
BASE_CARD_W = 340
HISTORY_LIMIT = 300
COMMIT_DELAY_MS = 450
ZOOM_MIN = 0.6          # smallest the whole UI shrinks to when the window is made small
ZOOM_PRESETS = (60, 75, 90, 100, 110, 125, 150, 175, 200, 240)   # percent, for the zoom menu
COMFORT_ZOOM = 1.0       # the UI is never made smaller than this just to avoid scrolling
ZOOM_MAX = 2.4          # largest it grows to when the window is made big
# whole-number ratios used to scale the (pixel-art) pictures: zoom(a) then subsample(b)
IMAGE_RATIOS = [(1, 2), (3, 5), (2, 3), (3, 4), (4, 5), (1, 1), (5, 4), (4, 3), (3, 2),
                (5, 3), (7, 4), (2, 1), (9, 4), (5, 2)]
MAX_VALUE = 1e15
DRAG_THRESHOLD = 6      # pixels the pointer must move before a press on a title becomes a drag
SHIFT_MASK = 0x0001     # Tk event.state bit for the Shift key

BG_OK = "#ffffff"
BG_RO = "#eceff1"
BG_BAD = "#ffd9d9"
GREEN = "#1a7f37"
RED = "#c62828"
AMBER = "#b45309"
MUTED = "#777777"

DEFAULT_STATE = {
    "type": "profit",
    "nickname": "",
    "base": "",
    "scrolls": "",
    "scroll_price": "",
    "materials": [],          # list of {"cost": str, "qty": str}
    "tax": "3%",
    "mode": "price",          # what you type: "price" (sale price), "profit" or "percent" (profit %)
    "sale_price": "",
    "target_profit": "",
    "target_pct": "",
}


# --------------------------------------------------------------------------- #
# Pure helpers (no GUI)
# --------------------------------------------------------------------------- #
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_num(text, allow_negative=False):
    """Blank -> 0.0, invalid -> None. Understands commas, k / m / b suffixes and a trailing %."""
    t = str(text).strip().replace(",", "").replace(" ", "").replace("_", "").rstrip("%")
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

    mode = d.get("mode")
    if mode == "profit":
        # sale * (1 - rate) - cost = target  ->  round UP so the target is always met
        sale = max(0, math.ceil((cost + num("target_profit")) / (1 - rate) - 1e-9))
    elif mode == "percent":
        # profit % is measured against the total cost: profit = cost * pct / 100
        sale = max(0, math.ceil(cost * (1 + num("target_pct") / 100.0) / (1 - rate) - 1e-9))
    else:
        sale = num("sale_price")

    tax = sale * rate
    net = sale - tax
    profit = net - cost
    roi = (profit / cost * 100.0) if cost > 0 else None
    return {"base": base, "scroll_total": scroll_total, "mat_total": mat_total,
            "cost": cost, "rate": rate, "sale": sale, "tax": tax, "net": net,
            "profit": profit, "roi": roi}


# Reward picture for each profit level. "Profit %" = profit / total cost. Checked from the top,
# a tier applies when the profit % is MORE than its floor (compared at 2 decimals).
TIERS = [
    # floor, picture,       title,          panel colour, text colour
    (25.0, "gold_bag",    "Jackpot!",      "#fff3bf", "#7a5c00"),
    (20.0, "money_bag",   "Great profit",  "#e8f4dc", "#2c6a1c"),
    (10.0, "cash_stack",  "Good profit",   "#dff2f6", "#14606f"),
    (5.0,  "gold_coin",   "Decent profit", "#fff0c2", "#80590a"),
    (0.0,  "copper_coin", "Small profit",  "#fae5d3", "#80441a"),
]
LOSS_TIER = ("grave", "Loss", "#e9e9ef", "#4b5563")
BREAKEVEN_TIER = (None, "Break-even", "#f1f2f4", "#4b5563")
NEUTRAL_TIER = (None, "Waiting for numbers", "#f1f2f4", "#6b7280")


def tier_for(roi):
    """(picture, title, panel colour, text colour) for a profit % (None = nothing to judge yet)."""
    if roi is None:
        return NEUTRAL_TIER
    r = round(roi, 2)
    if r < 0:
        return LOSS_TIER
    for floor, key, title, bg, fg in TIERS:
        if r > floor:
            return (key, title, bg, fg)
    return BREAKEVEN_TIER


def sanitize_item(d):
    """Make an item dict from untrusted data (e.g. a hand-edited save file)."""
    out = copy.deepcopy(DEFAULT_STATE)
    if not isinstance(d, dict):
        return out
    for k in ("nickname", "base", "scrolls", "scroll_price", "sale_price", "target_profit", "target_pct"):
        if isinstance(d.get(k), str):
            out[k] = d[k]
    if d.get("tax") in TAX_CHOICES:
        out["tax"] = d["tax"]
    if d.get("mode") in ("price", "profit", "percent"):
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


# --------------------------------------------------------------------------- #
# Scroll simulator: the maths (no GUI)
# --------------------------------------------------------------------------- #
MAX_SLOTS = 10
MAX_SECTIONS = 6
# key: (name shown in the list, chance a scroll succeeds, chance the item is destroyed when it fails)
SCROLL_KINDS = {
    "chaos": ("Chaos - 10%, 50% destroy", 0.10, 0.50),
    "greater": ("Greater - 10%", 0.10, 0.0),
    "intermediate": ("Intermediate - 60%", 0.60, 0.0),
    "lesser": ("Lesser - 100%", 1.00, 0.0),
}
KIND_BY_LABEL = {v[0]: k for k, v in SCROLL_KINDS.items()}

DEFAULT_SCROLL_STATE = {
    "type": "scroll",
    "nickname": "",
    "equip_cost": "",
    "slots": "",              # blank = as many slots as scrolls used
    "basis": "atleast",       # "exact": items/cost for exactly k successes, "atleast": k or more
    "sections": [{"kind": "intermediate", "count": "", "cost": ""}],
    # restart rules (blank = off): give up on the item and start again with a new one when...
    "stop_streak": "",        # ...this many scrolls in a row fail
    "stop_total": "",         # ...this many scrolls have failed in total
    "stop_at": "",            # ...any of these scrolls fails, e.g. "1, 2" or "1-3"
}


def parse_int(text, lo=0, hi=None):
    """Whole number from a box: blank -> 0, anything that is not a whole number in range -> None."""
    v = parse_num(text)
    if v is None or abs(v - round(v)) > 1e-9:
        return None
    v = int(round(v))
    if v < lo or (hi is not None and v > hi):
        return None
    return v


def parse_positions(text):
    """Scroll numbers such as "1, 2" or "1-3" -> {1, 2, 3}. Blank -> empty set, invalid -> None."""
    t = str(text).replace(" ", "").replace(";", ",").replace("&", ",").rstrip(",")
    out = set()
    if not t:
        return out
    for part in t.split(","):
        a, sep, b = part.partition("-")
        lo, hi = parse_int(a, 1, MAX_SLOTS), parse_int(b, 1, MAX_SLOTS) if sep else None
        if not a or lo is None or (sep and (not b or hi is None or hi < lo)):
            return None
        out.update(range(lo, (hi if sep else lo) + 1))
    return out


def scroll_sim(seq, streak=0, total=0, positions=()):
    """Odds for scrolls used one after another, with optional restart rules.

    seq: [(chance to succeed, chance the item is destroyed on a failure), ...] in the order used.
    Every scroll uses one slot whether it passes or fails; a destroyed item ends the run.
    The item is set aside (restarted with a new one) as soon as a surviving failure makes
    `streak` fails in a row, `total` fails in all, or happens on a scroll number in `positions`
    (0 / empty = that rule is off). Restarted items use no more scrolls.
    Returns (finished, destroyed, restarted, used):
      finished[k] chance the item gets through every scroll with exactly k successes
      destroyed   chance the item is destroyed
      restarted   chance the item is set aside by a restart rule
      used[j]     chance scroll j is actually used
    """
    positions = set(positions or ())
    states = {(0, 0, 0): 1.0}          # (successes, fails in a row, fails in total) -> chance
    destroyed = restarted = 0.0
    used = []
    for j, (success, destroy) in enumerate(seq, 1):
        used.append(sum(states.values()))
        nxt = {}
        for (k, row, fails), p in states.items():
            if success > 0:
                key = (k + 1, 0, fails)
                nxt[key] = nxt.get(key, 0.0) + p * success
            fail = p * (1.0 - success)
            if fail <= 0:
                continue
            destroyed += fail * destroy
            survive = fail * (1.0 - destroy)
            if survive <= 0:
                continue
            row2, fails2 = row + 1, fails + 1
            if (streak and row2 >= streak) or (total and fails2 >= total) or j in positions:
                restarted += survive
            else:
                key = (k, row2, fails2)
                nxt[key] = nxt.get(key, 0.0) + survive
        states = nxt
    finished = [0.0] * (len(seq) + 1)
    for (k, _, _), p in states.items():
        finished[k] += p
    return finished, destroyed, restarted, used


def scroll_odds(seq):
    """scroll_sim without restart rules: (alive, destroyed, used)."""
    finished, destroyed, _, used = scroll_sim(seq)
    return finished, destroyed, used


def scroll_report(d):
    """Everything a scroll simulator shows, or {"error": text} (with "soft": True if nothing is wrong yet)."""
    slots_text = str(d.get("slots", "")).strip()
    slots = parse_int(slots_text, 0, MAX_SLOTS)
    equip = parse_num(d.get("equip_cost", ""))
    if slots is None:
        return {"error": f"Slots must be a whole number from 0 to {MAX_SLOTS} (or blank)."}
    if equip is None:
        return {"error": "Equipment cost is not a valid number."}
    seq = []                                   # (success, destroy, cost each) per scroll, in order
    kinds_seq = []                             # the scroll type of each of those scrolls
    for i, sec in enumerate(d.get("sections", []), 1):
        count = parse_int(sec.get("count", ""), 0, MAX_SLOTS)
        cost = parse_num(sec.get("cost", ""))
        if count is None:
            return {"error": f"Scroll row {i}: 'Used' must be a whole number from 0 to {MAX_SLOTS}."}
        if cost is None:
            return {"error": f"Scroll row {i}: cost is not a valid number."}
        kind = sec.get("kind") if sec.get("kind") in SCROLL_KINDS else "intermediate"
        _, success, destroy = SCROLL_KINDS[kind]
        seq += [(success, destroy, cost)] * count
        kinds_seq += [kind] * count
    streak = parse_int(d.get("stop_streak", ""), 0, MAX_SLOTS)
    total = parse_int(d.get("stop_total", ""), 0, MAX_SLOTS)
    positions = parse_positions(d.get("stop_at", ""))
    if streak is None:
        return {"error": f"Restart rule: 'fails in a row' must be a whole number from 1 to {MAX_SLOTS} (or blank)."}
    if total is None:
        return {"error": f"Restart rule: 'fails in total' must be a whole number from 1 to {MAX_SLOTS} (or blank)."}
    if positions is None:
        return {"error": f"Restart rule: list scroll numbers from 1 to {MAX_SLOTS}, e.g. 1, 2 or 1-3."}
    n = len(seq)
    if n == 0:
        return {"error": "Enter how many scrolls you use.", "soft": True}
    if not slots_text:
        slots = n                              # blank: the item has exactly the slots you use
    if n > slots:
        return {"error": f"That uses {n} scrolls but the item has only {slots} slot{'' if slots == 1 else 's'}."}
    finished, destroyed, restarted, used = scroll_sim([(p, q) for p, q, _ in seq], streak, total, positions)
    scroll_cost = sum(cost * u for (_, _, cost), u in zip(seq, used))
    per_item = equip + scroll_cost
    kinds, by_kind = [], {}                    # per base item: scrolls of each type used, and what they cost
    for kind, (_, _, cost), u in zip(kinds_seq, seq, used):
        if kind not in by_kind:
            by_kind[kind] = {"used": 0.0, "cost": 0.0}
            kinds.append(kind)
        by_kind[kind]["used"] += u
        by_kind[kind]["cost"] += cost * u

    def times(items, x):                       # items may be infinity; 0 stays 0
        return 0.0 if x == 0 else items * x

    rows = []
    for k in range(1, n + 1):
        exact, at_least = finished[k], sum(finished[k:])
        chance = exact if d.get("basis") == "exact" else at_least
        items = 1.0 / chance if chance > 1e-15 else math.inf
        rows.append({"k": k, "exact": exact, "atleast": at_least, "items": items,
                     "extra": items - 1.0,
                     "cost": math.inf if items == math.inf else items * per_item,
                     "base": times(items, equip),
                     "kind_cost": {kd: times(items, by_kind[kd]["cost"]) for kd in kinds},
                     "kind_used": {kd: times(items, by_kind[kd]["used"]) for kd in kinds}})
    rules = bool(streak or total or (positions & set(range(1, n + 1))))
    return {"n": n, "slots": slots, "zero": finished[0], "destroyed": destroyed, "restarted": restarted,
            "rules": rules, "equip": equip, "scroll_cost": scroll_cost, "per_item": per_item,
            "avg_used": sum(used), "kinds": kinds, "by_kind": by_kind, "rows": rows}


SCROLL_SHORT = {"chaos": "Chaos", "greater": "Greater", "intermediate": "Interm.", "lesser": "Lesser"}


def kind_header(kind):
    """Two-line column heading such as 'Greater' over '10%'."""
    return f"{SCROLL_SHORT[kind]}\n{round(SCROLL_KINDS[kind][1] * 100)}%"


def fmt_chance(p):
    if p <= 0:
        return "0%"
    v = p * 100.0
    return f"{v:,.2f}%" if v >= 0.01 else f"{v:.1e}%"


def short_num(v):
    """123 -> 123, 12,345 -> 12.3k, 1.2e9 -> 1.2b (infinity -> the infinity sign)."""
    if v is None or math.isnan(v):
        return "—"
    if math.isinf(v):
        return "∞"
    a = abs(v)
    for div, suffix in ((1e12, "t"), (1e9, "b"), (1e6, "m"), (1e3, "k")):
        if a >= div:
            x = v / div
            text = f"{x:.0f}" if abs(x) >= 100 else f"{x:.1f}" if abs(x) >= 10 else f"{x:.2f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text + suffix
    return fmt_num(v)


def fmt_items(v):
    if math.isinf(v):
        return "∞"
    if v < 10:
        return f"{v:.2f}"
    if v < 1000:
        return f"{v:,.1f}"
    return short_num(v)


def fmt_money(v):
    return fmt_num(v) if v < 1e12 else short_num(v)


def sanitize_scroll(d):
    """Make a scroll-simulator dict from untrusted data (e.g. a hand-edited save file)."""
    out = copy.deepcopy(DEFAULT_SCROLL_STATE)
    if not isinstance(d, dict):
        return out
    for k in ("nickname", "equip_cost", "slots", "stop_streak", "stop_total", "stop_at"):
        if isinstance(d.get(k), str):
            out[k] = d[k]
    if d.get("basis") in ("exact", "atleast"):
        out["basis"] = d["basis"]
    secs = []
    if isinstance(d.get("sections"), list):
        for sec in d["sections"][:MAX_SECTIONS]:
            if isinstance(sec, dict):
                kind = sec.get("kind") if sec.get("kind") in SCROLL_KINDS else "intermediate"
                c, p = sec.get("count"), sec.get("cost")
                secs.append({"kind": kind, "count": c if isinstance(c, str) else "",
                             "cost": p if isinstance(p, str) else ""})
    if secs:
        out["sections"] = secs
    return out


def sanitize_card(d):
    """Either kind of item card, chosen by its "type" (old save files have none = profit)."""
    if isinstance(d, dict) and d.get("type") == "scroll":
        return sanitize_scroll(d)
    return sanitize_item(d)


def default_state(kind="profit"):
    return copy.deepcopy(DEFAULT_SCROLL_STATE if kind == "scroll" else DEFAULT_STATE)


_DATA_FILE_OVERRIDE = None   # set by selftest() only


def data_file():
    if _DATA_FILE_OVERRIDE:
        return _DATA_FILE_OVERRIDE
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "ProfitCalculator", "entries.json")


def settings_file():
    return os.path.join(os.path.dirname(data_file()), "settings.json")


def parse_zoom(text):
    """'Auto' -> None (fit the window); '125', '125%', '1.25x' -> 1.25. Out of range values are
    clamped to the allowed zoom. Returns (ok, value); ok is False if the text is not understood."""
    t = str(text).strip().lower().replace(" ", "")
    if t in ("auto", "fit"):
        return True, None
    if not t:
        return False, None
    try:
        if t.endswith("x"):
            z = float(t[:-1])
        else:
            z = float(t.rstrip("%")) / 100.0
    except ValueError:
        return False, None
    if not math.isfinite(z) or z <= 0:
        return False, None
    return True, max(ZOOM_MIN, min(ZOOM_MAX, z))


def zoom_label(z):
    return "Auto" if z is None else f"{round(z * 100)}%"


def load_settings():
    try:
        with open(settings_file(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data):
    data = {**load_settings(), **data}          # keep the other settings
    try:
        os.makedirs(os.path.dirname(settings_file()), exist_ok=True)
        with open(settings_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


def default_app_state():
    return {"version": 1, "items": [copy.deepcopy(DEFAULT_STATE)]}


def _bumped(base_font, delta):
    f = base_font.copy()
    size = base_font.actual("size")
    f.configure(size=(size + delta) if size > 0 else (size - delta), weight="bold")
    return f


# --------------------------------------------------------------------------- #
# What every item card shares: the header (title, drag handle, move / clear / remove buttons)
# --------------------------------------------------------------------------- #
class CardBase(ttk.Frame):
    kind_label = "Item"          # the title reads "<kind_label> <number>"

    def __init__(self, parent, app, index):
        super().__init__(parent, padding=(12, 10), relief="groove", borderwidth=2)
        self.app = app
        self.index = index
        self._updating = False
        self._drag_target = None
        self.entries = []        # (entry, var, kind) for the fixed fields

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

    def _build_header(self):
        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        self.title_lbl = ttk.Label(head, text="", font=self.app.f_title)
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.title_lbl.config(cursor="fleur")
        for w in (self.title_lbl, head):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
        self.left_btn = ttk.Button(head, text="◀", width=3,
                                   command=lambda: self.app.move_card(self, self.index - 1))
        self.left_btn.grid(row=0, column=1, padx=(6, 0))
        self.right_btn = ttk.Button(head, text="▶", width=3,
                                    command=lambda: self.app.move_card(self, self.index + 1))
        self.right_btn.grid(row=0, column=2, padx=(2, 0))
        ttk.Button(head, text="Clear", width=7, command=self.clear).grid(row=0, column=3, padx=(8, 0))
        self.remove_btn = ttk.Button(head, text="Remove", width=8,
                                     command=lambda: self.app.remove_card(self))
        self.remove_btn.grid(row=0, column=4, padx=(4, 0))

    def display_name(self):
        return self.nick.get().strip() or f"{self.kind_label} {self.index + 1}"

    def set_index(self, i, removable, total=1):
        self.index = i
        if removable:
            self.remove_btn.grid()
        else:
            self.remove_btn.grid_remove()
        if total > 1:
            self.left_btn.grid()
            self.right_btn.grid()
            self.left_btn.state(["disabled" if i == 0 else "!disabled"])
            self.right_btn.state(["disabled" if i >= total - 1 else "!disabled"])
        else:
            self.left_btn.grid_remove()
            self.right_btn.grid_remove()
        self._update_title()

    def _update_title(self):
        nick = self.nick.get().strip()
        if len(nick) > 26:
            nick = nick[:25] + "…"
        self.title_lbl.config(text=f"{self.kind_label} {self.index + 1}" + (f" — {nick}" if nick else ""))

    # ---- drag to reorder -------------------------------------------------- #
    def _drag_start(self, event):
        self._drag_target = None
        self._press_at = (event.x_root, event.y_root)
        self._dragging = False

    def _drag_move(self, event):
        if not self._dragging:
            x0, y0 = getattr(self, "_press_at", None) or (event.x_root, event.y_root)
            if abs(event.x_root - x0) < DRAG_THRESHOLD and abs(event.y_root - y0) < DRAG_THRESHOLD:
                return                       # a click (or a tiny wobble) is not a drag
            self._dragging = True
            self.configure(relief="raised")
        target = self.app.nearest_card(event.x_root, event.y_root)
        if target is not self._drag_target:
            if self._drag_target is not None:
                self._drag_target.configure(relief="groove")
            self._drag_target = target if target is not self else None
            if self._drag_target is not None:
                self._drag_target.configure(relief="solid")

    def _drag_end(self, event):
        dragged = getattr(self, "_dragging", False)
        self._dragging = False
        self._press_at = None
        for c in self.app.cards:
            c.configure(relief="groove")
        self._drag_target = None
        if not dragged:                      # just a click on the title: never move the item
            return
        target = self.app.nearest_card(event.x_root, event.y_root)
        if target is not None and target is not self:
            self.app.move_card(self, target.index)

    # ---- events ----------------------------------------------------------- #
    def _on_var(self, *_):
        if self._updating or self.app.suspend:
            return
        self.recalc()
        self.app.changed()

    def on_zoom(self):
        """Called when the whole UI is scaled: refresh what does not scale by itself."""


# --------------------------------------------------------------------------- #
# One item calculator
# --------------------------------------------------------------------------- #
class Card(CardBase):
    def __init__(self, parent, app, index, state):
        super().__init__(parent, app, index)
        self.mat_entries = []    # same, for material rows (rebuilt often)
        self.mats = []           # list of (cost_var, qty_var)

        V = tk.StringVar
        self.nick, self.base, self.scrolls, self.sprice = V(), V(), V(), V()
        self.sale, self.target, self.pct, self.total = V(), V(), V(), V()
        self.tier_key = None
        self.tax, self.mode = V(value="3%"), V(value="price")
        for v in (self.nick, self.base, self.scrolls, self.sprice,
                  self.sale, self.target, self.pct, self.tax, self.mode):
            v.trace_add("write", self._on_var)

        self._build()
        self.load_state(state)

    # ---- widgets ---------------------------------------------------------- #
    def _build(self):
        app = self.app
        self.columnconfigure(0, weight=1)

        self._build_header()

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        body.columnconfigure(1, weight=1)
        r = 0

        def sep():
            nonlocal r
            ttk.Separator(body).grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
            r += 1

        def section(text):
            nonlocal r
            ttk.Label(body, text=text, style="Section.TLabel").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(0, 3))
            r += 1

        def field(text, var, kind, **kw):
            nonlocal r
            lbl = ttk.Label(body, text=text)
            lbl.grid(row=r, column=0, sticky="w", pady=1, padx=(0, 8))
            e = self._entry(body, var, kind, **kw)
            e.grid(row=r, column=1, sticky="ew", pady=1)
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
        ttk.Label(body, text="I type in:").grid(row=r, column=0, sticky="w", pady=1)
        mode_f = ttk.Frame(body)
        mode_f.grid(row=r, column=1, sticky="e")
        for text, value in (("Sale price", "price"), ("Profit", "profit"), ("Profit %", "percent")):
            ttk.Radiobutton(mode_f, text=text, value=value, variable=self.mode).pack(side="left", padx=(8, 0))
        r += 1
        self.sale_lbl, self.sale_entry = field("Preferred sale price", self.sale, "cost")
        self.target_lbl, self.target_entry = field("Preferred profit", self.target, "signed")
        self.pct_lbl, self.pct_entry = field("Preferred profit %", self.pct, "signed")
        sep()

        section("Results")
        self.tax_lbl = result("Tax paid")
        self.net_lbl = result("You receive after tax")
        self.profit_lbl = result("Profit", big=True)
        ttk.Label(body, text="Return on cost").grid(row=r, column=0, sticky="w", pady=1)
        roi_f = ttk.Frame(body)                      # [picture] [verdict] [profit %]
        roi_f.grid(row=r, column=1, sticky="e", pady=1)
        r += 1
        self.roi_lbl = ttk.Label(roi_f, text="\u2014", anchor="e", font=app.f_bold)
        self.roi_lbl.pack(side="right")
        self.reward_title = ttk.Label(roi_f, text="", font=app.f_bold)
        self.reward_title.pack(side="right", padx=(0, 8))
        self.reward_icon = ttk.Label(roi_f, image=app.blank_icon)
        self.reward_icon.pack(side="right", padx=(0, 6))

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
            "type": "profit",
            "nickname": self.nick.get(),
            "base": self.base.get(),
            "scrolls": self.scrolls.get(),
            "scroll_price": self.sprice.get(),
            "materials": [{"cost": c.get(), "qty": q.get()} for c, q in self.mats],
            "tax": self.tax.get(),
            "mode": self.mode.get(),
            "sale_price": self.sale.get(),
            "target_profit": self.target.get(),
            "target_pct": self.pct.get(),
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
            self.pct.set(d["target_pct"])
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
        typed = {"profit": self.target, "percent": self.pct}.get(self.mode.get(), self.sale)
        return bool(typed.get().strip())

    def on_zoom(self):
        """Called when the whole UI is scaled: refresh the things that don't scale by themselves."""
        z = self.app.zoom
        self.breakdown.config(wraplength=int(300 * self.app.scale * z))
        img = self.app.tier_images.get(self.tier_key) if self.tier_key else None
        self.reward_icon.config(image=img or self.app.blank_icon)

    def _set_reward(self, tier):
        key, title, _bg, fg = tier
        self.tier_key = key
        img = self.app.tier_images.get(key) if key else None
        self.reward_icon.config(image=img or self.app.blank_icon)
        self.reward_title.config(text="" if tier is NEUTRAL_TIER else title, foreground=fg)

    # ---- events ----------------------------------------------------------- #
    def _add_mat_vars(self, cost, qty):
        cv, qv = tk.StringVar(value=cost), tk.StringVar(value=qty)
        cv.trace_add("write", self._on_var)
        qv.trace_add("write", self._on_var)
        self.mats.append((cv, qv))

    def add_material(self):
        if len(self.mats) >= MAX_MATERIALS:
            return
        self.app.commit_now()
        self._add_mat_vars("", "1")
        self._rebuild_mats(focus_last=True)
        self.recalc()
        self.app.commit_now()
        self.app.autosize()

    def remove_material(self, i):
        self.app.commit_now()
        del self.mats[i]
        self._rebuild_mats()
        self.recalc()
        self.app.commit_now()
        self.app.autosize()

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
        mode = st["mode"]
        for entry, lbl, name, own in ((self.sale_entry, self.sale_lbl, "Preferred sale price", "price"),
                                      (self.target_entry, self.target_lbl, "Preferred profit", "profit"),
                                      (self.pct_entry, self.pct_lbl, "Preferred profit %", "percent")):
            entry.config(state="normal" if mode == own else "readonly")
            lbl.config(text=name + ("" if mode == own else "  (auto)"))
        self._update_title()

        if self._validate():
            self.total.set("—")
            self.breakdown.config(text="")
            for lbl in (self.tax_lbl, self.net_lbl, self.roi_lbl):
                lbl.config(text="—")
            self.profit_lbl.config(text="Check red fields", foreground=RED)
            self._set_reward(NEUTRAL_TIER)
            return

        r = compute(st)
        self._updating = True
        try:
            self.total.set(fmt_num(r["cost"]))
            if mode != "price":
                self.sale.set(fmt_num(r["sale"]))
            if mode != "profit":
                self.target.set(fmt_num(r["profit"]))
            if mode != "percent":
                self.pct.set("" if r["roi"] is None else fmt_num(round(r["roi"], 2)))
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
        roi = r["roi"]
        self.roi_lbl.config(text="—" if roi is None else f"{roi:,.2f}%")
        self._set_reward(tier_for(roi))


# --------------------------------------------------------------------------- #
# Scroll simulator: odds of 1, 2, 3... successes and what they cost on average
# --------------------------------------------------------------------------- #
class ScrollCard(CardBase):
    kind_label = "Scrolls"
    LABELS = [v[0] for v in SCROLL_KINDS.values()]

    def __init__(self, parent, app, index, state):
        super().__init__(parent, app, index)
        V = tk.StringVar
        self.nick, self.equip, self.slots = V(), V(), V()
        self.stop_streak, self.stop_total, self.stop_at = V(), V(), V()
        self.basis = V(value="atleast")
        self.sections = []       # [{"kind": StringVar (list text), "count": StringVar, "cost": StringVar}]
        self.sec_entries = []    # entries of the scroll rows (rebuilt often)
        self.report = None
        for v in (self.nick, self.equip, self.slots, self.basis,
                  self.stop_streak, self.stop_total, self.stop_at):
            v.trace_add("write", self._on_var)
        self._build()
        self.load_state(state)

    # ---- widgets ---------------------------------------------------------- #
    def _build(self):
        app = self.app
        self.columnconfigure(0, weight=1)
        self._build_header()

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        body.columnconfigure(1, weight=1)
        r = 0

        def field(text, var, kind):
            nonlocal r
            ttk.Label(body, text=text).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 8))
            self._entry(body, var, kind).grid(row=r, column=1, sticky="ew", pady=2)
            r += 1

        def note(text):
            nonlocal r
            lbl = ttk.Label(body, text=text, style="Muted.TLabel", justify="left",
                            wraplength=int(300 * app.scale))
            lbl.grid(row=r, column=0, columnspan=2, sticky="w")
            self.notes.append(lbl)
            r += 1

        def sep():
            nonlocal r
            ttk.Separator(body).grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
            r += 1

        def section(text):
            nonlocal r
            ttk.Label(body, text=text, style="Section.TLabel").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(0, 3))
            r += 1

        self.notes = []
        field("Equipment", self.nick, "text")
        pair = ttk.Frame(body)                       # cost and slots share one line
        pair.grid(row=r, column=0, columnspan=2, sticky="ew", pady=1)
        pair.columnconfigure(1, weight=1)
        ttk.Label(pair, text="Cost").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._entry(pair, self.equip, "cost").grid(row=0, column=1, sticky="ew")
        ttk.Label(pair, text=f"Slots (0-{MAX_SLOTS}, blank = auto)").grid(row=0, column=2, sticky="w", padx=(12, 8))
        self._entry(pair, self.slots, "int", width=4).grid(row=0, column=3)
        r += 1
        sep()

        self.sec_head = ttk.Frame(body)              # "Scrolls used" with the add button on the same line
        self.sec_head.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        self.sec_head.columnconfigure(0, weight=1)
        ttk.Label(self.sec_head, text="Scrolls used", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.add_btn = None
        r += 1
        self.sec_frame = ttk.Frame(body)
        self.sec_frame.grid(row=r, column=0, columnspan=2, sticky="ew")
        r += 1
        note("Used top to bottom; every scroll uses 1 slot, pass or fail.")
        sep()

        section("Restart with a new item when")
        rs = ttk.Frame(body)
        rs.grid(row=r, column=0, columnspan=2, sticky="ew")
        rs.columnconfigure(1, weight=1)
        rs.columnconfigure(3, weight=1)
        ttk.Label(rs, text="Fails in a row").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=1)
        self._entry(rs, self.stop_streak, "int", width=5).grid(row=0, column=1, sticky="ew", pady=1)
        ttk.Label(rs, text="Fails in total").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=1)
        self._entry(rs, self.stop_total, "int", width=5).grid(row=0, column=3, sticky="ew", pady=1)
        ttk.Label(rs, text="Any of these scrolls fails (e.g. 1, 2 or 1-3)").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=1)
        self._entry(rs, self.stop_at, "list", width=8).grid(row=1, column=3, sticky="ew", pady=1)
        r += 1
        note("Blank = never restart. Restarting stops scrolling that item and starts a new one.")
        sep()

        section("Results")
        self.sum_lbls = {}
        grid = ttk.Frame(body)                       # two columns of label + value
        grid.grid(row=r, column=0, columnspan=2, sticky="ew")
        for c in (1, 3):
            grid.columnconfigure(c, weight=1)
        items = (("slots", "Scrolls / slots"), ("avg_used", "Avg scrolls used"),
                 ("destroy", "Chance destroyed"), ("restart", "Chance restarted"),
                 ("zero", "Chance of 0 successes"), ("scroll_cost", "Avg scroll cost"))
        for idx, (key, text) in enumerate(items):
            row, col = divmod(idx, 2)
            c0 = col * 2
            ttk.Label(grid, text=text).grid(row=row, column=c0, sticky="w", pady=1,
                                            padx=(0 if col == 0 else 16, 6))
            lbl = ttk.Label(grid, text="\u2014", anchor="e")
            lbl.grid(row=row, column=c0 + 1, sticky="e", pady=1)
            self.sum_lbls[key] = lbl
        r += 1
        self.msg = ttk.Label(body, text="", justify="left", wraplength=int(300 * app.scale))
        self.msg.grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 0))
        r += 1
        sep()

        head = ttk.Frame(body)                       # title, then the exact/at-least choice on one line
        head.grid(row=r, column=0, columnspan=2, sticky="ew")
        ttk.Label(head, text="Successes", style="Section.TLabel").pack(side="left")
        ttk.Radiobutton(head, text="Avg for exactly N", value="exact", variable=self.basis).pack(
            side="right")
        ttk.Radiobutton(head, text="Avg for at least N", value="atleast", variable=self.basis).pack(
            side="right", padx=(0, 10))
        r += 1

        self.table = ttk.Frame(body)
        self.table.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        for c in range(5):
            self.table.columnconfigure(c, weight=1, uniform="scroll_table")
        for c, text in enumerate(("Successes", "Exactly", "At least", "Avg items", "Extra items")):
            ttk.Label(self.table, text=text, style="Section.TLabel", anchor="e").grid(
                row=0, column=c, sticky="e", padx=(0, 6))
        self.table_rows = []
        self._grids = {}                             # name -> label grid of the breakdown tables
        self.bd_titles, self.bd_frames = [], {}
        rr = r + 1
        for name, title in (("cost", "Cost to get N successes (base items + scrolls)"),
                            ("used", "Scrolls used to get N successes")):
            tl = ttk.Label(body, text=title, style="Section.TLabel")
            tl.grid(row=rr, column=0, columnspan=2, sticky="w", pady=(8, 0))
            fr = ttk.Frame(body)
            fr.grid(row=rr + 1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
            self.bd_titles.append(tl)
            self.bd_frames[name] = fr
            rr += 2
        self.table_note = ttk.Label(body, text="", style="Muted.TLabel", justify="left",
                                    wraplength=int(300 * app.scale))
        self.table_note.grid(row=rr, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.notes.append(self.table_note)
        for k in range(1, MAX_SLOTS + 1):
            labels = []
            for c in range(5):
                lbl = ttk.Label(self.table, text="", anchor="e")
                lbl.grid(row=k, column=c, sticky="e", padx=(0, 6), pady=0)
                labels.append(lbl)
            self.table_rows.append(labels)

    def _fill_grid(self, name, headers, rows):
        """Show a small table (headers + rows of text); labels are only rebuilt when its shape changes."""
        frame = self.bd_frames[name]
        g = self._grids.get(name)
        sig = (len(headers), len(rows))
        if g is None or g["sig"] != sig:
            for w in frame.winfo_children():
                w.destroy()
            for c in range(10):
                frame.columnconfigure(c, weight=0, uniform="")
            for c in range(len(headers)):
                frame.columnconfigure(c, weight=1, uniform="bd_" + name)
            hdr = []
            for c in range(len(headers)):
                lb = ttk.Label(frame, style="Section.TLabel", anchor="e", justify="right")
                lb.grid(row=0, column=c, sticky="e", padx=(0, 6))
                hdr.append(lb)
            cells = []
            for i in range(len(rows)):
                line = []
                for c in range(len(headers)):
                    lb = ttk.Label(frame, anchor="e")
                    lb.grid(row=i + 1, column=c, sticky="e", padx=(0, 6))
                    line.append(lb)
                cells.append(line)
            g = self._grids[name] = {"sig": sig, "hdr": hdr, "cells": cells}
        for lb, text in zip(g["hdr"], headers):
            lb.config(text=text)
        for line, texts in zip(g["cells"], rows):
            for lb, text in zip(line, texts):
                lb.config(text=text)
        frame.grid()

    def _wheel_passthrough(self, event):
        """Scroll the window instead of changing the list when the wheel is over a drop-down."""
        self.app._on_wheel(event)
        return "break"

    def _rebuild_sections(self):
        f = self.sec_frame
        for w in f.winfo_children():
            w.destroy()
        self.sec_entries = []
        f.columnconfigure(0, weight=1)
        for c, text in ((0, "Scroll type"), (1, "Used"), (2, "Cost each")):
            ttk.Label(f, text=text, style="Muted.TLabel").grid(row=0, column=c, sticky="w" if c == 0 else "e")
        many = len(self.sections) > 1
        for i, sec in enumerate(self.sections, start=1):
            combo = ttk.Combobox(f, textvariable=sec["kind"], values=self.LABELS, state="readonly", width=20)
            combo.grid(row=i, column=0, sticky="ew", pady=1)
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                combo.bind(seq, self._wheel_passthrough)
            self._entry(f, sec["count"], "int", width=5, store=self.sec_entries).grid(
                row=i, column=1, padx=(6, 0), pady=2)
            self._entry(f, sec["cost"], "cost", width=11, store=self.sec_entries).grid(
                row=i, column=2, padx=(6, 0), pady=2)
            btn = ttk.Button(f, text="×", width=2, command=lambda idx=i - 1: self.remove_section(idx))
            btn.grid(row=i, column=3, padx=(6, 0))
            if not many:
                btn.state(["disabled"])
        n = len(self.sections)
        if self.add_btn is not None:
            self.add_btn.destroy()
        self.add_btn = ttk.Button(self.sec_head, text=f"+ Add scroll type ({n}/{MAX_SECTIONS})",
                                  command=self.add_section)
        if n >= MAX_SECTIONS:
            self.add_btn.state(["disabled"])
        self.add_btn.grid(row=0, column=1, sticky="e")

    # ---- state ------------------------------------------------------------ #
    def _add_section_vars(self, kind_key, count, cost):
        label = SCROLL_KINDS.get(kind_key, SCROLL_KINDS["intermediate"])[0]
        sec = {"kind": tk.StringVar(value=label), "count": tk.StringVar(value=count),
               "cost": tk.StringVar(value=cost)}
        for v in sec.values():
            v.trace_add("write", self._on_var)
        self.sections.append(sec)

    def get_state(self):
        return {
            "type": "scroll",
            "nickname": self.nick.get(),
            "equip_cost": self.equip.get(),
            "slots": self.slots.get(),
            "basis": self.basis.get(),
            "stop_streak": self.stop_streak.get(),
            "stop_total": self.stop_total.get(),
            "stop_at": self.stop_at.get(),
            "sections": [{"kind": KIND_BY_LABEL.get(sec["kind"].get(), "intermediate"),
                          "count": sec["count"].get(), "cost": sec["cost"].get()}
                         for sec in self.sections],
        }

    def load_state(self, d):
        d = sanitize_scroll(d)
        self._updating = True
        try:
            self.nick.set(d["nickname"])
            self.equip.set(d["equip_cost"])
            self.slots.set(d["slots"])
            self.basis.set(d["basis"])
            self.stop_streak.set(d["stop_streak"])
            self.stop_total.set(d["stop_total"])
            self.stop_at.set(d["stop_at"])
            self.sections = []
            for sec in d["sections"]:
                self._add_section_vars(sec["kind"], sec["count"], sec["cost"])
        finally:
            self._updating = False
        self._rebuild_sections()
        self.recalc()

    def has_data(self):
        if any(v.get().strip() for v in (self.nick, self.equip, self.slots,
                                         self.stop_streak, self.stop_total, self.stop_at)):
            return True
        return len(self.sections) > 1 or any(
            sec["count"].get().strip() or sec["cost"].get().strip() for sec in self.sections)

    def on_zoom(self):
        wrap = int(300 * self.app.scale * self.app.zoom)
        for lbl in self.notes + [self.msg]:
            lbl.config(wraplength=wrap)

    # ---- actions ---------------------------------------------------------- #
    def add_section(self):
        if len(self.sections) >= MAX_SECTIONS:
            return
        self.app.commit_now()
        self._add_section_vars("intermediate", "", "")
        self._rebuild_sections()
        self.recalc()
        self.app.commit_now()
        self.app.autosize()

    def remove_section(self, i):
        if len(self.sections) <= 1:
            return
        self.app.commit_now()
        del self.sections[i]
        self._rebuild_sections()
        self.recalc()
        self.app.commit_now()
        self.app.autosize()

    def clear(self):
        ok = messagebox.askyesno(
            "Clear scroll simulator",
            f"Reset “{self.display_name()}” and clear all of its entries?\n\n"
            "You can bring them back with Undo.",
            icon="warning", default="no", parent=self.winfo_toplevel())
        if not ok:
            return
        self.app.commit_now()
        self.load_state(default_state("scroll"))
        self.app.commit_now()

    # ---- calculation ------------------------------------------------------ #
    def _validate(self):
        for e, var, kind in self.entries + self.sec_entries:
            if kind == "text":
                continue
            if kind == "int":
                ok = parse_int(var.get(), 0, MAX_SLOTS) is not None
            elif kind == "list":
                ok = parse_positions(var.get()) is not None
            else:
                ok = parse_num(var.get()) is not None
            e.config(bg=BG_OK if ok else BG_BAD)

    def recalc(self):
        self._update_title()
        self._validate()
        rep = scroll_report(self.get_state())
        self.report = rep
        if "error" in rep:
            self.msg.config(text=rep["error"], foreground=MUTED if rep.get("soft") else RED)
            for lbl in self.sum_lbls.values():
                lbl.config(text="—")
            self.table_note.config(text="")
            for labels in self.table_rows:
                for lbl in labels:
                    lbl.grid_remove()
            for fr in self.bd_frames.values():
                fr.grid_remove()
            for tl in self.bd_titles:
                tl.grid_remove()
            return
        self.msg.config(text="", foreground=MUTED)
        n = rep["n"]
        self.sum_lbls["slots"].config(text=f"{n} of {rep['slots']}")
        self.sum_lbls["destroy"].config(text=fmt_chance(rep["destroyed"]))
        self.sum_lbls["restart"].config(text=fmt_chance(rep["restarted"]) if rep["rules"] else "—")
        self.sum_lbls["zero"].config(text=fmt_chance(rep["zero"]))
        self.sum_lbls["avg_used"].config(text=f"{rep['avg_used']:.2f}")
        self.sum_lbls["scroll_cost"].config(text=fmt_money(rep["scroll_cost"]))
        basis = "exactly" if self.basis.get() == "exact" else "at least"
        self.table_note.config(text=(
            f"Avg items = base items you buy on average to get one with {basis} that many successes, "
            "counting the finished one; Extra items = the others, which fail"
            + (", are destroyed or restart" if rep["rules"] or rep["destroyed"] > 0 else "")
            + ". The tables above price those items and the scrolls used on all of them."))
        for tl in self.bd_titles:
            tl.grid()
        kinds = rep["kinds"]
        per = rep["by_kind"]
        head_cost = ["Successes", "Base items"] + [kind_header(k) for k in kinds] + ["Total"]
        rows_cost = [["1 item", short_num(rep["equip"])] + [short_num(per[k]["cost"]) for k in kinds]
                     + [short_num(rep["per_item"])]]
        head_used = ["Successes"] + [kind_header(k) for k in kinds] + ["All scrolls"]
        rows_used = [["1 item"] + [fmt_items(per[k]["used"]) for k in kinds] + [fmt_items(rep["avg_used"])]]
        for row in rep["rows"]:
            rows_cost.append([str(row["k"]), short_num(row["base"])]
                             + [short_num(row["kind_cost"][k]) for k in kinds] + [short_num(row["cost"])])
            rows_used.append([str(row["k"])] + [fmt_items(row["kind_used"][k]) for k in kinds]
                             + [fmt_items(sum(row["kind_used"].values()))])
        self._fill_grid("cost", head_cost, rows_cost)
        self._fill_grid("used", head_used, rows_used)
        for i, labels in enumerate(self.table_rows):
            if i < n:
                row = rep["rows"][i]
                texts = (str(row["k"]), fmt_chance(row["exact"]), fmt_chance(row["atleast"]),
                         fmt_items(row["items"]), fmt_items(row["extra"]))
                for lbl, text in zip(labels, texts):
                    lbl.config(text=text)
                    lbl.grid()
            else:
                for lbl in labels:
                    lbl.grid_remove()


def make_card(parent, app, index, state):
    """Build the right kind of card for a saved/default state."""
    cls = ScrollCard if isinstance(state, dict) and state.get("type") == "scroll" else Card
    return cls(parent, app, index, state)


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
        self.zoom = 1.0
        self._img_ratio = (1, 1)
        self._skip_fit = False
        self._fit_job = None
        self._last_size = None
        _cfg = load_settings()
        self.auto_resize = tk.BooleanVar(master=root, value=bool(_cfg.get("auto_resize", False)))
        _ok, _z = parse_zoom(_cfg.get("zoom", "auto"))
        self.manual_zoom = _z if _ok else None          # None = Auto (fit the window)
        self.zoom_var = tk.StringVar(master=root, value=zoom_label(self.manual_zoom))

        self._setup_style()
        self._load_icons()
        self._build_toolbar()
        self._build_canvas()
        self._bind_keys()
        self._build_menu()

        state = self._read_disk() or default_app_state()
        self._rebuild(state)
        snap = self._snap()
        self.history = [snap]
        self.hidx = 0
        self.saved_json = snap
        if self.manual_zoom is not None:
            self._apply_zoom(self.manual_zoom)
        self.autosize(initial=True)
        self._refresh()
        root.bind("<Configure>", self._on_root_configure)

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
        # every font that should scale with the window, with its size in pixels at zoom 1.0
        self._zoom_fonts = []
        for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont"):
            try:
                f = tkfont.nametofont(name)
                self._zoom_fonts.append((f, self._font_px(f)))
            except tk.TclError:
                pass
        for f in (self.f_bold, self.f_title, self.f_big):
            self._zoom_fonts.append((f, self._font_px(f)))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Section.TLabel", font=self.f_bold)
        self.default_fg = style.lookup("TLabel", "foreground") or "black"
        self.canvas_bg = style.lookup("TFrame", "background") or self.root.cget("bg")

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(side="top", fill="x")
        self.toolbar = bar
        self.add_btn = ttk.Button(bar, text="+ Add Item", command=self.add_card)
        self.add_btn.pack(side="left")
        self.add_scroll_btn = ttk.Button(bar, text="+ Add Scroll Simulator",
                                         command=lambda: self.add_card("scroll"))
        self.add_scroll_btn.pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.undo_btn = ttk.Button(bar, text=f"Undo ({self.mod_name}+Z)", command=self.undo)
        self.undo_btn.pack(side="left")
        redo_key = "Shift+Z" if self.mac else "Y"
        self.redo_btn = ttk.Button(bar, text=f"Redo ({self.mod_name}+{redo_key})", command=self.redo)
        self.redo_btn.pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.save_btn = ttk.Button(bar, text=f"Save ({self.mod_name}+S)", command=self.save)
        self.save_btn.pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(bar, text="Zoom").pack(side="left")
        self.zoom_out_btn = ttk.Button(bar, text="\u2212", width=2, command=lambda: self.step_zoom(-1))
        self.zoom_out_btn.pack(side="left", padx=(6, 0))
        self.zoom_box = ttk.Combobox(bar, textvariable=self.zoom_var, width=6, justify="center",
                                     values=["Auto"] + [f"{p}%" for p in ZOOM_PRESETS])
        self.zoom_box.pack(side="left", padx=2)
        self.zoom_box.bind("<<ComboboxSelected>>", lambda e: self.set_zoom_text(self.zoom_var.get()))
        self.zoom_box.bind("<Return>", lambda e: self.set_zoom_text(self.zoom_var.get()))
        self.zoom_box.bind("<FocusOut>", lambda e: self.set_zoom_text(self.zoom_var.get()))
        self.zoom_in_btn = ttk.Button(bar, text="+", width=2, command=lambda: self.step_zoom(1))
        self.zoom_in_btn.pack(side="left")
        self.status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.status.pack(side="right")
        ttk.Separator(self.root).pack(side="top", fill="x")

    def _build_canvas(self):
        wrap = ttk.Frame(self.root)
        wrap.pack(side="top", fill="both", expand=True)
        vs = ttk.Scrollbar(wrap, orient="vertical")
        vs.pack(side="right", fill="y")
        self.vscroll = vs
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

        def letter(ch, plain, shifted=None):
            # Bind both cases: with Caps Lock on, Tk reports Ctrl+Z as an upper-case "Z". Whether
            # it means the Shift version is decided by the Shift key itself, not by the letter case.
            def handler(e, plain=plain, shifted=shifted):
                use_shift = shifted is not None and bool(getattr(e, "state", 0) & SHIFT_MASK)
                (shifted if use_shift else plain)()
                return "break"
            for key in (ch.lower(), ch.upper()):
                try:
                    self.root.bind_all(f"<{m}-{key}>", handler)
                except tk.TclError:
                    pass
            self.key_handlers[ch.lower()] = handler

        self.key_handlers = {}
        letter("z", self.undo, self.redo)            # Ctrl+Z undo, Ctrl+Shift+Z redo
        if not self.mac:
            letter("y", self.redo)
        letter("s", self.save)
        for seq in ("equal", "plus"):
            bind(f"<{m}-{seq}>", lambda: self.step_zoom(1))
        bind(f"<{m}-minus>", lambda: self.step_zoom(-1))
        bind(f"<{m}-0>", lambda: self.set_zoom(None))

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        settings = tk.Menu(menubar, tearoff=0)
        settings.add_checkbutton(label="Auto-resize window when adding or removing items",
                                 variable=self.auto_resize, command=self._on_auto_resize_toggled)
        zoom_menu = tk.Menu(settings, tearoff=0)
        for label in ["Auto"] + [f"{p}%" for p in ZOOM_PRESETS]:
            zoom_menu.add_radiobutton(label="Auto (fit the window)" if label == "Auto" else label,
                                      variable=self.zoom_var, value=label,
                                      command=lambda v=label: self.set_zoom_text(v))
        settings.add_cascade(label="Zoom", menu=zoom_menu)
        menubar.add_cascade(label="Settings", menu=settings)
        self.root.config(menu=menubar)

    def _on_auto_resize_toggled(self):
        save_settings({"auto_resize": bool(self.auto_resize.get())})
        if self.auto_resize.get():
            self.autosize()

    # ---- manual zoom ------------------------------------------------------ #
    def set_zoom_text(self, text):
        ok, z = parse_zoom(text)
        if not ok:                                    # not understood: show the current value again
            self.zoom_var.set(zoom_label(self.manual_zoom))
            return
        self.set_zoom(z)

    def set_zoom(self, z):
        """z = None for Auto (fit the window), or a factor such as 1.25 for 125%."""
        if z is not None:
            z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        self.zoom_var.set(zoom_label(z))
        if z == self.manual_zoom:
            return
        self.manual_zoom = z
        save_settings({"zoom": "auto" if z is None else round(z * 100)})
        self._skip_fit = False
        if z is None:
            self._set_minsize()
            self._fit_to_window()
            return
        self._apply_zoom(z)
        self._measure()
        self.autosize()                               # resizes the window if auto-resize is on

    def step_zoom(self, direction):
        """Next preset above (+1) or below (-1) the zoom in use."""
        now = round((self.manual_zoom or self.zoom) * 100)
        if direction > 0:
            cands = [p for p in ZOOM_PRESETS if p > now]
            target = cands[0] if cands else ZOOM_PRESETS[-1]
        else:
            cands = [p for p in ZOOM_PRESETS if p < now]
            target = cands[-1] if cands else ZOOM_PRESETS[0]
        self.set_zoom(target / 100.0)

    def _font_px(self, font):
        size = font.actual("size")
        if size < 0:
            return -size
        return max(6, round(size * self.root.winfo_fpixels("1i") / 72.0))

    def _load_icons(self):
        """Decode the embedded pictures; set the leprechaun as the window icon."""
        self.tier_images = {}
        self._base_images = {}
        self.window_icons = []
        self.blank_icon = tk.PhotoImage(master=self.root, width=ICON_PX, height=ICON_PX)  # transparent
        if icons_data is None:
            return
        try:
            for key, b64 in icons_data.TIER_ICONS_SMALL.items():
                self._base_images[key] = tk.PhotoImage(master=self.root, data=b64)
            self.tier_images = dict(self._base_images)
            self.window_icons = [tk.PhotoImage(master=self.root, data=icons_data.APP_ICONS[size])
                                 for size in sorted(icons_data.APP_ICONS, reverse=True)]
            self.root.iconphoto(True, *self.window_icons)
        except tk.TclError:
            pass

    # ---- scale the whole UI with the window ----------------------------------------- #
    def _card_extent(self):
        """(width, height) one item needs at the current zoom, including the gap around it."""
        self.root.update_idletasks()
        gap = int(16 * self.scale)
        return (max(c.winfo_reqwidth() for c in self.cards) + gap,
                max(c.winfo_reqheight() for c in self.cards) + gap)

    def _apply_zoom(self, z):
        """Scale fonts and pictures to zoom z. Returns True if anything changed."""
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if abs(z - self.zoom) < 0.02:
            return False
        for font, base_px in self._zoom_fonts:
            font.configure(size=-max(7, round(base_px * z)))
        self.zoom = z
        a, b = min(IMAGE_RATIOS, key=lambda r: abs(r[0] / r[1] - z))
        if (a, b) != self._img_ratio:
            self._img_ratio = (a, b)
            self.tier_images = {k: (img if (a, b) == (1, 1) else img.zoom(a).subsample(b))
                                for k, img in self._base_images.items()}
            side = max(1, round(ICON_PX * a / b))
            self.blank_icon = tk.PhotoImage(master=self.root, width=side, height=side)
        for card in self.cards:
            card.on_zoom()
        return True

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if self._fit_job is None:       # throttle (not debounce): keep up with the drag, don't wait for its end
            self._fit_job = self.root.after(50, self._fit_to_window)

    def _fit_to_window(self):
        """Pick the zoom and number of columns that make all items fill the window."""
        self._fit_job = None
        if self._skip_fit or not self.cards:
            return
        self.root.update_idletasks()
        W = self.canvas.winfo_width()
        H = self.root.winfo_height() - self.toolbar.winfo_height() - 2
        if W < 60 or H < 60:
            return
        n = len(self.cards)
        if self.manual_zoom is not None:               # fixed zoom: just fill the width with columns
            changed = self._apply_zoom(self.manual_zoom)
            self._measure()
            self._set_minsize()
            cols = max(1, min(n, W // self.cw))
            if changed or cols != self._cols:
                self._layout_cards(force=True, cols=cols)
            return
        cw, ch = self._card_extent()
        cw1, ch1 = cw / self.zoom, ch / self.zoom      # size of one item at zoom 1.0
        best = None
        for cols in range(1, n + 1):
            rows = -(-n // cols)
            s = min(W / (cols * cw1), H / (rows * ch1))
            if best is None or (s, -rows) > best:
                best = (s, -rows)
        fit_all = best[0] >= COMFORT_ZOOM            # everything fits at a readable size
        tb_cap = self.root.winfo_width() / max(1.0, self.toolbar.winfo_reqwidth() / self.zoom)
        if fit_all:
            z, want_cols = best[0], None
        else:
            # Too many items to show at a readable size: keep the text readable, use as many
            # columns as fit at that size, and let the window scroll vertically.
            want_cols = 1
            for cols in range(n, 0, -1):
                if W / (cols * cw1) >= COMFORT_ZOOM:
                    want_cols = cols
                    break
            z = W / (want_cols * cw1)
        z = min(z, tb_cap)
        z = max(ZOOM_MIN, min(ZOOM_MAX, math.floor(z * 20 + 1e-6) / 20.0))   # 5% steps, rounded down so it fits
        changed = False
        for _ in range(5):                              # fonts come in whole pixels: verify and nudge
            changed = self._apply_zoom(z) or changed
            cw, ch = self._card_extent()
            cols = max(1, min(n, W // cw))
            if want_cols is not None:
                cols = max(1, min(want_cols, cols))
                if W >= cols * cw or z <= ZOOM_MIN + 0.01:
                    break
            elif -(-n // cols) * ch <= H or z <= ZOOM_MIN + 0.01:
                break
            z = max(ZOOM_MIN, z * 0.94)
        self._measure()
        if changed or cols != self._cols:
            self._layout_cards(force=True, cols=cols)

    def nearest_card(self, x_root, y_root):
        """The item under a screen position, else the one whose centre is closest (used while dragging)."""
        for c in self.cards:
            x, y = c.winfo_rootx(), c.winfo_rooty()
            if x <= x_root < x + c.winfo_width() and y <= y_root < y + c.winfo_height():
                return c
        best, best_d = None, None
        for c in self.cards:
            cx = c.winfo_rootx() + c.winfo_width() / 2
            cy = c.winfo_rooty() + c.winfo_height() / 2
            d = (cx - x_root) ** 2 + (cy - y_root) ** 2
            if best_d is None or d < best_d:
                best, best_d = c, d
        return best

    def move_card(self, card, new_index):
        """Move an item to a new position (0 = first). Undo/redo remember the order."""
        old = self.cards.index(card)
        new_index = max(0, min(len(self.cards) - 1, new_index))
        if new_index == old:
            return
        self.commit_now()
        self.cards.insert(new_index, self.cards.pop(old))
        self._renumber()
        self._layout_cards(force=True, cols=self._cols or None)
        self.commit_now()
        self.root.after(30, lambda: self._scroll_to(card))

    def _set_minsize(self):
        """Smallest window: the toolbar, and one item at the smallest zoom."""
        sw = self.root.winfo_screenwidth()
        sb_w = self.vscroll.winfo_reqwidth()
        pad = int(8 * self.scale)
        zmin = self.manual_zoom or ZOOM_MIN          # a fixed zoom keeps the window wide enough for it
        one_item = int(self.cw / self.zoom * zmin)
        toolbar = int(self.toolbar.winfo_reqwidth() / self.zoom * zmin)
        self.root.minsize(min(sw, max(one_item + sb_w + pad, toolbar)), int(320 * self.scale))

    def autosize(self, initial=False):
        """Fit the window to the items. Only the size is set, so the top-left corner stays put.

        With Settings > auto-resize switched off the window is left alone: the items are placed
        and scaled to fit the window as it is."""
        if not initial and not self.auto_resize.get():
            self._measure()
            self._layout_cards(force=True)
            self._set_minsize()
            self._fit_to_window()
            return
        self._skip_fit = True
        self.root.after(250, lambda: setattr(self, "_skip_fit", False))
        self._measure()
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        sb_w = self.vscroll.winfo_reqwidth()
        pad = int(8 * self.scale)
        max_cols = max(1, (sw - 80 - sb_w - pad) // self.cw)
        cols = max(1, min(len(self.cards), max_cols))
        self._layout_cards(force=True, cols=cols)
        self.root.update_idletasks()
        min_h = int(420 * self.scale)
        w = cols * self.cw + sb_w + pad
        h = self.toolbar.winfo_reqheight() + 2 + self.inner.winfo_reqheight() + pad
        h = max(min_h, min(h, sh - 120))
        self._set_minsize()
        self.root.geometry(f"{w}x{h}")

    # ---- layout ----------------------------------------------------------- #
    def _measure(self):
        self.root.update_idletasks()
        if self.cards:
            widest = max(c.winfo_reqwidth() for c in self.cards)
            self.cw = max(int(BASE_CARD_W * self.scale), widest + int(20 * self.scale))

    def _layout_cards(self, force=False, cols=None):
        if not self.cards:
            return
        if cols is None:
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
        # Only scroll the page for the main window; an open drop-down list scrolls by itself.
        w = e.widget
        if isinstance(w, str):                       # Tk-internal widget, e.g. a drop-down's list
            return
        try:
            if w.winfo_toplevel() is not self.root:
                return
        except (AttributeError, KeyError, tk.TclError):
            return
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
        if card not in self.cards or not card.winfo_exists():
            return                                   # removed while the delayed scroll was pending
        self.root.update_idletasks()
        total = max(self.inner.winfo_height(), 1)
        self.canvas.yview_moveto(max(0.0, (card.winfo_y() - 8) / total))

    def _renumber(self):
        removable = len(self.cards) > 1
        for i, c in enumerate(self.cards):
            c.set_index(i, removable, len(self.cards))

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
                self.cards.append(make_card(self.inner, self, i, sanitize_card(it)))
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
            self.autosize()
            self._refresh()

    def redo(self):
        self.commit_now()
        if self.hidx < len(self.history) - 1:
            self.hidx += 1
            self._rebuild(json.loads(self.history[self.hidx]))
            self.autosize()
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
        self.add_scroll_btn.state(["disabled" if n >= MAX_ITEMS else "!disabled"])
        if dirty:
            self.status.config(text="● Unsaved changes", foreground=AMBER)
        else:
            self.status.config(text=self.saved_text, foreground=MUTED)

    # ---- items ------------------------------------------------------------ #
    def add_card(self, kind="profit"):
        if len(self.cards) >= MAX_ITEMS:
            return
        self.commit_now()
        card = make_card(self.inner, self, len(self.cards), default_state(kind))
        self.cards.append(card)
        self._renumber()
        self.commit_now()
        self.autosize()
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
        self.commit_now()
        self.autosize()

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


def selftest(out_path):
    """Start the real GUI, drive it through the main features, then exit.

    Used by the release build to prove the packaged executable can start Tk and calculate.
    Writes "OK" or a traceback to out_path and returns the process exit code.
    Never touches the user's saved entries.
    """
    import tempfile
    import traceback
    global _DATA_FILE_OVERRIDE
    _DATA_FILE_OVERRIDE = os.path.join(tempfile.mkdtemp(), "entries.json")
    msg, code, root = "OK", 0, None
    import faulthandler
    global messagebox
    try:                          # a hang becomes a failure that shows where it was stuck
        hang_log = open(out_path, "w", encoding="utf-8")
        faulthandler.dump_traceback_later(150, exit=True, file=hang_log)
    except Exception:
        hang_log = None

    def _no_dialog(*a, **k):      # a dialog would wait for a click nobody can make
        raise AssertionError("unexpected dialog during self-test: %r" % (a[:1],))
    real_messagebox = messagebox
    messagebox = types.SimpleNamespace(askyesno=_no_dialog, askyesnocancel=_no_dialog, showerror=_no_dialog)
    try:
        for roi, want in ((None, None), (-0.01, "grave"), (0, None), (0.01, "copper_coin"),
                          (5, "copper_coin"), (5.01, "gold_coin"), (10, "gold_coin"), (10.01, "cash_stack"),
                          (20, "cash_stack"), (20.01, "money_bag"), (25, "money_bag"), (25.01, "gold_bag")):
            assert tier_for(roi)[0] == want, f"tier for {roi}% should be {want}, got {tier_for(roi)[0]}"
        alive, destroyed, used = scroll_odds([(1.0, 0.0), (1.0, 0.0), (0.1, 0.5)])
        assert abs(alive[3] - 0.1) < 1e-12 and abs(alive[2] - 0.45) < 1e-12 and abs(destroyed - 0.45) < 1e-12
        root = tk.Tk()
        app = App(root)
        assert icons_data is not None, "icons_data module is missing from the app"
        assert len(app.tier_images) == 6, "expected 6 tier pictures, got %d" % len(app.tier_images)
        for key, img in app.tier_images.items():
            assert (img.width(), img.height()) == (ICON_PX, ICON_PX), f"picture {key} is the wrong size"
        assert app.window_icons, "window icon was not loaded"
        assert len(app.cards) == 1, "should start with exactly one item"
        assert app.auto_resize.get() is False, "auto-resize should be off by default"
        app.auto_resize.set(True)       # the checks below are about resizing
        root.update()
        x0, y0, w0 = root.winfo_x(), root.winfo_y(), root.winfo_width()
        for _ in range(MAX_ITEMS - 1):
            app.add_card()
        root.update()
        assert len(app.cards) == MAX_ITEMS, f"should allow up to {MAX_ITEMS} items"
        assert not app.add_btn.instate(["!disabled"]), f"add button should disable at {MAX_ITEMS} items"
        if sys.platform != "darwin":    # macOS may nudge a window below the menu bar
            assert abs(root.winfo_x() - x0) <= 4 and abs(root.winfo_y() - y0) <= 4, "window moved while resizing"
        if root.winfo_screenwidth() >= 2 * app.cw + 160:
            assert root.winfo_width() > w0, "window did not grow when items were added"

        c = app.cards[0]
        c.base.set("1,000,000")
        c.scrolls.set("3")
        c.sprice.set("200k")
        c.add_material()
        c.mats[0][0].set("50k")
        c.mats[0][1].set("4")
        c.sale.set("2m")
        root.update()
        assert c.total.get() == "1,800,000", "total cost was " + c.total.get()
        assert c.target.get() == "140,000", "profit was " + c.target.get()

        assert c.tier_key == "cash_stack" or c.tier_key == "gold_bag" or c.tier_key == "money_bag" \
            or c.tier_key == "gold_coin", "unexpected picture for a profitable item: %r" % c.tier_key

        c.mode.set("percent")
        c.pct.set("20")
        root.update()
        assert c.sale.get() == "2,226,805", "sale price for 20%% was " + c.sale.get()
        assert c.tier_key == "cash_stack", "exactly 20%% should show the cash stack, got %r" % c.tier_key
        c.pct.set("30%")
        root.update()
        assert c.tier_key == "gold_bag", "30%% should show the gold bag, got %r" % c.tier_key
        c.pct.set("22")
        root.update()
        assert c.tier_key == "money_bag", "22%% should show the money bag, got %r" % c.tier_key
        c.mode.set("price")
        c.sale.set("1m")
        root.update()
        assert c.tier_key == "grave", "a loss should show the grave, got %r" % c.tier_key

        c.mode.set("profit")
        c.target.set("100k")
        root.update()
        assert c.sale.get() == "1,958,763", "sale price was " + c.sale.get()
        app.commit_now()

        app.undo()
        app.redo()
        c = app.cards[0]
        assert c.target.get() == "100k" and c.sale.get() == "1,958,763", "undo/redo lost state"

        c.nick.set("First")
        app.cards[1].nick.set("Second")
        app.commit_now()
        x, y = c.winfo_rootx() + 5, c.winfo_rooty() + 5
        assert app.nearest_card(x, y) is c, "nearest_card should find the item under the pointer"
        # a click (or a few pixels' wobble) on a title is not a drag: the item must stay put
        far = app.cards[-1]
        fx, fy = far.winfo_rootx() + far.winfo_width() // 2, far.winfo_rooty() + far.winfo_height() // 2
        ev = types.SimpleNamespace
        c._drag_start(ev(x_root=fx, y_root=fy))
        c._drag_move(ev(x_root=fx + 2, y_root=fy + 2))
        c._drag_end(ev(x_root=fx + 2, y_root=fy + 2))
        assert app.cards[0] is c and [k.nick.get() for k in app.cards[:2]] == ["First", "Second"], \
            "a click on an item's title moved it"
        app.move_card(app.cards[0], 1)
        assert [k.nick.get() for k in app.cards[:2]] == ["Second", "First"], "move item failed"
        assert app.cards[0].index == 0 and app.cards[1].index == 1, "items were not renumbered"
        app.undo()
        assert [k.nick.get() for k in app.cards[:2]] == ["First", "Second"], "undo should restore the order"
        app.redo()
        assert [k.nick.get() for k in app.cards[:2]] == ["Second", "First"], "redo should reapply the move"
        # keyboard shortcuts with Caps Lock on (state bit 0x2): Ctrl+Z still undoes, Ctrl+Shift+Z redoes
        app.key_handlers["z"](types.SimpleNamespace(state=0x2))
        assert [k.nick.get() for k in app.cards[:2]] == ["First", "Second"], "Ctrl+Z with Caps Lock should undo"
        app.key_handlers["z"](types.SimpleNamespace(state=0x2 | SHIFT_MASK))
        assert [k.nick.get() for k in app.cards[:2]] == ["Second", "First"], "Ctrl+Shift+Z should redo"


        app.remove_card(app.cards[-1])
        assert len(app.cards) == MAX_ITEMS - 1, "remove item failed"
        while len(app.cards) > 2:       # few items, so the zoom range is wide enough to measure
            app.remove_card(app.cards[-1])
        for _ in range(20):             # let the pause after an automatic resize end
            root.update()
            time.sleep(0.02)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry("640x480")
        for _ in range(15):
            root.update()
            time.sleep(0.02)
        z_small = app.zoom
        big_w, big_h = min(1500, sw - 60), min(1000, sh - 120)
        root.geometry(f"{big_w}x{big_h}")
        for _ in range(15):
            root.update()
            time.sleep(0.02)
        z_big = app.zoom
        assert ZOOM_MIN <= z_small <= ZOOM_MAX and ZOOM_MIN <= z_big <= ZOOM_MAX, "zoom out of range"
        if root.winfo_width() >= big_w - 4 and root.winfo_width() > 640 + 100:
            assert z_big >= z_small, f"UI did not scale up with the window ({z_small:.2f} -> {z_big:.2f})"
        assert app.tier_images["gold_bag"].width() > 0, "pictures lost after scaling"
        # --- Settings > auto-resize off: the window must stay exactly as it is
        app.auto_resize.set(False)
        app._on_auto_resize_toggled()
        assert load_settings().get("auto_resize") is False, "setting was not saved"
        root.update()
        size_before = (root.winfo_width(), root.winfo_height())
        n_before = len(app.cards)
        app.add_card("scroll")
        root.update()
        assert len(app.cards) == n_before + 1, "scroll simulator was not added"
        assert (root.winfo_width(), root.winfo_height()) == size_before, \
            "window was resized although auto-resize is switched off"
        app.auto_resize.set(True)
        app._on_auto_resize_toggled()
        assert load_settings().get("auto_resize") is True, "setting was not saved"

        # --- manual zoom: percentage typed or picked, and Auto again
        assert parse_zoom("125%") == (True, 1.25) and parse_zoom("150") == (True, 1.5)
        assert parse_zoom("Auto") == (True, None) and parse_zoom("abc")[0] is False and parse_zoom("")[0] is False
        assert parse_zoom("5%") == (True, ZOOM_MIN) and parse_zoom("900") == (True, ZOOM_MAX)
        app.set_zoom_text("125%")
        root.update()
        assert app.manual_zoom == 1.25 and abs(app.zoom - 1.25) < 0.03, "manual zoom was not applied"
        assert app.zoom_var.get() == "125%"
        assert load_settings().get("zoom") == 125 and load_settings().get("auto_resize") is True, "zoom not saved"
        app.set_zoom_text("not a number")
        assert app.zoom_var.get() == "125%", "bad zoom text should revert"
        app.step_zoom(1)
        assert app.manual_zoom == 1.5, "zoom + button"
        app.step_zoom(-1)
        app.step_zoom(-1)
        assert app.manual_zoom == 1.1, "zoom - button"
        app.set_zoom(None)
        root.update()
        assert app.manual_zoom is None and app.zoom_var.get() == "Auto" and load_settings().get("zoom") == "auto"

        # --- scroll simulator card
        sc = app.cards[-1]
        assert isinstance(sc, ScrollCard), "last card should be a scroll simulator"
        sc.nick.set("Test claw")
        sc.equip.set("1m")
        sc.slots.set("3")
        first = sc.sections[0]
        first["kind"].set(SCROLL_KINDS["lesser"][0])
        first["count"].set("2")
        first["cost"].set("100")
        sc.add_section()
        second = sc.sections[1]
        second["kind"].set(SCROLL_KINDS["chaos"][0])
        second["count"].set("1")
        second["cost"].set("500k")
        root.update()
        rep_ = sc.report
        assert rep_ and "error" not in rep_, "scroll report failed: %r" % (rep_,)
        assert rep_["n"] == 3 and abs(rep_["destroyed"] - 0.45) < 1e-9, "wrong scroll odds"
        assert abs(rep_["rows"][2]["exact"] - 0.1) < 1e-9, "wrong chance of 3 successes"
        assert sc.sum_lbls["destroy"].cget("text") == "45.00%", sc.sum_lbls["destroy"].cget("text")
        assert sc.table_rows[2][1].cget("text") == "10.00%", sc.table_rows[2][1].cget("text")
        sc.slots.set("2")
        root.update()
        assert "only 2 slots" in sc.msg.cget("text"), "too many scrolls for the slots should be reported"
        sc.slots.set("3")
        sc.basis.set("atleast")
        root.update()
        assert abs(sc.report["rows"][1]["items"] - 1 / sc.report["rows"][1]["atleast"]) < 1e-9
        # restart rules: lesser, lesser, chaos; restart if scroll 3 fails -> 90% x 50% survive = 45%
        assert sc.sum_lbls["restart"].cget("text") == "—", "no restart rule should show a dash"
        sc.stop_at.set("3")
        root.update()
        assert abs(sc.report["restarted"] - 0.45) < 1e-9, "wrong restart chance: %r" % (sc.report,)
        assert sc.sum_lbls["restart"].cget("text") == "45.00%", sc.sum_lbls["restart"].cget("text")
        # cost / usage breakdown by scroll type: base + each scroll type adds up to the total
        rp = scroll_report({"slots": "", "equip_cost": "20000", "basis": "atleast", "stop_at": "1, 2",
                            "sections": [{"kind": "greater", "count": "1", "cost": "100000"},
                                         {"kind": "intermediate", "count": "4", "cost": "300000"}]})
        assert rp["kinds"] == ["greater", "intermediate"]
        assert abs(rp["by_kind"]["greater"]["used"] - 1.0) < 1e-9
        assert abs(rp["by_kind"]["intermediate"]["used"] - 0.28) < 1e-9, rp["by_kind"]
        for rw in rp["rows"]:
            tot = rw["base"] + sum(rw["kind_cost"].values())
            assert abs(tot - rw["cost"]) < 1e-6 * max(1.0, rw["cost"]), (rw["k"], tot, rw["cost"])
            assert abs(rw["base"] - rw["items"] * 20000) < 1e-6 * max(1.0, rw["base"])
            assert abs(rw["extra"] - (rw["items"] - 1.0)) < 1e-9
        assert sc.bd_frames["cost"].winfo_children(), "breakdown table was not built"
        sc.stop_at.set("0")
        root.update()
        assert "Restart rule" in sc.msg.cget("text"), "a bad scroll number should be reported"
        sc.stop_at.set("")
        sc.stop_streak.set("1")
        root.update()
        assert abs(sc.report["restarted"] - 0.45) < 1e-9, "fails-in-a-row rule"
        sc.stop_streak.set("")
        sc.slots.set("")
        root.update()
        assert "error" not in sc.report and sc.report["slots"] == 3, "blank slots should mean 'as many as used'"
        sc.slots.set("3")
        root.update()
        sc.remove_section(1)
        assert len(sc.sections) == 1, "remove scroll type failed"
        app.move_card(sc, 0)
        assert app.cards[0] is sc and sc.index == 0, "scroll simulator could not be reordered"
        app.commit_now()
        state_now = app.get_state()
        app.undo()
        app.redo()
        assert app.get_state() == state_now, "undo/redo lost the scroll simulator"
        assert isinstance(app.cards[0], ScrollCard), "scroll simulator type lost after undo/redo"

        assert app.save() and os.path.exists(data_file()), "save failed"
        root.update()
    except BaseException:
        msg, code = traceback.format_exc(), 1
    finally:
        messagebox = real_messagebox
        try:
            faulthandler.cancel_dump_traceback_later()
            if hang_log:
                hang_log.close()
        except Exception:
            pass
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(msg)
    except OSError:
        pass
    if code:
        sys.stderr.write(msg)
    return code


def main():
    if any(a in ("--version", "-V") for a in sys.argv[1:]):
        print(f"{APP_NAME} {__version__}")
        return
    if "--selftest" in sys.argv[1:]:
        i = sys.argv.index("--selftest")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "selftest-result.txt"
        sys.exit(selftest(out))
    if sys.platform.startswith("win"):
        try:
            import ctypes
            try:  # lets Windows show our own icon on the taskbar instead of Python's
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HimekoTachibana.ProfitCalculator")
            except Exception:
                pass
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
