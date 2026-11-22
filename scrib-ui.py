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

def pick_audio(name):
    """Use Android's multi-file picker. Long-press selects a file without previewing it."""
    nav('Transcribe','scrib/tab/file')
    click(await_item('Transcribe an audio file',mode='part'))
    await_item('Show roots')
    r=read()
    if find(r,name) is None:
        click(find(r,'Show roots'))
        click(await_item('Downloads'))
    time.sleep(1)
    r=read()
    list_button=find(r,'List view')
    if list_button is not None:
        click(list_button)
    item=await_item(name,15)
    device.long_click(*center(item),duration=.85)
    time.sleep(1)
    r=read()
    save(name+'-selected',r)
    for label in ('Open','Select','Choose','Done'):
        matches=[n for n in r.iter('node') if n.get('text','').lower()==label.lower()
                 and n.get('enabled')=='true']
        if matches:
            click(matches[-1])
            return
    raise RuntimeError('No file-selection confirmation in Android: '+repr(labels(r)))

def main():
    time.sleep(2);r=read()
    for label in ('Allow','While using the app','Only this time','Got it','Close'):
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
    save('04-download-requested')
    nav('Home','scrib/tab/home')
    start=time.monotonic(); tick=0
    while time.monotonic()-start<890:
        r=read();txt=labels(r)
        if int(time.monotonic()-start)//25>tick:
            tick+=1;print('download elapsed',int(time.monotonic()-start),txt[:45],flush=True)
            if tick%3==0:
                nav('Settings','scrib/tab/settings')
                settings=read();save('05-download-progress',settings)
                if any('download failed' in t.lower() for t in labels(settings)):
                    raise ValueError('Scrib could not download the model: '+str(labels(settings)))
                nav('Home','scrib/tab/home')
        if any('failed' in t.lower() or 'invalid link' in t.lower() for t in txt):
            raise ValueError('app reported download failure '+str(txt))
        # The first installed model becomes active automatically on an empty device.
        if find(r,'Fourier-2B-Q8_0') is not None:
            break
        time.sleep(1)
    else:raise ValueError('timeout downloading model '+str(labels(read())))
    r=read();save('06-active-home',r)
    assert any('fourier' in t.lower() for t in labels(r)),labels(r)
    subprocess.run(['adb','shell','cmd','connectivity','airplane-mode','enable'],check=True)
    time.sleep(4)
    mode=subprocess.check_output(['adb','shell','settings','get','global','airplane_mode_on'],text=True).strip()
    assert mode=='1',mode
    network=subprocess.check_output(['adb','shell','dumpsys','connectivity'],text=True)
    (out/'offline.txt').write_text('airplane_mode_on='+mode+'\n'+'\n'.join(x.strip() for x in network.splitlines() if 'Active default network' in x))
    fixtures = [('Kennedy.wav','audio/wav',expected),('Scenery.mp3','audio/mpeg',
          'shakespeare on scenery by oscar wilde this is a librivox recording all librivox recordings are in the public domain'.split())]
    results = []
    for name, mime, ref in fixtures:
        # Android shares a content:// URI and a one-file read grant with the same
        # ACTION_SEND receiver that the normal audio share sheet opens.
        collection='content://media/external/audio/media'
        entries=subprocess.check_output(['adb','shell','content','query','--uri',collection,
                                          '--projection','_id:_display_name'],text=True)
        matches=[re.search(r'_id=(\d+)',line).group(1) for line in entries.splitlines()
                 if line.strip().endswith('_display_name='+name)]
        assert len(matches)==1, (name,entries[:1200])
        uri=collection+'/'+matches[0]
        start=time.monotonic()
        entry='Android file picker'
        try:
            pick_audio(name)
        except (AssertionError, RuntimeError, ValueError) as exc:
            print('Picker fallback:', str(exc), flush=True)
            entry='Android shared audio (cold launch)'
            launched=subprocess.run(['adb','shell','am','start','-S','-W','-a','android.intent.action.SEND',
                '-t',mime,'--eu','android.intent.extra.STREAM',uri,'--grant-read-uri-permission',
                '-n','org.scrib.transcriber/.MainActivity'],check=True,text=True,capture_output=True)
            (out/(name+'-share.txt')).write_text(launched.stdout+launched.stderr)
            assert 'Exception' not in launched.stdout+launched.stderr,launched.stderr
        seen=set()
        while time.monotonic()-start<300:
            r=read(); txt=labels(r)
            # A fresh Android 15 install asks for permission when Scrib starts its
            # notification-backed transcription. Accept it on this disposable AVD.
            if any('allow scrib to send you notifications' in t.lower() for t in txt):
                save(name+'-notification-prompt',r)
                click(await_item('Allow'))
                continue
            change=' | '.join(txt)[:900]
            if change not in seen:
                print('share UI',name,change,flush=True);seen.add(change)
            close=find(r,'Close')
            save_button=find(r,'Save .',mode='part')
            copy=find(r,'Copy')
            title=find(r,name,mode='part')
            if close is not None and (copy is not None or save_button is not None) and title is not None:
                # These short transcripts fit in the dialog. Read from the actual app's
                # text, independent from the expected answer or relative vertical positions.
                candidates=[n.get('text','') for n in r.iter('node')
                            if n.get('package')=='org.scrib.transcriber' and len(n.get('text','').split())>=5]
                assert candidates,txt
                actual=max(candidates,key=lambda x:len(x.split()))
                words=re.findall(r'[a-z]+',actual.lower());row=list(range(len(words)+1))
                for index,w in enumerate(ref,1):
                    prior,row=row,[index]
                    for col,v in enumerate(words,1):
                        row.append(min(row[-1]+1,prior[col]+1,prior[col-1]+(w!=v)))
                save(name+'-transcript',r)
                results.append(dict(fixture=name,entry_point=entry,raw_visible_text=actual,normalized_reference_words=len(ref),
                                    word_edits=row[-1],wall_seconds=round(time.monotonic()-start,1)))
                (out/'result.json').write_text(json.dumps({'source':model_url,'apk_version':'0.31',
                                    'results':results},indent=2))
                assert row[-1]<len(ref)*.7,(actual,ref)
                click(close);break
            if close is not None and title is not None and copy is None and time.monotonic()-start>12:
                raise AssertionError('Scrib finished without a transcript: '+change)
            time.sleep(2)
        else:
            raise RuntimeError('No finished transcript for '+name+': '+repr(labels(read())))
try:main()
except BaseException:
    save('error');raise
