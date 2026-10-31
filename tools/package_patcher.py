"""Build a standalone local browser/CLI patcher without original firmware images."""
from pathlib import Path
import argparse,base64,hashlib,html,json,sys,zipfile
from make_drum_carriers import make
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'patcher'))
from patch_bento import apply_patch
STOCK='14475e9d5068f5659d0fe0b00fc1278c1479c43ed9fda3d40654d5f3a7a6bbb3'
CONTROLLER='8100906327093463fb58f531ee28583423a9881ea3a7d5b77874a7700735e99d'
def digest(b):return hashlib.sha256(b).hexdigest()
RELEASES={
 '1.6E9':('EU9','White velocity symbols, lock conditions and Select in the sequencer header.'),
 '1.6W22':('W22','Programmable drums, Euclidean patterns, chords, Arp, macros, track effects and hands-on shortcuts. Motion now includes Wavetable Position, loaded waveforms keep their own display, and holding PLAY shows the first track&#39;s one-shot mute lights.'),
 'Preview 0.1':('Preview_0.1','Five drum synths, Analog synthesis, editable Euclidean patterns, chords, Arp, macros, track effects and navigation shortcuts. Motion captures supported instrument controls into native A-D lanes. Experimental; device validation remains pending.'),
 'Alpha 1.0':('Alpha_1.0','Five drum synths, Analog synthesis, editable Euclidean patterns, chords, Arp, macros, track effects and navigation shortcuts. Motion captures supported instrument controls into native A-D lanes. Experimental; device validation remains pending.')
}
def package(stock,controller,image,out,label='1.6E9',source_url=None):
 assert digest(stock)==STOCK and digest(controller)==CONTROLLER
 release,overview=RELEASES[label]
 if label in ('Preview 0.1','Alpha 1.0'):
  from preview_identity import displayed_version
  assert displayed_version(image)==label
  expected={'Preview 0.1':'a6e22c9a0f876cf04d4fc747c8988bfad6cb01ca14c4b8ec5e283eebe103b0da',
            'Alpha 1.0':'ca569652cafc82efbc339bdd38ae81a5a8673caff7ce76b67bff18774c74ec4e'}
  assert digest(image)==expected[label],'Exact '+label+' image required'
 else:assert image[0x818bad4-0x8040000:][:len(label)+1]==label.encode()+b'\0'
 assert len(image)%4==0 and 0x08040000+len(image)<=0x081e0000
 if label=='1.6W22':assert digest(image)=='d618b84c271d1f1791597a13d3304bbcc617132b4aad73dbf19c624234240724','Exact delivered W22 image required'
 writes=[];i=0
 while i<len(image):
  if i<len(stock) and stock[i]==image[i]:i+=1;continue
  start=i;i+=1
  while i<len(image) and (i>=len(stock) or stock[i]!=image[i]):i+=1
  writes.append([start,base64.b64encode(image[start:i]).decode()])
 import tempfile
 with tempfile.TemporaryDirectory() as tmp:
  carriers={p.name:base64.b64encode(p.read_bytes()).decode() for p in make(tmp).iterdir() if label!='1.6E9' or p.name in ('BENTO_Kick_K2.wav','BENTO_Synth_Snare.wav','BENTO_Synth_HiHat.wav')}
 p=dict(format='bento-delta-v1',label=label,install_filename=f'Bento_{release}_Install.zip',input_size=len(stock),input_sha256=STOCK,controller_sha256=CONTROLLER,output_size=len(image),output_sha256=digest(image),writes=writes,carriers=carriers)
 if source_url:p['source_url']=source_url
 assert apply_patch(stock,controller,p)==image
 data=json.dumps(p,separators=(',',':'));page=(ROOT/'patcher/patcher.template.html').read_text().replace('__PATCH_DATA__',data).replace('__LABEL__',html.escape(label)).replace('__RELEASE_OVERVIEW__',overview)
 readme=f'''Bento Playground {label} offline patcher - experimental

1. Extract this ZIP.
2. Double-click OPEN_BENTO_PATCHER.html to open it in your browser.
3. Select bento1.bin AND bento2.bin from your original Bento 1.6.1 download.
4. Click Create firmware ZIP. The patcher checks both inputs and the finished output.
5. Open that new ZIP and follow 00_START_HERE.txt.

No installation, account or internet connection is needed. No original firmware
images are included in this patcher. It does not flash or connect to Bento.
Older modified firmware, unsupported versions and damaged files are refused.

For developers: python3 patch_bento.py --main /path/to/original/bento1.bin --controller /path/to/original/bento2.bin --out Bento_{release}_Install.zip
The newest changes still need hardware testing. Back up your projects first.
Source: {source_url or 'See the source repository accompanying this release.'}
'''
 out.mkdir(parents=True,exist_ok=True)
 assert not any(out.iterdir()),'Choose an empty patcher output directory'
 names=['OPEN_BENTO_PATCHER.html',release+'.patch.json','README.txt','patch_bento.py','LICENSE','THIRD_PARTY_NOTICES.md']
 (out/'OPEN_BENTO_PATCHER.html').write_text(page);(out/(release+'.patch.json')).write_text(data);(out/'README.txt').write_text(readme);(out/'patch_bento.py').write_bytes((ROOT/'patcher/patch_bento.py').read_bytes())
 for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:(out/name).write_bytes((ROOT/name).read_bytes())
 zpath=out.parent/f'Bento_{release}_Offline_Patcher.zip'
 assert not zpath.exists(),'Refusing to overwrite an existing patcher'
 with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
  for name in names:z.write(out/name,f'Bento_{release}_Offline_Patcher/'+name)
 with zipfile.ZipFile(zpath) as z:assert z.testzip() is None
 print(zpath.resolve(),digest(zpath.read_bytes()),'delta ranges',len(writes));return p
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stock-dir',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--source-url');a=p.parse_args();m=json.loads(a.image.with_name('FULL_MANIFEST.json').read_text());assert m['label'] in RELEASES and digest(a.image.read_bytes())==m['sha256'];package((a.stock_dir/'bento1.bin').read_bytes(),(a.stock_dir/'bento2.bin').read_bytes(),a.image.read_bytes(),a.out,m['label'],a.source_url)
