"""Keystone branch guard (installed in every build process by tools/ks_guard/sitecustomize.py): every keystone
Thumb assembly is checked as it is emitted. Keystone mis-encodes Thumb-2
conditional branches (T3) to absolute targets. A branch whose target lies
outside the snippet must go to an address written in the source; a branch
inside the snippet must land on an instruction boundary that starts a label.
Words holding the snippet's own literal constants (=0x.., .word) are data.
Set KS_AUDIT_LOG to also log every call. Raises KsGuardError on a mismatch."""
import os,re,json,struct
BR=re.compile(r'^(b|bl|blx|b\.w|cbz|cbnz|b(eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)(\.w|\.n)?)$')
class KsGuardError(Exception):pass
def _stmts(src):return [s.strip() for s in re.split(r'[;\n]',src) if s.strip()]
def _heads(src):
 out={};st=_stmts(src)
 for k,x in enumerate(st):
  m=re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$',x)
  if not m:continue
  nxt=m[2] or next((y for y in st[k+1:] if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*:\s*$',y)),'')
  out[m[1]]=nxt.split()[0].split('.')[0].lower() if nxt else ''
 return out
def _data(src,code,addr):
 consts={int(x,16)&0xffffffff for x in re.findall(r'=\s*(0x[0-9a-fA-F]+)',src)}
 for w in re.findall(r'\.word\s+([^\n;]+)',src):consts|={int(x,0)&0xffffffff for x in re.findall(r'0x[0-9a-fA-F]+|\b\d+\b',w)}
 out=set()
 for o in range(0,len(code)-3,2):
  if (addr+o)%4==0 and struct.unpack_from('<I',code,o)[0] in consts:out|={addr+o+k for k in range(4)}
 return out
def problems(src,addr,code):
 import capstone
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True
 absolute={int(x,16) for x in re.findall(r'0x[0-9a-fA-F]+',src)};data=_data(src,code,addr)
 insn=None;heads=None;bad=[]
 for i in cs.disasm(code,addr):
  if not BR.match(i.mnemonic) or i.address in data or i.address+i.size-1 in data:continue
  m=re.search(r'#(0x[0-9a-f]+)$',i.op_str)
  if not m:continue
  t=int(m[1],16)
  if addr<=t<addr+len(code):
   if insn is None:insn={x.address:x.mnemonic.split('.')[0] for x in cs.disasm(code,addr)};heads=_heads(src)
   if insn.get(t) is None or not heads or insn[t] not in heads.values():bad.append('%08x %s %s (in-snippet target is not a label)'%(i.address,i.mnemonic,i.op_str))
  elif t not in absolute and (t|1) not in absolute:bad.append('%08x %s %s (target not named in the source)'%(i.address,i.mnemonic,i.op_str))
 return bad
def install():
 import keystone
 if getattr(keystone.Ks.asm,'_ks_guard',False):return
 _orig=keystone.Ks.asm
 def _asm(self,src,addr=0,*a,**k):
  r=_orig(self,src,addr,*a,**k)
  if self._arch==keystone.KS_ARCH_ARM and r and r[0]:
   text=src if isinstance(src,str) else src.decode();code=bytes(r[0])
   if os.environ.get('KS_AUDIT_LOG'):
    with open(os.environ['KS_AUDIT_LOG'],'a') as f:f.write(json.dumps(dict(src=text,addr=addr,bytes=code.hex()))+'\n')
   if self._mode&keystone.KS_MODE_THUMB:
    bad=problems(text,addr,code)
    if bad:raise KsGuardError('keystone branch mis-encoding at %#x: %s; source: %s'%(addr,'; '.join(bad),text[:300]))
  return r
 _asm._ks_guard=True;_asm._orig=_orig
 keystone.Ks.asm=_asm
