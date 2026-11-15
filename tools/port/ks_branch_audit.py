"""Audit keystone-assembled branches (read-only).

Input: JSONL of keystone calls (src, addr, bytes) logged during a real build
(see docs/port-1.6.8/README.md). For every emitted conditional branch
(B<c>, B<c>.W, CBZ/CBNZ) and every unconditional B/B.W/BL/BLX:
  - a target outside the snippet must equal an absolute address written in the
    source statement list, and
  - a target inside the snippet must be the address of one of its labels
    (label addresses computed independently: assemble the prefix before the label).
Keystone is known to mis-encode Thumb-2 conditional branches (T3) to absolute
targets (e.g. bne.w 0x08062080 at 0x08062466 -> 0x080C44EA).
"""
import json,re,sys,collections
import capstone
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
ks=Ks(KS_ARCH_ARM,KS_MODE_THUMB);cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB)
BR=re.compile(r'^(b|bl|blx|b\.w|cbz|cbnz|b(eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)(\.w|\.n)?)$')
def stmts(src):return [s.strip() for s in re.split(r'[;\n]',src) if s.strip()]
def label_heads(src):
 """mnemonic of the first statement after each label (for structural checks)"""
 out={};st=stmts(src)
 for k,x in enumerate(st):
  m=re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$',x)
  if not m:continue
  nxt=m[2] or next((y for y in st[k+1:] if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*:\s*$',y)),'')
  out[m[1]]=nxt.split()[0].split('.')[0].lower() if nxt else ''
 return out
def data_words(src,code,addr):
 """addresses of 4-byte words that hold a literal-pool constant (=0x..) or .word data"""
 import struct
 consts={int(x,16)&0xffffffff for x in re.findall(r'=\s*(0x[0-9a-fA-F]+)',src)}
 for w in re.findall(r'\.word\s+([^\n;]+)',src):consts|={int(x,0)&0xffffffff for x in re.findall(r'0x[0-9a-fA-F]+|\b\d+\b',w)}
 out=set()
 for o in range(0,len(code)-3,2):
  if (addr+o)%4==0 and struct.unpack_from('<I',code,o)[0] in consts:out|={addr+o+k for k in range(4)}
 if '.word' in src:   # tables: everything from the first .word label on is data
  m=re.search(r'\.align',src)
 return out
def audit(rec):
 src,addr,code=rec['src'],rec['addr'],bytes.fromhex(rec['bytes'])
 data=data_words(src,code,addr)
 absolute={int(x,16) for x in re.findall(r'0x[0-9a-fA-F]+',src)}
 labs=None;bad=[];n=0
 for i in cs.disasm(code,addr):
  mn=i.mnemonic
  if not BR.match(mn):continue
  if i.address in data or i.address+i.size-1 in data:continue
  m=re.search(r'#(0x[0-9a-f]+)$',i.op_str)
  if not m:continue
  t=int(m[1],16);n+=1;cond=mn not in('b','bl','blx','b.w')
  if addr<=t<addr+len(code):
   if labs is None:labs=label_heads(src);insn={x.address:x.mnemonic.split('.')[0] for x in cs.disasm(code,addr)}
   at=insn.get(t)
   if at is None:bad.append(('%08x %s %s'%(i.address,mn,i.op_str),'in-snippet target is not an instruction boundary'))
   elif labs and at not in labs.values():bad.append(('%08x %s %s'%(i.address,mn,i.op_str),'target instruction %s does not start any label'%at,labs))
   elif not labs:bad.append(('%08x %s %s'%(i.address,mn,i.op_str),'in-snippet target but source has no label'))
  elif t not in absolute and (t|1) not in absolute:
   bad.append(('%08x %s %s'%(i.address,mn,i.op_str),'target not named in source','conditional' if cond else 'unconditional'))
 return n,bad
if __name__=='__main__':
 recs=[json.loads(l) for l in open(sys.argv[1])]
 seen=set();tot=0;bads=[];kinds=collections.Counter()
 for r in recs:
  k=(r['src'],r['addr'])
  if k in seen:continue
  seen.add(k);n,b=audit(r);tot+=n
  for x in b:bads.append((r['src'][:160],hex(r['addr']),x))
 print('%d unique snippets, %d branches checked, %d problems'%(len(seen),tot,len(bads)))
 for b in bads[:40]:print(b)
 raise SystemExit(1 if bads else 0)
