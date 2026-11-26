# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

Each GitHub release uses the section for its version as its release notes, so every release
must have an entry here **before** its tag is pushed (see [RELEASING.md](RELEASING.md)).

## [Unreleased]

## [1.5.1] - 2026-11-25

### Changed
- Scroll Simulator: how many copies of the base item you need is now spelled out. The success
  table's columns are **Base items** (copies bought on average, including the finished one) and
  **Duplicates** (the others), and the "Scrolls used" table gets a **Base items** column next to
  the scroll counts, so each success count shows the base items and the scrolls of each type side by side.

## [1.5.0] - 2026-11-25

### Changed
- **No limit on the number of items.** The 10-item cap is gone; the button now just shows how
  many items you have, e.g. "+ Add Item (12)".
- **The Scroll Simulator now takes the space of two item cards** when the window has room: inputs
  and results on the left, the success, cost and scroll tables on the right, so it is about as tall
  as a normal item. In a narrow window (one column) it stacks as before. Zoom, auto-fit, window
  resizing and reordering all account for the wider card.

## [1.4.0] - 2026-11-25

### Added
- **Scroll Simulator breakdown by scroll type.** Two new tables under the success table:
  - *Cost to get N successes*: the cost of the base items, the cost of each scroll type (Chaos,
    Greater, Intermediate, Lesser) and the total, for 1, 2, 3 ... successes (up to 10 if used).
  - *Scrolls used to get N successes*: how many of each scroll type that takes.
  Both start with a "1 item" row showing what a single base item costs and uses on average, so the
  old "Avg scrolls used" figure is now split by type.
- **Extra items** column: how many base items beyond the finished one you have to buy (they fail,
  are destroyed or restart).

### Changed
- Removed "Avg total cost / item" from the results (it mixed the base item with the scrolls). The
  base item, each scroll type and the total now have their own columns. The success table's
  "Avg cost" column moved into the new cost table as "Total".

## [1.3.2] - 2026-11-25

### Changed
- **More compact Scroll Simulator** so it is closer to the height of a normal item card: equipment
  cost and slots share a line, the "Add scroll type" button sits on the "Scrolls used" heading,
  the three restart fields take two lines, results are shown in two columns, the exactly /
  at-least choice sits on the "Successes" heading line, and the explanatory notes are shorter.
  All numbers are unchanged.

## [1.3.1] - 2026-11-25

### Changed
- **Resize window automatically is now off by default** (Settings > Resize window automatically). If
  you already turned it on, your choice is kept.
- **Smaller, tighter item cards** so more fit on screen: the big picture panel under the results is
  gone. The profit picture is now a small icon beside the verdict and the profit % on the
  "Return on cost" line, the "I type in" options share one line, and spacing is tighter.

### Fixed
- Resizing the window no longer feels laggy: the UI now rescales while you drag instead of waiting
  until you stop, and it rescales in 5% steps so far fewer redraws are needed.

## [1.3.0] - 2026-11-25

### Added
- **Restart rules in the Scroll Simulator.** A new "Restart with a new item when" section stops
  scrolling an item and starts over with a new one when:
  - this many scrolls fail **in a row** (e.g. `2`),
  - this many scrolls have failed **in total** (e.g. `2` = give up once a 2nd scroll fails), or
  - **any of the listed scrolls** fails (e.g. `1, 2` = restart if the 1st or 2nd scroll fails;
    `1-3` = any of the first three).
  Restarted items use no more scrolls, so the average scrolls used and scroll cost per item drop
  to match. A new **Chance item is restarted** result shows how often a rule kicks in, and
  restarted items count as misses in the success table.

### Changed
- Scroll Simulator **Slots** can be left blank: the item then has as many slots as the scrolls
  you use. No more red error while you are still filling it in.
- New Scroll Simulators show average items and cost for **at least** that many successes by
  default (what you usually want when aiming for a target). "Exactly" is still one click away.
- A short note under the success table explains what Avg items and Avg cost mean.

## [1.2.1] - 2026-11-25

### Fixed
- Clicking an item's title (without dragging) could move the item to another position when a
  taller item sat below a shorter one. Items now only move after a real drag, and they drop onto
  the item under the pointer.
- With Caps Lock on, Ctrl+Z (Cmd+Z) redid instead of undoing, and Ctrl+S / Ctrl+Y did nothing.
  Shortcuts now work the same with Caps Lock on or off.
- Scrolling the mouse wheel inside an open drop-down list (zoom, scroll type) no longer scrolls the
  whole window as well.

### Changed
- The release workflow uses the current GitHub Actions versions (Node.js 24), so runs no longer
  show the Node.js 20 deprecation warning.

