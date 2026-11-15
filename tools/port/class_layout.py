"""Field offsets of native classes in two stock images, read from their methods (1.6.8 port evidence).

  python3 tools/port/class_layout.py PROFILE.json [VTABLE_OLD ...] [--all]

A native widget class is known by its vtable. For a vtable of the old image (and its mapped address in
the new image) every method pair is disassembled and aligned instruction by instruction; where two
aligned instructions differ only in a memory displacement or an added constant (not sp/pc relative),
the pair old -> new is counted. A class whose methods show such pairs changed its layout (or reads an
object that did): every offset our code uses on an instance needs the same evidence
(native_ids.h NOFF_*). The 1.6.8 wave pane (081B3A18) was found this way: +134 -> +29C, +174 -> +2DC.
Without vtable arguments, every vtable address the firmware sources name is checked.
Read-only. Stock paths: BENTO_STOCK_OLD / BENTO_STOCK_NEW. Evidence of where fields are, not of behaviour.
"""
import json,os,sys,re,struct,bisect,collections,difflib,capstone
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from fwmatch import BASE,bl_target
cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True
def code_ptr(img,v):return v&1 and BASE<=v<BASE+len(img)
def slots(img,a):
 out=[]
 while a-BASE+4<=len(img):
  v=struct.unpack_from('<I',img,a-BASE)[0]
  if not code_ptr(img,v):break
  out.append(v&~1);a+=4
 return out
def starts(img):
 s=set()
 for o in range(0,len(img)-4,2):
  r=bl_target(img,o)
  if r and r[0]=='bl' and BASE<=r[1]<BASE+len(img):s.add(r[1])
 for o in range(0,len(img)-4,4):
  v=struct.unpack_from('<I',img,o)[0]
  if code_ptr(img,v):s.add(v&~1)
 return sorted(s)
DISP=re.compile(r'#(-?0x[0-9a-f]+|-?\d+)')
def body(img,st,a,limit=0x1800):
 i=bisect.bisect_right(st,a);e=min(st[i] if i<len(st) else a+limit,a+limit)
 out=[]
 for ins in cs.disasm(img[a-BASE:e-BASE],a):
  op=ins.op_str;m=ins.mnemonic
  if m.startswith('b') and op.startswith('#') or m in('bl','blx','cbz','cbnz'):key=m+' T';val=None
  elif 'pc' in op or 'sp' in op or m.startswith(('movw','movt','push','pop','it','.')):key=m+' '+DISP.sub('#',op);val=None
  else:
   d=DISP.findall(op);key=m+' '+DISP.sub('#',op);val=tuple(int(x,0) for x in d) if d and ('[' in op or m.startswith(('add','sub'))) else None
  out.append((key,val,ins.address))
 return out
def compare(old,new,so,sn,a,b):
 A=body(old,so,a);B=body(new,sn,b);pairs=collections.Counter()
 sm=difflib.SequenceMatcher(None,[x[0] for x in A],[x[0] for x in B],autojunk=False)
 same=0
 for tag,i1,i2,j1,j2 in sm.get_opcodes():
  if tag!='equal':continue
  for k in range(i2-i1):
   x,y=A[i1+k],B[j1+k];same+=1
   if x[1] and y[1] and x[1]!=y[1] and len(x[1])==len(y[1]):
    for u,v in zip(x[1],y[1]):
     if u!=v and u>=0x20:pairs[(u,v)]+=1
 return pairs,same,len(A),len(B)
def main():
 args=[a for a in sys.argv[1:] if not a.startswith('--')]
 old=open(os.environ.get('BENTO_STOCK_OLD','/home/claude/stock/bento1.bin'),'rb').read()
 new=open(os.environ.get('BENTO_STOCK_NEW','/home/claude/fw168/bento1.bin'),'rb').read()
 prof=json.load(open(args[0]))
 ov={int(k,16):int(v,16) for k,v in json.load(open(os.path.dirname(os.path.abspath(__file__))+'/../../bento_mods/profiles/bento-1.6.8.overrides.json'))['addresses'].items()}
 fm={int(k,16):e for k,e in prof['flash'].items()}
 def mapped(a):
  if a in ov:return ov[a]
  e=fm.get(a);return int(e['new'],16) if e and e.get('new') else None
 if len(args)>1:tables=[int(x,16) for x in args[1:]]
 else:
  tables=[a for a,e in sorted(fm.items()) if a%4==0 and 0x08190000<=a<0x081b3f3c and len(slots(old,a))>=2
          and any(not('test_' in u or 'research/' in u) for u in e.get('used_by',[]))]
 so,sn=starts(old),starts(new);done=set()
 for t in tables:
  # walk back to the first slot of the vtable (sources often name slot n)
  base=t
  while code_ptr(old,struct.unpack_from('<I',old,base-4-BASE)[0]):base-=4
  if base in done:continue
  done.add(base);n=mapped(t)
  if n is None:print('%08x: not mapped'%t);continue
  nb=n-(t-base);A=slots(old,base);B=slots(new,nb)
  total=collections.Counter();low=[]
  for i,(a,b) in enumerate(zip(A,B)):
   p,same,la,lb=compare(old,new,so,sn,a,b);total.update(p)
   if same<0.5*min(la,lb):low.append('[%d] %08x/%08x %d of %d/%d'%(i,a,b,same,la,lb))
  flag='CHANGED' if total else 'same'
  print('%08x -> %08x  %d/%d slots  %s  %s'%(base,nb,len(A),len(B),flag,' '.join('+%x->+%x(%d)'%(u,v,c) for (u,v),c in sorted(total.items()))[:900]))
  if low and '--all' in sys.argv:print('   weakly aligned methods:',' ; '.join(low)[:400])
if __name__=='__main__':main()
