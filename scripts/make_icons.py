#!/usr/bin/env python3
"""Regenerate every icon the app uses from the pictures in assets/source/.

    python scripts/make_icons.py            (needs Pillow: pip install pillow)

Writes
    assets/icons/<tier>.png        the six profit-tier icons, all exactly ICON x ICON pixels
    assets/app_icon.png            leprechaun, 256 x 256
    assets/icon.ico  assets/icon.icns   executable / app icons for Windows and macOS
    icons_data.py                  everything above embedded as base64 so the app needs no data files

Tier -> picture:
    gold_bag      (profit > 25%)  assets/source/gold_bag_big.png
    money_bag     (profit > 20%)  bag      from assets/source/money_sheet.png
    cash_stack    (profit > 10%)  bills    from assets/source/money_sheet.png
    gold_coin     (profit >  5%)  gold coin from assets/source/money_sheet.png
    copper_coin   (profit >  0%)  copper coin from assets/source/money_sheet.png
    grave         (loss)          assets/source/grave.png
"""
import base64
import io
import os
import sys
import textwrap
from collections import deque

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "source")
OUT = os.path.join(ROOT, "assets")
ICON = 96          # every tier icon is exactly ICON x ICON pixels
SMALL = 32         # the small copies shown beside the profit % in each item
FIT = 84           # longest side of the picture inside that square (same for all icons)
WHITE_THRESHOLD = 235


def load(name):
    return Image.open(os.path.join(SRC, name)).convert("RGB")


# ----------------------------------------------------------------------------- background
def background_mask(im, thr=WHITE_THRESHOLD):
    """Boolean grid: True for near-white pixels connected to the picture's border."""
    w, h = im.size
    px = im.load()
    near = lambda p: min(p) >= thr
    seen = [[False] * w for _ in range(h)]
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near(px[x, y]) and not seen[y][x]:
                seen[y][x] = True
                dq.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if near(px[x, y]) and not seen[y][x]:
                seen[y][x] = True
                dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and near(px[nx, ny]):
                seen[ny][nx] = True
                dq.append((nx, ny))
    return seen


def cut_out(im, soften=False):
    """RGB picture on white -> RGBA with the white background transparent."""
    w, h = im.size
    bg = background_mask(im)
    out = im.convert("RGBA")
    px = out.load()
    for y in range(h):
        for x in range(w):
            if bg[y][x]:
                px[x, y] = (255, 255, 255, 0)
    if soften:
        # Blurry sources leave a light fringe; fade pale pixels that touch the background.
        for _ in range(2):
            edge = []
            for y in range(h):
                for x in range(w):
                    if px[x, y][3] == 0:
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < w and 0 <= ny < h) or px[nx, ny][3] == 0:
                            edge.append((x, y))
                            break
            for x, y in edge:
                r, g, b, a = px[x, y]
                lum = (r + g + b) / 3
                if lum > 205:
                    px[x, y] = (r, g, b, 0)
    return out


def trim(im):
    box = im.getchannel("A").getbbox()
    return im.crop(box)


