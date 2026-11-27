# MSCW Merchant Simulator

Work out profit when buying, crafting and selling items, and plan scrolling runs: how many base
items and scrolls it takes, what it costs, and how many finished items a budget will get you.
Compare as many items as you like with unlimited item cards, and use the built-in **Scroll
Simulator** for the odds. The full guide below is also inside the app under **Settings > How to use**
(or press **F1**).

Current version: see [CHANGELOG.md](CHANGELOG.md).

## Download (no installs needed)

Get the file for your system from the [Releases](../../releases) page (the version is in every file name, e.g. `MSCW-Merchant-Simulator-v1.7.3-Windows-x64.exe`). Python is bundled inside,
so there is nothing else to install.

| System | Download | First launch |
| --- | --- | --- |
| Windows 10/11 | `MSCW-Merchant-Simulator-v<version>-Windows-x64.exe` | Double-click. If SmartScreen warns, choose **More info → Run anyway** (the app is not code-signed). |
| macOS, Apple Silicon (M1 and newer) | `MSCW-Merchant-Simulator-v<version>-macOS-AppleSilicon.zip` | Unzip, then right-click the app and choose **Open** the first time (not notarized). |
| macOS, Intel | `MSCW-Merchant-Simulator-v<version>-macOS-Intel.zip` | Same as above. |
| Linux x64 (CachyOS, Arch, Ubuntu, Fedora…) | `MSCW-Merchant-Simulator-v<version>-Linux-x64.tar.gz` | `tar xzf MSCW-Merchant-Simulator-v<version>-Linux-x64.tar.gz && ./MSCW-Merchant-Simulator` |
| Linux arm64 | `MSCW-Merchant-Simulator-v<version>-Linux-arm64.tar.gz` | Same as above. |

If macOS says the app is damaged, run `xattr -dr com.apple.quarantine MSCW-Merchant-Simulator.app` once.
Linux builds need a normal desktop session (X11 or Wayland) and a reasonably recent distribution
(built on Ubuntu 22.04). `SHA256SUMS.txt` on each release lets you verify a download.

<!-- guide:start -->
## What it does

MSCW Merchant Simulator helps you decide what to buy, craft and sell. Use **item cards** to see the
profit on an item once its costs and tax are included, and the **Scroll Simulator** to see how many
base items and scrolls it takes, on average, to get an item with the scrolls you want. Everything
is saved on your computer and loads again the next time you open the app.

## Quick start

1. Open the app. You start with one item card. Type a nickname, the base item price, how many scrolls
   you will use and what each costs. Add materials if the item needs them.
2. Pick the tax rate (3% or 5%) and type the price you plan to sell at. The profit, the profit %
   and a small picture that rates it appear straight away.
3. Press **+ Add Item** for the next item and compare them. **Sort by profit %** puts the best first.
4. Need to know how many scrolls and base items it takes to make something? Press **+ Add Scroll
   Simulator** and fill it in (see "Scroll Simulator" below).

Numbers can be typed with commas or shorthand: `500k`, `1.5m`, `2b`. A box that turns red does not
contain a valid number, and the results stay empty (a dash) until it is fixed.

## Item cards

Each item card works out what an item costs to make and what you keep when you sell it.

- **Nickname**: any name, shown in the card title.
- **Costs**: the **base item price**; **scrolls to use** times the **scroll price (each)**; and up to
  five **materials** (press **+ Add material**; each has a cost and a quantity). The **total cost
  to create** is all of these added together.
- **Selling**: choose the **tax rate** (3% or 5%), then choose what you want to type under **I type
  in**: the **sale price**, the **profit**, or the **profit %**. The other two boxes (grey) are
  worked out for you. Typing a profit % is the quickest way to find the price you must charge to hit
  a target.
- **Results**: the **break-even sale price** (the lowest price with no loss, after tax), the **tax
  paid**, **what you receive after tax**, the **profit**, and the **return on cost** (profit divided
  by total cost).
- **The picture** beside the return shows how good the deal is: more than 25% a gold bag, more than
  20% a bag of gold, more than 10% a band of money, more than 5% a gold coin, more than 0% a copper
  coin, and a loss shows a grave.

## Card buttons

- **◀ ▶** move the card earlier or later. You can also drag a card by its title onto another.
- **Clear** empties the card (it asks first). **Remove** deletes it (it asks first if it has data).
  Both can be undone.
- **☆ Star** marks a favourite; starred items go first when you sort.
- **Duplicate** copies the card with everything in it, right after the original. Use it to try a
  different price or scroll mix without losing the first one.
