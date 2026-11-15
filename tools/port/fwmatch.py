"""Relocation-masked matching of two Bento main images (e.g. stock 1.6.1 -> 1.6.8).

Read-only analysis; never writes firmware. Usage as a library:
  m=Matcher(old_bytes,new_bytes); m.map(addr) -> MapResult
Method (no guessing):
  1. normalise both images: BL/BLX/B.W immediates, MOVW/MOVT immediates and
     every aligned word that looks like a flash/RAM/SDRAM pointer are masked;
  2. 24-byte windows unique in both images are anchors; anchors are grown into
     maximal equal blocks (old start, old end, delta);
  3. an address maps through the block containing it; function extent is
     estimated from BL targets with a prologue, so a result says whether the
     whole containing function is identical modulo relocation;
  4. pointer words and BL targets inside matched blocks give independent
     (old value -> new value) evidence for data/RAM/function addresses.
"""
import struct,bisect,collections
BASE=0x08040000
PTR_RANGES=[(0x08000000,0x08200000),(0x20000000,0x20020000),(0x24000000,0x24080000),
            (0x30000000,0x30048000),(0x38000000,0x38010000),(0xC0000000,0xC8000000)]
def is_ptr(v):return any(lo<=v<hi for lo,hi in PTR_RANGES)
def bl_target(img,o):
 """Decode a Thumb-2 BL/BLX/B.W (T4) at offset o; return (kind,target) or None."""
 if o+4>len(img):return None
 h1,h2=struct.unpack_from('<HH',img,o)
 if h1&0xF800!=0xF000:return None
 k=h2&0xD000
 if k not in (0xD000,0xC000,0x9000):return None
 s=(h1>>10)&1;j1=(h2>>13)&1;j2=(h2>>11)&1;i1=1-(j1^s);i2=1-(j2^s)
 imm=(s<<24)|(i1<<23)|(i2<<22)|((h1&0x3FF)<<12)|((h2&0x7FF)<<1)
 if s:imm-=1<<25
 t=BASE+o+4+imm
 if k==0xC000:t&=~3
 return ({0xD000:'bl',0xC000:'blx',0x9000:'b.w'}[k],t)
