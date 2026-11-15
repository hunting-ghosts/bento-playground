"""Argument registers a mapped native function reads before writing them (linear scan from entry up to
the first call/branch), old vs new image. A new register in the new image = a possible new parameter."""
import json,sys,re,capstone
from capstone.arm import *
import os
img={'161':os.environ.get('BENTO_STOCK_OLD','/home/claude/stock/bento1.bin'),'168':os.environ.get('BENTO_STOCK_NEW','/home/claude/fw168/bento1.bin')}
D={k:open(v,'rb').read() for k,v in img.items()}
cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.detail=True
ARG={ARM_REG_R0:'r0',ARM_REG_R1:'r1',ARM_REG_R2:'r2',ARM_REG_R3:'r3'}
def args(v,a,n=400):
    used=set();written=set();alias={}
    for k,i in enumerate(cs.disasm(D[v][a-0x08040000:a-0x08040000+4*n],a)):
        try:rd,wr=i.regs_access()
        except Exception:break
        for r in rd:
            if r in ARG and r not in written:used.add(ARG[r])
        if i.mnemonic in('bl','blx'):
            # a call consumes r0-r3 that are still unwritten only if passed through: stop here
            break
        if i.mnemonic.startswith('b') and i.mnemonic not in('bic','bics','bfi','bfc') :break
        if i.mnemonic in('cbz','cbnz','tbb','tbh','pop','bx'):break
        for r in wr:
            if r in ARG:written.add(r)
    return used
prof=json.load(open(sys.argv[1]))
ov={int(k,16):int(v,16) for k,v in json.load(open(os.path.dirname(os.path.abspath(__file__))+'/../../bento_mods/profiles/bento-1.6.8.overrides.json'))['addresses'].items()}
seen=set()
for k,e in sorted(prof['flash'].items()):
    o=int(k,16)&~1
    if o in seen:continue
    fw=[u for u in e.get('used_by',[]) if re.search(r'\.(c|h|cpp|s|S)(:|$)',u.split(' ')[0]) and 'comment' not in u]
    if not fw:continue
    seen.add(o)
    n=ov.get(o) or ov.get(o|1) or (int(e['new'],16) if e.get('new') else None)
    if n is None:continue
    n&=~1
    if not(0x08040000<=o<0x081b3f3c):continue
    a=args('161',o);b=args('168',n)
    if b-a:print('%08x -> %08x old %s new %s  %s'%(o,n,sorted(a),sorted(b),fw[0]))
print(len(seen),'firmware-called addresses checked')
