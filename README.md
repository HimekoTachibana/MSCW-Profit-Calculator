# MSCW Profit Calculator

Quickly work out profit when buying, crafting and selling items. Compare up to 10 items at once,
include scroll and material costs, apply 3% or 5% tax, and type in a sale price, a profit or a
profit % - the other two are worked out for you. A small picture beside the profit % shows how good the
profit is:

| Profit % (of total cost) | Picture |
| --- | --- |
| over 25% | gold bag |
| over 20% | bag of gold |
| over 10% | band of money |
| over 5% | gold coin |
| over 0% | copper coin |
| loss | grave |

A **Scroll Simulator** card (toolbar button) works out scrolling odds: slots, scrolls of each type
(Chaos 10% with 50% destroy on fail, Greater 10%, Intermediate 60%, Lesser 100%), the chance of
getting exactly or at least N successes, and the average number of items to buy per success count.
Restart rules let you give up on an item and start over with a new one when N scrolls fail in a row,
N fail in total, or particular scrolls fail (e.g. "restart if the 1st or 2nd scroll fails").
Rates follow [MeowDB's scrolling guide](https://meowdb.com/msclassic/forum/guides/Jacob/the-complete-scrolling-guide).

Current version: see [CHANGELOG.md](CHANGELOG.md).

## Download (no installs needed)

Get the file for your system from the [Releases](../../releases) page (the version is in every file name, e.g. `ProfitCalculator-v1.4.0-Windows-x64.exe`). Python is bundled inside,
so there is nothing else to install.

| System | Download | First launch |
| --- | --- | --- |
| Windows 10/11 | `ProfitCalculator-v<version>-Windows-x64.exe` | Double-click. If SmartScreen warns, choose **More info → Run anyway** (the app is not code-signed). |
| macOS, Apple Silicon (M1 and newer) | `ProfitCalculator-v<version>-macOS-AppleSilicon.zip` | Unzip, then right-click the app and choose **Open** the first time (not notarized). |
| macOS, Intel | `ProfitCalculator-v<version>-macOS-Intel.zip` | Same as above. |
| Linux x64 (CachyOS, Arch, Ubuntu, Fedora…) | `ProfitCalculator-v<version>-Linux-x64.tar.gz` | `tar xzf ProfitCalculator-v<version>-Linux-x64.tar.gz && ./ProfitCalculator` |
| Linux arm64 | `ProfitCalculator-v<version>-Linux-arm64.tar.gz` | Same as above. |

If macOS says the app is damaged, run `xattr -dr com.apple.quarantine ProfitCalculator.app` once.
Linux builds need a normal desktop session (X11 or Wayland) and a reasonably recent distribution
(built on Ubuntu 22.04). `SHA256SUMS.txt` on each release lets you verify a download.

## Run from source

Only needed if you don't use the downloads above. Needs Python 3 with Tkinter (no other packages). Keep `profit_calculator.py` and `icons_data.py` together.

| System | Setup | Run |
| --- | --- | --- |
| Windows | Install Python 3 from python.org | `python profit_calculator.py` |
| macOS | Install Python 3 from python.org (Homebrew: `brew install python-tk`) | `python3 profit_calculator.py` |
| CachyOS / Arch | `sudo pacman -S python tk` | `python profit_calculator.py` |

`python profit_calculator.py --version` prints the version.

## Tips

- Numbers accept commas and shorthand: `500k`, `1.5m`, `2b`.
- Reorder items with the ◀ ▶ buttons, or drag an item's title onto another item.
- Resize the window and the whole app scales to fit; it can also resize itself as you add or remove items (turn that on under Settings).
- Zoom: use the toolbar's Zoom box (type `125`, pick a percentage, or use − / +), or Ctrl/Cmd and `+` / `-`; `Auto` (Ctrl/Cmd+0) fits the window.
- Undo / Redo: Ctrl+Z / Ctrl+Y (Cmd+Z / Cmd+Shift+Z on macOS). Save: Ctrl+S / Cmd+S.
- Saved entries load automatically on the next launch.

## Releases

See [RELEASING.md](RELEASING.md). Every release's notes come from [CHANGELOG.md](CHANGELOG.md).