def normalise(img):
 n=bytearray(img);L=len(img)-(len(img)%2)
 hw=struct.unpack_from('<%dH'%(L//2),img)
 for i in range(len(hw)-1):
  h1,h2=hw[i],hw[i+1]
  if h1&0xF800==0xF000 and h2&0xD000 in (0xD000,0xC000,0x9000):
   struct.pack_into('<HH',n,2*i,h1&0xF800,h2&0xD000)
  elif h1&0xFBF0 in (0xF240,0xF2C0) and not h2&0x8000:
   struct.pack_into('<HH',n,2*i,h1&0xFBF0,h2&0x0F00)
 for o in range(0,len(img)-3,4):
  v=struct.unpack_from('<I',img,o)[0]
  if is_ptr(v):struct.pack_into('<I',n,o,(v&0xFF000000)|0x00A5A5A5)
 return bytes(n)
class Block:
 __slots__=('s','e','d')
 def __init__(s,a,b,d):s.s,s.e,s.d=a,b,d
class Matcher:
 K=24
 def __init__(self,old,new):
  self.old,self.new=old,new
  self.no,self.nn=normalise(old),normalise(new)
  self._blocks();self._functions();self._evidence()
 def _index(self,n):
  c={};K=self.K
  for o in range(0,len(n)-K,2):
   w=n[o:o+K]
   if w.count(0)>K//2:continue   # zero/near-zero padding is not evidence
   c[w]=-1 if w in c else o
  return c
 def _blocks(self):
  io,inn=self._index(self.no),self._index(self.nn)
  anchors=sorted((o,inn[w]) for w,o in io.items() if o>=0 and inn.get(w,-1)>=0)
  blocks=[];no,nn=self.no,self.nn
  covered={}  # delta -> end of last block with that delta
  for a,b in anchors:
   d=b-a
   if covered.get(d,-1)>a:continue
   s=a
   while s>=2 and s+d>=2 and no[s-2:s]==nn[s-2+d:s+d]:s-=2
   e=a
   while e+2<=len(no) and e+d+2<=len(nn) and no[e:e+2]==nn[e+d:e+d+2]:e+=2
   blocks.append(Block(s,e,d));covered[d]=e
  blocks.sort(key=lambda x:x.s);self.blocks=blocks
  self.starts=[x.s for x in blocks];self.maxlen=max((x.e-x.s for x in blocks),default=0)
 def _functions(self):
  """Approximate function starts in the old image: BL targets with a prologue."""
  st=set()
  for img,store in ((self.old,st),):
   for o in range(0,len(img)-4,2):
    r=bl_target(img,o)
    if not r or r[0]!='bl':continue
    t=r[1]-BASE
    if 0<=t<len(img)-4:
     h=struct.unpack_from('<H',img,t)[0]
     if h&0xFF00 in (0xB500,0xB400) or h==0xE92D or h&0xFF80==0xB080:store.add(t)
  self.fstarts=sorted(st)
 def candidates(self,o):
  i=bisect.bisect_right(self.starts,o);out=[]
  j=i-1
  while j>=0 and self.starts[j]>o-self.maxlen-2:
   b=self.blocks[j]
   if b.s<=o<b.e:out.append(b)
   j-=1
  return out
 def function_of(self,o):
  i=bisect.bisect_right(self.fstarts,o)-1
  if i<0:return None
  s=self.fstarts[i];e=self.fstarts[i+1] if i+1<len(self.fstarts) else s+0x200
  return s,e
 def _evidence(self):
  """old->new pairs for pointer literals and BL targets seen inside matched blocks."""
  ptr=collections.defaultdict(collections.Counter);bl=collections.defaultdict(collections.Counter)
  lits=self.literal_slots(self.old)
  for b in self.blocks:
   if b.e-b.s<48:continue
   o=b.s+((-b.s)%4)
   while o+4<=b.e:
    v=struct.unpack_from('<I',self.old,o)[0]
    if is_ptr(v) and o in lits:ptr[v][struct.unpack_from('<I',self.new,o+b.d)[0]]+=1
    o+=4
   for o in range(b.s,b.e-2,2):
    r=bl_target(self.old,o)
    if r:
     q=bl_target(self.new,o+b.d)
     if q and q[0]==r[0]:bl[r[1]][q[1]]+=1
  self.ptr_ev,self.bl_ev=ptr,bl
 @staticmethod
 def literal_slots(img):
  """Offsets of words loaded PC-relative (LDR literal T1/T2, VLDR) anywhere in img."""
  out=set();L=len(img)-4
  for o in range(0,L,2):
   h=img[o]|img[o+1]<<8
   if h&0xF800==0x4800:out.add(((o+4)&~3)+(h&0xFF)*4)
   elif h in (0xF8DF,0xF85F):
    h2=img[o+2]|img[o+3]<<8;d=h2&0xFFF;out.add(((o+4)&~3)+(d if h==0xF8DF else -d))
   elif h&0xFF7F==0xED1F or h&0xFF7F==0xED5F:pass
  return out
 def map(self,addr):
  """Map an old flash address. Returns dict with new address, confidence and evidence."""
  o=addr-BASE;res=dict(old=addr)
  if not 0<=o<len(self.old):res.update(conf='outside-old-image');return res
  c=self.candidates(o)
  # evidence from callers/pointers (thumb bit tolerant)
  ev=collections.Counter()
  for k in (addr,addr|1):
   for v,n in self.ptr_ev.get(k,{}).items():ev[(v&~1) if k&1 else v]+=n
  for v,n in self.bl_ev.get(addr,{}).items():ev[v]+=n
  res['ref_votes']={hex(k):v for k,v in ev.most_common(3)}
  if not c:
   if len(ev)==1:
    res.update(new=next(iter(ev)),conf='low',how='only caller/pointer evidence (site not in a matched block)')
   else:res.update(conf='unmatched',how='no relocation-masked block contains the address')
   return res
  c.sort(key=lambda b:-(b.e-b.s))
  best=c[0];ctx=(o-best.s,best.e-o)
  if len(c)>1 and c[1].e-c[1].s>=0.5*(best.e-best.s) and c[1].d!=best.d:
   res.update(conf='ambiguous',how='%d blocks with different deltas'%len(c),alts=[hex(BASE+o+b.d) for b in c[:4]]);return res
  new=addr+best.d;res.update(new=new,block=(hex(BASE+best.s),hex(BASE+best.e)),ctx=ctx)
  f=self.function_of(o)
  whole=f and best.s<=f[0] and f[1]<=best.e
  raw=self.old[o:o+4]==self.new[o+best.d:o+best.d+4]
  res['raw_equal4']=raw
  if ev and new not in ev and (new|1) not in ev:res['ref_conflict']=True
  if whole:res.update(conf='high',how='containing function identical modulo relocation')
  elif min(ctx)>=64:res.update(conf='medium',how='>=64 B identical context each side; containing function differs elsewhere')
  else:res.update(conf='low',how='short identical context (%d/%d B)'%ctx)
  if res.get('ref_conflict'):res['conf']='conflict'
  return res
 def map_value(self,v):
  """Map an old pointer value (RAM/flash data) by pointer-literal evidence."""
  e=self.ptr_ev.get(v)
  if e:
   (nv,n),*rest=e.most_common()
   return dict(old=v,new=nv,votes=n,others=len(rest),conf='high' if not rest and n>=1 else 'ambiguous')
  return dict(old=v,conf='unmatched')
 def ram_segments(self):
  """Piecewise RAM relocation: sorted (old value, delta, votes) from literal pairs."""
  out=[]
  for v,c in self.ptr_ev.items():
   if v>=0x20000000 and len(c)==1:
    nv,n=next(iter(c.items()));out.append((v,nv-v,n))
  return sorted(out)

# ---- fuzzy mapping inside changed code (between two matched blocks) ----
import difflib,re
_cs=None
def _disasm(img,lo,hi):
 global _cs
 import capstone
 if _cs is None:_cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);_cs.skipdata=True
 return [(i.address,i.size,i.mnemonic,i.op_str) for i in _cs.disasm(img[lo-BASE:hi-BASE],lo)]
def _key(ins):
 _,_,mn,op=ins
 op=re.sub(r'#0x[0-9a-f]{5,}|#-?0x[0-9a-f]+(?=\]?$)|#\d+(?=\]?$)','#X',op) if mn.startswith(('b','cb','ldr','adr','add')) and 'pc' in op or mn.startswith(('b','cb')) else op
 return mn+' '+op
def fuzzy(m,addr,pad=0x40):
 """Locate addr inside a changed region by instruction alignment between the
 neighbouring matched blocks. Returns dict(new=..., conf='fuzzy-equal'|'fuzzy-changed', diff=[...])."""
 o=addr-BASE
 prev=[b for b in m.blocks if b.e<=o and b.e-b.s>=24];nxt=[b for b in m.blocks if b.s>o and b.e-b.s>=24]
 if not prev or not nxt:return dict(old=addr,conf='unmatched',how='no neighbour blocks')
 p=max(prev,key=lambda b:b.e);q=min(nxt,key=lambda b:b.s)
 olo,ohi=BASE+p.e,BASE+q.s;nlo,nhi=BASE+p.e+p.d,BASE+q.s+q.d
 if ohi-olo>0x1000 or nhi-nlo>0x1000 or nhi<nlo:return dict(old=addr,conf='unmatched',how='gap too large or inverted (%x..%x -> %x..%x)'%(olo,ohi,nlo,nhi))
 A=_disasm(m.old,olo,ohi);Bn=_disasm(m.new,nlo,nhi)
 sm=difflib.SequenceMatcher(None,[_key(x) for x in A],[_key(x) for x in Bn],autojunk=False)
 res=dict(old=addr,gap_old=(hex(olo),hex(ohi)),gap_new=(hex(nlo),hex(nhi)),delta_before=hex(p.d),delta_after=hex(q.d))
 diff=[]
 for tag,i1,i2,j1,j2 in sm.get_opcodes():
  for k in range(max(i2-i1,j2-j1)):
   a=A[i1+k] if i1+k<i2 else None;b=Bn[j1+k] if j1+k<j2 else None
   diff.append((tag,a,b))
   if a and a[0]<=addr<a[0]+a[1]:
    res['new']=b[0]+(addr-a[0]) if (b and tag=='equal') else None
    res['conf']='fuzzy-equal' if tag=='equal' else 'fuzzy-changed'
 res['diff']=diff
 if 'conf' not in res:res['conf']='unmatched'
 return res
def show_diff(r,ctx=6,addr=None):
 lines=[];d=r.get('diff',[]);addr=addr or r['old']
 idx=[i for i,(t,a,b) in enumerate(d) if a and a[0]<=addr<a[0]+a[1]]
 rng=range(len(d)) if not idx else range(max(0,idx[0]-ctx),min(len(d),idx[0]+ctx+1))
 for i in rng:
  t,a,b=d[i]
  fa='%08x %-7s %-28s'%(a[0],a[2],a[3][:28]) if a else ' '*46
  fb='%08x %-7s %s'%(b[0],b[2],b[3][:28]) if b else ''
  lines.append(('>>' if i in idx else '  ')+('=' if t=='equal' else '!')+' '+fa+' | '+fb)
 return '\n'.join(lines)
