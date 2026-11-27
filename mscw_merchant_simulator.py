#!/usr/bin/env python3
"""
MSCW Merchant Simulator
=================
Quickly work out profit when buying, crafting and selling items.
Starts with one item; add as many as you like.

Runs on Windows, macOS and Linux (CachyOS/Arch) using only Python's
built-in Tkinter - nothing to pip install.

How to run
----------
Windows : install Python 3 from python.org (Tcl/Tk is included), then
          double-click this file or run:  python mscw_merchant_simulator.py
          (rename to mscw_merchant_simulator.pyw to hide the console window)
macOS   : install Python 3 from python.org (Homebrew users: brew install python-tk)
          python3 mscw_merchant_simulator.py
CachyOS : sudo pacman -S python tk
          python mscw_merchant_simulator.py

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
import csv
import io
import json
import math
import os
import queue
import re
import sys
import tempfile
import threading
import time
import types
import webbrowser
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk

try:  # the embedded pictures are optional - the app still works without them
    import icons_data
except Exception:  # pragma: no cover
    icons_data = None
try:
    import updater
except Exception:  # pragma: no cover - the app still works without update support
    updater = None
UPDATES_ENABLED = True       # selftest() switches this off so it never touches the network
ICON_PX = getattr(icons_data, "SMALL_SIZE", 32)   # size of the profit picture beside the percentage

__version__ = "1.7.0"   # single source of truth - keep in sync with CHANGELOG.md

APP_NAME = "MSCW Merchant Simulator"
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
ENTRY_FG = "black"
ENTRY_BORDER = "#c8ccd0"
THEME = "light"
THEMES = {
    "light": {"BG_OK": "#ffffff", "BG_RO": "#eceff1", "BG_BAD": "#ffd9d9", "GREEN": "#1a7f37", "RED": "#c62828",
              "AMBER": "#b45309", "MUTED": "#777777", "ENTRY_FG": "black", "ENTRY_BORDER": "#c8ccd0"},
    "dark": {"BG_OK": "#2d333b", "BG_RO": "#22272e", "BG_BAD": "#5c2b2b", "GREEN": "#3fb950", "RED": "#ff7b72",
             "AMBER": "#e3b341", "MUTED": "#9aa4b0", "ENTRY_FG": "#e6edf3", "ENTRY_BORDER": "#444c56"},
}
DARK_UI = {"win": "#1c2128", "fg": "#e6edf3", "btn": "#373e47", "btn_active": "#444c56",
           "border": "#444c56", "dis": "#6e7681", "accent": "#58a6ff"}


def apply_theme(name):
    """Switch the colour constants used when widgets are built ("light" or "dark")."""
    global THEME
    THEME = name if name in THEMES else "light"
    globals().update(THEMES[THEME])
    return THEME


def lighten(color, amount=0.55):
    """'#rrggbb' blended toward white (used so dark-on-light verdict colours stay readable on dark)."""
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(v + (255 - v) * amount) for v in (r, g, b))

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
    "collapsed": False,       # card folded to its title line
    "starred": False,         # starred items sort first
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
    break_even = max(0, math.ceil(cost / (1 - rate) - 1e-9)) if cost > 0 else 0     # lowest price with no loss
    return {"break_even": break_even, "base": base, "scroll_total": scroll_total, "mat_total": mat_total,
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
    out["collapsed"] = d.get("collapsed") is True
    out["starred"] = d.get("starred") is True
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
    "goal": "",               # successes wanted (blank = every scroll succeeds)
    "budget": "",             # optional: what you are willing to spend
    "collapsed": False,
    "starred": False,
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
    goal = parse_int(d.get("goal", ""), 0, MAX_SLOTS)
    if goal is None or goal > n:
        return {"error": f"Goal must be a whole number from 1 to {n} (or blank = all {n})."}
    budget = parse_num(d.get("budget", ""))
    if budget is None:
        return {"error": "Budget is not a valid number."}
    finished, destroyed, restarted, used = scroll_sim([(p, q) for p, q, _ in seq], streak, total, positions)
    scroll_cost = sum(cost * u for (_, _, cost), u in zip(seq, used))
    per_item = equip + scroll_cost
    kinds, by_kind = [], {}                    # per base item: scrolls of each type used, and what they cost
    for kind, (_, _, cost), u in zip(kinds_seq, seq, used):
        if kind not in by_kind:
            by_kind[kind] = {"used": 0.0, "cost": 0.0, "succ": 0.0}
            kinds.append(kind)
        by_kind[kind]["used"] += u
        by_kind[kind]["cost"] += cost * u
        by_kind[kind]["succ"] += SCROLL_KINDS[kind][1] * u       # successes of this type per base item

    def times(items, x):                       # items may be infinity; 0 stays 0
        return 0.0 if x == 0 else items * x

    per_success = {}                           # per success of one scroll type, added up over base items
    for kd in kinds:
        b = by_kind[kd]
        items = 1.0 / b["succ"] if b["succ"] > 1e-15 else math.inf
        per_success[kd] = {"items": items,
                           "scrolls": times(items, b["used"]),
                           "base_cost": times(items, equip),
                           "scroll_cost": times(items, b["cost"])}
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

    kk = goal or n                             # the number of successes the goal section talks about
    grow = rows[kk - 1]
    pg = grow["exact"] if d.get("basis") == "exact" else grow["atleast"]

    def within(q):                             # base items needed so that you get there with chance q
        if pg >= 1 - 1e-12:
            return 1.0
        if pg <= 1e-15:
            return math.inf
        return float(max(1, math.ceil(math.log(1 - q) / math.log(1 - pg) - 1e-9)))
    i50, i90 = within(0.5), within(0.9)
    info = {"k": kk, "given": bool(goal), "p": pg, "items": grow["items"], "cost": grow["cost"],
            "items50": i50, "cost50": times(i50, per_item), "items90": i90, "cost90": times(i90, per_item),
            "budget": budget, "afford": None, "budget_chance": None}
    if budget > 0 and per_item > 0:
        afford = int(math.floor(budget / per_item + 1e-9))
        info["afford"] = afford
        info["budget_chance"] = 0.0 if afford <= 0 else (1.0 if pg >= 1 - 1e-12 else 1 - (1 - pg) ** afford)
    word = "success" if kk == 1 else "successes"
    if grow["items"] == math.inf:
        summary = f"{kk} {word} cannot be reached with these scrolls."
    else:
        summary = (f"For {kk} {word}: about {fmt_items(grow['items'])} base items and {short_num(grow['cost'])} "
                   f"in total (9 times in 10 under {short_num(info['cost90'])}).")
    return {"goal": info, "summary": summary, "n": n, "slots": slots, "zero": finished[0], "destroyed": destroyed, "restarted": restarted,
            "rules": rules, "equip": equip, "scroll_cost": scroll_cost, "per_item": per_item,
            "avg_used": sum(used), "kinds": kinds, "by_kind": by_kind,
            "per_success": per_success, "rows": rows}


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
    for k in ("nickname", "equip_cost", "slots", "stop_streak", "stop_total", "stop_at", "goal", "budget"):
        if isinstance(d.get(k), str):
            out[k] = d[k]
    out["collapsed"] = d.get("collapsed") is True
    out["starred"] = d.get("starred") is True
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
    new = os.path.join(base, "MSCW Merchant Simulator")
    old = os.path.join(base, "ProfitCalculator")          # folder used before the rename (before 1.6.0)
    if not os.path.isdir(new) and os.path.isdir(old):
        try:                                              # keep the user's saved cards and settings
            import shutil
            shutil.copytree(old, new)
        except OSError:
            pass
    return os.path.join(new, "entries.json")


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
    wide_capable = False         # True: may spread over two columns (see ScrollCard)
    span = 1                     # columns the card covers right now

    def set_wide(self, wide):
        """Called by the layout; only cards that are wide_capable change their look."""

    def __init__(self, parent, app, index):
        super().__init__(parent, padding=(12, 10), relief="groove", borderwidth=2)
        self.app = app
        self.index = index
        self._updating = False
        self._drag_target = None
        self.entries = []        # (entry, var, kind) for the fixed fields
        self.collapsed = False   # folded to its title line
        self.starred = False     # starred items come first when sorting
        self._summary = ""       # short text shown on the title line while folded
        self.body = None
        self.last = None         # latest calculation result (item cards only)

    # ---- widgets ---------------------------------------------------------- #
    def _entry(self, parent, var, kind, width=14, store=None, bold=False):
        kw = {}
        if bold:
            kw["font"] = self.app.f_bold
        e = tk.Entry(parent, textvariable=var, width=width,
                     justify="left" if kind == "text" else "right",
                     relief="solid", bd=1, bg=BG_OK, fg=ENTRY_FG,
                     readonlybackground=BG_RO, insertbackground=ENTRY_FG,
                     disabledforeground=ENTRY_FG, highlightthickness=1,
                     highlightbackground=ENTRY_BORDER, highlightcolor="#3b82f6", **kw)
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
        row2 = ttk.Frame(head)                       # star, duplicate, fold - and a summary while folded
        row2.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(4, 0))
        row2.columnconfigure(3, weight=1)
        self.star_btn = ttk.Button(row2, text="\u2606", width=3, command=self.toggle_star)
        self.star_btn.grid(row=0, column=0)
        self.dup_btn = ttk.Button(row2, text="Duplicate", width=9, command=lambda: self.app.duplicate_card(self))
        self.dup_btn.grid(row=0, column=1, padx=(4, 0))
        self.fold_btn = ttk.Button(row2, text="Collapse", width=9, command=self.toggle_collapse)
        self.fold_btn.grid(row=0, column=2, padx=(4, 0))
        self.sum_lbl = ttk.Label(row2, text="", style="Muted.TLabel", anchor="e")
        self.sum_lbl.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.head = head

    def _bind_recall(self, entry):
        """Leaving the nickname box fills in prices remembered for that name (if the price boxes are empty)."""
        entry.bind("<FocusOut>", lambda e: self.app.recall_price(self), add="+")

    def toggle_star(self):
        self.app.commit_now()
        self.starred = not self.starred
        self._apply_flags()
        self._update_title()
        self.app.commit_now()

    def toggle_collapse(self):
        self.app.commit_now()
        self.collapsed = not self.collapsed
        self._apply_flags()
        self.app.commit_now()
        self.app.autosize()

    def _apply_flags(self):
        self.star_btn.config(text="\u2605" if self.starred else "\u2606")
        self.fold_btn.config(text="Expand" if self.collapsed else "Collapse")
        if self.body is not None:
            if self.collapsed:
                self.body.grid_remove()
            else:
                self.body.grid()
        self.sum_lbl.config(text=self._summary if self.collapsed else "")

    def _set_summary(self, text):
        self._summary = text
        if self.collapsed:
            self.sum_lbl.config(text=text)

    def _load_flags(self, d):
        self.collapsed, self.starred = bool(d.get("collapsed")), bool(d.get("starred"))
        self._apply_flags()

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
        self.title_lbl.config(text=("\u2605 " if self.starred else "")
                              + f"{self.kind_label} {self.index + 1}" + (f" — {nick}" if nick else ""))

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
        self.last = None         # result of the latest calculation (None while a field is invalid)
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
        self.body = body
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
        self._bind_recall(self.entries[-1][0])
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
        self.be_lbl = result("Break-even sale price")
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
            "collapsed": self.collapsed,
            "starred": self.starred,
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
        self._load_flags(d)
        self._update_title()

    def recall(self, mem):
        """Fill in remembered prices, but only into boxes that are still empty."""
        if mem.get("base") and not self.base.get().strip():
            self.base.set(mem["base"])
        if mem.get("scroll_price") and not self.sprice.get().strip():
            self.sprice.set(mem["scroll_price"])

    def price_memory(self):
        out = {}
        for key, var in (("base", self.base), ("scroll_price", self.sprice)):
            t = var.get().strip()
            if t and parse_num(t) is not None:
                out[key] = t
        return out

    def sort_key(self):
        """Starred first, then the best profit % first; items without a result last."""
        roi = self.last["roi"] if self.last and self.last["roi"] is not None else -math.inf
        return (0 if self.starred else 1, -roi)

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
        self.reward_title.config(text="" if tier is NEUTRAL_TIER else title,
                                 foreground=lighten(fg) if THEME == "dark" else fg)

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
            self.last = None
            self._set_summary("")
            self.total.set("—")
            self.breakdown.config(text="")
            for lbl in (self.be_lbl, self.tax_lbl, self.net_lbl, self.roi_lbl):
                lbl.config(text="—")
            self.profit_lbl.config(text="Check red fields", foreground=RED)
            self._set_reward(NEUTRAL_TIER)
            return

        r = compute(st)
        self.last = r
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

        self.be_lbl.config(text=fmt_num(r["break_even"]) if r["cost"] > 0 else "—")
        self.tax_lbl.config(text=fmt_num(r["tax"]))
        self.net_lbl.config(text=fmt_num(r["net"]))
        p = r["profit"]
        color = GREEN if p > 0.005 else RED if p < -0.005 else self.app.default_fg
        self.profit_lbl.config(text=("+" if p > 0.005 else "") + fmt_num(p), foreground=color)
        roi = r["roi"]
        self.roi_lbl.config(text="—" if roi is None else f"{roi:,.2f}%")
        self._set_reward(tier_for(roi))
        self._set_summary("" if r["cost"] <= 0 else
                          f"{'+' if p > 0.005 else ''}{short_num(p)}" + ("" if roi is None else f"  ({roi:,.1f}%)"))


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
        self.goal, self.budget, self.view = V(), V(), V(value="cost")
        self.sections = []       # [{"kind": StringVar (list text), "count": StringVar, "cost": StringVar}]
        self.sec_entries = []    # entries of the scroll rows (rebuilt often)
        self.report = None
        for v in (self.nick, self.equip, self.slots, self.basis, self.goal, self.budget,
                  self.stop_streak, self.stop_total, self.stop_at):
            v.trace_add("write", self._on_var)
        self.view.trace_add("write", self._on_view)
        self._build()
        self.load_state(state)

    # ---- widgets ---------------------------------------------------------- #
    def _build(self):
        app = self.app
        self.columnconfigure(0, weight=1)
        self._build_header()

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.body = body
        left, right = ttk.Frame(body), ttk.Frame(body)   # inputs + results | tables
        self.left, self.right = left, right
        self.vsep = ttk.Separator(body, orient="vertical")
        for f in (left, right):
            f.columnconfigure(1, weight=1)
        left.grid(row=0, column=0, sticky="nsew")
        right.grid(row=1, column=0, sticky="nsew", pady=(8, 0))   # narrow layout: tables underneath
        self.wide, self.span = False, 1
        self._grids = {}                                 # name -> label grid of the small result tables
        self.bd_titles, self.bd_frames = [], {}
        cur = {"f": left, "r": 0}                        # the frame and row being filled

        def field(text, var, kind):
            f, r = cur["f"], cur["r"]
            ttk.Label(f, text=text).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 8))
            self._entry(f, var, kind).grid(row=r, column=1, sticky="ew", pady=2)
            cur["r"] += 1

        def note(text):
            lbl = ttk.Label(cur["f"], text=text, style="Muted.TLabel", justify="left",
                            wraplength=int(300 * app.scale))
            lbl.grid(row=cur["r"], column=0, columnspan=2, sticky="w")
            self.notes.append(lbl)
            cur["r"] += 1

        def sep():
            ttk.Separator(cur["f"]).grid(row=cur["r"], column=0, columnspan=2, sticky="ew", pady=4)
            cur["r"] += 1

        def section(text):
            ttk.Label(cur["f"], text=text, style="Section.TLabel").grid(
                row=cur["r"], column=0, columnspan=2, sticky="w", pady=(0, 3))
            cur["r"] += 1

        def place(widget, **kw):
            widget.grid(row=cur["r"], column=0, columnspan=2, **kw)
            cur["r"] += 1

        self.notes = []
        field("Equipment", self.nick, "text")
        self._bind_recall(self.entries[-1][0])
        pair = ttk.Frame(left)                       # cost and slots share one line
        pair.columnconfigure(1, weight=1)
        ttk.Label(pair, text="Cost").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._entry(pair, self.equip, "cost").grid(row=0, column=1, sticky="ew")
        ttk.Label(pair, text=f"Slots (0-{MAX_SLOTS}, blank = auto)").grid(row=0, column=2, sticky="w", padx=(12, 8))
        self._entry(pair, self.slots, "int", width=4).grid(row=0, column=3)
        place(pair, sticky="ew", pady=1)
        sep()

        self.sec_head = ttk.Frame(left)              # "Scrolls used" with the add button on the same line
        self.sec_head.columnconfigure(0, weight=1)
        ttk.Label(self.sec_head, text="Scrolls used", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.add_btn = None
        place(self.sec_head, sticky="ew", pady=(0, 2))
        self.sec_frame = ttk.Frame(left)
        place(self.sec_frame, sticky="ew")
        pr = ttk.Frame(left)
        self.preset_btn = ttk.Button(pr, text="Presets \u25be", command=self.show_presets)
        self.preset_btn.pack(side="left")
        ttk.Label(pr, text="save and reuse a mix of scrolls and rules", style="Muted.TLabel").pack(
            side="left", padx=(8, 0))
        place(pr, sticky="w", pady=(2, 0))
        note("Used top to bottom; every scroll uses 1 slot, pass or fail.")
        sep()

        section("Restart with a new item when")
        rs = ttk.Frame(left)
        rs.columnconfigure(1, weight=1)
        rs.columnconfigure(3, weight=1)
        ttk.Label(rs, text="Fails in a row").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=1)
        self._entry(rs, self.stop_streak, "int", width=5).grid(row=0, column=1, sticky="ew", pady=1)
        ttk.Label(rs, text="Fails in total").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=1)
        self._entry(rs, self.stop_total, "int", width=5).grid(row=0, column=3, sticky="ew", pady=1)
        ttk.Label(rs, text="Any of these scrolls fails (e.g. 1, 2 or 1-3)").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=1)
        self._entry(rs, self.stop_at, "list", width=8).grid(row=1, column=3, sticky="ew", pady=1)
        place(rs, sticky="ew")
        note("Blank = never restart. Restarting stops scrolling that item and starts a new one.")
        sep()

        section("Results")
        self.sum_lbls = {}
        grid = ttk.Frame(left)                       # two columns of label + value
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
        place(grid, sticky="ew")
        self.msg = ttk.Label(left, text="", justify="left", wraplength=int(300 * app.scale))
        place(self.msg, sticky="w", pady=(2, 0))
        self.summary_lbl = ttk.Label(left, text="", justify="left", font=app.f_bold,
                                     wraplength=int(300 * app.scale))
        place(self.summary_lbl, sticky="w", pady=(2, 0))
        self.notes.append(self.summary_lbl)
        gl = ttk.Label(left, text="Goal and budget", style="Section.TLabel")
        place(gl, sticky="w", pady=(8, 0))
        gf = ttk.Frame(left)
        gf.columnconfigure(1, weight=1)
        gf.columnconfigure(3, weight=1)
        ttk.Label(gf, text="Successes wanted").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=1)
        self._entry(gf, self.goal, "int", width=5).grid(row=0, column=1, sticky="ew", pady=1)
        ttk.Label(gf, text="Budget").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=1)
        self._entry(gf, self.budget, "cost", width=10).grid(row=0, column=3, sticky="ew", pady=1)
        place(gf, sticky="ew")
        self.goal_lbls = {}
        gg = ttk.Frame(left)
        gg.columnconfigure(1, weight=1)
        for idx, (key, text) in enumerate((("avg", "On average"), ("p50", "Half the time within"),
                                           ("p90", "9 times in 10 within"), ("budget", "Chance within budget"))):
            ttk.Label(gg, text=text).grid(row=idx, column=0, sticky="w", pady=1, padx=(0, 8))
            lbl = ttk.Label(gg, text="\u2014", anchor="e")
            lbl.grid(row=idx, column=1, sticky="e", pady=1)
            self.goal_lbls[key] = lbl
        place(gg, sticky="ew")
        note("Blank = every scroll succeeds. The percentages assume each base item costs its average "
             "(so the costs are close, not exact).")
        self.send_btn = ttk.Button(left, text="Send to item card", command=self.send_to_item)
        place(self.send_btn, sticky="w", pady=(4, 0))
        tl = ttk.Label(left, text="Per scroll success (successes of one scroll type)", style="Section.TLabel")
        place(tl, sticky="w", pady=(8, 0))
        fr = ttk.Frame(left)
        place(fr, sticky="ew", pady=(2, 0))
        self.bd_titles.append(tl)
        self.bd_frames["per"] = fr
        note("Base items and scrolls it takes, added up over items, for 1 success of that scroll "
             "type (x N for N). Items lost along the way are included.")
        self.per_note = self.notes[-1]

        cur["f"], cur["r"] = right, 0                # ---- right half: the tables
        head = ttk.Frame(right)                      # title, then the exact/at-least choice on one line
        ttk.Label(head, text="Successes", style="Section.TLabel").pack(side="left")
        ttk.Radiobutton(head, text="Avg for exactly N", value="exact", variable=self.basis).pack(
            side="right")
        ttk.Radiobutton(head, text="Avg for at least N", value="atleast", variable=self.basis).pack(
            side="right", padx=(0, 10))
        place(head, sticky="ew")

        self.table = ttk.Frame(right)
        place(self.table, sticky="ew", pady=(4, 0))
        for c in range(5):
            self.table.columnconfigure(c, weight=1, uniform="scroll_table")
        for c, text in enumerate(("Successes", "Exactly", "At least", "Base items", "Duplicates")):
            ttk.Label(self.table, text=text, style="Section.TLabel", anchor="e").grid(
                row=0, column=c, sticky="e", padx=(0, 6))
        self.table_rows = []
        tabs = ttk.Frame(right)
        ttk.Radiobutton(tabs, text="Cost table", value="cost", variable=self.view).pack(side="left")
        ttk.Radiobutton(tabs, text="Scrolls used table", value="used", variable=self.view).pack(
            side="left", padx=(10, 0))
        place(tabs, sticky="w", pady=(8, 0))
        for name, title in (("cost", "Cost to get N successes (base items + scrolls)"),
                            ("used", "Scrolls used to get N successes")):
            tl = ttk.Label(right, text=title, style="Section.TLabel")
            place(tl, sticky="w", pady=(8, 0))
            fr = ttk.Frame(right)
            place(fr, sticky="ew", pady=(2, 0))
            self.bd_titles.append(tl)
            self.bd_frames[name] = fr
        self.table_note = ttk.Label(right, text="", style="Muted.TLabel", justify="left",
                                    wraplength=int(300 * app.scale))
        place(self.table_note, sticky="w", pady=(4, 0))
        self.notes.append(self.table_note)
        for k in range(1, MAX_SLOTS + 1):
            labels = []
            for c in range(5):
                lbl = ttk.Label(self.table, text="", anchor="e")
                lbl.grid(row=k, column=c, sticky="e", padx=(0, 6), pady=0)
                labels.append(lbl)
            self.table_rows.append(labels)

    wide_capable = True

    def set_wide(self, wide):
        """Two halves side by side when the layout gives this card two columns, else stacked."""
        if wide == self.wide:
            return
        self.wide, self.span = wide, 2 if wide else 1
        if wide:
            self.body.columnconfigure(0, weight=1, uniform="halves")
            self.body.columnconfigure(2, weight=1, uniform="halves")
            self.left.grid(row=0, column=0, sticky="nsew")
            self.vsep.grid(row=0, column=1, sticky="ns", padx=10)
            self.right.grid(row=0, column=2, columnspan=1, sticky="nsew", pady=0)
        else:
            self.vsep.grid_remove()
            self.body.columnconfigure(0, weight=1, uniform="")
            self.body.columnconfigure(2, weight=0, uniform="")
            self.right.grid(row=1, column=0, columnspan=1, sticky="nsew", pady=(8, 0))

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
            "goal": self.goal.get(),
            "budget": self.budget.get(),
            "collapsed": self.collapsed,
            "starred": self.starred,
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
            self.goal.set(d["goal"])
            self.budget.set(d["budget"])
            self.sections = []
            for sec in d["sections"]:
                self._add_section_vars(sec["kind"], sec["count"], sec["cost"])
        finally:
            self._updating = False
        self._rebuild_sections()
        self.recalc()
        self._load_flags(d)
        self._update_title()

    def has_data(self):
        if any(v.get().strip() for v in (self.nick, self.equip, self.slots, self.goal, self.budget,
                                         self.stop_streak, self.stop_total, self.stop_at)):
            return True
        return len(self.sections) > 1 or any(
            sec["count"].get().strip() or sec["cost"].get().strip() for sec in self.sections)

    def on_zoom(self):
        wrap = int(300 * self.app.scale * self.app.zoom)
        for lbl in self.notes + [self.msg]:
            lbl.config(wraplength=wrap)

    def recall(self, mem):
        if mem.get("base") and not self.equip.get().strip():
            self.equip.set(mem["base"])

    def price_memory(self):
        t = self.equip.get().strip()
        return {"base": t} if t and parse_num(t) is not None else {}

    def sort_key(self):
        return (0 if self.starred else 1, 0)

    def _on_view(self, *_):
        self._apply_view()
        if not self.app.suspend and not self._updating:
            self.app.autosize()

    def _apply_view(self):
        """Show the cost table or the scrolls-used table (the tabs), not both."""
        show = self.view.get()
        for name, title in (("cost", self.bd_titles[1]), ("used", self.bd_titles[2])):
            if self.report is None or "error" in self.report or name != show:
                title.grid_remove()
                self.bd_frames[name].grid_remove()
            else:
                title.grid()
                self.bd_frames[name].grid()

    # ---- presets ---------------------------------------------------------- #
    def show_presets(self):
        presets = self.app.presets()
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Save the current scrolls and rules as a preset...", command=self.save_preset)
        m.add_separator()
        names = sorted(presets, key=str.lower)
        if names:
            for name in names:
                m.add_command(label=name, command=lambda n=name: self.apply_preset(n))
            m.add_separator()
            dm = tk.Menu(m, tearoff=0)
            for name in names:
                dm.add_command(label=name, command=lambda n=name: self.app.delete_preset(n))
            m.add_cascade(label="Delete a preset", menu=dm)
        else:
            m.add_command(label="No presets saved yet", state="disabled")
        x = self.preset_btn.winfo_rootx()
        y = self.preset_btn.winfo_rooty() + self.preset_btn.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def preset_data(self):
        st = self.get_state()
        return {k: st[k] for k in ("slots", "sections", "stop_streak", "stop_total", "stop_at")}

    def save_preset(self):
        name = simpledialog.askstring(APP_NAME, "Name for this preset (scrolls, costs and restart rules):",
                                      parent=self.winfo_toplevel())
        if name and name.strip():
            self.app.save_preset(name.strip()[:40], self.preset_data())

    def apply_preset(self, name):
        data = self.app.presets().get(name)
        if not data:
            return
        self.app.commit_now()
        self.load_state({**self.get_state(), **data})
        self.app.commit_now()
        self.app.autosize()

    # ---- send to an item card -------------------------------------------- #
    def send_to_item(self):
        rep_ = self.report
        if not rep_ or "error" in rep_:
            messagebox.showinfo(APP_NAME, "Fill in the scroll simulator first.", parent=self.winfo_toplevel())
            return
        k = rep_["goal"]["k"]
        row = rep_["rows"][k - 1]
        if math.isinf(row["cost"]):
            messagebox.showinfo(APP_NAME, f"{k} success{'' if k == 1 else 'es'} cannot be reached with these "
                                "scrolls, so there is no cost to send.", parent=self.winfo_toplevel())
            return
        name = self.nick.get().strip() or "Equipment"
        st = default_state("profit")
        st.update({"nickname": f"{name} +{k}",
                   "base": fmt_num(round(row["base"])) if row["base"] else "",
                   "scrolls": "1",
                   "scroll_price": fmt_num(round(row["cost"] - row["base"]))})
        self.app.insert_card(self.index + 1, st)

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
            self.per_note.grid_remove()
            self.summary_lbl.config(text="")
            for lbl in self.goal_lbls.values():
                lbl.config(text="\u2014")
            self._set_summary("")
            return
        self.msg.config(text="", foreground=MUTED)
        self.summary_lbl.config(text=rep["summary"])
        g = rep["goal"]
        self.goal_lbls["avg"].config(text=f"{fmt_items(g['items'])} items \u00b7 {short_num(g['cost'])}")
        self.goal_lbls["p50"].config(text=f"{fmt_items(g['items50'])} items \u00b7 {short_num(g['cost50'])}")
        self.goal_lbls["p90"].config(text=f"{fmt_items(g['items90'])} items \u00b7 {short_num(g['cost90'])}")
        if g["budget_chance"] is not None:
            self.goal_lbls["budget"].config(text=f"{fmt_chance(g['budget_chance'])} ({g['afford']} items)")
        else:
            self.goal_lbls["budget"].config(text="\u2014")
        self._set_summary("" if math.isinf(g["cost"]) else f"{g['k']} succ.: {short_num(g['cost'])}")
        n = rep["n"]
        self.sum_lbls["slots"].config(text=f"{n} of {rep['slots']}")
        self.sum_lbls["destroy"].config(text=fmt_chance(rep["destroyed"]))
        self.sum_lbls["restart"].config(text=fmt_chance(rep["restarted"]) if rep["rules"] else "—")
        self.sum_lbls["zero"].config(text=fmt_chance(rep["zero"]))
        self.sum_lbls["avg_used"].config(text=f"{rep['avg_used']:.2f}")
        self.sum_lbls["scroll_cost"].config(text=fmt_money(rep["scroll_cost"]))
        basis = "exactly" if self.basis.get() == "exact" else "at least"
        self.table_note.config(text=(
            f"Base items = copies of the base item you buy on average to get one with {basis} that many "
            "successes (counting the finished one); Duplicates = the others, which fail"
            + (", are destroyed or restart" if rep["rules"] or rep["destroyed"] > 0 else "")
            + ". The tables above price those copies and the scrolls used on all of them."))
        self.bd_titles[0].grid()
        kinds = rep["kinds"]
        per = rep["by_kind"]
        head_cost = ["Successes", "Base items"] + [kind_header(k) for k in kinds] + ["Total"]
        rows_cost = [["1 item", short_num(rep["equip"])] + [short_num(per[k]["cost"]) for k in kinds]
                     + [short_num(rep["per_item"])]]
        head_used = ["Successes", "Base items"] + [kind_header(k) for k in kinds] + ["All scrolls"]
        rows_used = [["1 item", "1"] + [fmt_items(per[k]["used"]) for k in kinds] + [fmt_items(rep["avg_used"])]]
        for row in rep["rows"]:
            rows_cost.append([str(row["k"]), short_num(row["base"])]
                             + [short_num(row["kind_cost"][k]) for k in kinds] + [short_num(row["cost"])])
            rows_used.append([str(row["k"]), fmt_items(row["items"])] + [fmt_items(row["kind_used"][k]) for k in kinds]
                             + [fmt_items(sum(row["kind_used"].values()))])
        rows_per = [[f"{SCROLL_SHORT[k]} {round(SCROLL_KINDS[k][1] * 100)}%",
                     fmt_items(rep["per_success"][k]["items"]), fmt_items(rep["per_success"][k]["scrolls"]),
                     short_num(rep["per_success"][k]["base_cost"]),
                     short_num(rep["per_success"][k]["scroll_cost"])] for k in kinds]
        self._fill_grid("per", ["Scroll", "Base items", "Scrolls used", "Base cost", "Scroll cost"], rows_per)
        self.per_note.grid()
        self._fill_grid("cost", head_cost, rows_cost)
        self._fill_grid("used", head_used, rows_used)
        self._apply_view()
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


def changelog_lines(text):
    """CHANGELOG.md -> [(tag, text)] for the What's new window: headings, bullets and plain lines."""
    out = []
    for raw in text.splitlines():
        line = raw.rstrip().replace("**", "")
        if not line.strip() or line.startswith("# ") or re.match(r"^\[[^\]]+\]: ", line):
            continue
        if line.startswith("## "):
            out.append(("h2", line[3:]))
        elif line.startswith("### "):
            out.append(("h3", line[4:]))
        elif line.lstrip().startswith("- "):
            out.append(("bullet", "\u2022 " + line.lstrip()[2:]))
        elif line.startswith(" "):
            out.append(("cont", line.strip()))
        else:
            out.append(("", line))
    return out


