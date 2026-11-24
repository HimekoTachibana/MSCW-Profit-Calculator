# MSCW Profit Calculator

Quickly work out profit when buying, crafting and selling items. Compare up to 5 items at once,
include scroll and material costs, apply 3% or 5% tax, and either enter a sale price to see your
profit or enter the profit you want to see the price to list at.

Current version: see [CHANGELOG.md](CHANGELOG.md) · Download builds from the
[Releases](../../releases) page.

## Run from source

Needs Python 3 with Tkinter (no other packages).

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
