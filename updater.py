"""Update checking and self-update for the downloaded (PyInstaller) builds of Profit Calculator.

Pure Python, no Tk, so it can be tested on its own. The flow is:

    fetch_latest()        ask GitHub for the newest release of this repository
    is_newer(...)         compare it with the running version
    prepare(info, dir)    download the build for THIS system and check its SHA-256 against the
                          release's SHA256SUMS.txt (nothing is installed if it does not match)
    install(archive, ..)  swap the running app for the new one and start it; the caller then exits

Self-update only happens for the downloaded apps (sys.frozen). When running from source the app
just tells you a new version exists.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

REPO = "HimekoTachibana/MSCW-Profit-Calculator"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
APP = "ProfitCalculator"
SUMS_NAME = "SHA256SUMS.txt"


class UpdateError(Exception):
    """Anything that stops an update; the message is shown to the person."""


# --------------------------------------------------------------------------- #
# Versions and file names
# --------------------------------------------------------------------------- #
def parse_version(text):
    """'v1.6.0' / '1.6.0' -> (1, 6, 0); anything else -> None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text).strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def platform_tag(system=None, machine=None):
    """The part of a release file name that names this system, or None if there is no build for it."""
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Windows":
        return "Windows-x64" if machine in ("amd64", "x86_64", "x64") else None
    if system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "macOS-AppleSilicon"
        return "macOS-Intel" if machine in ("x86_64", "amd64") else None
    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "Linux-x64"
        return "Linux-arm64" if machine in ("aarch64", "arm64") else None
    return None


def asset_name(version, tag):
    """ProfitCalculator-v1.6.0-Windows-x64.exe, ...-macOS-Intel.zip, ...-Linux-x64.tar.gz"""
    ext = ".exe" if tag.startswith("Windows") else ".zip" if tag.startswith("macOS") else ".tar.gz"
    return f"{APP}-v{version}-{tag}{ext}"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def can_self_update():
    return is_frozen() and platform_tag() is not None


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #
def _context():
    """TLS settings. The bundled certifi list is used when present (frozen macOS builds have no
    system list Python can see); otherwise the system's own."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": APP + "-updater",
                                               "Accept": "application/vnd.github+json, */*"})
    return urllib.request.urlopen(req, timeout=timeout, context=_context())


def fetch_latest(timeout=8, opener=None):
    """Newest release: {"version", "tag", "notes", "page", "assets": {file name: url}}."""
    try:
        with (opener or _open)(API_LATEST, timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:                       # offline, rate limited, no releases, ...
        raise UpdateError(f"Could not reach GitHub ({exc}).") from exc
    tag = str(data.get("tag_name", ""))
    if parse_version(tag) is None:
        raise UpdateError(f"The latest release has an unexpected version name: {tag!r}.")
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])
              if a.get("name") and a.get("browser_download_url")}
    return {"version": tag.lstrip("v"), "tag": tag, "notes": data.get("body") or "",
            "page": data.get("html_url") or RELEASES_PAGE, "assets": assets}


def parse_checksums(text):
    """Lines of 'sha256  file name' (sha256sum's format) -> {file name: lowercase hex}."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_url(url):
    if not str(url).startswith(DOWNLOAD_PREFIX):
        raise UpdateError("The release points at a download outside this project; not trusting it.")


def download(url, dest, progress=None, timeout=30, opener=None):
    _check_url(url)
    try:
        with (opener or _open)(url, timeout) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"The download failed ({exc}).") from exc


def prepare(info, workdir, progress=None, opener=None):
    """Download the build for this system into workdir and verify it. Returns the file's path."""
    tag = platform_tag()
    if tag is None:
        raise UpdateError("There is no download for this kind of computer.")
    name = asset_name(info["version"], tag)
    if name not in info["assets"]:
        raise UpdateError(f"The release {info['tag']} has no file named {name}.")
    if SUMS_NAME not in info["assets"]:
        raise UpdateError(f"The release {info['tag']} has no {SUMS_NAME}, so the download cannot be verified.")
    sums_path = os.path.join(workdir, SUMS_NAME)
    download(info["assets"][SUMS_NAME], sums_path, opener=opener)
    with open(sums_path, encoding="utf-8", errors="replace") as f:
        expected = parse_checksums(f.read()).get(name)
    if not expected:
        raise UpdateError(f"{SUMS_NAME} does not list {name}.")
    path = os.path.join(workdir, name)
    download(info["assets"][name], path, progress, opener=opener)
    if sha256_file(path) != expected:
        os.remove(path)
        raise UpdateError("The downloaded file does not match its checksum, so it was thrown away.")
    return path


# --------------------------------------------------------------------------- #
# Installing (replace the running app, start the new one)
# --------------------------------------------------------------------------- #
def clean_env():
    """Environment for the new app: without the variables PyInstaller sets for the running one."""
    drop = ("_MEIPASS2", "TCL_LIBRARY", "TK_LIBRARY", "LD_LIBRARY_PATH_ORIG")
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k not in drop}
    orig = os.environ.get("LD_LIBRARY_PATH_ORIG")      # PyInstaller on Linux keeps the user's value here
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def _writable_dir(folder):
    try:
        with tempfile.NamedTemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def windows_script(old, new, in_place):
    """PowerShell run after the app exits: swap the files (retrying while the old exe is still
    locked), then start the new one. in_place: new is moved over old; otherwise old is deleted."""
    target = old if in_place else new
    action = ("Move-Item -LiteralPath $new -Destination $old -Force -ErrorAction Stop" if in_place
              else "if ($old -ne $new) { Remove-Item -LiteralPath $old -Force -ErrorAction Stop }")
    return (f"$old = {_ps_quote(old)}; $new = {_ps_quote(new)}; $target = {_ps_quote(target)}\n"
            "for ($i = 0; $i -lt 60; $i++) {\n"
            f"  try {{ {action}; break }} catch {{ Start-Sleep -Milliseconds 500 }}\n"
            "}\n"
            "Start-Process -FilePath $target\n"
            "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n")


