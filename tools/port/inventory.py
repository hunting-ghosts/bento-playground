"""Generate the 1.6.1 dependency inventory of a Playground build (read-only).

Inputs: the build directory of tools/build_g3.py (FULL_MANIFEST.json, bento1.bin,
SOURCE_INPUTS.json), stock 1.6.1, and the source tree. Output JSON:
  writes   - every write against stock, classified (hook/data patch vs cave/append)
  refs     - every native address our bytes use (calls, jumps, literal words,
             MOVW/MOVT pairs, pointer-looking data words) with the sites using it
  tokens   - every address-range hex constant in the build sources (file:line)
  offsets  - non-address immediates >= 0x80 in the sources (struct offsets,
             native ids), for evidence checks against native code
Nothing here is written by hand; rerun after any source change.
"""
import argparse,json,re,struct,collections,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fwmatch
BASE=fwmatch.BASE
def region_kind(v,stock_end):
 if 0x08000000<=v<0x08040000:return 'bootloader'
 if BASE<=v<stock_end:return 'flash'
 if 0x080E0000<=v<0x08100000:return 'disk-program'
 if stock_end<=v<0x08200000 or 0x080cf4a0<=v<0x080e0000:return 'flash-beyond'
 if 0x20000000<=v<0x20020000:return 'dtcm'
 if 0x24000000<=v<0x24080000:return 'axi-sram'
 if 0x30000000<=v<0x30048000:return 'sram123'
 if 0x38000000<=v<0x38010000:return 'sram4'
 if 0xC0000000<=v<0xC8000000:return 'sdram'
 if 0x40000000<=v<0x60000000 or 0xE0000000<=v:return 'mmio'
 if 0x60000000<=v<0x60002000:return 'fmc'
 return None
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--stock',type=Path,required=True)
 p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 stock=a.stock.read_bytes();img=(a.build/'bento1.bin').read_bytes();man=json.loads((a.build/'FULL_MANIFEST.json').read_text())
 send=BASE+len(stock)
 writes=[];ours=[]
 for w in man['writes']:
  lo=w['address'];hi=lo+w['size'];orig=bytes.fromhex(w['original_hex'])
  if lo>=send:k='append'
  elif not any(orig):k='cave'
  else:k='patch'
  writes.append(dict(address=hex(lo),end=hex(hi),size=w['size'],kind=k,original_hex=w['original_hex'] if k=='patch' else None,replacement_hex=w['replacement_hex'] if k=='patch' else None,reason=w['reason']))
  if k!='patch':ours.append((lo,hi))
  # patches that differ from stock only partly: the replaced bytes are ours
 ours.sort()
 def is_ours(v):return any(lo<=v<hi for lo,hi in ours)
 import capstone
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True;cs.detail=False
 refs=collections.defaultdict(lambda:dict(sites=collections.Counter()))
 def add(v,kind,site):
  if is_ours(v&~1) and BASE<=v<0x08200000:return
  rk=region_kind(v,send)
  if rk is None or rk=='mmio':return
  r=refs[v];r['region']=rk;r['sites'][(kind,site)]+=1
 scan=[(w['address'],w['address']+w['size'],w['kind']) for w in [dict(address=int(x['address'],16),size=x['size'],kind=x['kind']) for x in writes]]
 for lo,hi,k in scan:
  data=img[lo-BASE:hi-BASE]
  if k=='patch':
   # decode the replacement in place (trampolines, literal edits)
   pass
  movw={}
  for ins in cs.disasm(data,lo):
   mn,op=ins.mnemonic,ins.op_str
   if mn in ('bl','blx','b.w','b','cbz','cbnz') or (mn.startswith('b') and op.startswith('#0x') and len(mn)<=6):
    m=re.search(r'#(0x[0-9a-f]+)$',op)
    if m:
     t=int(m[1],16)
     if not(lo<=t<hi):add(t,'call' if mn.startswith('bl') else 'jump','%08x'%ins.address)
   elif 'pc' in op and mn.startswith(('ldr','vldr')) and '[pc' in op:
    m=re.search(r'#(-?0x[0-9a-f]+|-?\d+)\]',op);d=int(m[1],0) if m else 0
    la=((ins.address+4)&~3)+d
    if BASE<=la<BASE+len(img)-4 and mn in ('ldr','ldr.w'):add(struct.unpack_from('<I',img,la-BASE)[0],'literal','%08x'%ins.address)
   elif mn in ('movw','movt'):
    m=re.match(r'(\w+), #(0x[0-9a-f]+|\d+)',op)
    if m:
     if mn=='movw':movw[m[1]]=int(m[2],0)
     elif m[1] in movw:add((int(m[2],0)<<16)|movw.pop(m[1]),'movw/movt','%08x'%ins.address)
  for o in range(lo+((-lo)%4),hi-3,4):
   v=struct.unpack_from('<I',img,o-BASE)[0]
   if region_kind(v,send) in ('flash','axi-sram','sram123','dtcm','sram4','sdram','disk-program','bootloader') and not is_ours(v&~1):add(v,'word','%08x'%o)
 # source tokens
 src=json.loads((a.build/'SOURCE_INPUTS.json').read_text()).keys()
 extra=['tools/build_g3.py','tools/build_k16.py','tools/playground_palette.py','tools/preview_identity.py']
 # emulator harness and suites that validate_p30 runs but the build does not hash
 # (their native addresses must be matched too, or the 1.6.8 suites call 1.6.1 code)
 for pat in ('research/display_emulator/*.py','chord_work/test_*.py','eu4_work/test_*.py','eu4_work/integration/test_*.py','eu4_work/integration/kit_seq_*.py','eu4_work/drums/test_*.py','tools/test_*.py'):
  extra+=[str(f.relative_to(a.root)) for f in sorted(a.root.glob(pat)) if str(f.relative_to(a.root)) not in src]
 tokens=collections.defaultdict(list);offsets=collections.defaultdict(list)
 tok=re.compile(r'(?<![0-9A-Za-z_])0[xX]([0-9a-fA-F]{1,8})(?:[uU][lL]{0,2}|[lL]{1,2}[uU]?)?(?![0-9A-Za-z_])') # C suffixes too: 0x10238u was invisible to the offset evidence
 for rel in list(src)+extra:
  f=a.root/rel
  if f.suffix not in ('.c','.h','.cpp','.s','.S','.ld','.py','.hpp','.inc'):continue
  for n,line in enumerate(f.read_text(errors='replace').splitlines(),1):
   s=line.strip();comment=s.startswith(('#','//','/*','*','"""'))
   for m in tok.finditer(line):
    v=int(m[1],16);rk=region_kind(v,send)
    if rk and rk!='mmio' and len(m[1])>=7:tokens[v].append('%s:%d%s'%(rel,n,' (comment)' if comment else ''))
    elif not rk and 0x80<=v<0x01000000 and not comment:offsets[v].append('%s:%d'%(rel,n))
 out=dict(build=str(a.build),label=man.get('label'),sha256=man.get('sha256'),stock_sha256=man.get('stock_sha256'),stock_end=hex(send),
  writes=writes,ours=[(hex(x),hex(y)) for x,y in ours],
  refs={hex(v):dict(region=r['region'],uses=sum(r['sites'].values()),kinds=sorted({k for k,_ in r['sites']}),sites=sorted({s for _,s in r['sites']})[:40],source_tokens=tokens.get(v,tokens.get(v&~1,[]))[:20]) for v,r in sorted(refs.items())},
  tokens={hex(v):l for v,l in sorted(tokens.items())},
  offsets={hex(v):l[:12]+(['... %d more'%(len(l)-12)] if len(l)>12 else []) for v,l in sorted(offsets.items())})
 a.out.write_text(json.dumps(out,indent=1)+'\n')
 c=collections.Counter(r['region'] for r in out['refs'].values())
 print('writes',collections.Counter(w['kind'] for w in writes),'refs',len(refs),dict(c),'tokens',len(tokens),'offset-like',len(offsets))
if __name__=='__main__':main()
