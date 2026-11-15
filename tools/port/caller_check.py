"""Caller check of the final 1.6.1 -> 1.6.8 flash mapping (profile + manual overrides).

  python3 tools/port/caller_check.py PROFILE.json [--all] [--strict]

For every mapped flash address the firmware sources use, independent evidence is collected from the
two stock images (read-only):
  votes    native BL/B.W sites and pointer literals inside relocation-identical blocks of the old image
           that reference the old address, and what the same site references in the new image;
  reverse  native BL/B.W sites of the new image that reference the mapped address, and what the same
           site referenced in the old image;
  block    the address itself lies in a relocation-identical block (old + delta = mapped address).
Verdicts: WEAK (only a short identical block, under 64 bytes), CONFLICT (a vote or reverse vote names another address: the kind of wrong match that
08136FB4 -> 08138548 was), OK (votes agree or the address lies in an identical block), REVIEW (no
independent evidence: a site inside changed code, decided by hand; see docs/port-1.6.8/AUDIT.md).
A vote proves which function the native callers reach. It does not prove behaviour.
--strict exits 1 on any CONFLICT. Stock paths: BENTO_STOCK_OLD / BENTO_STOCK_NEW (defaults as elsewhere).
"""
import json,os,sys,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import fwmatch
from fwmatch import BASE,bl_target
WEAK=64   # an identical block shorter than this is weak evidence on its own
def main():
 args=[a for a in sys.argv[1:] if not a.startswith('--')];flags={a for a in sys.argv[1:] if a.startswith('--')}
 old=open(os.environ.get('BENTO_STOCK_OLD','/home/claude/stock/bento1.bin'),'rb').read()
 new=open(os.environ.get('BENTO_STOCK_NEW','/home/claude/fw168/bento1.bin'),'rb').read()
 prof=json.load(open(args[0]))
 ov=json.load(open(os.path.dirname(os.path.abspath(__file__))+'/../../bento_mods/profiles/bento-1.6.8.overrides.json'))['addresses']
 ovm={int(k,16):int(v,16) for k,v in ov.items()}
 m=fwmatch.Matcher(old,new)
 rev=collections.defaultdict(collections.Counter)
 for b in m.blocks:
  if b.e-b.s<48:continue
  for o in range(b.s,b.e-2,2):
   r=bl_target(old,o)
   if r:
    q=bl_target(new,o+b.d)
    if q and q[0]==r[0]:rev[q[1]][r[1]]+=1
 rows=[];seen=set()
 for k,e in sorted(prof['flash'].items()):
  o=int(k,16);o2=o&~1
  if o2 in seen or not(0x08040000<=o2<0x081b3f3c) or 0x080cf4a0<=o2<0x08100000:continue
  n=ovm.get(o) or ovm.get(o2) or (ovm.get(o|1) and ovm[o|1]&~1) or (int(e['new'],16) if e.get('new') else None)
  src='override' if (o in ovm or o2 in ovm or (o|1) in ovm) else e.get('conf','')
  fw=[u for u in e.get('used_by',[]) if not('test_' in u or 'research/' in u or 'kit_seq_input' in u)]
  if not fw and '--all' not in flags:continue
  seen.add(o2)
  if n is None:rows.append(('UNMAPPED',o2,0,src,{},{},fw));continue
  n&=~1
  ev=collections.Counter()
  for kk in (o2,o2|1):
   for v,c in m.ptr_ev.get(kk,{}).items():ev[v&~1]+=c
  for v,c in m.bl_ev.get(o2,{}).items():ev[v&~1]+=c
  rv=collections.Counter({v&~1:c for v,c in rev.get(n,{}).items()})
  blk=[b for b in m.candidates(o2-BASE) if o2+b.d==n]
  bad=[v for v in ev if v!=n] or [v for v in rv if v!=o2]
  big=[b for b in blk if b.e-b.s>=WEAK]
  verdict='CONFLICT' if bad else 'OK' if (ev or big) else 'WEAK' if blk else 'REVIEW'
  rows.append((verdict,o2,n,src,dict(ev),dict(rv),fw or e.get('used_by',[])))
 cnt=collections.Counter(r[0] for r in rows)
 for v,o,n,src,ev,rv,fw in rows:
  if v=='OK' and '--verbose' not in flags:continue
  print('%-8s %08x -> %08x %-13s votes %s reverse %s  %s'%(v,o,n,src,{('%08x'%a):c for a,c in ev.items()} or '-',{('%08x'%a):c for a,c in rv.items()} or '-',(fw or [''])[0]))
 print(dict(cnt),len(rows),'addresses')
 if '--strict' in flags and cnt.get('CONFLICT'):sys.exit(1)
if __name__=='__main__':main()