# ----------------------------------------------------------------------------- sprite sheet
def runs(flags):
    """[(start, end)] of consecutive True values."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i))
            start = None
    return out


def split_sheet(sheet_rgb):
    """Return {'top_left','top_right','bottom_left','bottom_right'} sprites (RGBA, trimmed)."""
    rgba = cut_out(sheet_rgb)
    w, h = rgba.size
    a = rgba.getchannel("A").load()
    col_has = [any(a[x, y] for y in range(h)) for x in range(w)]
    col_groups = runs(col_has)
    if len(col_groups) != 2:
        sys.exit(f"expected 2 columns of sprites in the sheet, found {len(col_groups)}")
    sprites = {}
    for ci, (x0, x1) in enumerate(col_groups):
        row_has = [any(a[x, y] for x in range(x0, x1)) for y in range(h)]
        row_groups = runs(row_has)
        if len(row_groups) != 2:
            sys.exit(f"expected 2 sprites in column {ci}, found {len(row_groups)}: {row_groups}")
        for ri, (y0, y1) in enumerate(row_groups):
            key = ("top" if ri == 0 else "bottom") + ("_left" if ci == 0 else "_right")
            sprites[key] = trim(rgba.crop((x0, y0, x1, y1)))
    return sprites


# ----------------------------------------------------------------------------- normalising
def fit_icon(sprite):
    """Scale a trimmed RGBA sprite so its longest side is FIT px and centre it on an ICON square.

    Small pixel-art sprites are first enlarged by a whole number with no smoothing (keeps the
    pixels crisp) and then resized to the exact size, so every icon ends up the same size.
    """
    w, h = sprite.size
    scale = FIT / max(w, h)
    big = sprite
    if scale > 1:
        k = int(scale) + 1
        big = sprite.resize((w * k, h * k), Image.NEAREST)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    sized = big.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (ICON, ICON), (0, 0, 0, 0))
    canvas.paste(sized, ((ICON - nw) // 2, (ICON - nh) // 2), sized)
    return canvas


def png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main():
    sheet = split_sheet(load("money_sheet.png"))
    tiers = {
        "gold_bag": trim(cut_out(load("gold_bag_big.png"), soften=True)),
        "money_bag": sheet["bottom_left"],
        "cash_stack": sheet["top_left"],
        "gold_coin": sheet["bottom_right"],
        "copper_coin": sheet["top_right"],
        "grave": trim(cut_out(load("grave.png"), soften=True)),
    }
    os.makedirs(os.path.join(OUT, "icons"), exist_ok=True)
    data, small = {}, {}
    for name, sprite in tiers.items():
        icon = fit_icon(sprite)
        assert icon.size == (ICON, ICON)
        icon.save(os.path.join(OUT, "icons", name + ".png"), optimize=True)
        data[name] = png_bytes(icon)
        small[name] = png_bytes(icon.resize((SMALL, SMALL), Image.LANCZOS))
        print(f"{name:12s} sprite {sprite.size[0]:3d}x{sprite.size[1]:<3d} -> {ICON}x{ICON}")

    # ---- leprechaun: window / app icon ---------------------------------------------------
    lep = Image.open(os.path.join(SRC, "leprechaun.png")).convert("RGBA")
    lep = trim(lep)
    side = max(lep.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(lep, ((side - lep.width) // 2, (side - lep.height) // 2), lep)
    base = square.resize((256, 256), Image.NEAREST) if side * 4 == 256 else None
    if base is None:  # keep pixels crisp: integer upscale, then fit exactly
        k = -(-256 // side)
        base = square.resize((side * k, side * k), Image.NEAREST).resize((256, 256), Image.LANCZOS)
    base.save(os.path.join(OUT, "app_icon.png"), optimize=True)
    base.save(os.path.join(OUT, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    try:
        big = base.resize((1024, 1024), Image.NEAREST)
        big.save(os.path.join(OUT, "icon.icns"))
    except Exception as exc:  # pragma: no cover
        print("could not write icon.icns:", exc)

    app = {}
    for size in (16, 32, 48, 64, 128):
        app[size] = png_bytes(base.resize((size, size), Image.LANCZOS if size < 64 else Image.NEAREST))

    # ---- embed everything as base64 so the app needs no data files -----------------------
    def block(name, mapping):
        lines = [f"{name} = {{"]
        for key, raw in mapping.items():
            b64 = base64.b64encode(raw).decode("ascii")
            wrapped = textwrap.wrap(b64, 96)
            lines.append(f"    {key!r}: (")
            lines += [f'        "{part}"' for part in wrapped]
            lines.append("    ),")
        lines.append("}")
        return "\n".join(lines)

    with open(os.path.join(ROOT, "icons_data.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write('"""AUTO-GENERATED by scripts/make_icons.py from assets/source/ - do not edit by hand."""\n\n')
        f.write(f"ICON_SIZE = {ICON}\nSMALL_SIZE = {SMALL}\n\n")
        f.write(block("TIER_ICONS", data) + "\n\n")
        f.write(block("TIER_ICONS_SMALL", small) + "\n\n")
        f.write(block("APP_ICONS", app) + "\n")
    print("wrote icons_data.py and assets/icon.ico, icon.icns, app_icon.png")


if __name__ == "__main__":
    main()
