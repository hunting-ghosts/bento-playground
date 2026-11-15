"""Generate a translated source tree for another stock version (1.6.8).

  python3 tools/port/make_tree.py --profile PROFILE.json --overrides OVERRIDES.json --out DIR [--experimental]

Copies the COMMITTED tree (git archive HEAD) to DIR and rewrites address tokens
in the build-input and test trees. The repository is never modified; the
1.6.1 build is untouched. Token classes (fail closed):
  native flash (1.6.1 image range)   -> profile 'flash' map (status auto; review
                                        only with --experimental) or overrides
  our append (081B3F3C..081E0000)    -> + append_shift (stock end -> new stock end)
  bank-1 areas 080D0000..080E0000    -> unchanged (zero in both); ratchet cave
                                        080CF4A0..080D0000 via overrides only
  RAM                                -> profile 'ram' map or overrides; M7 RAM
                                        unchanged (startup tables identical)
  fixed limits / magic tags          -> unchanged (FIXED, MAGIC)
Writes DIR/PORT_REPORT.json (every rewrite and every refusal).
"""
import argparse,json,re,subprocess,io,tarfile,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TREES=('eu4_work','tf2_work','k16_work','k16_overlay','chord_work','research/display_emulator','tools','bento_mods','motion_work')
SUFFIX=('.py','.c','.h','.cpp','.s','.S','.ld','.json')
FIXED={0x08000000,0x08040000,0x08100000,0x080E0000,0x08200000,0x081E0000,0x080FFFFF,0x081FFFFF,0x0803FFFF,0x08020000,0x081F8380,0x081DFFFF,0x080DFFFF,0x080D0000,0x080C0000,0x08180000}
TOK=re.compile(r'(?<![0-9A-Za-z_])0[xX]([0-9a-fA-F]{7,8})([uU]?)(?![0-9A-Za-z_])')
def ascii_tag(v):
 b=v.to_bytes(4,'little');return all(32<=c<127 for c in b)
def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--overrides',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--experimental',action='store_true');p.add_argument('--patch',type=Path,help='reviewed version patch applied after translation (git apply)');a=p.parse_args()
 prof=json.loads(a.profile.read_text());ov=json.loads(a.overrides.read_text())
 out=a.out.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit('Choose an empty output directory')
 out.mkdir(parents=True,exist_ok=True)
 tar=subprocess.run(['git','-C',str(ROOT),'archive','HEAD'],capture_output=True,check=True).stdout
 tarfile.open(fileobj=io.BytesIO(tar)).extractall(out,filter='data')
 accept={'auto'}|({'review'} if a.experimental else set())
 fm={int(k,16):v for k,v in prof['flash'].items()};rm={int(k,16):v for k,v in prof['ram'].items()}
 old_end=int(ov['old_stock_end'],16);new_end=int(ov['new_stock_end'],16);shift=int(ov['append_shift'],16)
 manual={int(k,16):int(v,16) for k,v in ov['addresses'].items()}
 refused=collections.defaultdict(list);rewrites=collections.Counter();changed_files=0
 def new_value(v,where):
  if v in manual:return manual[v],'override'
  if v&1 and (v&~1) in manual:return manual[v&~1]|1,'override'
  if v in FIXED:return v,None
  if 0x08000000<=v<0x08040000 or 0x080E0000<=v<0x08100000:return v,None   # bounds checks only
  if v==old_end:return new_end,'stock-end'
  if 0x08040000<=v<old_end and not (0x080CF4A0<=v<0x080E0000):
   e=fm.get(v) or fm.get(v|1) or fm.get(v&~1)
   if e and e['status'] in accept and e.get('new'):
    n=int(e['new'],16);return (n|1 if v&1 else n&~1),'flash-'+e['status']
   refused['flash'].append(where);return v,None
  if 0x080CF4A0<=v<0x080D0000:refused['ratchet-cave'].append(where);return v,None
  if 0x080D0000<=v<0x080E0000:return v,None
  if old_end<v<0x081E0000:return v+shift,'append-shift'
  if 0x20000000<=v<0x38010000 or 0xC0000000<=v<0xC8000000:
   if ascii_tag(v) or not (0x30000000<=v<0x30048000):return v,None   # only M4 SRAM moved (startup tables)
   if v&0xffff==0 or v in (0x30048000,):return v,None                # physical range bounds
   e=rm.get(v)
   if e and e['status'] in accept|{'auto'} and e.get('new'):return int(e['new'],16),'ram-'+e['status']
   if v<0x30000104:return v,None   # M4 .data 30000000..30000104: same size and load in both versions
   refused['ram'].append(where);return v,None
  return v,None
 for top in TREES:
  for f in sorted((out/top).rglob('*')) if (out/top).exists() else []:
   if not f.is_file() or f.suffix not in SUFFIX or 'port' in f.parts and f.parent.name=='port':continue
   text=f.read_text(errors='surrogateescape');orig=text
   for old,new in ov.get('strings',{}).items():text=text.replace(old,new)
   def sub(m):
    v=int(m[1],16);where='%s:%d'%(f.relative_to(out),text.count('\n',0,m.start())+1)
    n,why=new_value(v,where)
    if why:rewrites[why]+=1
    if n==v:return m[0]
    w=len(m[1]);s=('%0*x'%(w,n)) if m[1].islower() or m[1].isdigit() else ('%0*X'%(w,n))
    return m[0][:2]+s+m[2]
   text=TOK.sub(sub,text)
   if text!=orig:f.write_text(text,errors='surrogateescape');changed_files+=1
 # the translated tree becomes its own git repository so the version patch can be made and applied
 subprocess.run(['git','init','-q'],cwd=out,check=True);subprocess.run(['git','add','-A'],cwd=out,check=True)
 subprocess.run(['git','-c','user.email=port@local','-c','user.name=port','commit','-qm','translated tree'],cwd=out,check=True)
 if a.patch:subprocess.run(['git','apply','--index',str(a.patch.resolve())],cwd=out,check=True);subprocess.run(['git','-c','user.email=port@local','-c','user.name=port','commit','-qm','version patch '+a.patch.name],cwd=out,check=True)
 rep=dict(profile=str(a.profile),experimental=a.experimental,changed_files=changed_files,rewrites=dict(rewrites),refused={k:v for k,v in refused.items()})
 (out/'PORT_REPORT.json').write_text(json.dumps(rep,indent=1)+'\n')
 print(json.dumps(dict(changed_files=changed_files,rewrites=dict(rewrites),refused={k:len(v) for k,v in refused.items()})))
 fw=[x for k,v in refused.items() for x in v if not re.search(r'(^|/)test_|/tests/',x)]
 if fw and not a.experimental:raise SystemExit('refused firmware tokens: %d (see PORT_REPORT.json)'%len(fw))
if __name__=='__main__':main()
