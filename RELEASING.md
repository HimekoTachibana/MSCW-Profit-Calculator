# Releasing

Versions follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: changes that break saved data or remove features
- **MINOR**: new features
- **PATCH**: bug fixes and small tweaks

Everything below can be done in the browser on GitHub.

## 1. Prepare the version (edit files on GitHub, commit to `main`)

1. In `profit_calculator.py`, change `__version__` (for example to `"1.1.0"`).
2. In `CHANGELOG.md`, rename the `## [Unreleased]` entries into a new `## [1.1.0] - YYYY-MM-DD`
   section (use **Added**, **Changed**, **Fixed**, **Removed** headings), leave a fresh empty
   `## [Unreleased]` above it, and add the compare link at the bottom.

## 2. Build and publish (Actions tab)

1. Open the repo's **Actions** tab and choose **Build & Release** in the left list.
2. Click **Run workflow**, keep the branch on **main**, and tick **Publish a GitHub release**.
3. Click the green **Run workflow** button.

The workflow reads the version from `profit_calculator.py`, checks that `CHANGELOG.md` has an entry
for it and that the tag does not exist yet, builds standalone apps (Windows x64, macOS Apple Silicon
+ Intel, Linux x64 + arm64), starts each built app with `--selftest`, and only then creates the tag
`v<version>` and publishes the release. The release notes are that version's changelog section, and
a `SHA256SUMS.txt` is attached. If any check, build or self-test fails, nothing is tagged or published.

## Trying a build without releasing

Run the same workflow with **Publish a GitHub release** left unticked. The apps appear under that
run's **Artifacts**, and no tag or release is created.

## Changing the pictures

The pictures live in `assets/source/`. After replacing one, run `python scripts/make_icons.py`
(needs `pip install pillow`) and commit the regenerated `assets/` and `icons_data.py`.

## If something goes wrong

- *"Tag v1.1.0 already exists"*: bump `__version__` and add a new changelog entry, then run again.
- *A build or self-test failed*: open the failed job's log; nothing was published, so fix and rerun.
- *Published a bad release*: on the **Releases** page delete the release, then delete the tag (the
  tags list on the repo's main page), fix the problem, and run the workflow again.

## Command-line alternative

Pushing a tag also works: `git tag v1.1.0 && git push origin v1.1.0`. The tag must match
`__version__`. To check locally: `python scripts/release_notes.py --check v1.1.0`; to preview the
release notes: `python scripts/release_notes.py v1.1.0`.

## How in-app updates find a release

The app asks GitHub for the repository's *latest* release and looks for the file named
`ProfitCalculator-v<version>-<system>.<ext>` plus `SHA256SUMS.txt`. The workflow produces exactly
those names, so do not rename release files by hand. Draft and pre-releases are not offered.
`python tests/test_updater.py` checks the logic locally.
