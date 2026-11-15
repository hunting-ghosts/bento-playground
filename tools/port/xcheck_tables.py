"""Independent cross-check of our 1.6.1 -> 1.6.8 flash map (read-only).

Re-implements two ideas from romanjeff's bento_enhanced Ghidra tools
(tools/ghidra-1.6.1/port_anchors.py, vtable_compare.py; GPL-3.0; idea only,
no code copied) without Ghidra and without our byte-block matcher:
 1. instruction-shape fingerprints: a function's ordered mnemonic list
    (operands dropped), from its entry to its first return, >= 12
    instructions; accepted only when unique in BOTH images;
 2. pointer tables (vtables, handler tables): runs of >= 3 aligned Thumb
    pointers into the image's code; an old table corresponds to the new table
    whose slots agree with the fingerprint map at the most slot indices; each
    agreeing table then maps every slot (old target -> new target).
The result is compared with match.json (our map) for every Playground
dependency: agree / disagree / not covered by this method.
"""
import argparse,json,struct,collections,hashlib,sys
from pathlib import Path
import capstone
B=0x08040000
CODE=[(0x08040000,0x080d0000),(0x08100000,0x081c0000)]
def incode(v,end):return any(lo<=v<min(hi,end) for lo,hi in CODE)
def tables(img):
 end=B+len(img);out=[];o=0;L=len(img)
 while o<L-3:
  run=[]
  while o<L-3:
   v=struct.unpack_from('<I',img,o)[0]
   if v&1 and incode(v&~1,end):run.append(v&~1);o+=4
   else:break
  if len(run)>=3:out.append((B+o-4*len(run),run))
  o+=4 if not run else 0
  if run and len(run)<3:o+=0
 return out
def entries(img,tbls):
 """function entries: table targets and BL targets with a prologue"""
 import fwmatch
 end=B+len(img);st=set(t for _,r in tbls for t in r)
 for o in range(0,len(img)-4,2):
  r=fwmatch.bl_target(img,o)
  if r and r[0]=='bl' and incode(r[1],end):
   h=struct.unpack_from('<H',img,r[1]-B)[0]
   if h&0xFF00 in(0xB500,0xB400) or h==0xE92D:st.add(r[1])
 return st
def fingerprint(cs,img,a):
 seq=[]
 for i in cs.disasm(img[a-B:a-B+0x800],a):
  seq.append(i.mnemonic)
  if i.mnemonic in('bx',) and i.op_str=='lr' or i.mnemonic.startswith('pop') and 'pc' in i.op_str:break
  if len(seq)>400:break
 return hashlib.sha1(' '.join(seq).encode()).hexdigest() if len(seq)>=12 else None
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',required=True);p.add_argument('--new',required=True);p.add_argument('--match',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 o=open(a.old,'rb').read();n=open(a.new,'rb').read()
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB)
 to,tn=tables(o),tables(n)
 eo,en=entries(o,to),entries(n,tn)
 def fpmap(img,es):
  d=collections.defaultdict(list)
  for e in es:
   f=fingerprint(cs,img,e)
   if f:d[f].append(e)
  return d
 fo,fn=fpmap(o,eo),fpmap(n,en)
 fp={v[0]:fn[k][0] for k,v in fo.items() if len(v)==1 and len(fn.get(k,()))==1}
 # table correspondence by slot agreement
 newslots=collections.defaultdict(list)   # new target -> [(table, index)]
 for ta,run in tn:
  for i,t in enumerate(run):newslots[t].append((ta,i))
 tmap={};vt={}
 for ta,run in to:
  votes=collections.Counter()
  for i,t in enumerate(run):
   if t in fp:
    for nb,j in newslots.get(fp[t],()):
     if j==i:votes[nb]+=1
  if votes:
   (nb,c),*rest=votes.most_common()
   if c>=2 and (not rest or c>rest[0][1]):
    tmap[ta]=nb;nrun=dict(tn)[nb]
    for i,t in enumerate(run):
     if i<len(nrun):vt.setdefault(t,collections.Counter())[nrun[i]]+=1
 vtmap={k:c.most_common(1)[0][0] for k,c in vt.items() if len(c)==1}
 ours=json.loads(open(a.match).read())['flash']
 res=collections.Counter();rows=[]
 for k,e in ours.items():
  v=int(k,16)&~1;mine=int(e['new'],16)&~1 if e.get('new') else None
  ind=fp.get(v,vtmap.get(v))
  how='fingerprint' if v in fp else ('vtable slot' if v in vtmap else None)
  if ind is None:res['not covered']+=1;continue
  st='agree' if mine==ind else ('ours unresolved, cross-check has it' if mine is None else 'DISAGREE')
  res[st]+=1
  if st!='agree':rows.append(dict(old=k,ours=e.get('new'),ours_conf=e['conf'],xcheck='%08x'%ind,how=how))
 # vtable slots we patch: does the slot correspondence agree with our hook table?
 json.dump(dict(summary=res,tables=dict(old=len(to),new=len(tn),matched=len(tmap)),fingerprints=len(fp),vtable_slot_pairs=len(vtmap),
  differences=rows,table_map={'%08x'%k:'%08x'%v for k,v in tmap.items()}),open(a.out,'w'),indent=1)
 print('tables old/new/matched %d/%d/%d; unique fingerprints %d; slot pairs %d'%(len(to),len(tn),len(tmap),len(fp),len(vtmap)))
 print(dict(res));[print(' ',r) for r in rows[:30]]
if __name__=='__main__':main()