def mac_script(pid, app, new_app):
    """sh run after the app exits: swap the .app folders, clear the quarantine flag, open it."""
    q = lambda p: "'" + str(p).replace("'", "'\\''") + "'"
    return ("#!/bin/sh\n"
            f"i=0; while kill -0 {int(pid)} 2>/dev/null && [ $i -lt 120 ]; do sleep 0.5; i=$((i+1)); done\n"
            f"OLD={q(str(app) + '.old')}; APP={q(app)}; NEW={q(new_app)}\n"
            'rm -rf "$OLD"\n'
            'if mv "$APP" "$OLD"; then\n'
            '  if mv "$NEW" "$APP"; then rm -rf "$OLD"; else mv "$OLD" "$APP"; fi\n'
            "fi\n"
            'xattr -dr com.apple.quarantine "$APP" 2>/dev/null\n'
            'open "$APP"\n')


def linux_replace(archive, exe):
    """Put the binary inside the .tar.gz over the running one (Linux allows this) and return its path."""
    try:
        with tarfile.open(archive, "r:gz") as tar:
            member = next((m for m in tar.getmembers() if m.isfile() and os.path.basename(m.name) == APP), None)
            if member is None:
                raise UpdateError(f"The download does not contain {APP}.")
            src = tar.extractfile(member)
            tmp = os.path.join(os.path.dirname(exe), f".{APP}.update")
            with open(tmp, "wb") as out:
                shutil.copyfileobj(src, out)
        os.chmod(tmp, 0o755)
        os.replace(tmp, exe)
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError(f"Could not replace the app ({exc}).") from exc
    return exe


def _spawn(args, **kw):
    return subprocess.Popen(args, env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, close_fds=True, **kw)


def install(archive, info):
    """Install a verified download over the running app and arrange for the new one to start.

    Returns once everything is in place; the caller must then exit promptly (the helper waits
    for this process to finish). Raises UpdateError if this app cannot be replaced."""
    if not is_frozen():
        raise UpdateError("Updating itself only works in the downloaded app, not when run from source.")
    exe = os.path.abspath(sys.executable)
    system = platform.system()
    if system == "Windows":
        folder = os.path.dirname(exe)
        if not _writable_dir(folder):
            raise UpdateError(f"Cannot write to {folder}. Move the app to a folder you can write to, or "
                              "download the new version from the Releases page.")
        versioned = re.fullmatch(rf"{APP}-v\d+\.\d+\.\d+-Windows-x64\.exe", os.path.basename(exe), re.I)
        if versioned:               # keep the version in the name: new file next to it, old one removed
            new = os.path.join(folder, os.path.basename(archive))
            shutil.move(archive, new)
            script = windows_script(exe, new, in_place=False)
        else:                       # a differently named copy keeps its name
            new = exe + ".new"
            shutil.move(archive, new)
            script = windows_script(exe, new, in_place=True)
        ps1 = os.path.join(tempfile.mkdtemp(prefix="pc-update-"), "update.ps1")
        with open(ps1, "w", encoding="utf-8-sig") as f:        # BOM: Windows PowerShell then reads non-ASCII paths right
            f.write(script)
        _spawn(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden", "-File", ps1],
               creationflags=0x08000000 | 0x00000008 | 0x00000200)   # no window, detached, own group
    elif system == "Darwin":
        app = os.path.dirname(os.path.dirname(os.path.dirname(exe)))     # .../ProfitCalculator.app
        if not app.endswith(".app"):
            raise UpdateError("Could not find the app folder to replace.")
        if not _writable_dir(os.path.dirname(app)):
            raise UpdateError(f"Cannot write to {os.path.dirname(app)}. Move the app to a folder you can write "
                              "to, or download the new version from the Releases page.")
        stage = tempfile.mkdtemp(prefix="pc-update-", dir=os.path.dirname(app))
        res = subprocess.run(["ditto", "-x", "-k", archive, stage], capture_output=True)
        new_app = os.path.join(stage, APP + ".app")
        if res.returncode != 0 or not os.path.isdir(new_app):
            shutil.rmtree(stage, ignore_errors=True)
            raise UpdateError("Could not unpack the download.")
        script = mac_script(os.getpid(), app, new_app) + "rm -rf '" + stage.replace("'", "'\\''") + "'\n"
        _spawn(["/bin/sh", "-c", script], start_new_session=True)
    elif system == "Linux":
        if not _writable_dir(os.path.dirname(exe)):
            raise UpdateError(f"Cannot write to {os.path.dirname(exe)}. Move the app to a folder you can write "
                              "to, or download the new version from the Releases page.")
        linux_replace(archive, exe)
        _spawn([exe], start_new_session=True)
    else:
        raise UpdateError("Updating is not supported on this system.")
