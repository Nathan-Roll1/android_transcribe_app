import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import uiautomator2 as u2

device = u2.connect()
out = Path(sys.argv[1])
model_url = "https://huggingface.co/oruk/oruk-fourier-2b/resolve/8bcce21695e4ba13569c48de6cedffcb8a7576f5/Fourier-2B-Q8_0.gguf"
expected = "and so my fellow americans ask not what your country can do for you ask what you can do for your country".split()
def read():
    for _ in range(4):
        try:
            return ET.fromstring(device.dump_hierarchy())
        except (ET.ParseError,RuntimeError):
            time.sleep(1)
    raise RuntimeError('unable to read UI')
def find(root, word, mode='exact', pos=None):
    matches=[]
    for node in root.iter('node'):
        data=[node.get(k,'') for k in ['text','content-desc','resource-id','class']]
        if any((word.casefold() in v.casefold()) if mode=='part' else (word.casefold()==v.casefold()) for v in data):
            matches.append(node)
    return (matches[-1] if pos=='last' else matches[0]) if matches else None
def center(node):
    a,b,c,d=map(int,re.findall(r'\d+',node.get('bounds')));return (a+c)//2,(b+d)//2
def click(n):
    assert n is not None;device.click(*center(n));time.sleep(.5)
def labels(r):return [n.get('text') or n.get('content-desc') for n in r.iter('node') if n.get('text') or n.get('content-desc')]
def save(name,r=None):
    if r is None:r=read()
    (out/(name+'.xml')).write_bytes(ET.tostring(r,encoding='utf-8'))
    device.screenshot(str(out/(name+'.png')))
    print(name,labels(r)[:70],flush=True)
def await_item(word,timeout=12,mode='exact'):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        r=read()
        a=find(r,word,mode)
        if a is not None:return a
        time.sleep(.5)
    raise ValueError('Missing '+word+' on '+repr(labels(r))[:550])
def nav(word,tag):
    r=read(); n=find(r,tag);n=n if n is not None else find(r,word,pos='last');click(n)
def up():
    device.swipe(.51,.81,.51,.34,.35);time.sleep(.55)
def main():
    time.sleep(2);r=read()
    for label in ('Allow','While using the app','Only this time','Got it'):
        n=find(r,label)
        if n is not None:click(n);r=read()
    save('01-home')
    nav('Settings','scrib/tab/settings')
    expanded=False
    for attempt in range(18):
        r=read()
        n=find(r,'Add model from HuggingFace', 'part')
        if n is not None:click(n);break
        sect=find(r,'CUSTOM MODELS')
        if sect is not None and not expanded:
            click(sect);expanded=True;continue
        standard=find(r,'STANDARD MODELS')
        if standard is not None and any('Tiny' in t for t in labels(r)):click(standard);continue
        up()
    else: raise ValueError('No URL entry: '+str(labels(r)))
    save('02-url-dialog')
    edit=await_item('android.widget.EditText')
    click(edit)
    device.set_input_ime(True)
    device.send_keys(model_url,clear=True)
    r=read();assert any(model_url==n.get('text') for n in r.iter('node')),labels(r)
    save('03-entered-url',r)
    click(await_item('Download'))
    start=time.monotonic(); tick=0; first=True
    while time.monotonic()-start<890:
        r=read();txt=labels(r)
        if first:
            save('04-downloading',r);first=False
        if int(time.monotonic()-start)//25>tick:
            tick+=1;print('download elapsed',int(time.monotonic()-start),txt[:45],flush=True)
        if any('failed' in t.lower() or 'invalid link' in t.lower() for t in txt):
            raise ValueError('app reported download failure '+str(txt))
        use=find(r,'Use')
        if use is not None and any('fourier' in t.lower() for t in txt):
            save('05-imported',r);click(use);break
        if any('fourier' in t.lower() for t in txt) and find(r,'Active') is not None:
            break
        if not any('fourier' in t.lower() for t in txt):up()
        time.sleep(1)
    else:raise ValueError('timeout downloading model '+str(labels(read())))
    nav('Home','scrib/tab/home')
    r=read();save('06-active-home',r)
    assert any('fourier' in t.lower() for t in labels(r)),labels(r)
    nav('Transcribe','scrib/tab/file')
    click(await_item('Transcribe an audio file',mode='part'))
    time.sleep(2);r=read();save('07-file-picker',r)
    if find(r,'Kennedy.wav') is None:
        menu=find(r,'Show roots');menu=menu if menu is not None else find(r,'Open navigation drawer')
        if menu is not None:click(menu);n=await_item('Downloads');click(n)
    click(await_item('Kennedy.wav',18,'part'))
    time.sleep(1);r=read()
    if any('documentsui' in n.get('package','') for n in r.iter('node')):
        ok=find(r,'OPEN');ok=ok if ok is not None else find(r,'Select')
        if ok is not None:click(ok)
    save('08-file-selected')
    start=time.monotonic()
    while time.monotonic()-start<640:
        r=read()
        txt=labels(r)
        for t in txt:
            words=re.findall('[a-z]+',t.lower())
            if any(words[i:i+len(expected)]==expected for i in range(len(words)-len(expected)+1)):
                save('09-transcript',r)
                (out/'result.json').write_text(json.dumps({'source':model_url,'fixture':'Kennedy.wav','raw_visible_text':t,'normalized_reference_words':len(expected),'seconds_until_visible':round(time.monotonic()-start,1)},indent=2))
                return
        if any('failed' in t.lower() or 'cannot load' in t.lower() for t in txt):
            raise RuntimeError('app returned error: '+repr(txt))
        time.sleep(2)
    raise RuntimeError('no visible transcript: '+repr(labels(read())))
try:main()
except BaseException:
    save('error');raise