## [1.2.0] - 2026-11-24

### Added
- **Zoom control**: a Zoom box in the toolbar (type a percentage such as `125`, pick from the list, or use the − / + buttons), also under Settings > Zoom. `Auto` keeps the old behaviour of fitting the window; a percentage fixes the zoom (60%-240%) and the items use as many columns as fit. Shortcuts: Ctrl/Cmd and `+`, `-`, `0` (back to Auto). The choice is remembered.

### Fixed
- With many items the UI no longer shrinks to tiny text to avoid scrolling. It now stays at a readable size (never below 100% unless the window itself is too narrow), uses as many columns as fit, and scrolls vertically for the rest.

### Changed
- Every build's file name now includes the version, e.g. `ProfitCalculator-v1.2.0-Windows-x64.exe`.

## [1.1.0] - 2026-11-24

### Added
- Up to **10** items at once (was 5).
- **Profit %** pricing: next to "Sale price" and "Profit" you can now type the profit percentage
  you want (of your total cost, e.g. `20` or `20%`); the sale price to list at and the profit are
  worked out for you.
- A picture under each item's results shows how good the profit is (profit % = profit / total cost):
  gold bag over 25%, bag of gold over 20%, band of money over 10%, gold coin over 5%, copper coin
  over 0%, and a grave for a loss. All pictures are the same size.
- The purple leprechaun is now the app icon (Windows `.exe`, macOS app) and the window icon.
- Reorder items with the ◀ ▶ buttons or by dragging an item's title onto another item. Undo and
  redo remember the order.
- The whole app scales with the window: resize it by hand and the text, buttons and pictures grow
  or shrink, and the items rearrange into as many columns as fit.
- The window now resizes itself when items or materials are added or removed. Its top-left corner
  stays where it is. **Settings > Resize window automatically** turns this off (remembered between
  launches); with it off the app scales to fit the current window instead.
- **Scroll Simulator** item (toolbar button "+ Scroll Simulator"; counts toward the 10 items).
  Enter the item's slots (0-10), add one or more scroll sections (Chaos 10% / 50% destroy on fail,
  Greater 10%, Intermediate 60%, Lesser 100%) with how many of each you use and the cost per scroll,
  plus base equipment and its cost. It shows the chance of exactly and at least 1, 2, ... successes,
  the chance the item is destroyed, expected scroll cost, and the average number of items you need
  to buy per success count.

### Fixed
- Moving an item and then removing it right away no longer raises a stray error.

### Changed
- Return on cost is shown with two decimals.
- The release workflow downloads build files into `release-files/` so they cannot mix with the
  repository's `assets/` folder.


## [1.0.0] - 2026-11-23

First release.

### Added
- Profit calculator for buying, crafting and selling items, with up to **5 items** at once.
  It starts with one item; **+ Add Item** and **Remove** add or remove calculators.
- Item fields: nickname, base item price, number of scrolls, scroll price (each), and tax rate
  (3% or 5%, 3% by default).
- Optional crafting materials (cost and quantity needed, up to 5 per item). None are shown by
  default; add and remove them as needed.
- Automatic results: total cost to create, tax paid, amount received after tax, profit, and
  return on cost.
- Two ways to price a sale: enter the preferred sale price to see the profit, or enter the
  preferred profit to get the sale price you need to list at (rounded up so the target is met).
- Number entry accepts commas and shorthand (`500k`, `1.5m`, `2b`); invalid entries are
  highlighted in red.
- Per-item **Clear** button with a confirmation popup.
- **Undo** and **Redo** buttons (Ctrl+Z / Ctrl+Y; Cmd+Z / Cmd+Shift+Z on macOS). Clearing and
  removing items can be undone.
- **Save** (Ctrl+S / Cmd+S) stores all entries and reloads them on the next launch; closing with
  unsaved changes asks whether to save.
- Runs on Windows, macOS and Linux (including CachyOS) using only Python's built-in Tkinter.
- Version number shown in the window title, and `--version` command-line flag.
- Standalone downloads that need **no installs** (Python and Tk are bundled inside):
  Windows x64 (`.exe`), macOS Apple Silicon and Intel (`.zip`), Linux x64 and arm64 (`.tar.gz`).
- GitHub Actions workflow ("Build & Release") that builds every app, starts each built app and
  runs a built-in self-test (`--selftest`) before publishing, and uses this changelog as the
  release notes. Run it from the Actions tab: leave **Publish a GitHub release** unticked to just
  build and test, or tick it to create the version tag and publish the release automatically.
- `SHA256SUMS.txt` checksums attached to every release.

[Unreleased]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.3.2...v1.4.0
[1.3.2]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/releases/tag/v1.0.0
