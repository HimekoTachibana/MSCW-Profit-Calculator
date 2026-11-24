# MSCW Profit Calculator

Quickly work out profit when buying, crafting and selling items. Compare up to 5 items at once,
include scroll and material costs, apply 3% or 5% tax, and either enter a sale price to see your
profit or enter the profit you want to see the price to list at.

Current version: see [CHANGELOG.md](CHANGELOG.md).

## Download (no installs needed)

Get the file for your system from the [Releases](../../releases) page. Python is bundled inside,
so there is nothing else to install.

| System | Download | First launch |
| --- | --- | --- |
| Windows 10/11 | `ProfitCalculator-Windows-x64.exe` | Double-click. If SmartScreen warns, choose **More info → Run anyway** (the app is not code-signed). |
| macOS, Apple Silicon (M1 and newer) | `ProfitCalculator-macOS-AppleSilicon.zip` | Unzip, then right-click the app and choose **Open** the first time (not notarized). |
| macOS, Intel | `ProfitCalculator-macOS-Intel.zip` | Same as above. |
| Linux x64 (CachyOS, Arch, Ubuntu, Fedora…) | `ProfitCalculator-Linux-x64.tar.gz` | `tar xzf ProfitCalculator-Linux-x64.tar.gz && ./ProfitCalculator` |
| Linux arm64 | `ProfitCalculator-Linux-arm64.tar.gz` | Same as above. |

If macOS says the app is damaged, run `xattr -dr com.apple.quarantine ProfitCalculator.app` once.
Linux builds need a normal desktop session (X11 or Wayland) and a reasonably recent distribution
(built on Ubuntu 22.04). `SHA256SUMS.txt` on each release lets you verify a download.

## Run from source

Only needed if you don't use the downloads above. Needs Python 3 with Tkinter (no other packages).

| System | Setup | Run |
| --- | --- | --- |
| Windows | Install Python 3 from python.org | `python profit_calculator.py` |
| macOS | Install Python 3 from python.org (Homebrew: `brew install python-tk`) | `python3 profit_calculator.py` |
| CachyOS / Arch | `sudo pacman -S python tk` | `python profit_calculator.py` |

`python profit_calculator.py --version` prints the version.

## Tips

- Numbers accept commas and shorthand: `500k`, `1.5m`, `2b`.
- Undo / Redo: Ctrl+Z / Ctrl+Y (Cmd+Z / Cmd+Shift+Z on macOS). Save: Ctrl+S / Cmd+S.
- Saved entries load automatically on the next launch.

## Releases

See [RELEASING.md](RELEASING.md). Every release's notes come from [CHANGELOG.md](CHANGELOG.md).