- **Collapse** folds the card down to its title line, which then shows the profit and profit %
  (or the goal summary for a Scroll Simulator). **Expand** opens it again. Collapse the cards you
  have finished with to fit more on screen.

## Toolbar and totals

- **+ Add Item** and **+ Add Scroll Simulator** add cards. There is no limit on how many.
- **Undo / Redo** step back and forward through your edits, including moves, removals, loading a
  set and importing a file.
- **Save** writes your cards to disk. The app also asks if you want to save when you close it with
  unsaved changes.
- **Zoom**: type a percentage, pick one from the list, or use the − and + buttons. **Auto** fits the
  window.
- **The totals line** under the toolbar adds up the total cost and the total profit (and profit %)
  of all your item cards. **Sort by profit %** orders the item cards from best to worst, starred
  first; Scroll Simulator cards stay where they are.

## Scroll Simulator

The Scroll Simulator answers: *"If I keep buying base items and scrolling them, what will it take to
end up with an item that has N successful scrolls?"* Scroll rates follow MeowDB's scrolling guide
(https://meowdb.com/msclassic/forum/guides/Jacob/the-complete-scrolling-guide).

### Fill in the left side

- **Equipment** and **Cost**: a name, and the price of one base item.
- **Slots** (0 to 10): how many scroll slots the item has. Leave it blank and the app uses the number
  of scrolls you list.
- **Scrolls used**: pick a scroll type, how many of them you use and what each costs. Chaos 10% (50%
  chance to destroy the item on failure), Greater 10%, Intermediate 60% and Lesser 100%. You can add
  up to six rows. Scrolls are used from the top row down, and every scroll takes one slot whether it
  passes or fails.
- **Presets**: save the current scrolls, costs and restart rules under a name, and load them again
  later. Handy for mixes you use often.
- **Restart with a new item when**: give up on an item and start over with a fresh one when a number
  of scrolls fail in a row, a number fail in total, or particular scrolls fail (for example `1, 2`
  or `1-3` means "restart if the 1st or 2nd scroll fails"). Leave these blank (or type `0`) to keep
  scrolling every item to the end.
- **Results**: scrolls versus slots, average scrolls used, the chance an item is destroyed or
  restarted, the chance of 0 successes, and the average scroll cost. The bold sentence under it
  sums up your goal.

### Read the right side

- **Successes** shows, for 1, 2, 3 ... successful scrolls: the chance of getting *exactly* that many,
  the chance of getting *at least* that many, how many **base items** you need to buy on average to
  get one item with that result (counting the finished one), and how many **duplicates** (the other
  items, which failed, were destroyed or restarted). Choose **Avg for at least N** or **Avg for
  exactly N** for how the averages are counted.
- The four tabs under it:
  - **Cost**: what it costs to get N successes. Each cell shows the cost, with how many base items
    or scrolls that is underneath, split by scroll type, plus the total.
  - **Scrolls used**: the same, as plain counts: base items, scrolls of each type, and all scrolls.
  - **Per success**: for one success of a single scroll type, the base items and scrolls it takes
    and what they cost. For example, how many base items you burn per Chaos scroll success.
  - **Goal**: plan for a result and a budget (below).

### Goal and budget

- **Successes on each item**: how many successful scrolls a finished item needs (blank = every
  scroll succeeds). A finished item means *one item with that many successes on it*.
- **Finished items wanted**: how many such items you want (blank = 1).
- **Budget** (optional): what you are willing to spend.
- You get the **average**, **half the time within** and **9 times in 10 within** (base items and
  cost for all the items you want), and with a budget: the **chance of reaching** the number you
  want, the **finished items expected** for that money, and the number you are **9 times in 10
  sure** to get at least.
- **Send to item card** creates an item card for one finished item, right after the simulator, with
  the average base item spending and scroll spending filled in. Add your sale price there to see
  the profit.

### How to read the numbers

- Everything is an **average over many attempts**. One real attempt can be much luckier or
  unluckier. For budgeting, trust the "9 times in 10" figures more than the averages.
- The budget answers treat each base item as costing its average (with its scrolls), so they are
  close, not exact.
- The model assumes the rates you entered are exact, every scroll uses a slot pass or fail, and
  your restart rules are followed every time.

## Menus

- **Sets**: save all the cards on screen under a name (for example "Cape runs") and load them later
  (it asks before replacing what is on screen, and Undo brings it back). Also delete sets here.
- **Import**: open a cards file (replaces the cards on screen) or add the cards from a file to the
  ones you have.
- **Export**: save all cards as a file (to back up or share with someone, and import it again
  later), copy the results as text to paste into chat, or save them as a CSV file that opens in
  Excel.
- **Settings**:
  - **Auto-resize window when adding or removing items**: the window grows and shrinks to fit as you add or remove cards (off by
    default).
  - **Zoom**: the same choices as the toolbar.
  - **Theme**: light or dark (applies after you restart the app).
  - **Remember prices by nickname**: when you type a nickname you used before, the base item and
    scroll prices are filled in if those boxes are empty.
  - **How to use**: this guide. **What's new**: the changelog.
  - **Check for updates now**, **Check for updates when the app starts** and **Install updates
    automatically**: see "Updates".

## Keyboard shortcuts

- **Ctrl+Z** undo, **Ctrl+Y** or **Ctrl+Shift+Z** redo, **Ctrl+S** save (on a Mac use Cmd instead of
  Ctrl, and Cmd+Shift+Z to redo).
- **Ctrl and +**, **Ctrl and -**, **Ctrl+0** zoom in, zoom out and Auto (Cmd on a Mac).
- **F1** opens this guide.

## Saving and your data

- Your cards are saved when you press **Save** (Ctrl+S) or answer Yes when closing, and they load
  automatically the next time. A "Saved" or "Unsaved changes" note sits at the right of the toolbar.
- They are stored in a folder called "MSCW Merchant Simulator": on Windows in `%APPDATA%`, on a Mac
  in `~/Library/Application Support`, and on Linux in `~/.config`. `entries.json` holds your cards;
  `settings.json` holds your settings, sets, presets and remembered prices.
- Use **Export > Save all cards as a file** for a backup you can keep anywhere.

## Updates

- **Settings > Check for updates now** looks for a newer release. If there is one you are asked:
  **Yes** downloads, verifies and installs it and restarts the app (your cards are saved first),
  **No** skips that version, **Cancel** asks again later.
- The download is checked against the release's SHA-256 checksum and thrown away if it does not
  match. Only the downloaded apps can update themselves; running from source just shows the download
  page.
- If the app does not come back after an update on Windows, a log of what happened is at
  `%TEMP%\MSCW-Merchant-Simulator-update.log`.

## Getting the most out of it

- **Pricing an item to sell**: enter all its costs, then under "I type in" choose **Profit %** and
  type the margin you want. The **sale price** box shows what to list it for. Check the break-even
  price if you may have to sell low.
- **Comparing options**: duplicate a card and change one thing, then use **Sort by profit %** and the
  totals line.
- **Planning a scrolling run**: set up the simulator, look at **Per success** and **Cost** to see
  where the money goes, then use **Goal** with your budget to see how many finished items to expect.
  Save the mix as a **Preset**. Try a restart rule and see if the cost drops.
- **From scrolls to profit**: press **Send to item card**, add the price you can sell for, and read
  the profit.
- **Tidying up**: star what matters, collapse what is done, and save groups with **Sets**.
- **Keeping a backup or sharing**: use **Export > Save all cards as a file**.

## Troubleshooting

- **Red box / dashes in the results**: a box has something that is not a number. Fix it and the
  results come back. In the Scroll Simulator a message under "Results" says what is wrong.
- **Windows says the app is not recognised**: the app is not code-signed. Choose **More info > Run
  anyway**. On a Mac, right-click the app and choose **Open** the first time.
- **The window is too small or too big**: change the **Zoom**, or turn auto-resize on or off under
  Settings.
- **Dark theme looks wrong or did not change**: the theme applies after you restart the app.
- **Lost cards**: press **Undo**, or check your backups (**Import > Open a cards file**).
<!-- guide:end -->

## Run from source

Only needed if you don't use the downloads above. Needs Python 3 with Tkinter (no other packages). Keep `mscw_merchant_simulator.py`, `icons_data.py`, `updater.py`, `changelog_data.py` and `guide_data.py` together (run `python scripts/embed_changelog.py` to refresh the changelog and the guide the app shows).

| System | Setup | Run |
| --- | --- | --- |
| Windows | Install Python 3 from python.org | `python mscw_merchant_simulator.py` |
| macOS | Install Python 3 from python.org (Homebrew: `brew install python-tk`) | `python3 mscw_merchant_simulator.py` |
| CachyOS / Arch | `sudo pacman -S python tk` | `python mscw_merchant_simulator.py` |

`python mscw_merchant_simulator.py --version` prints the version.

## Releases

See [RELEASING.md](RELEASING.md). Every release's notes come from [CHANGELOG.md](CHANGELOG.md).
