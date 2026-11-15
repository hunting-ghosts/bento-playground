"""Evidence for non-address constants (struct offsets, native ids) across versions.

For each constant >= 0x80 in the firmware sources (inventory 'offsets'), find every
1.6.1 native instruction that uses it as an immediate and look at the instruction
the matcher maps it to in the new image. same = the new instruction is identical
text; changed = it maps but the immediate/instruction differs; unmapped = site in
changed code. Constants with no native use cannot be verified this way.
"""
import argparse,json,re,sys,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fwmatch,capstone
BASE=fwmatch.BASE
def fixture(t):
 f=t.split(':')[0].split('/')[-1];return f.startswith('test_') or '/tests/' in t
def index(img,ranges):
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True
 idx=collections.defaultdict(list);text={}
 for lo,hi in ranges:
  for i in cs.disasm(img[lo-BASE:min(hi,BASE+len(img))-BASE],lo):
   if i.mnemonic=='.byte':continue
   if 'pc' in i.op_str:continue
   for m in re.finditer(r'#(0x[0-9a-f]+|\d+)',i.op_str):
    v=int(m[1],0)
    if v>=0x80:idx[v].append(i.address)
   text[i.address]=i.mnemonic+' '+i.op_str
 return idx,text
def composites(img,ranges):
 """Split offsets: add.w/addw rd,rn,#A followed within 3 instructions by
 adds rd,#B or a load/store [rd,#B] -> A+B, keyed by the address of the add."""
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True
 out={}
 for lo,hi in ranges:
  ins=[i for i in cs.disasm(img[lo-BASE:min(hi,BASE+len(img))-BASE],lo)]
  for k,i in enumerate(ins):
   m=re.match(r'(r\d+|sb|sl|fp|ip), (r\d+|sb|sl|fp|ip), #(0x[0-9a-f]+|\d+)$',i.op_str)
   if i.mnemonic not in('add.w','addw','add') or not m or m[2] in('sp','pc'):continue
   A=int(m[3],0);rd=m[1]
   if A<0x100:continue
   for j in ins[k+1:k+4]:
    mm=re.match(r'%s, #(0x[0-9a-f]+|\d+)$'%rd,j.op_str) if j.mnemonic in('adds','add.w','addw') else re.search(r'\[%s, #(0x[0-9a-f]+|\d+)\]'%rd,j.op_str)
    if mm:out[i.address]=A+int(mm[1],0);break
    if re.match(rd+r'\b',j.op_str):break
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 inv=json.loads(a.inventory.read_text());old=a.old.read_bytes();new=a.new.read_bytes();m=fwmatch.Matcher(old,new)
 R=[(0x08040000,0x080cf4a0),(0x08100000,0x081b3f3c)]
 io,to=index(old,R);_,tn=index(new,[(0x08040000,0x080cfc60),(0x08100000,0x081b6e34)])
 co=composites(old,R);cn=composites(new,[(0x08040000,0x080cfc60),(0x08100000,0x081b6e34)])
 cold_by_val=collections.defaultdict(list)
 for a_,v_ in co.items():cold_by_val[v_].append(a_)
 cnew_by_addr=cn
 res={};c=collections.Counter()
 for k,sites in inv['offsets'].items():
  fw=[s for s in sites if not fixture(s)]
  if not fw:continue
  v=int(k,16);uses=io.get(v,[])
  st=collections.Counter();ex=[]
  for u in uses:
   r=m.map(u)
   if r.get('new') is None or r['conf'] in ('unmatched','ambiguous','conflict'):st['unmapped']+=1;continue
   t=tn.get(r['new'])
   if t==to[u]:st['same']+=1
   else:st['changed']+=1;ex.append('%08x %s -> %08x %s'%(u,to[u],r['new'],t))
  verdict='no-native-use' if not uses else ('stable' if st['same'] and not st['changed'] else ('changed' if st['changed'] and not st['same'] else ('mixed' if st['changed'] else 'unverified')))
  c[verdict]+=1
  # split offsets (A+B) at matched native sites
  cu=cold_by_val.get(v,[]);cst=collections.Counter();cnew=collections.Counter()
  for u in cu:
   r=m.map(u)
   if r.get('new') is None or r['conf'] in ('unmatched','ambiguous','conflict'):cst['unmapped']+=1;continue
   nv=cnew_by_addr.get(r['new'])
   if nv is None:cst['unmapped']+=1
   elif nv==v:cst['same']+=1
   else:cst['changed']+=1;cnew[nv]+=1
  if cu and verdict in('no-native-use','unverified'):
   verdict='split-stable' if cst['same'] and not cst['changed'] else ('split-changed' if cst['changed'] and not cst['same'] else ('split-mixed' if cst['changed'] else verdict))
  res[k]=dict(split_evidence=dict(cst),split_new_values={hex(x):n for x,n in cnew.items()},verdict=verdict,native_uses=len(uses),evidence=dict(st),changed_examples=ex[:4],source=fw[:4])
 json.dump(dict(summary=c,constants=res),a.out.open('w'),indent=1);print(dict(c))
if __name__=='__main__':main()
