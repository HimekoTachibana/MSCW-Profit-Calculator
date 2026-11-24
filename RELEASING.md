# Releasing

Versions follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: changes that break saved data or remove features
- **MINOR**: new features
- **PATCH**: bug fixes and small tweaks

## Steps

1. Change `__version__` in `profit_calculator.py` (for example `"1.1.0"`).
2. In `CHANGELOG.md`, rename the `## [Unreleased]` entries into a new `## [1.1.0] - YYYY-MM-DD`
   section (use **Added**, **Changed**, **Fixed**, **Removed** headings), leave a fresh empty
   `## [Unreleased]` above it, and add the compare link at the bottom.
3. Commit and push to `main`.
4. Create and push the tag, which must be `v` + the version:

   ```
   git tag v1.1.0
   git push origin v1.1.0
   ```

5. The **Build & Release** workflow checks that the tag, `__version__` and changelog agree, builds
   standalone apps (Windows x64, macOS Apple Silicon + Intel, Linux x64 + arm64), starts each built
   app with `--selftest`, and only then publishes the release with the changelog section as its
   notes plus a `SHA256SUMS.txt`. If any build or self-test fails, nothing is published.

To test the builds without releasing, open the repo's **Actions** tab, choose **Build & Release**,
and click **Run workflow**. The apps appear under that run's **Artifacts**.

If a check fails, fix the problem, delete the tag (`git tag -d v1.1.0 && git push origin :refs/tags/v1.1.0`)
and tag again.

You can run the check locally: `python scripts/release_notes.py --check v1.1.0`, and preview the
release notes with `python scripts/release_notes.py v1.1.0`.
