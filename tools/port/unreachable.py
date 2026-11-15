"""Space accounting only: native code made unreachable by Playground (read-only).

Candidates: native functions whose entry is overwritten by one of our patches,
and native functions whose pointer we replaced in a vtable/table slot.
A candidate range [start, end) is reclaimable only if, in the FINAL image:
 (a) its entry is redirected (patch at start, or slot repointed) and nothing else
     enters it;
 (b) no reference from outside the dead set lands inside it. References are
     collected conservatively over the whole image (native and ours): every
     decodable BL/BLX/B.W/B<c>.W/B/B<c>/CBZ/CBNZ target at every halfword, every
     PC-relative literal/ADR target, and every aligned 32-bit word, any of them
     possibly data (false positives only shrink the result);
 (c) literal pools inside the range: any load from outside lands inside -> (b);
 (d) is a property of the later patch, not checked here.
Callees referenced only from dead ranges are added until a fixpoint.
Function extent = next function start (BL targets with prologue, pointer targets,
vtable slots); extents are approximate, so every row carries a confidence.
"""
import argparse,json,struct,bisect,collections,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fwmatch
B=fwmatch.BASE
def refs(img,lo_img,hi_img):
 """target -> set(source offsets)"""
 R=collections.defaultdict(set);L=len(img)
 for o in range(0,L-4,2):
  h1=img[o]|img[o+1]<<8;h2=img[o+2]|img[o+3]<<8;a=B+o
  if h1&0xF800==0xF000 and h2&0xC000==0x8000|0x4000 or (h1&0xF800==0xF000 and h2&0xD000 in(0xD000,0xC000,0x9000)):
   r=fwmatch.bl_target(img,o)
   if r:R[r[1]].add(a)
  if h1&0xF800==0xF000 and h2&0xD000==0x8000:   # B<c>.W T3
   s=(h1>>10)&1;j1=(h2>>13)&1;j2=(h2>>11)&1
   imm=(s<<20)|(j2<<19)|(j1<<18)|((h1&0x3F)<<12)|((h2&0x7FF)<<1)
   if s:imm-=1<<21
   R[a+4+imm].add(a)
  if h1&0xF800==0xE000:                             # B T2
   imm=(h1&0x7FF)<<1
   if imm&0x800:imm-=0x1000
   R[a+4+imm].add(a)
  if h1&0xF000==0xD000 and (h1>>8)&0xF<0xE:         # B<c> T1
   imm=(h1&0xFF)<<1
   if imm&0x100:imm-=0x200
   R[a+4+imm].add(a)
  if h1&0xF500==0xB100:                             # CBZ/CBNZ
   R[a+4+(((h1>>9)&1)<<6|((h1>>3)&0x1F)<<1)].add(a)
  if h1&0xF800==0x4800:R[((a+4)&~3)+(h1&0xFF)*4].add(a)      # LDR lit
  if h1&0xF800==0xA000:R[((a+4)&~3)+(h1&0xFF)*4].add(a)      # ADR
  if h1 in(0xF8DF,0xF85F):d=h2&0xFFF;R[((a+4)&~3)+(d if h1==0xF8DF else -d)].add(a)
 for o in range(0,L-3,4):
  v=struct.unpack_from('<I',img,o)[0]
  if lo_img<=v<hi_img:R[v&~1].add(B+o)
 return R
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--stock',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 stock=a.stock.read_bytes();img=(a.build/'bento1.bin').read_bytes();man=json.loads((a.build/'FULL_MANIFEST.json').read_text())
 send=B+len(stock)
 m=fwmatch.Matcher(stock,stock)   # function starts of stock
 starts=set(B+x for x in m.fstarts)
 for o in range(0,len(stock)-3,4):
  v=struct.unpack_from('<I',stock,o)[0]
  if v&1 and B<=v<send:
   t=(v&~1)-B;h=struct.unpack_from('<H',stock,t)[0]
   if h&0xFF00 in(0xB500,0xB400) or h==0xE92D or h&0xFF80==0xB080:starts.add(v&~1)
 starts=sorted(starts)
 def extent(s):
  i=bisect.bisect_right(starts,s);return s,starts[i] if i<len(starts) else s+0x100
 patches=[w for w in man['writes'] if w['address']<send and any(bytes.fromhex(w['original_hex']))]
 patched=lambda x:any(w['address']<=x<w['address']+w['size'] for w in patches)
 cand={}
 for w in patches:
  lo=w['address']
  if lo in starts:cand[lo]='entry patched (%s)'%w['reason'][:60]
  o=bytes.fromhex(w['original_hex'])
  for k in range(0,len(o)-3,4):
   if (lo+k)%4:continue
   v=struct.unpack_from('<I',o,k)[0]
   if v&1 and B<=v<send and (v&~1) in starts:cand.setdefault(v&~1,'pointer slot %08x repointed (%s)'%(lo+k,w['reason'][:50]))
 R=refs(img,B,0x08200000)
 dead={}
 def outside_refs(lo,hi,deadset):
  bad=[]
  for t in range(lo,hi,1):
   for src in R.get(t,()):
    if lo<=src<hi:continue
    if any(dl<=src<dh for dl,dh in deadset):continue
    if patched(src) and src==lo and t==lo:continue
    bad.append((t,src))
  return bad
 # fixpoint: candidates first, then callees only referenced from dead
 changed=True;rows={}
 work=dict(cand)
 while changed:
  changed=False
  ds=[extent(s) for s in dead]
  for s,why in list(work.items()):
   if s in dead:continue
   lo,hi=extent(s)
   # entry itself: the only allowed external refs are from patched bytes or dead ranges
   bad=[(t,src) for t,src in outside_refs(lo,hi,ds) if not patched(src)]
   if not bad:dead[s]=why;changed=True
   else:rows[s]=dict(why=why,blocked_by=['%08x<-%08x'%(t,x) for t,x in bad[:4]])
  if changed:
   ds=[extent(s) for s in dead]
   # callees of dead ranges
   for s in starts:
    if s in dead or s in work or not B<=s<send:continue
    srcs=R.get(s,())
    if srcs and all(any(dl<=x<dh for dl,dh in ds) for x in srcs):work[s]='only referenced from dead ranges'
 out=[]
 for s,why in sorted(dead.items()):
  lo,hi=extent(s);body=stock[lo-B:hi-B]
  # extent confidence: last non-pool instruction should be a return/branch
  conf='medium (extent from next function start)'
  out.append(dict(range='%08x..%08x'%(lo,hi),size=hi-lo,why=why,confidence=conf,still_patched_bytes=sum(1 for w in patches if lo<=w['address']<hi)))
 blocked=[dict(start='%08x'%s,**r) for s,r in sorted(rows.items()) if s not in dead]
 json.dump(dict(total=sum(r['size'] for r in out),reclaimable=out,blocked=blocked),a.out.open('w'),indent=1)
 print('candidates',len(cand),'reclaimable',len(out),'bytes',sum(r['size'] for r in out),'blocked',len(blocked))
if __name__=='__main__':main()
