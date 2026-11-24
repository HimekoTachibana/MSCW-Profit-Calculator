# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

Each GitHub release uses the section for its version as its release notes, so every release
must have an entry here **before** its tag is pushed (see [RELEASING.md](RELEASING.md)).

## [Unreleased]

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
- GitHub Actions workflow that builds Windows, macOS and Linux executables and publishes a
  release, using this changelog as the release notes.

[Unreleased]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/HimekoTachibana/MSCW-Profit-Calculator/releases/tag/v1.0.0