def export_text(state):
    """The results of every card as plain text (for pasting into chat or notes)."""
    lines = [f"{APP_NAME} v{__version__} - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for i, raw in enumerate(state.get("items", []), 1):
        it = sanitize_card(raw)
        name = it["nickname"].strip()
        if it["type"] == "scroll":
            head = f"Scrolls {i}" + (f" - {name}" if name else "")
            rep_ = scroll_report(it)
            if "error" in rep_:
                lines += [head + ": (not filled in)", ""]
                continue
            lines += [head, "  " + rep_["summary"],
                      f"  Average cost of one base item with its scrolls: {fmt_money(rep_['per_item'])}", ""]
        else:
            head = f"Item {i}" + (f" - {name}" if name else "")
            r = compute(it)
            if r["cost"] <= 0 and r["sale"] <= 0:
                lines += [head + ": (empty)", ""]
                continue
            pct = "" if r["roi"] is None else f" ({r['roi']:,.2f}%)"
            lines += [head, f"  Total cost: {fmt_num(r['cost'])}",
                      f"  Break-even sale price: {fmt_num(r['break_even'])}",
                      f"  Sale price: {fmt_num(r['sale'])}  (tax {round(r['rate'] * 100)}%: {fmt_num(r['tax'])})",
                      f"  You receive: {fmt_num(r['net'])}",
                      f"  Profit: {fmt_num(r['profit'])}{pct}", ""]
    return "\n".join(lines).rstrip() + "\n"


def export_csv(state):
    """The results of every card as CSV text: one table for the items, one block per scroll simulator."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["Item", "Name", "Total cost", "Break-even price", "Sale price", "Tax rate", "Tax paid",
                "You receive", "Profit", "Profit %"])
    scrolls = []
    for i, raw in enumerate(state.get("items", []), 1):
        it = sanitize_card(raw)
        if it["type"] == "scroll":
            scrolls.append((i, it))
            continue
        r = compute(it)
        if r["cost"] <= 0 and r["sale"] <= 0:
            continue
        w.writerow([i, it["nickname"].strip(), round(r["cost"], 2), r["break_even"], round(r["sale"], 2),
                    f"{round(r['rate'] * 100)}%", round(r["tax"], 2), round(r["net"], 2), round(r["profit"], 2),
                    "" if r["roi"] is None else round(r["roi"], 2)])
    for i, it in scrolls:
        rep_ = scroll_report(it)
        if "error" in rep_:
            continue
        w.writerow([])
        w.writerow([f"Scroll simulator {i}", it["nickname"].strip(), "cost of 1 base item with scrolls",
                    round(rep_["per_item"], 2)])
        w.writerow(["Successes", "Exactly", "At least", "Base items", "Total cost"])
        for row in rep_["rows"]:
            w.writerow([row["k"], round(row["exact"], 6), round(row["atleast"], 6),
                        "" if math.isinf(row["items"]) else round(row["items"], 2),
                        "" if math.isinf(row["cost"]) else round(row["cost"], 2)])
    return out.getvalue()


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
        apply_theme(_cfg.get("theme", "light"))
        self.theme_var = tk.StringVar(master=root, value=THEME)
        self.remember_prices = tk.BooleanVar(master=root, value=bool(_cfg.get("remember_prices", True)))
        self.prices = {}                                 # nickname (lower case) -> remembered prices
        if isinstance(_cfg.get("prices"), dict):
            for k, v in _cfg["prices"].items():
                if isinstance(k, str) and isinstance(v, dict):
                    self.prices[k] = {a: b for a, b in v.items() if a in ("base", "scroll_price") and isinstance(b, str)}
        self._prices_saved = json.dumps(self.prices, sort_keys=True)
        self.auto_resize = tk.BooleanVar(master=root, value=bool(_cfg.get("auto_resize", False)))
        _ok, _z = parse_zoom(_cfg.get("zoom", "auto"))
        self.manual_zoom = _z if _ok else None          # None = Auto (fit the window)
        self.zoom_var = tk.StringVar(master=root, value=zoom_label(self.manual_zoom))
        self.check_updates = tk.BooleanVar(master=root, value=bool(_cfg.get("check_updates", True)))
        self.auto_install = tk.BooleanVar(master=root, value=bool(_cfg.get("auto_install", False)))
        self._update_busy = False
        self._changelog_win = None

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
        if updater is not None and UPDATES_ENABLED and self.check_updates.get():
            root.after(3000, lambda: self.check_for_updates(manual=False))      # quietly, in the background

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
        if THEME == "dark":
            self._dark_style(style)
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

    def _dark_style(self, style):
        """Colours for the dark theme (the plain 'clam' theme is the one that can be recoloured everywhere)."""
        u = DARK_UI
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.configure(bg=u["win"])
        style.configure(".", background=u["win"], foreground=u["fg"], fieldbackground=BG_OK,
                        bordercolor=u["border"], lightcolor=u["win"], darkcolor=u["win"],
                        troughcolor=BG_RO, focuscolor=u["win"], insertcolor=u["fg"])
        style.configure("TButton", background=u["btn"], foreground=u["fg"], padding=3)
        style.map("TButton", background=[("disabled", u["win"]), ("active", u["btn_active"])],
                  foreground=[("disabled", u["dis"])])
        style.configure("TCombobox", fieldbackground=BG_OK, background=u["btn"], foreground=ENTRY_FG,
                        arrowcolor=u["fg"])
        style.map("TCombobox", fieldbackground=[("readonly", BG_OK)], foreground=[("readonly", ENTRY_FG)],
                  background=[("active", u["btn_active"])])
        style.configure("TRadiobutton", background=u["win"], foreground=u["fg"])
        style.map("TRadiobutton", background=[("active", u["win"])],
                  indicatorcolor=[("selected", u["accent"]), ("!selected", BG_OK)])
        style.configure("TScrollbar", background=u["btn"], troughcolor=u["win"], arrowcolor=u["fg"])
        style.configure("TSeparator", background=u["border"])
        try:
            self.root.option_add("*TCombobox*Listbox.background", BG_OK)
            self.root.option_add("*TCombobox*Listbox.foreground", ENTRY_FG)
        except tk.TclError:
            pass

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
        self.totals_bar = ttk.Frame(self.root, padding=(10, 4))   # totals over all items + the sort button
        self.totals_bar.pack(side="top", fill="x")
        self.sort_btn = ttk.Button(self.totals_bar, text="Sort by profit %", command=self.sort_cards)
        self.sort_btn.pack(side="right")
        self.totals = ttk.Label(self.totals_bar, text="", style="Muted.TLabel")
        self.totals.pack(side="left")
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
        self.sets_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Sets", menu=self.sets_menu)
        self._rebuild_sets_menu()
        export = tk.Menu(menubar, tearoff=0)
        export.add_command(label="Copy results as text", command=self.copy_text)
        export.add_command(label="Save results as CSV (opens in Excel)...", command=self.save_csv)
        menubar.add_cascade(label="Export", menu=export)
        settings = tk.Menu(menubar, tearoff=0)
        settings.add_checkbutton(label="Auto-resize window when adding or removing items",
                                 variable=self.auto_resize, command=self._on_auto_resize_toggled)
        zoom_menu = tk.Menu(settings, tearoff=0)
        for label in ["Auto"] + [f"{p}%" for p in ZOOM_PRESETS]:
            zoom_menu.add_radiobutton(label="Auto (fit the window)" if label == "Auto" else label,
                                      variable=self.zoom_var, value=label,
                                      command=lambda v=label: self.set_zoom_text(v))
        settings.add_cascade(label="Zoom", menu=zoom_menu)
        theme_menu = tk.Menu(settings, tearoff=0)
        for label, value in (("Light", "light"), ("Dark", "dark")):
            theme_menu.add_radiobutton(label=label, variable=self.theme_var, value=value,
                                       command=self._on_theme_changed)
        settings.add_cascade(label="Theme (applies after restart)", menu=theme_menu)
        settings.add_checkbutton(label="Remember prices by nickname", variable=self.remember_prices,
                                 command=self._on_update_settings)
        settings.add_separator()
        settings.add_command(label="What's new (changelog)...", command=self.show_changelog)
        settings.add_separator()
        settings.add_command(label=f"Check for updates now (you have v{__version__})",
                             command=lambda: self.check_for_updates(manual=True))
        settings.add_checkbutton(label="Check for updates when the app starts",
                                 variable=self.check_updates, command=self._on_update_settings)
        settings.add_checkbutton(label="Install updates automatically (no question asked)",
                                 variable=self.auto_install, command=self._on_update_settings)
        menubar.add_cascade(label="Settings", menu=settings)
        self.root.config(menu=menubar)

    def _on_update_settings(self):
        save_settings({"check_updates": bool(self.check_updates.get()),
                       "auto_install": bool(self.auto_install.get()),
                       "remember_prices": bool(self.remember_prices.get())})

    def _on_theme_changed(self):
        save_settings({"theme": self.theme_var.get()})
        if self.theme_var.get() != THEME:
            messagebox.showinfo(APP_NAME, "The new theme is used the next time you start the app.",
                                parent=self.root)

    # ---- sets (named groups of cards) ------------------------------------- #
    def sets(self):
        data = load_settings().get("sets")
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} \
            if isinstance(data, dict) else {}

    def _rebuild_sets_menu(self):
        m = self.sets_menu
        m.delete(0, "end")
        m.add_command(label="Save the current cards as a set...", command=self.save_set)
        names = sorted(self.sets(), key=str.lower)
        m.add_separator()
        if names:
            for name in names:
                m.add_command(label=f"Load: {name}", command=lambda n=name: self.load_set(n))
            m.add_separator()
            dm = tk.Menu(m, tearoff=0)
            for name in names:
                dm.add_command(label=name, command=lambda n=name: self.delete_set(n))
            m.add_cascade(label="Delete a set", menu=dm)
        else:
            m.add_command(label="No sets saved yet", state="disabled")

    def save_set(self):
        self.commit_now()
        name = simpledialog.askstring(APP_NAME, "Name for this set of cards:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()[:40]
        sets = self.sets()
        if name in sets and not messagebox.askyesno(APP_NAME, f"Replace the set “{name}”?",
                                                    icon="warning", default="no", parent=self.root):
            return
        sets[name] = self.get_state()
        if save_settings({"sets": sets}):
            self._rebuild_sets_menu()
        else:
            messagebox.showerror(APP_NAME, "Could not save the set.", parent=self.root)

    def load_set(self, name):
        state = self.sets().get(name)
        if not state:
            return
        self.commit_now()
        if any(c.has_data() for c in self.cards) and not messagebox.askyesno(
                APP_NAME, f"Replace the cards on screen with the set “{name}”?\n\n"
                "You can bring them back with Undo.", icon="warning", default="no", parent=self.root):
            return
        self._rebuild(state)
        self.autosize()
        self.commit_now()

    def delete_set(self, name):
        sets = self.sets()
        if name in sets and messagebox.askyesno(APP_NAME, f"Delete the set “{name}”?", icon="warning",
                                                default="no", parent=self.root):
            del sets[name]
            save_settings({"sets": sets})
            self._rebuild_sets_menu()

    # ---- presets (scroll mixes) ------------------------------------------- #
    def presets(self):
        data = load_settings().get("presets")
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} \
            if isinstance(data, dict) else {}

    def save_preset(self, name, data):
        presets = self.presets()
        if name in presets and not messagebox.askyesno(APP_NAME, f"Replace the preset “{name}”?",
                                                       icon="warning", default="no", parent=self.root):
            return
        presets[name] = data
        if not save_settings({"presets": presets}):
            messagebox.showerror(APP_NAME, "Could not save the preset.", parent=self.root)

    def delete_preset(self, name):
        presets = self.presets()
        if name in presets and messagebox.askyesno(APP_NAME, f"Delete the preset “{name}”?", icon="warning",
                                                   default="no", parent=self.root):
            del presets[name]
            save_settings({"presets": presets})

    # ---- export ----------------------------------------------------------- #
    def copy_text(self):
        self.commit_now()
        self.root.clipboard_clear()
        self.root.clipboard_append(export_text(self.get_state()))
        self.status.config(text="Copied results to the clipboard", foreground=MUTED)

    def save_csv(self):
        self.commit_now()
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", title="Save results",
                                            initialfile="merchant-simulator.csv",
                                            filetypes=[("CSV (Excel)", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(export_csv(self.get_state()))
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not save the file:\n\n{exc}", parent=self.root)
            return
        self.status.config(text="Saved " + os.path.basename(path), foreground=MUTED)

    # ---- remembered prices ------------------------------------------------ #
    def recall_price(self, card):
        if self.suspend or not self.remember_prices.get():
            return
        key = card.nick.get().strip().lower()
        mem = self.prices.get(key) if key else None
        if mem:
            card.recall(mem)

    def _remember_prices(self):
        if not self.remember_prices.get():
            return
        for c in self.cards:
            key = c.nick.get().strip().lower()
            fields = c.price_memory() if key else {}
            if fields:
                self.prices.setdefault(key, {}).update(fields)
        while len(self.prices) > 300:                    # forget the oldest names
            self.prices.pop(next(iter(self.prices)))

    def _flush_prices(self):
        self._remember_prices()
        now = json.dumps(self.prices, sort_keys=True)
        if now != self._prices_saved and save_settings({"prices": self.prices}):
            self._prices_saved = now

    # ---- sorting and totals ----------------------------------------------- #
    def sort_cards(self):
        """Item cards by profit % (starred first); scroll simulators keep their places."""
        self.commit_now()
        slots = [i for i, c in enumerate(self.cards) if isinstance(c, Card)]
        ordered = sorted((self.cards[i] for i in slots), key=lambda c: c.sort_key())
        if [self.cards[i] for i in slots] == ordered:
            return
        for i, c in zip(slots, ordered):
            self.cards[i] = c
        self._renumber()
        self._layout_cards(force=True, cols=self._cols or None)
        self.commit_now()

    def _update_totals(self):
        n, cost, profit = 0, 0.0, 0.0
        for c in self.cards:
            r = getattr(c, "last", None)
            if r and r["cost"] > 0:
                n += 1
                cost += r["cost"]
                profit += r["profit"]
        if not n:
            self.totals.config(text="")
            return
        pct = f"  ({profit / cost * 100:,.1f}%)" if cost > 0 else ""
        self.totals.config(text=f"{n} item{'' if n == 1 else 's'}  \u00b7  Total cost {fmt_money(cost)}"
                                f"  \u00b7  Total profit {'+' if profit > 0.005 else ''}{fmt_money(profit)}{pct}")

    # ---- changelog -------------------------------------------------------- #
    def show_changelog(self):
        """Settings > What's new: the changelog of this version and every one before it."""
        if self._changelog_win is not None and self._changelog_win.winfo_exists():
            self._changelog_win.lift()
            return
        try:
            from changelog_data import CHANGELOG as text
        except Exception:
            messagebox.showinfo(APP_NAME, "The changelog is not included in this copy of the app.\n\n"
                                f"You can read it on the Releases page:\n{updater.RELEASES_PAGE if updater else ''}",
                                parent=self.root)
            return
        win = tk.Toplevel(self.root)
        self._changelog_win = win
        win.title(f"{APP_NAME} - What's new")
        win.geometry("760x560")
        box = ttk.Frame(win)
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        view = tk.Text(box, wrap="word", padx=14, pady=10, relief="flat", borderwidth=0)
        bar = ttk.Scrollbar(box, orient="vertical", command=view.yview)
        view.config(yscrollcommand=bar.set)
        view.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        view.tag_configure("h2", font=self.f_title, spacing1=14, spacing3=2)
        view.tag_configure("h3", font=self.f_bold, spacing1=6)
        view.tag_configure("bullet", lmargin1=12, lmargin2=26)
        view.tag_configure("cont", lmargin1=26, lmargin2=26)
        for line in changelog_lines(text):
            kind, body = line
            view.insert("end", body + "\n", kind)
        view.config(state="disabled")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))

    # ---- updates ---------------------------------------------------------- #
    def check_for_updates(self, manual=False):
        """Ask GitHub for the newest release in the background; manual=True also reports 'up to date' and errors."""
        if updater is None or not UPDATES_ENABLED or self._update_busy:
            return
        self._update_busy = True
        results = queue.Queue()

        def work():
            try:
                results.put(("ok", updater.fetch_latest()))
            except Exception as exc:
                results.put(("err", str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self._poll(results, lambda res: self._on_update_info(res, manual))

    def _poll(self, results, done):
        try:
            item = results.get_nowait()
        except queue.Empty:
            self.root.after(150, lambda: self._poll(results, done))
            return
        done(item)

    def _on_update_info(self, res, manual):
        self._update_busy = False
        if res[0] == "err":
            if manual:
                messagebox.showerror(APP_NAME, f"Could not check for updates.\n\n{res[1]}", parent=self.root)
            return
        info = res[1]
        if not updater.is_newer(info["version"], __version__):
            if manual:
                messagebox.showinfo(APP_NAME, f"You are up to date (version {__version__}).", parent=self.root)
            return
        if not manual and load_settings().get("skip_version") == info["version"]:
            return
        if not manual and self.auto_install.get() and updater.can_self_update():
            self._install_update(info)
            return
        notes = "\n".join(l for l in info["notes"].splitlines() if l.strip())[:900]
        head = f"Version {info['version']} is available (you have {__version__}).\n\n{notes}\n\n"
        if not updater.can_self_update():
            if messagebox.askyesno(APP_NAME, head + "This copy cannot update itself (it is not the downloaded "
                                   "app). Open the download page?", parent=self.root):
                webbrowser.open(info["page"])
            return
        ans = messagebox.askyesnocancel(
            APP_NAME, head + "Yes = update now and restart\nNo = skip this version\nCancel = ask me again later",
            parent=self.root)
        if ans:
            self._install_update(info)
        elif ans is False:
            save_settings({"skip_version": info["version"]})

    def _install_update(self, info):
        win = tk.Toplevel(self.root)
        win.title("Updating")
        win.resizable(False, False)
        label = ttk.Label(win, text=f"Downloading version {info['version']}...", padding=(20, 14, 20, 6))
        label.pack()
        bar = ttk.Progressbar(win, length=320, mode="determinate", maximum=100)
        bar.pack(padx=20, pady=(0, 16))
        win.protocol("WM_DELETE_WINDOW", lambda: None)          # not while it is downloading
        results = queue.Queue()

        def work():
            try:
                folder = tempfile.mkdtemp(prefix="pc-update-")
                last = [-1]

                def progress(done, total):
                    pct = int(done * 100 / total) if total else 0
                    if pct != last[0]:
                        last[0] = pct
                        results.put(("p", pct))
                results.put(("done", updater.prepare(info, folder, progress)))
            except Exception as exc:
                results.put(("err", str(exc)))
        threading.Thread(target=work, daemon=True).start()

        def fail(message):
            win.destroy()
            if messagebox.askyesno(APP_NAME, f"The update did not work:\n\n{message}\n\nOpen the download page "
                                   "to get it by hand?", parent=self.root):
                webbrowser.open(info["page"])

        def step(item=None):
            try:
                while True:
                    kind, val = results.get_nowait()
                    if kind == "p":
                        bar.config(value=val)
                    elif kind == "err":
                        return fail(val)
                    else:
                        label.config(text="Installing and restarting...")
                        self.root.update_idletasks()
                        return self._finish_update(val, info, fail)
            except queue.Empty:
                self.root.after(100, step)
        step()

    def _finish_update(self, path, info, fail):
        self.commit_now()
        if self._snap() != self.saved_json and not self.save():     # keep the entries before closing
            return fail("Your entries could not be saved first, so nothing was changed.")
        try:
            updater.install(path, info)
        except Exception as exc:
            return fail(str(exc))
        self.root.after(300, self.root.destroy)

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
        return (int(max((c.winfo_reqwidth() + gap) / c.span for c in self.cards)),
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
            cols = max(1, min(self._units(), W // self.cw))
            if changed or cols != self._cols:
                self._layout_cards(force=True, cols=cols)
            return
        cw, ch = self._card_extent()
        cw1, ch1 = cw / self.zoom, ch / self.zoom      # size of one item at zoom 1.0
        best = None
        units = self._units()
        for cols in range(1, units + 1):
            rows = self._flow_rows(cols)
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
            for cols in range(units, 0, -1):
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
            cols = max(1, min(units, W // cw))
            if want_cols is not None:
                cols = max(1, min(want_cols, cols))
                if W >= cols * cw or z <= ZOOM_MIN + 0.01:
                    break
            elif self._flow_rows(cols) * ch <= H or z <= ZOOM_MIN + 0.01:
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
        cols = max(1, min(self._units(), max_cols))
        self._layout_cards(force=True, cols=cols)
        self.root.update_idletasks()
        min_h = int(420 * self.scale)
        w = cols * self.cw + sb_w + pad
        h = (self.toolbar.winfo_reqheight() + self.totals_bar.winfo_reqheight() + 4
             + self.inner.winfo_reqheight() + pad)
        h = max(min_h, min(h, sh - 120))
        self._set_minsize()
        self.root.geometry(f"{w}x{h}")

    # ---- layout ----------------------------------------------------------- #
    def _units(self):
        """How many single-item columns all items need side by side (a wide card counts for two)."""
        return sum(2 if c.wide_capable else 1 for c in self.cards)

    def _flow(self, cols):
        """[(row, column, columnspan)] for each item when `cols` columns are available."""
        out, row, col = [], 0, 0
        for c in self.cards:
            span = min(2, cols) if c.wide_capable else 1
            if col + span > cols:
                row, col = row + 1, 0
            out.append((row, col, span))
            col += span
        return out

    def _flow_rows(self, cols):
        flow = self._flow(cols)
        return flow[-1][0] + 1 if flow else 0

    def _measure(self):
        self.root.update_idletasks()
        if self.cards:
            widest = max((c.winfo_reqwidth() + int(20 * self.scale)) / c.span for c in self.cards)
            self.cw = max(int(BASE_CARD_W * self.scale), int(widest))

    def _layout_cards(self, force=False, cols=None):
        if not self.cards:
            return
        if cols is None:
            width = self.canvas.winfo_width()
            cols = max(1, min(self._units(), width // self.cw))
        if cols == self._cols and not force:
            return
        self._cols = cols
        self._cfg_cols = max(getattr(self, "_cfg_cols", 0), cols)
        for c in range(self._cfg_cols):
            self.inner.grid_columnconfigure(c, weight=1 if c < cols else 0,
                                            uniform="cards" if c < cols else "")
        for card, (row, col, span) in zip(self.cards, self._flow(cols)):
            card.set_wide(span > 1)                  # the Scroll Simulator spreads over two columns when it can
            card.grid(row=row, column=col, columnspan=span, padx=8, pady=8, sticky="nsew")

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
            for i, it in enumerate(items):
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
        self._remember_prices()
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
        self.add_btn.config(text=f"+ Add Item ({n})")
        self._update_totals()
        if dirty:
            self.status.config(text="● Unsaved changes", foreground=AMBER)
        else:
            self.status.config(text=self.saved_text, foreground=MUTED)

    # ---- items ------------------------------------------------------------ #
    def add_card(self, kind="profit"):
        self.commit_now()
        card = make_card(self.inner, self, len(self.cards), default_state(kind))
        self.cards.append(card)
        self._renumber()
        self.commit_now()
        self.autosize()
        self.root.after(60, lambda: self._scroll_to(card))

    def insert_card(self, index, state):
        """Add a card made from `state` at position `index`."""
        self.commit_now()
        card = make_card(self.inner, self, index, sanitize_card(state))
        self.cards.insert(index, card)
        self._renumber()
        self.commit_now()
        self.autosize()
        self.root.after(60, lambda: self._scroll_to(card))

    def duplicate_card(self, card):
        state = copy.deepcopy(card.get_state())
        state["starred"] = False
        self.insert_card(self.cards.index(card) + 1, state)

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
        self._flush_prices()
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
        self._flush_prices()
        self.root.destroy()


def selftest(out_path):
    """Start the real GUI, drive it through the main features, then exit.

    Used by the release build to prove the packaged executable can start Tk and calculate.
    Writes "OK" or a traceback to out_path and returns the process exit code.
    Never touches the user's saved entries.
    """
    import tempfile
    import traceback
    global _DATA_FILE_OVERRIDE, UPDATES_ENABLED
    UPDATES_ENABLED = False       # the self-test must never go online
    _DATA_FILE_OVERRIDE = os.path.join(tempfile.mkdtemp(), "entries.json")
    msg, code, root = "OK", 0, None
    import faulthandler
    global messagebox, simpledialog
    try:                          # a hang becomes a failure that shows where it was stuck
        hang_log = open(out_path, "w", encoding="utf-8")
        faulthandler.dump_traceback_later(150, exit=True, file=hang_log)
    except Exception:
        hang_log = None

    def _no_dialog(*a, **k):      # a dialog would wait for a click nobody can make
        raise AssertionError("unexpected dialog during self-test: %r" % (a[:1],))
    real_messagebox, real_simpledialog = messagebox, simpledialog
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
        for _ in range(11):             # there is no limit on the number of items
            app.add_card()
        root.update()
        assert len(app.cards) == 12, "items should not be limited"
        assert app.add_btn.instate(["!disabled"]), "add button should stay enabled"
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
        assert len(app.cards) == 11, "remove item failed"
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

        # --- changelog window, update settings and the update decisions (no network, no dialogs)
        assert app.check_updates.get() is True and app.auto_install.get() is False, "update setting defaults"
        got = changelog_lines("# Changelog\n\n## [1.0.0] - x\n\n### Added\n- **Bold** thing\n  continued\n\n[1.0.0]: http://x\n")
        assert got == [("h2", "[1.0.0] - x"), ("h3", "Added"), ("bullet", "\u2022 Bold thing"), ("cont", "continued")], got
        try:
            import changelog_data
        except ImportError:
            changelog_data = None
        if changelog_data is not None:
            assert changelog_data.CHANGELOG.count("## [") >= 5 and __version__ in changelog_data.CHANGELOG, \
                "the bundled changelog does not mention this version"
            app.show_changelog()
            assert app._changelog_win is not None, "changelog window was not opened"
            app._changelog_win.destroy()
            app._changelog_win = None
        app.check_updates.set(False)
        app._on_update_settings()
        assert load_settings().get("check_updates") is False and load_settings().get("zoom") == "auto", \
            "update setting not saved (or it wiped another setting)"
        app.check_updates.set(True)
        app._on_update_settings()
        assert updater is not None, "updater module missing"
        assert updater.parse_version("v1.10.0") == (1, 10, 0) and updater.is_newer("1.10.0", "1.9.9")
        assert updater.asset_name("1.2.3", "Windows-x64") == "MSCW-Merchant-Simulator-v1.2.3-Windows-x64.exe"
        assert updater.platform_tag() is not None, "no release build is named for this system"
        real_messagebox, real_open, real_can = messagebox, webbrowser.open, updater.can_self_update
        said, opened = [], []
        webbrowser.open = lambda url, *a, **k: opened.append(url)
        answer = {"ync": False}
        messagebox = types.SimpleNamespace(
            showinfo=lambda *a, **k: said.append(("info", a[1])), showerror=lambda *a, **k: said.append(("error", a[1])),
            askyesno=lambda *a, **k: said.append(("yesno", a[1])) or True,
            askyesnocancel=lambda *a, **k: said.append(("ync", a[1])) or answer["ync"])
        try:
            newer = {"version": "999.0.0", "tag": "v999.0.0", "notes": "- a change", "page": "https://example.test/r",
                     "assets": {}}
            updater.can_self_update = lambda: False              # a built app would say True here
            app._update_busy = True
            app._on_update_info(("ok", newer), True)             # not the downloaded app: offers the download page
            assert opened == ["https://example.test/r"] and not app._update_busy, (opened, said)
            said.clear()
            app._on_update_info(("ok", dict(newer, version=__version__)), True)
            assert said[-1][0] == "info" and "up to date" in said[-1][1], said
            app._on_update_info(("err", "offline"), True)
            assert said[-1][0] == "error" and "offline" in said[-1][1], said
            said.clear()
            app._on_update_info(("err", "offline"), False)       # automatic checks stay quiet
            app._on_update_info(("ok", dict(newer, version=__version__)), False)
            assert not said, said
            updater.can_self_update = lambda: True               # pretend to be the downloaded app
            app._on_update_info(("ok", newer), False)            # asks; "No" = skip this version
            assert said and said[-1][0] == "ync" and load_settings().get("skip_version") == "999.0.0", said
            said.clear()
            app._on_update_info(("ok", newer), False)            # skipped: no more questions
            assert not said, "a skipped version should not ask again"
            app._on_update_info(("ok", newer), True)             # but a manual check always asks
            assert said and said[-1][0] == "ync"
        finally:
            messagebox, webbrowser.open, updater.can_self_update = real_messagebox, real_open, real_can
            save_settings({"skip_version": ""})

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
        ps = rp["per_success"]
        assert abs(ps["greater"]["items"] - 1 / 0.1) < 1e-9, ps         # Greater: 10% and always used once
        assert abs(ps["greater"]["scrolls"] - 1 / 0.1) < 1e-9
        assert abs(ps["intermediate"]["items"] - 1 / (0.6 * 0.28)) < 1e-9, ps
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

        # --- 1.7.0: break-even, duplicate, fold, star, sort, totals, memory, export, sets, presets, goal, theme
        strict = messagebox
        messagebox = types.SimpleNamespace(askyesno=lambda *a, **k: True, askyesnocancel=lambda *a, **k: True,
                                           showerror=_no_dialog, showinfo=lambda *a, **k: None)
        said_name = {"v": "Set one"}
        simpledialog = types.SimpleNamespace(askstring=lambda *a, **k: said_name["v"])
        try:
            assert compute({"base": "1000", "tax": "3%", "mode": "price", "sale_price": "0"})["break_even"] == 1031
            assert compute({"base": "1000", "tax": "5%", "mode": "price"})["break_even"] == 1053
            apply_theme("dark")
            assert BG_OK == "#2d333b" and lighten("#000000") == "#8c8c8c" and THEME == "dark"
            apply_theme("light")
            assert BG_OK == "#ffffff" and THEME == "light"

            app.add_card()
            pc = app.cards[-1]
            pc.nick.set("Cape")
            pc.base.set("1m")
            pc.scrolls.set("2")
            pc.sprice.set("100k")
            pc.sale.set("1.5m")
            root.update()
            assert pc.be_lbl.cget("text") == "1,237,114", "break-even was " + pc.be_lbl.cget("text")
            app.commit_now()
            assert "Total cost" in app.totals.cget("text"), "totals line is empty"

            n = len(app.cards)
            app.duplicate_card(pc)
            dup = app.cards[pc.index + 1]
            assert len(app.cards) == n + 1 and dup.get_state()["nickname"] == "Cape" and dup is not pc
            dup.toggle_star()
            assert dup.starred and dup.get_state()["starred"] is True
            app.sort_cards()
            first = [c for c in app.cards if isinstance(c, Card)][0]
            assert first is dup, "a starred item should sort first"
            pc.toggle_collapse()
            assert pc.collapsed and pc.get_state()["collapsed"] is True and pc.sum_lbl.cget("text"), "fold failed"
            pc.toggle_collapse()
            assert not pc.collapsed
            app.commit_now()
            keep = app.get_state()
            app.undo()
            app.redo()
            assert app.get_state() == keep, "undo/redo lost the new card settings"
            pc = next(c for c in app.cards if isinstance(c, Card) and c.nick.get() == "Cape" and not c.starred)
            assert sanitize_item({"collapsed": "yes", "starred": 1})["collapsed"] is False

            app.add_card()
            nc = app.cards[-1]
            nc.nick.set("cape")
            app.recall_price(nc)
            assert nc.base.get() == pc.base.get() and nc.sprice.get() == pc.sprice.get(), "remembered price missing"
            app.remember_prices.set(False)
            nc2 = Card(app.inner, app, 99, default_state("profit"))
            nc2.nick.set("cape")
            app.recall_price(nc2)
            assert not nc2.base.get(), "price memory should be switchable off"
            nc2.destroy()
            app.remember_prices.set(True)

            txt = export_text(app.get_state())
            assert "Cape" in txt and "Break-even sale price" in txt, txt
            rows = list(csv.reader(io.StringIO(export_csv(app.get_state()))))
            assert rows[0][0] == "Item" and any("Cape" in r for r in rows), rows

            said_name["v"] = "Set one"
            app.save_set()
            assert "Set one" in app.sets(), "set not saved"
            app.add_card()
            app.load_set("Set one")
            assert len(app.cards) == len(app.sets()["Set one"]["items"]), "set did not replace the cards"
            app.delete_set("Set one")
            assert "Set one" not in app.sets()

            sc = next(c for c in app.cards if isinstance(c, ScrollCard))
            while len(sc.sections) > 1:
                sc.remove_section(1)
            sc.sections[0]["kind"].set(SCROLL_KINDS["intermediate"][0])
            sc.sections[0]["count"].set("1")
            sc.sections[0]["cost"].set("100")
            sc.slots.set("")
            sc.equip.set("1000")
            for v in (sc.stop_streak, sc.stop_total, sc.stop_at):
                v.set("")
            sc.goal.set("1")
            sc.budget.set("2200")
            root.update()
            g = scroll_report(sc.get_state())["goal"]
            assert g["items50"] == 1.0 and g["items90"] == 3.0 and abs(g["budget_chance"] - 0.84) < 1e-9, g
            assert "error" in scroll_report(dict(sc.get_state(), goal="5")), "goal above the scrolls should be refused"
            assert "1 success" in sc.summary_lbl.cget("text"), sc.summary_lbl.cget("text")
            sc.view.set("used")
            root.update()
            sc.view.set("cost")
            said_name["v"] = "Mix A"
            sc.sections[0]["count"].set("1")
            sc.save_preset()
            assert "Mix A" in app.presets(), "preset not saved"
            sc.sections[0]["cost"].set("5")
            sc.apply_preset("Mix A")
            assert sc.sections[0]["cost"].get() == "100", "preset not applied"
            app.delete_preset("Mix A")
            assert "Mix A" not in app.presets()

            n = len(app.cards)
            sc.send_to_item()
            sent = app.cards[sc.index + 1]
            assert len(app.cards) == n + 1 and isinstance(sent, Card), "send to item card failed"
            assert sent.base.get() == "1,667" and "+1" in sent.nick.get(), (sent.base.get(), sent.nick.get())
            sc.toggle_collapse()
            assert sc.sum_lbl.cget("text"), "folded scroll card has no summary"
            sc.toggle_collapse()

            app.theme_var.set("dark")
            app._on_theme_changed()
            assert load_settings().get("theme") == "dark"
            app.theme_var.set("light")
            app._on_theme_changed()
            app._flush_prices()
            assert "cape" in load_settings().get("prices", {}), "prices were not saved"
        finally:
            messagebox = strict
            simpledialog = real_simpledialog

        assert app.save() and os.path.exists(data_file()), "save failed"
        root.update()
    except BaseException:
        msg, code = traceback.format_exc(), 1
    finally:
        messagebox, simpledialog = real_messagebox, real_simpledialog
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
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HimekoTachibana.MSCWMerchantSimulator")
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
