"""Tests for updater.py. Run: python tests/test_updater.py  (the release workflow runs it on every OS)."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import updater as u

# versions / names
assert u.parse_version("v1.6.0")==(1,6,0) and u.parse_version("1.10.2")==(1,10,2) and u.parse_version("1.6")is None and u.parse_version("v1.6.0-rc1") is None
assert u.is_newer("1.10.0","1.9.9") and not u.is_newer("1.6.0","1.6.0") and not u.is_newer("1.5.9","1.6.0") and not u.is_newer("junk","1.0.0")
for (s,m),exp in {("Windows","AMD64"):"Windows-x64",("Windows","ARM64"):None,("Darwin","arm64"):"macOS-AppleSilicon",("Darwin","x86_64"):"macOS-Intel",("Linux","x86_64"):"Linux-x64",("Linux","aarch64"):"Linux-arm64",("FreeBSD","x86_64"):None}.items():
    assert u.platform_tag(s,m)==exp,(s,m)
assert u.asset_name("1.6.0","Windows-x64")=="MSCW-Merchant-Simulator-v1.6.0-Windows-x64.exe"
assert u.asset_name("1.6.0","macOS-Intel")=="MSCW-Merchant-Simulator-v1.6.0-macOS-Intel.zip"
assert u.asset_name("1.6.0","Linux-arm64")=="MSCW-Merchant-Simulator-v1.6.0-Linux-arm64.tar.gz"
h="a"*64
assert u.parse_checksums(f"{h}  MSCW-Merchant-Simulator-v1-x.exe\n{'B'*64} *other.zip\nbad line")=={"MSCW-Merchant-Simulator-v1-x.exe":h,"other.zip":"b"*64}

# fetch_latest with a fake opener
class R:
    def __init__(s,b,headers=None): s.b=b; s.headers=headers or {}; s.p=0
    def read(s,n=-1):
        if n<0: n=len(s.b)
        c=s.b[s.p:s.p+n]; s.p+=len(c); return c
    def __enter__(s): return s
    def __exit__(s,*a): pass
API={"tag_name":"v9.9.9","body":"notes","html_url":"https://github.com/x","assets":[]}
tag=u.platform_tag(); print("this system:",tag)
name=u.asset_name("9.9.9",tag)
payload=os.urandom(300000)
sums=f"{hashlib.sha256(payload).hexdigest()}  {name}\n".encode()
base=u.DOWNLOAD_PREFIX+"v9.9.9/"
API["assets"]=[{"name":name,"browser_download_url":base+name},{"name":u.SUMS_NAME,"browser_download_url":base+u.SUMS_NAME}]
def opener(url,timeout):
    if url==u.API_LATEST: return R(json.dumps(API).encode())
    if url==base+name: return R(payload,{"Content-Length":str(len(payload))})
    if url==base+u.SUMS_NAME: return R(sums)
    raise OSError("404 "+url)
info=u.fetch_latest(opener=opener); assert info["version"]=="9.9.9" and name in info["assets"]
d=tempfile.mkdtemp(); seen=[]
p=u.prepare(info,d,progress=lambda a,b:seen.append((a,b)),opener=opener)
assert open(p,"rb").read()==payload and seen[-1]==(300000,300000)
# tampered download is rejected and removed
bad=dict(info); 
def opener2(url,timeout):
    r=opener(url,timeout)
    if url==base+name: return R(payload[:-1]+b"X",{"Content-Length":str(len(payload))})
    return r
d2=tempfile.mkdtemp()
try: u.prepare(info,d2,opener=opener2); raise SystemExit("tampered file accepted!")
except u.UpdateError as e: print("tamper ->",e); assert not os.path.exists(os.path.join(d2,name))
# missing checksum file / foreign url
i2=dict(info); i2["assets"]={k:v for k,v in info["assets"].items() if k!=u.SUMS_NAME}
try: u.prepare(i2,tempfile.mkdtemp(),opener=opener); raise SystemExit("no sums accepted")
except u.UpdateError as e: print("no sums ->",e)
i3=dict(info); i3["assets"]=dict(info["assets"]); i3["assets"][name]="https://evil.example/x"
try: u.prepare(i3,tempfile.mkdtemp(),opener=opener); raise SystemExit("foreign url accepted")
except u.UpdateError as e: print("foreign ->",e)
try: u.fetch_latest(opener=lambda *a: (_ for _ in ()).throw(OSError("offline"))); raise SystemExit
except u.UpdateError as e: print("offline ->",e)

# linux replace: tar with the binary inside, replacing a "running" file
w=tempfile.mkdtemp(); exe=os.path.join(w,"MSCW-Merchant-Simulator"); open(exe,"w").write("old"); os.chmod(exe,0o755)
tgz=os.path.join(w,"new.tar.gz")
src=os.path.join(w,"src"); open(src,"w").write("#!/bin/sh\necho new\n")
with tarfile.open(tgz,"w:gz") as t: t.add(src,arcname="MSCW-Merchant-Simulator")
u.linux_replace(tgz,exe); assert open(exe).read().startswith("#!/bin/sh") and os.access(exe,os.X_OK) and not os.path.exists(os.path.join(w,".MSCW-Merchant-Simulator.update"))
with tarfile.open(tgz,"w:gz") as t: t.add(src,arcname="wrong")
try: u.linux_replace(tgz,exe); raise SystemExit
except u.UpdateError as e: print("no binary ->",e)

if platform.system() != 'Windows':
  # mac script: run it for real with stub open/xattr, a finished pid, fake .app dirs
  m=tempfile.mkdtemp(); app=os.path.join(m,"MSCW-Merchant-Simulator.app"); os.makedirs(app+"/Contents"); open(app+"/Contents/v","w").write("old")
  stage=os.path.join(m,"stage"); new=os.path.join(stage,"MSCW-Merchant-Simulator.app"); os.makedirs(new+"/Contents"); open(new+"/Contents/v","w").write("new")
  bin_=os.path.join(m,"bin"); os.makedirs(bin_)
  for c in ("open","xattr"):
      open(os.path.join(bin_,c),"w").write(f"#!/bin/sh\necho {c} \"$@\" >> '{m}/calls'\n"); os.chmod(os.path.join(bin_,c),0o755)
  dead=subprocess.Popen(["true"]); dead.wait()
  script=u.mac_script(dead.pid,app,new)+"rm -rf '"+stage+"'\n"
  open(os.path.join(m,"s.sh"),"w").write(script)
  r=subprocess.run(["sh","-n",os.path.join(m,"s.sh")]); assert r.returncode==0
  r=subprocess.run(["sh",os.path.join(m,"s.sh")],env={**os.environ,"PATH":bin_+":"+os.environ["PATH"]},timeout=20)
  assert open(app+"/Contents/v").read()=="new" and not os.path.exists(app+".old") and not os.path.exists(stage)
  print("mac calls:",open(os.path.join(m,"calls")).read().split("\n")[:2])
  # mac script with a path containing a quote and a space
  m2=tempfile.mkdtemp(); app2=os.path.join(m2,"it's mine","MSCW-Merchant-Simulator.app"); os.makedirs(app2); new2=os.path.join(m2,"n","MSCW-Merchant-Simulator.app"); os.makedirs(new2); open(new2+"/f","w").write("n")
  open(os.path.join(m2,"s.sh"),"w").write(u.mac_script(dead.pid,app2,new2)); 
  subprocess.run(["sh",os.path.join(m2,"s.sh")],env={**os.environ,"PATH":bin_+":"+os.environ["PATH"]},timeout=20)
  assert os.path.exists(app2+"/f"), "quoted path swap failed"

# windows script text (cannot run PowerShell here): check quoting of awkward paths
ws=u.windows_script(r"C:\Users\O'Neil\Downloads\MSCW-Merchant-Simulator-v1.0.0-Windows-x64.exe", r"C:\Users\O'Neil\Downloads\MSCW-Merchant-Simulator-v1.1.0-Windows-x64.exe", False)
print(ws)
assert "O''Neil" in ws and "Remove-Item" in ws and "$target = 'C:\\Users\\O''Neil\\Downloads\\MSCW-Merchant-Simulator-v1.1.0-Windows-x64.exe'" in ws
wi=u.windows_script(r"C:\a\PC.exe", r"C:\a\PC.exe.new", True); assert "Move-Item" in wi and "$target = 'C:\\a\\PC.exe'" in wi
# install refuses to run from source
try: u.install("x",info); raise SystemExit
except u.UpdateError as e: print("source ->",e)

# the real PowerShell swap, on Windows only (whoami.exe stands in for the app: it starts and ends at once)
if platform.system() == "Windows":
    who = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "whoami.exe")
    def ps(script_text, wait=True):
        d = tempfile.mkdtemp(); f = os.path.join(d, "u.ps1")
        with open(f, "w", encoding="utf-8-sig") as fh: fh.write(script_text)
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", f]
        return (subprocess.run(cmd, timeout=90, check=True) if wait else subprocess.Popen(cmd)), f
    d = tempfile.mkdtemp(prefix="O'Neil \u00e9 ")
    old = os.path.join(d, "MSCW-Merchant-Simulator-v1.0.0-Windows-x64.exe"); new = os.path.join(d, "MSCW-Merchant-Simulator-v1.1.0-Windows-x64.exe")
    shutil.copy(who, old); shutil.copy(who, new)
    _, f = ps(u.windows_script(old, new, False))
    assert not os.path.exists(old) and os.path.exists(new) and not os.path.exists(f), "versioned swap"
    old2 = os.path.join(d, "PC.exe"); shutil.copy(who, old2); open(old2 + ".new", "wb").write(open(who, "rb").read() + b"\0")
    ps(u.windows_script(old2, old2 + ".new", True))
    assert os.path.exists(old2) and not os.path.exists(old2 + ".new") and os.path.getsize(old2) == os.path.getsize(who) + 1, "in-place swap"
    # a locked old exe (as while the app is still running): the script must wait, then finish
    old3 = os.path.join(d, "MSCW-Merchant-Simulator-v1.2.0-Windows-x64.exe"); new3 = os.path.join(d, "MSCW-Merchant-Simulator-v1.3.0-Windows-x64.exe")
    shutil.copy(who, old3); shutil.copy(who, new3)
    held = open(old3, "rb")                      # Python opens without share-delete, like a running exe
    proc, _ = ps(u.windows_script(old3, new3, False), wait=False)
    time.sleep(3)
    assert os.path.exists(old3), "deleted a locked file?!"
    held.close(); proc.wait(timeout=60)
    assert not os.path.exists(old3) and os.path.exists(new3), "swap after the lock was released"
    print("windows swap OK")

# install() end to end on Linux: a fake frozen app replaces itself and starts the new one
if platform.system() == "Linux":
    d = tempfile.mkdtemp(); exe = os.path.join(d, "MSCW-Merchant-Simulator")
    open(exe, "w").write("#!/bin/sh\necho old\n"); os.chmod(exe, 0o755)
    marker = os.path.join(d, "started"); newsrc = os.path.join(d, "n")
    open(newsrc, "w").write(f"#!/bin/sh\necho started > '{marker}'\n")
    arch = os.path.join(d, "a.tar.gz")
    with tarfile.open(arch, "w:gz") as t: t.add(newsrc, arcname="MSCW-Merchant-Simulator")
    real = (sys.executable, getattr(sys, "frozen", False))
    sys.executable, sys.frozen = exe, True
    try: u.install(arch, {"version": "9.9.9"})
    finally: sys.executable = real[0]; sys.frozen = real[1]
    for _ in range(50):
        if os.path.exists(marker): break
        time.sleep(0.1)
    assert os.path.exists(marker) and "started" in open(exe).read(), "install() on Linux"
    print("linux install OK")

print("ALL UPDATER TESTS PASSED")
