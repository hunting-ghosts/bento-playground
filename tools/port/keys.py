"""Native parameter-key map between two versions (read-only).

The native registry is filled by calls to an 'add' function (1.6.1: 08163952,
args obj, r1 key, r2 type, r3 name). The ordered call sequences of both images
are aligned by (name, type); aligned pairs give old key -> new key.
Also tabulates immediate evidence for UI/action ids (0x1000..0x10FF).
"""
import argparse,json,re,struct,collections,difflib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fwmatch,capstone
B=fwmatch.BASE
def _str(img,v):
 o=v-B
 if not 0<=o<len(img):return None
 e=img.find(b'\0',o,o+48)
 if e<=o:return None
 t=img[o:e];return t.decode() if all(32<=c<127 for c in t) else None
def calls(img,lo,hi):
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True
 regs={};out=collections.defaultdict(list)
 for i in cs.disasm(img[lo-B:hi-B],lo):
  mn,op=i.mnemonic,i.op_str
  m=re.match(r'(r[0-3]), #(0x[0-9a-f]+|\d+)$',op)
  if mn in('movw','mov.w','movs','mov') and m:regs[m[1]]=('k',int(m[2],0));continue
  m=re.match(r'(r[0-3]), \[pc, #(0x[0-9a-f]+|\d+)\]$',op)
  if mn in('ldr','ldr.w') and m:
   la=((i.address+4)&~3)+int(m[2],0)
   if la-B+4<=len(img):
    v=struct.unpack_from('<I',img,la-B)[0];t=_str(img,v);regs[m[1]]=('s',t) if t else ('v',v)
   continue
  if mn=='bl':out[int(op[1:],16)].append((i.address,dict(regs)));regs={};continue
  if mn.startswith(('b','pop','bx')):regs={}
  else:
   m=re.match(r'(r[0-3])\b',op)
   if m and not mn.startswith(('str','cmp','tst','push','vstr')):regs.pop(m[1],None)
 return out
def seq(img,end,fn):
 out=[]
 for a,r in sorted(calls(img,0x08100000,end)[fn]):
  k,nm,ty=r.get('r1'),r.get('r3'),r.get('r2')
  out.append((a,k[1] if k and k[0]=='k' else None,nm[1] if nm and nm[0]=='s' else None,ty[1] if ty and ty[0]=='k' else None))
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--registry-add',default='08163952');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 o,n=a.old.read_bytes(),a.new.read_bytes();m=fwmatch.Matcher(o,n)
 f1=int(a.registry_add,16);r=m.map(f1);assert r['conf']=='high',r;f2=r['new']
 S1=seq(o,B+len(o),f1);S2=seq(n,B+len(n),f2)
 sm=difflib.SequenceMatcher(None,[(x[2],x[3]) for x in S1],[(x[2],x[3]) for x in S2],autojunk=False)
 km=collections.defaultdict(collections.Counter);changes=[]
 for tag,i1,i2,j1,j2 in sm.get_opcodes():
  if tag=='equal':
   for x,y in zip(S1[i1:i2],S2[j1:j2]):
    if x[1] is not None and y[1] is not None:km[x[1]][y[1]]+=1
  else:changes.append(dict(tag=tag,old=[(hex(x[1]) if x[1] is not None else None,x[2]) for x in S1[i1:i2]],new=[(hex(x[1]) if x[1] is not None else None,x[2]) for x in S2[j1:j2]]))
 keys={hex(k):hex(c.most_common(1)[0][0]) for k,c in sorted(km.items()) if len(c)==1}
 amb={hex(k):{hex(x):y for x,y in c.items()} for k,c in km.items() if len(c)>1}
 json.dump(dict(registry_add=dict(old=hex(f1),new=hex(f2)),registrations=(len(S1),len(S2)),keys=keys,ambiguous=amb,changes=changes),a.out.open('w'),indent=1)
 d=collections.Counter(int(v,16)-int(k,16) for k,v in keys.items());print(len(S1),len(S2),'registrations;',len(keys),'keys;',dict(d))
if __name__=='__main__':main()
