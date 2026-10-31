"""Alpha 1.0: exact W22 functionality with the readable native version name.
The palette is applied last and folded into the reversible write list.
Historical releases retain their pinned builders."""
from pathlib import Path
import argparse,subprocess,sys,os,shutil,json,hashlib,re
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--stock',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--test',action='store_true');p.add_argument('--no-motion',action='store_true',help='Compatibility flag: retired recorder stays excluded; native clip capture remains included');a=p.parse_args()
out=a.out.resolve();stock=a.stock.resolve()
if out.exists() and any(out.iterdir()):raise SystemExit('Choose an empty output directory')
out.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,str(ROOT/'tools/build_k16.py'),'--stock',str(stock),'--out',str(out/'baseline')],check=True)
work=out/'workspace';work.mkdir()
for name in ['eu4_work','tf2_work','k16_work','k16_overlay','chord_work','research/display_emulator']:
 shutil.copytree(ROOT/name,work/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.elf','*.o','*.so','arm_objects'))
baseline=out/'baseline/bento1.bin'
subprocess.run([sys.executable,str(work/'eu4_work/integration/build_fx.py'),str(baseline),str(out)],check=True,env=dict(os.environ,BENTO_NATIVE_MOTION='0'))
# Keep the extension-stage image for guarded comparisons and recovery.
fx=out/'fx';fx.mkdir()
for f in ['bento1.bin','manifest.json']:shutil.copy(out/f,fx/f)
fxui=json.loads((fx/'manifest.json').read_text())['ui_symbols']
assert len((fx/'bento1.bin').read_bytes())+0x08040000<=0x081e0000,'Application must stay below 081E0000; the retired motion M4 reservation is unused'
motion={'writes':[]} # Retired motion_work is never a build default.
# G1: Playground palette and pad colours, last step, recorded as writes.
sys.path.insert(0,str(ROOT/'tools'));import playground_palette as mp
before=(out/'bento1.bin').read_bytes();after,_=mp.apply(before)
from preview_identity import apply as preview_identity, LABEL
after,identity_writes=preview_identity(after)
(out/'bento1.bin').write_bytes(after)
pal=[];i=0
while i<len(after):
 if i>=len(before) or after[i]!=before[i]:
  j=i
  while j<len(after) and (j>=len(before) or after[j]!=before[j]):j+=1
  pal.append(dict(address=0x08040000+i,size=j-i,original_hex=before[i:j].hex(),replacement_hex=after[i:j].hex(),reason='Playground palette / release identity'));i=j
 else:i+=1
(out/'PALETTE_MANIFEST.json').write_text(json.dumps(dict(writes=pal),indent=2)+'\n')
image=(out/'bento1.bin').read_bytes();base=baseline.read_bytes();original=stock.read_bytes()
assert len(image)%4==0 and 0x08040000+len(image)<=0x081e0000,'P22: the application must end below the last flash sector 081E0000 (owner: verify error 19)'
fm=json.loads((out/'baseline/FULL_MANIFEST.json').read_text());extra=json.loads((out/'manifest.json').read_text())
merged=[]
for w in fm['writes']:
 w=dict(w);o=w['address']-0x08040000
 if not w['original_hex']:w['size']=len(image)-o
 w['replacement_hex']=image[o:o+w['size']].hex();merged.append(w)
for w in extra['writes']:
 lo=w['address'];hi=lo+w['size']
 if any(x['address']<=lo and hi<=x['address']+x['size'] for x in merged):continue
 if lo>=0x08040000+len(original):continue
 # A2: the synth cave payload grew past K16's original cave write; record only
 # the part beyond it (stock bytes there are the same verified-zero cave).
 grown=[x for x in merged if x['address']<=lo<x['address']+x['size']<hi]
 if grown:
  end=grown[0]['address']+grown[0]['size'];o=end-0x08040000
  assert original[o:o+hi-end]==bytes(hi-end),'cave growth must cover zero stock bytes'
  w=dict(w,address=end,size=hi-end,replacement_hex=image[o:o+hi-end].hex(),reason='synth cave growth: '+w['reason']);lo=end
 assert not any(lo<x['address']+x['size'] and x['address']<hi for x in merged)
 w=dict(w);o=lo-0x08040000;w['original_hex']=original[o:o+w['size']].hex();merged.append(w)
# Motion writes may land on Playground writes (it chains existing hooks); fold
# everything into disjoint ranges against stock: original = stock (zero past
# its end), replacement = the final image.
spans=sorted([(w['address'],w['address']+w['size'],w['reason']) for w in merged+motion['writes']+pal])
folded=[]
for lo,hi,why in spans:
 if folded and lo<=folded[-1][1]:folded[-1][1]=max(folded[-1][1],hi);folded[-1][2].append(why)
 else:folded.append([lo,hi,[why]])
merged=[]
for lo,hi,whys in folded:
 o=lo-0x08040000;orig=original[o:hi-0x08040000];orig=orig+bytes(hi-lo-len(orig))
 merged.append(dict(address=lo,size=hi-lo,original_hex=orig.hex(),replacement_hex=image[o:hi-0x08040000].hex(),reason='; '.join(dict.fromkeys(whys))[:400]))
restored=bytearray(image)
for w in reversed(merged):
 o=w['address']-0x08040000;restored[o:o+w['size']]=bytes.fromhex(w['original_hex'])
assert bytes(restored[:len(original)])==original and not any(restored[len(original):])
report=dict(label=LABEL,native_motion=False,clip_motion=True,sha256=hashlib.sha256(image).hexdigest(),stock_sha256=digest(stock),baseline_sha256=digest(baseline),writes=merged)
(out/'FULL_MANIFEST.json').write_text(json.dumps(report,indent=2)+'\n')
env=dict(os.environ,BENTO_STOCK_IMAGE=str(stock),BENTO_K16_IMAGE=str(baseline),BENTO_FX_CANDIDATE=str(out))
records={}
for name in ['eu4_work','tf2_work','k16_work','k16_overlay','chord_work']:
 for f in (work/name).rglob('*'):
  if not f.is_file() or f.suffix in ['.elf','.pyc','.o','.so'] or '__pycache__' in f.parts:continue
  rel=f.relative_to(work);assert f.read_bytes()==(ROOT/rel).read_bytes(),str(rel)
  records[rel.as_posix()]=digest(f)
(out/'SOURCE_INPUTS.json').write_text(json.dumps(records,indent=2)+'\n')
print(report['label'],report['sha256'],len(image),'bytes; exact stock and K16 reversal verified')

if a.test:
 subprocess.run([sys.executable,str(ROOT/'chord_work/build.py'),'--out',str(out/'chord-core')],check=True)
 subprocess.run([sys.executable,str(ROOT/'tools/validate_p30.py'),'--build',str(out),'--stock',str(stock),'--core',str(out/'chord-core')],check=True)
