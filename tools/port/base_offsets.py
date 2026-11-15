"""Struct-offset evidence for objects at a fixed RAM address (1.6.8 port).

A register that was loaded with a known object address (literal pool word or
MOVW/MOVT pair) is followed through the next instructions; every load/store/
address computation base+offset is recorded (also through add/addw/adds of a
constant and register copies). Each 1.6.1 site is mapped to 1.6.8 with the
block matcher and the offset used there is read the same way. The result is
old offset -> new offset(s) with site counts: evidence for layout changes of
MODEL (30024B00), the root header and other fixed objects.

usage: base_offsets.py --old STOCK_161 --new STOCK_168 --base 0x30024b00[:0xNEWBASE] [--json OUT] [--all]
"""
import argparse,collections,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fwmatch,capstone
BASE=fwmatch.BASE
REG=r'(r\d+|sb|sl|fp|ip|lr)'
def uses(img,ranges,obj,span=0x40000):
 """address -> offset for every instruction that addresses obj+offset."""
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True;out={}
 for lo,hi in ranges:
  reg={} # register -> offset from obj
  for i in cs.disasm(img[lo-BASE:hi-BASE],lo):
   mn,op=i.mnemonic,i.op_str
   if mn=='.byte':reg={};continue
   base=mn.split('.')[0]
   if base in('push','bx','pop','b','bl','blx','cbz','cbnz','tbb','tbh') or (base.startswith('b') and base[1:] in('eq','ne','lo','hs','hi','ls','lt','ge','gt','le','mi','pl','cc','cs','vs','vc')):
    # calls keep callee-saved registers; anything else ends the straight-line window
    if base in('bl','blx'):reg={r:o for r,o in reg.items() if r in('r4','r5','r6','r7','r8','sb','sl','fp')}
    elif base in('push',):pass
    elif base in('cbz','cbnz') or len(base)==3:pass # conditional: fall-through keeps the state
    else:reg={}
    continue
   m=re.match(REG+r', \[pc, #(0x[0-9a-f]+|\d+)\]$',op)
   if base=='ldr' and m:
    a=((i.address+4)&~3)+int(m[2],0);v=int.from_bytes(img[a-BASE:a-BASE+4],'little') if 0<=a-BASE<len(img)-3 else None
    if v is not None and obj<=v<obj+span:reg[m[1]]=v-obj
    else:reg.pop(m[1],None)
    continue
   m=re.match(REG+r', '+REG+r', #(0x[0-9a-f]+|\d+)$',op)
   if base in('add','addw','adds') and m and m[2] in reg:
    reg[m[1]]=reg[m[2]]+int(m[3],0);out[i.address]=reg[m[1]];continue
   if base in('sub','subw','subs') and m and m[2] in reg:
    reg[m[1]]=reg[m[2]]-int(m[3],0);out[i.address]=reg[m[1]];continue
   m=re.match(REG+r', #(0x[0-9a-f]+|\d+)$',op)
   if base in('add','adds','addw') and m and m[1] in reg:
    reg[m[1]]+=int(m[2],0);out[i.address]=reg[m[1]];continue
   m=re.match(REG+r', '+REG+r'$',op)
   if base in('mov','movs') and m and m[2] in reg:reg[m[1]]=reg[m[2]];continue
   mem=re.search(r'\['+REG+r'(?:, #(0x[0-9a-f]+|\d+))?\]',op)
   if mem and mem[1] in reg and not op.rstrip().endswith('!') and '], #' not in op:
    out[i.address]=reg[mem[1]]+(int(mem[2],0) if mem[2] else 0)
   # destination registers lose their tracking
   if base in('ldr','ldrb','ldrh','ldrsb','ldrsh','mov','movs','movw','movt','add','adds','addw','sub','subs','subw','and','ands','orr','orrs','eor','eors','lsl','lsls','lsr','lsrs','asr','asrs','mul','muls','mvn','mvns','rsb','rsbs','bic','bics','adc','adcs','sbc','sbcs','uxtb','uxth','sxtb','sxth','mla','mls','udiv','sdiv','ubfx','sbfx','clz','rev','neg','negs','orn','ldrd','umull','smull','adr'):
    d=re.match(REG,op)
    if d:reg.pop(d[1],None)
    if base in('ldrd','umull','smull'):
     d2=re.match(REG+', '+REG,op)
     if d2:reg.pop(d2[2],None)
 return out
def evidence(old,new,obj_old,obj_new,ro,rn):
 m=fwmatch.Matcher(old,new);uo=uses(old,ro,obj_old);un=uses(new,rn,obj_new)
 table=collections.defaultdict(collections.Counter);sites=collections.defaultdict(list);unmapped=collections.Counter()
 for a,off in uo.items():
  r=m.map(a)
  if r.get('new') is None or r['conf'] in('unmatched','ambiguous','conflict') or r['new'] not in un:unmapped[off]+=1;continue
  table[off][un[r['new']]]+=1
  if len(sites[off])<3:sites[off].append('%08x->%08x'%(a,r['new']))
 return table,sites,unmapped
RO=[(0x08040000,0x080cf4a0),(0x08100000,0x081b3f3c)];RN=[(0x08040000,0x080cfc60),(0x08100000,0x081b6e34)]
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True)
 p.add_argument('--base',required=True);p.add_argument('--json',type=Path);p.add_argument('--all',action='store_true');a=p.parse_args()
 b=a.base.split(':');bo=int(b[0],16);bn=int(b[-1],16)
 table,sites,unmapped=evidence(a.old.read_bytes(),a.new.read_bytes(),bo,bn,RO,RN)
 rows=[]
 for off in sorted(set(table)|set(unmapped)):
  c=table.get(off,{});best=max(c,key=c.get) if c else None
  rows.append(dict(old=off,new=best,delta=None if best is None else best-off,votes=dict((hex(k),v) for k,v in c.items()),unmapped=unmapped.get(off,0),sites=sites.get(off,[])))
 if a.json:a.json.write_text(json.dumps(dict(base_old=hex(bo),base_new=hex(bn),offsets=rows),indent=1)+'\n')
 last=None
 for r in rows:
  if r['new'] is None:
   if a.all:print('+%05x  no mapped site (%d unmapped)'%(r['old'],r['unmapped']))
   continue
  conflict=len(r['votes'])>1
  if a.all or r['delta']!=last or conflict:
   print('+%05x -> +%05x  delta %+#x  votes %s%s  %s'%(r['old'],r['new'],r['delta'],r['votes'],'  CONFLICT' if conflict else '',' '.join(r['sites'][:2])))
  last=r['delta']
 print('%d offsets with mapped evidence, %d without'%(sum(1 for r in rows if r['new'] is not None),sum(1 for r in rows if r['new'] is None)))
if __name__=='__main__':main()
