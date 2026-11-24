# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

Each GitHub release uses the section for its version as its release notes, so every release
must have an entry here **before** its tag is pushed (see [RELEASING.md](RELEASING.md)).

## [Unreleased]

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
  stays where it is.

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

[Unreleased]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/releases/tag/v1.0.0
