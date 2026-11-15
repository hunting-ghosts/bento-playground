"""Build-time address translation of a workspace copy (design prototype).

--dry-run only reports what would happen; nothing in the repo is ever rewritten.
Token classes (fail closed: anything unclassified stops a real translation):
  native flash/RAM  -> profile map (auto | review | unresolved)
  our regions       -> region rules of the profile (identity / shift / unresolved)
  fixed limits      -> identity (bootloader, disk program, sector and bank bounds)
"""
import argparse,json,re,collections
from pathlib import Path
FIXED={0x08000000,0x08040000,0x08100000,0x080E0000,0x08200000,0x081E0000,0x080FFFFF,0x081FFFFF,0x080D0000,0x080C0000,0x0803FFFF,0x08020000,0x081C0000,0x08180000,0x081F8380,0x081E0000-1}
def fixture(rel):
 f=rel.split('/')[-1];return f.startswith('test_') or '/tests/' in rel or 'display_emulator' in rel
def region_rule(v,old_end):
 if 0x080CF4A0<=v<0x080D0000:return 'unresolved','ratchet M7 cave: 1.6.8 native code now ends 080CFC59'
 if 0x080D0000<=v<0x080E0000:return 'identity','bank-1 cave area: zero in 1.6.8 as in 1.6.1'
 if old_end<=v<0x081E0000:return 'shift-blocked','K16 append/UI: must start >=081B6E40 in 1.6.8; does not fit below 081E0000 (space)'
 return None,None
def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
 p.add_argument('--dry-run',action='store_true',required=True);p.add_argument('--out',type=Path);a=p.parse_args()
 prof=json.loads(a.profile.read_text());old_end=0x081B3F3C
 fm={int(k,16):v for k,v in prof['flash'].items()};rm={int(k,16):v for k,v in prof['ram'].items()}
 src=list(json.loads((a.build/'SOURCE_INPUTS.json').read_text()))+['tools/build_g3.py','tools/build_k16.py','tools/playground_palette.py','tools/preview_identity.py']
 tok=re.compile(r'(?<![0-9A-Za-z_])0[xX]([0-9a-fA-F]{7,8})(?![0-9A-Za-z_])')
 stats={'firmware':collections.Counter(),'fixture':collections.Counter()};unres=collections.defaultdict(list)
 for rel in src:
  f=a.root/rel
  if f.suffix not in ('.c','.h','.cpp','.s','.S','.ld','.py'):continue
  kind='fixture' if fixture(rel) else 'firmware'
  for n,line in enumerate(f.read_text(errors='replace').splitlines(),1):
   if line.strip().startswith(('#','//','*','/*')):continue
   for m in tok.finditer(line):
    v=int(m[1],16)
    if v in FIXED:stats[kind]['fixed-identity']+=1;continue
    if 0x08040000<=v<old_end:
     e=fm.get(v) or fm.get(v|1) or fm.get(v&~1)
     st=e['status'] if e else 'not-in-profile'
    elif 0x080CF4A0<=v<0x081E0000:
     st,_=region_rule(v,old_end)
    elif 0x08000000<=v<0x08040000 or 0x080E0000<=v<0x08100000:st='forbidden-area-token'
    elif 0x20000000<=v<0x38010000 or 0xC0000000<=v<0xC8000000:
     e=rm.get(v);st=('ram-'+e['status']) if e else ('ram-unlisted-fixture' if kind=='fixture' else 'ram-unlisted')
    else:continue
    stats[kind][st]+=1
    if st not in ('auto','identity','fixed-identity','ram-auto','review','ram-review'):unres[(kind,st)].append('%s:%d %s'%(rel,n,m[0]))
 rep=dict(stats={k:dict(v) for k,v in stats.items()},unresolved={'%s/%s'%k:v[:60]+(['... %d more'%(len(v)-60)] if len(v)>60 else []) for k,v in unres.items()})
 if a.out:a.out.write_text(json.dumps(rep,indent=1)+'\n')
 print(json.dumps(rep['stats'],indent=1));print({k:len(v) for k,v in unres.items()})
if __name__=='__main__':main()
