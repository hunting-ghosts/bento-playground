"""Function-entry similarity of every mapped code address (old vs new image): masked instruction
sequences of the next N instructions compared with difflib. Low ratio = suspicious match."""
import json,struct,sys,re,difflib,capstone
import os
img={'161':os.environ.get('BENTO_STOCK_OLD','/home/claude/stock/bento1.bin'),'168':os.environ.get('BENTO_STOCK_NEW','/home/claude/fw168/bento1.bin')}
D={k:open(v,'rb').read() for k,v in img.items()}
cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True
def seq(v,a,n=48):
    out=[]
    for i in cs.disasm(D[v][a-0x08040000:a-0x08040000+n*4],a):
        op=i.op_str
        if i.mnemonic in('bl','b','b.w','blx') or i.mnemonic.startswith('b') and op.startswith('#'):op='#T'
        op=re.sub(r'\[pc, #0x[0-9a-f]+\]|\[pc, #\d+\]','[pc]',op)
        out.append(i.mnemonic+' '+op)
        if len(out)>=n:break
    return out
prof=json.load(open(sys.argv[1]));thr=float(sys.argv[2]) if len(sys.argv)>2 else 0.75
ov=json.load(open(os.path.dirname(os.path.abspath(__file__))+'/../../bento_mods/profiles/bento-1.6.8.overrides.json'))['addresses']
ovm={int(k,16):int(v,16) for k,v in ov.items()}
seen=set();rows=[]
items=[(int(k,16),e) for k,e in prof['flash'].items()]
for o,e in sorted(items):
    o2=o&~1
    n=ovm.get(o) or ovm.get(o2) or (int(e['new'],16) if e.get('new') else None)
    if n is None or o2 in seen:continue
    seen.add(o2);n&=~1
    if not(0x08040000<=o2<0x081b3f3c) or (0x080d0000<=o2<0x08100000):continue
    a=seq('161',o2);b=seq('168',n)
    if not a or not b:continue
    r=difflib.SequenceMatcher(None,a,b,autojunk=False).ratio()
    r8=difflib.SequenceMatcher(None,a[:10],b[:10],autojunk=False).ratio()
    fw=[u for u in e.get('used_by',[]) if not ('test_' in u or 'research/' in u or 'kit_seq_input' in u)]
    rows.append((r,r8,'%08x'%o2,'%08x'%n,e['conf'],'FW' if fw else 'fixture',(fw or e.get('used_by') or [''])[0]))
for r in sorted(rows):
    if r[0]<thr or r[1]<0.6:print('%.2f %.2f'%r[:2],*r[2:])
print(len(rows),'checked')
