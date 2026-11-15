"""Match every 1.6.1 dependency in an inventory against a new stock image.

python3 tools/port/match_report.py --inventory INV.json --old stock161.bin --new stock168.bin --out MATCH.json
Read-only. Confidence (flash code):
  high          containing function identical modulo relocation
  medium        >=64 B identical context each side, function differs elsewhere
  low           identical but short context
  fuzzy-equal   inside changed code; instruction alignment finds an equal instruction
  fuzzy-changed inside changed code; the instruction itself differs  -> manual
  unmatched / ambiguous / conflict                                  -> manual
RAM: literal-pool evidence (exact), else bracketed by equal deltas, else unmatched.
"""
import argparse,json,struct,sys,collections,bisect
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fwmatch
BASE=fwmatch.BASE
import re
def fixture(t):
 f=t.split(':')[0].split('/')[-1]
 return f.startswith('test_') or '/tests/' in t or 'emulator' in t or f in ('run_arm_suite.py','fixtures.py')
def H(v):return None if v is None else '%08x'%v
class Port:
 def __init__(s,old,new):
  s.old,s.new=old,new;s.m=fwmatch.Matcher(old,new)
  segs=[(v,d,n) for v,d,n in s.m.ram_segments()]
  s.ram=segs;s.ramk=[v for v,_,_ in segs]
 def fn_identity(s,o):
  f=s.m.function_of(o)
  if not f:return None
  cov=0
  for b in s.m.candidates(o):
   cov=max(cov,min(b.e,f[1])-max(b.s,f[0]))
  return round(cov/max(1,f[1]-f[0]),3),H(BASE+f[0]),f[1]-f[0]
 def flash(s,v):
  t=v&~1;r=s.m.map(t);o=t-BASE
  out=dict(conf=r['conf'],how=r.get('how'),new=H(r['new']|(v&1)) if r.get('new') is not None else None)
  if r['conf'] in ('unmatched','ambiguous','conflict'):
   f=fwmatch.fuzzy(s.m,t)
   if f['conf'].startswith('fuzzy'):
    out.update(conf=f['conf'],how='instruction alignment in changed gap %s..%s -> %s..%s'%(f['gap_old']+f['gap_new']),new=H(f['new']|(v&1)) if f.get('new') else None)
    out['diff']=fwmatch.show_diff(f,4,t).splitlines()
   else:out['why']=f.get('how')
   if r.get('alts'):out['alts']=r['alts']
  elif r['conf']=='low':
   f=fwmatch.fuzzy(s.m,t)
   if f.get('new') is not None and f['new']==r['new']:out['conf']='low-aligned';out['how']+='; instruction alignment of the neighbouring gap agrees'
  if r.get('ref_votes'):out['ref_votes']=r['ref_votes']
  fi=s.fn_identity(o)
  if fi:out['function']=dict(start=fi[1],size=fi[2],identical_fraction=fi[0])
  return out
 def ramv(s,v):
  e=s.m.ptr_ev.get(v)
  if e:
   (top,n),*rest=e.most_common()
   if not rest:return dict(conf='exact',new=H(top),votes=n,how='native literal pool has this value (%d sites)'%n)
   if n>=2 and n>=3*rest[0][1]:return dict(conf='exact-majority',new=H(top),votes=n,how='%d native literal sites agree, %d disagree (edge-of-block noise)'%(n,sum(c for _,c in rest)))
   return dict(conf='ambiguous',how='native literals map to several values',alts={H(x):c for x,c in e.items()})
  i=bisect.bisect_right(s.ramk,v)
  lo=s.ram[i-1] if i>0 else None;hi=s.ram[i] if i<len(s.ram) else None
  if lo and hi and lo[1]==hi[1] and (v>>24)==(lo[0]>>24)==(hi[0]>>24):
   return dict(conf='bracketed',new=H(v+lo[1]),how='between native literals %08x and %08x, both delta %+#x'%(lo[0],hi[0],lo[1]))
  if lo and v-lo[0]<=0x400 and (v>>24)==(lo[0]>>24):
   return dict(conf='base+offset',new=H(v+lo[1]),how='%#x past native literal %08x (delta %+#x); next literal %s has delta %s - check the object'%(v-lo[0],lo[0],lo[1],H(hi[0]) if hi else '-',hex(hi[1]) if hi else '-'))
  return dict(conf='unmatched',how='between %s (delta %s) and %s (delta %s)'%(H(lo[0]) if lo else '-',hex(lo[1]) if lo else '-',H(hi[0]) if hi else '-',hex(hi[1]) if hi else '-'))
 def patch(s,w):
  lo=int(w['address'],16);n=w['size'];orig=bytes.fromhex(w['original_hex'])
  r=s.flash(lo)
  res=dict(address=w['address'],size=n,reason=w['reason'][:160],match=r)
  if r.get('new'):
   no=int(r['new'],16)-BASE;new_bytes=s.new[no:no+n]
   res['new_original_hex']=new_bytes.hex()
   if new_bytes==orig:res['guard']='same-bytes'
   elif fwmatch.normalise(new_bytes)==fwmatch.normalise(orig) and len(orig)%2==0:res['guard']='relocated-bytes'
   else:res['guard']='different-bytes'
  else:res['guard']='no-site'
  return res
