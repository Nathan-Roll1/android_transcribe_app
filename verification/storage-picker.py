"""Exercise the app's picker over ADB without writing to its private model store."""
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

APP = "dev.notune.transcribe"
MODEL = "Fourier-2B-Q8_0.gguf"
OUT = Path(os.environ["RUNNER_TEMP"], "picker-evidence")
OUT.mkdir(exist_ok=True)

def adb(*args, check=True):
    return subprocess.run(["adb", *args], capture_output=True, check=check, timeout=30).stdout

def shell(*args):
    return adb("shell", *args).decode().strip()

def read_screen():
    for attempt in range(4):
        try:
            adb("shell", "uiautomator", "dump", "/data/local/tmp/picker-ui.xml")
            data = adb("exec-out", "cat", "/data/local/tmp/picker-ui.xml")
            return ET.fromstring(data)
        except (ET.ParseError, subprocess.SubprocessError):
            time.sleep(1)
    raise RuntimeError("Could not read Android UI hierarchy")

def get(root, *, text=None, desc=None, rid=None):
    for n in root.iter("node"):
        a = n.attrib
        if a.get("enabled") == "false":
            continue
        if text is not None and a.get("text","").casefold() != text.casefold():
            continue
        if desc is not None and a.get("content-desc","").casefold() != desc.casefold():
            continue
        if rid is not None and a.get("resource-id","").split("/")[-1] != rid:
            continue
        return n
    return None

def locate(root, candidates):
    for query in candidates:
        n = get(root, **query)
        if n is not None: return n
    return None

def snapshot(label, root):
    (OUT / (label+".xml")).write_bytes(ET.tostring(root, encoding="utf-8"))
    (OUT / (label+".png")).write_bytes(adb("exec-out","screencap","-p"))
    print(label, [(n.get("text") or n.get("content-desc"))[:82] for n in root.iter("node") if n.get("text") or n.get("content-desc")][:35], flush=True)

def tap(node):
    x1,y1,x2,y2 = [int(x) for x in re.findall(r"-?\d+", node.get("bounds",""))]
    adb("shell","input","tap",str((x1+x2)//2),str((y1+y2)//2))
    time.sleep(0.55)

def wait_for(candidates, seconds=25, allow_scroll=False):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        root = read_screen()
        n = locate(root, candidates)
        if n is not None: return root,n
        if allow_scroll: adb("shell","input","swipe","500","1750","500","730","280")
    snapshot("failed-lookup",root)
    raise RuntimeError("Missing "+str(candidates))

def in_files(root):
    return any("documentsui" in n.get("package","") for n in root.iter("node"))

def select_file():
    root, n = wait_for([{"rid":"btn_voice_add_model"},{"rid":"btn_models"}],allow_scroll=True)
    snapshot("01-no-model",root)
    tap(n)
    root,n = wait_for([{"rid":"btn_import"}],allow_scroll=True)
    snapshot("02-import-button",root)
    tap(n)
    root = read_screen()
    assert in_files(root), {n.get("package") for n in root.iter("node")}
    snapshot("03-system-picker", root)
    sources = [("Downloads",[{"text":"Downloads"}]),("internal storage",[{"text":shell("getprop","ro.product.model")},{"rid":"root_device"}])]
    visible = [{"text":MODEL}]
    for where, queries in sources:
        if get(root,text=MODEL) is not None: break
        root, menu = wait_for([{"desc":"Show roots"},{"desc":"Show navigation drawer"},{"desc":"Open navigation drawer"},{"desc":"Navigate up"}],seconds=12)
        tap(menu)
        root = read_screen()
        snapshot("04-drawer-"+where.replace(" ","-"),root)
        location=locate(root,queries)
        if location is None and where=="internal storage":
            roots=[n for n in root.iter("node") if n.get("resource-id","").endswith("/title") and n.get("text") and n.get("text") not in {"Downloads","Recent","Images","Videos","Audio","Documents","Drive","Photos"}]
            location=roots[-1] if roots else None
        if location is None:
            adb("shell","input","keyevent","BACK");root=read_screen();continue
        tap(location);root=read_screen()
        if where=="internal storage":
            folder=locate(root,[{"text":"Download"},{"text":"Downloads"}])
            if folder is not None: tap(folder);root=read_screen()
        snapshot("05-"+where.replace(" ","-"),root)
    root,n=wait_for(visible,seconds=20)
    assert in_files(root)
    snapshot("06-public-model-picked",root)
    tap(n)
    root=read_screen()
    if in_files(root):
        confirm=locate(root,[{"text":"Open"},{"desc":"Open"},{"rid":"button_select"}])
        if confirm is not None: tap(confirm)
    root,n=wait_for([{"rid":"txt_model_name","text":MODEL}],seconds=200)
    assert n.get("package")==APP
    snapshot("07-imported-model",root)
    tap(n)  # The F-Droid flavor auto-selects the first model, so this can be a no-op.

def main():
    if sys.argv[1]=="import":
        select_file()
    else:
        root,n=wait_for([{"rid":"txt_result"}],seconds=150)
        deadline=time.monotonic()+210
        expected="and so my fellow americans ask not what your country can do for you ask what you can do for your country".split()
        while time.monotonic()<deadline:
            root=read_screen()
            n=get(root,rid="txt_result")
            if n is not None and re.findall(r"[a-z]+",n.get("text","").lower())==expected:
                snapshot("08-file-transcript",root)
                print("PASS picker import + active model + 22 exact normalized spoken words",flush=True); return
            time.sleep(2)
        snapshot("failed-transcription",root);raise RuntimeError("Expected public JFK transcript")
if __name__=="__main__": main()