def main():
 p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 inv=json.loads(a.inventory.read_text());P=Port(a.old.read_bytes(),a.new.read_bytes());old_end=BASE+len(P.old)
 fs=set(P.m.fstarts)
 patches=[P.patch(w) for w in inv['writes'] if w['kind']=='patch']
 flash={};ram={};noise=[];fixtures={}
 cand=collections.OrderedDict()
 for v,r in inv['refs'].items():cand[int(v,16)]=r
 for v in inv['tokens']:
  v=int(v,16);cand.setdefault(v,dict(region=None,kinds=['source'],sites=[],source_tokens=inv['tokens'][H(v) if False else hex(v)]))
 for v,r in sorted(cand.items()):
  toks=inv['tokens'].get(hex(v),r.get('source_tokens',[]))
  fw=[t for t in toks if not fixture(t)];fx=[t for t in toks if fixture(t)]
  if not r.get('sites') and not fw:   # only emulator fixtures name it: still matched (fixtures run against the new image too)
   fixtures[H(v)]=fx[:6]
   if BASE<=v<old_end:e=P.flash(v);e.update(kinds=['fixture'],uses=0,sites=[],source=[],fixtures=fx[:4]);flash[H(v)]=e
   elif 0x30000000<=v<0x30048000:e=P.ramv(v);e.update(kinds=['fixture'],uses=0,sites=[],source=[],fixtures=fx[:4]);ram[H(v)]=e
   continue
  weak=r.get('kinds')==['word']
  if BASE<=v<old_end:
   if weak and not toks and (v&~1)-BASE not in fs and v not in P.m.ptr_ev:noise.append(H(v));continue
   e=P.flash(v);e.update(kinds=r.get('kinds'),uses=r.get('uses',0),sites=r.get('sites',[])[:8],source=fw[:6],fixtures=fx[:4]);flash[H(v)]=e
  elif 0x20000000<=v<0x38010000 or 0xC0000000<=v<0xC8000000:
   if weak and not toks and v not in P.m.ptr_ev:noise.append(H(v));continue
   e=P.ramv(v);e.update(kinds=r.get('kinds'),uses=r.get('uses',0),sites=r.get('sites',[])[:8],source=fw[:6],fixtures=fx[:4]);ram[H(v)]=e
 summary=dict(patches=collections.Counter(x['guard']+'/'+x['match']['conf'] for x in patches),
  fixture_only=len(fixtures),flash=collections.Counter(x['conf'] for x in flash.values()),ram=collections.Counter(x['conf'] for x in ram.values()),noise_words_dropped=len(noise))
 json.dump(dict(summary=summary,patches=patches,flash=flash,ram=ram,fixture_only=fixtures,dropped_noise=noise),a.out.open('w'),indent=1)
 print(json.dumps(summary,indent=1))
if __name__=='__main__':main()
