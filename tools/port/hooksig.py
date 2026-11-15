"""Hook inventory with context signatures, and a signature finder for a new stock image.

Tooling only: nothing here writes firmware.

  hooksig.py build --build BUILD_DIR --stock STOCK --out hook_sites.json [--md HOOK_SITES.md]
      Every write of the build against its stock image (FULL_MANIFEST.json):
      patched stock sites with original/replacement bytes, purpose, owning
      feature and BENTO_DISABLE group (tools/port/hook_features.json), the
      containing native function and a context signature; plus the stock-zero
      areas the build occupies. Self-test: every signature must find exactly
      its own site in the image it was made from.

  hooksig.py find --sites hook_sites.json --stock NEW_STOCK --out report.json [--md REPORT.md]
                  [--match match.json] [--overrides overrides.json]
      Locate every site in another stock image. Per site: found-unique,
      ambiguous or missing, the proposed address, how it was found (tier) and
      whether the bytes there still equal the guarded original. With --match/
      --overrides the proposals are compared with an existing mapping.

Signature = the bytes around a site with relocation fields wildcarded (BL/B.W/
BLX targets, MOVW/MOVT immediates, pointer-looking aligned words). Tiers, tried
in this order; the first tier with any candidate decides:
  exact     context + site bytes match under the mask
  context   context matches, the site bytes themselves changed
  pre/post  only the context before, or only after, the site matches
  pointer   for a patched pointer slot (vtable, table): the functions the
            neighbouring slots point to are located by their own code
            signature, then the table is found by the relocated pointer run
  skeleton  the instruction sequence around the site matches with all
            immediates ignored (struct offsets, ids and stack frames may change)
A site found by anything but `exact` needs a human look before it is trusted.
"""
import argparse,bisect,collections,hashlib,json,re,struct,sys
from pathlib import Path
BASE=0x08040000
PTR_RANGES=((0x08000000,0x08200000),(0x20000000,0x20020000),(0x24000000,0x24080000),(0x30000000,0x30048000),(0x38000000,0x38010000),(0xC0000000,0xC8000000))
def is_ptr(v):return any(lo<=v<hi for lo,hi in PTR_RANGES)
def mask_image(img):
 """0xFF where a byte must match, 0x00 where it is a relocation field.
 Same rules as fwmatch.normalise (kept separate: this one returns the mask)."""
 m=bytearray(b'\xff'*len(img));L=len(img)-(len(img)%2);hw=struct.unpack_from('<%dH'%(L//2),img)
 for i in range(len(hw)-1):
  h1,h2=hw[i],hw[i+1]
  if h1&0xF800==0xF000 and h2&0xD000 in (0xD000,0xC000,0x9000):struct.pack_into('<HH',m,2*i,0xF800,0xD000)
  elif h1&0xFBF0 in (0xF240,0xF2C0) and not h2&0x8000:struct.pack_into('<HH',m,2*i,0xFBF0,0x0F00)
 for o in range(0,len(img)-3,4):
  if is_ptr(struct.unpack_from('<I',img,o)[0]):struct.pack_into('<I',m,o,0xFF000000)
 return bytes(m)
def band(a,b):return (int.from_bytes(a,'little')&int.from_bytes(b,'little')).to_bytes(len(a),'little')
class Pattern:
 """Masked byte pattern; `at` is the offset of the site inside it."""
 def __init__(s,data,mask,at):
  s.mask=mask;s.data=band(data,mask);s.at=at;s.n=len(data);s.im=int.from_bytes(mask,'little');s.id=int.from_bytes(s.data,'little')
  # longest run of fully fixed bytes = search anchor
  best=(0,0);i=0
  while i<s.n:
   if mask[i]==0xff:
    j=i
    while j<s.n and mask[j]==0xff:j+=1
    if j-i>best[1]:best=(i,j-i)
    i=j
   else:i+=1
  s.a_off,s.a_len=best;s.anchor=s.data[s.a_off:s.a_off+s.a_len]
 def fixed(s):return sum(1 for b in s.mask if b==0xff)
 def find(s,img,limit=64,parity=None):
  """Offsets (of the site) where the pattern matches img."""
  out=[]
  if s.a_len<4:return None # too little fixed content to search
  i=img.find(s.anchor)
  while i>=0:
   st=i-s.a_off
   if st>=0 and st+s.n<=len(img) and (parity is None or (st+s.at)%2==parity):
    if int.from_bytes(img[st:st+s.n],'little')&s.im==s.id:
     out.append(st+s.at)
     if len(out)>=limit:break
   i=img.find(s.anchor,i+1)
  return out
def fn_starts(img):
 """Approximate native function starts: BL targets that begin with a prologue."""
 st=set();L=len(img)-4
 for o in range(0,L,2):
  h1,h2=struct.unpack_from('<HH',img,o)
  if h1&0xF800!=0xF000 or h2&0xD000!=0xD000:continue
  s_=(h1>>10)&1;i1=1-(((h2>>13)&1)^s_);i2=1-(((h2>>11)&1)^s_)
  t=o+4+((s_<<24)|(i1<<23)|(i2<<22)|((h1&0x3ff)<<12)|((h2&0x7ff)<<1))-((1<<25) if s_ else 0)
  if 0<=t<L:
   h=struct.unpack_from('<H',img,t)[0]
   if h&0xFF00 in (0xB500,0xB400) or h==0xE92D or h&0xFF80==0xB080:st.add(t)
 return sorted(st)
def code_tokens(img,ranges):
 """Linear sweep: (offset, token) with every immediate and branch target removed."""
 import capstone
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);cs.skipdata=True;offs=[];toks=[]
 for lo,hi in ranges:
  for a,size,mn,op in cs.disasm_lite(img[lo:hi],lo):
   if mn=='.byte':t='?'
   elif mn[0]=='b' and mn not in('bic','bics','bfc','bfi','bkpt') or mn in('cbz','cbnz'):t=mn.split('.')[0]+(' '+op.split(',')[0] if mn in('cbz','cbnz') else '')
   else:t=mn.split('.')[0]+' '+re.sub(r'#-?(0x[0-9a-f]+|\d+)','#',op)
   offs.append(a);toks.append(t)
 return offs,toks
CODE=lambda img:[(0,min(len(img),0x080cf4a0-BASE)),(0x08100000-BASE,len(img))] if len(img)>0x08100000-BASE else [(0,len(img))]
# ---------------------------------------------------------------- build
CTX_MIN,CTX_STEP,CTX_MAX,CTX_EXTRA=16,8,160,8
ONE_SIDED=(16,24,32,48,64,96,128,168)
FORBIDDEN=((0x080E0000,0x08100000),) # the second program in the image: never patched, never a candidate
def signature(img,mask,off,size):
 """Smallest context (same number of bytes each side) whose context-only
 pattern is unique in img, plus CTX_EXTRA; falls back to exact uniqueness."""
 parity=off%2;how=None
 for ctx in range(CTX_MIN,CTX_MAX+1,CTX_STEP):
  lo=max(0,off-ctx);hi=min(len(img),off+size+ctx)
  cm=bytearray(mask[lo:hi]);cm[off-lo:off-lo+size]=bytes(size)
  hits=Pattern(img[lo:hi],bytes(cm),off-lo).find(img,limit=3,parity=parity)
  if hits==[off]:how='context';break
 if not how:
  for ctx in range(CTX_MIN,CTX_MAX+1,CTX_STEP):
   lo=max(0,off-ctx);hi=min(len(img),off+size+ctx)
   hits=Pattern(img[lo:hi],mask[lo:hi],off-lo).find(img,limit=3,parity=parity)
   if hits==[off]:how='exact';break
 if not how:ctx=CTX_MAX
 ctx=min(CTX_MAX,ctx+CTX_EXTRA);lo=max(0,off-ctx);hi=min(len(img),off+size+ctx)
 # shortest one-sided context that alone identifies the site in the source image (None: never)
 def one(side):
  for n in ONE_SIDED:
   if side=='pre':
    if off-n<lo:break
    h=Pattern(img[off-n:off],mask[off-n:off],n).find(img,limit=3,parity=parity)
   else:
    if off+size+n>hi:break
    h=Pattern(img[off+size:off+size+n],mask[off+size:off+size+n],-size).find(img,limit=3,parity=parity)
   if h==[off]:return n
  return None
 return dict(pre=img[lo:off].hex(),pre_mask=mask[lo:off].hex(),post=img[off+size:hi].hex(),post_mask=mask[off+size:hi].hex(),
             site_mask=mask[off:off+size].hex(),unique_in_source=how or 'no',pre_unique_len=one('pre'),post_unique_len=one('post'))
LM_LEN,LM_STEP,LM_REACH=32,16,0x1800
def landmarks(img,mask,off,size):
 """Nearest unique 32-byte windows before and after the site's own context:
 where they land in another image tells how far the surroundings moved."""
 out={}
 for side,start,step in (('before',off-CTX_MAX-CTX_EXTRA-LM_LEN,-LM_STEP),('after',off+size+CTX_MAX+CTX_EXTRA,LM_STEP)):
  o=start-(start%4)
  while 0<=o<=len(img)-LM_LEN and abs(o-off)<=LM_REACH:
   p=Pattern(img[o:o+LM_LEN],mask[o:o+LM_LEN],0)
   if p.fixed()>=24 and p.find(img,limit=3)==[o]:out[side]=dict(rel=o-off,code=img[o:o+LM_LEN].hex(),mask=mask[o:o+LM_LEN].hex());break
   o+=step
 return out
def pointer_signature(img,mask,off,size,fstarts):
 """For a patched slot holding code pointers: the neighbouring slots' target
 functions, each with a code signature of its first bytes."""
 if off%4 or size%4:return None
 def target(o):
  if o<0 or o+4>len(img):return None
  v=struct.unpack_from('<I',img,o)[0]
  return v if v&1 and BASE<=v<BASE+len(img) else None
 if not all(target(off+k) for k in range(0,size,4)):return None
 def fsig(v):
  t=(v&~1)-BASE
  for n in (24,32,48,64,96):
   p=Pattern(img[t:t+n],mask[t:t+n],0)
   if p.find(img,limit=3,parity=t%2)==[t]:return dict(code=img[t:t+n].hex(),mask=mask[t:t+n].hex())
  return None
 slots=[]
 for k in range(-8,size//4+8):
  v=target(off+4*k)
  if v is None:
   if k<0:slots=[];continue      # a non-pointer word before the site: start over
   if k>=size//4:break           # ... after it: stop
  s=fsig(v)
  slots.append(dict(rel=4*k,old='%08x'%v,fn=s))
 inside=[s for s in slots if 0<=s['rel']<size];outside=[s for s in slots if not 0<=s['rel']<size and s['fn']]
 if not any(s['fn'] for s in slots):return None
 return dict(slots=slots,neighbours=len(outside),own=sum(1 for s in inside if s['fn']))
SK=8;SK1=14 # instructions each side (two-sided); one side alone
def skeleton_signature(offs,toks,off,size,pos1):
 i=bisect.bisect_left(offs,off)
 if i>=len(offs) or offs[i]!=off:return None
 j=bisect.bisect_left(offs,off+size)
 if j>=len(offs) or offs[j]!=off+size:return None
 pre=toks[max(0,i-SK1):i];post=toks[j:j+SK1]
 if '?' in pre[-SK:] or '?' in post[:SK] or len(pre)<SK or len(post)<SK:return None
 d=dict(pre=pre[-SK:],site=toks[i:j],post=post[:SK])
 # one side alone, only where it identifies the site in the source image
 if len(pre)==SK1 and '?' not in pre and len(pos1.get(tuple(pre),()))==1:d['pre_long']=pre
 if len(post)==SK1 and '?' not in post and len(pos1.get(tuple(post),()))==1:d['post_long']=post
 return d
def load_features(path):
 rules=json.loads(Path(path).read_text())
 return [(re.compile(r['match']),r['feature'],r.get('group'),r.get('note')) for r in rules['rules']]
def classify(reason,rules):
 for rx,f,g,n in rules:
  if rx.search(reason):return f,g,n
 return 'unclassified',None,None
def build(a):
 img=a.stock.read_bytes();man=json.loads((a.build/'FULL_MANIFEST.json').read_text());mask=mask_image(img);rules=load_features(a.features)
 assert hashlib.sha256(img).hexdigest()==man['stock_sha256'],'stock image is not the one this build was made from'
 fst=fn_starts(img);offs,toks=code_tokens(img,CODE(img));end=BASE+len(img)
 pos1=collections.defaultdict(list)
 for i in range(len(toks)-SK1):pos1[tuple(toks[i:i+SK1])].append(i)
 sites=[];areas=[]
 for w in sorted(man['writes'],key=lambda w:w['address']):
  lo=w['address'];size=w['size'];orig=bytes.fromhex(w['original_hex']);off=lo-BASE
  if lo>=end:areas.append(dict(address='%08x'%lo,size=size,kind='append',purpose=w['reason'][:160]));continue
  assert img[off:off+size]==orig,'manifest original bytes differ from stock at %08x'%lo
  if not any(orig):areas.append(dict(address='%08x'%lo,size=size,kind='stock-zero area',purpose=w['reason'][:160]));continue
  repl=bytes.fromhex(w['replacement_hex']);feature,group,note=classify(w['reason'],rules)
  k=bisect.bisect_right(fst,off)-1;fn=fst[k] if k>=0 and off-fst[k]<0x4000 else None
  kind='pointer slot' if size%4==0 and off%4==0 and all(struct.unpack_from('<I',orig,i)[0]&1 and BASE<=struct.unpack_from('<I',orig,i)[0]<end for i in range(0,size,4)) else 'code/data'
  s=dict(address='%08x'%lo,size=size,kind=kind,purpose=w['reason'],feature=feature,group=group,
         original=orig.hex(),replacement=repl.hex(),function=('%08x'%(BASE+fn) if fn is not None else None),
         signature=signature(img,mask,off,size))
  s['landmarks']=landmarks(img,mask,off,size)
  if note:s['note']=note
  if kind=='pointer slot':
   ps=pointer_signature(img,mask,off,size,fst)
   if ps:s['pointer_signature']=ps
  sk=skeleton_signature(offs,toks,off,size,pos1)
  if sk:s['skeleton']=sk
  sites.append(s)
 doc=dict(schema=1,stock_sha256=man['stock_sha256'],build_label=man.get('label'),build_sha256=man.get('sha256'),base='%08x'%BASE,sites=sites,areas=areas)
 doc['merge_candidates'],doc['drop_candidates']=candidates(sites)
 # self-test: every signature finds exactly its own site in its own image
 rep=locate(doc,img);bad=[r for r in rep if r['status']!='found-unique' or r['new']!=r['old'] or r['confidence']!='high' and not r['tier'].startswith('pointer')]
 doc['selftest']=dict(sites=len(sites),unique_exact_at_own_address=len(sites)-len(bad),not_self_locating=[dict(address=r['old'],status=r['status'],tier=r['tier']) for r in bad])
 a.out.write_text(json.dumps(doc,indent=1)+'\n')
 if a.md:a.md.write_text(sites_md(doc))
 c=collections.Counter(s['feature'] for s in sites)
 print('%d patched stock sites, %d areas; features: %s'%(len(sites),len(areas),', '.join('%s %d'%x for x in c.most_common())))
 print('self-test: %d/%d signatures find exactly their own site%s'%(len(sites)-len(bad),len(sites),'' if not bad else '; NOT self-locating: '+', '.join(r['old'] for r in bad)))
 unc=[s['address'] for s in sites if s['feature']=='unclassified']
 if unc:print('unclassified (add a rule to hook_features.json): '+', '.join(unc))
 return 0
def candidates(sites):
 """Rule-based hints only; every entry names its rule."""
 merge=[];drop=[];byfn=collections.defaultdict(list)
 for s in sites:
  if s['function'] and s['kind']!='pointer slot':byfn[s['function']].append(s)
 for fn,l in sorted(byfn.items()):
  if len(l)>1:merge.append(dict(rule='several hooks in one native function (one entry/exit adapter could serve them)',function=fn,sites=[x['address'] for x in l],features=sorted({x['feature'] for x in l})))
 srt=sorted(sites,key=lambda s:int(s['address'],16));run=[srt[0]] if srt else []
 for s in srt[1:]:
  if int(s['address'],16)-(int(run[-1]['address'],16)+run[-1]['size'])<=8 and s['kind']==run[-1]['kind']:run.append(s)
  else:
   if len(run)>1:merge.append(dict(rule='adjacent writes (gap <= 8 bytes): one guarded write',sites=[x['address'] for x in run],features=sorted({x['feature'] for x in run})))
   run=[s]
 if len(run)>1:merge.append(dict(rule='adjacent writes (gap <= 8 bytes): one guarded write',sites=[x['address'] for x in run],features=sorted({x['feature'] for x in run})))
 for s in sites:
  if s['original']==s['replacement']:drop.append(dict(rule='replacement equals the original bytes (no-op write)',site=s['address'],feature=s['feature']))
  if s.get('note'):drop.append(dict(rule=s['note'],site=s['address'],feature=s['feature']))
 return merge,drop
# ---------------------------------------------------------------- find
def pat(sig,orig,which):
 pre=bytes.fromhex(sig['pre']);pm=bytes.fromhex(sig['pre_mask']);post=bytes.fromhex(sig['post']);qm=bytes.fromhex(sig['post_mask']);sm=bytes.fromhex(sig['site_mask'])
 if which=='exact':return Pattern(pre+orig+post,pm+sm+qm,len(pre))
 if which=='context':return Pattern(pre+orig+post,pm+bytes(len(orig))+qm,len(pre))
 if which=='pre':return Pattern(pre,pm,len(pre))
 if which=='post':return Pattern(post,qm,-len(orig))
def find_pointer(s,img,cache):
 ps=s.get('pointer_signature')
 if not ps:return []
 size=s['size'];new={}
 for sl in ps['slots']:
  if not sl['fn']:continue
  key=sl['fn']['code']
  if key not in cache:
   code=bytes.fromhex(sl['fn']['code']);h=Pattern(code,bytes.fromhex(sl['fn']['mask']),0).find(img,limit=3,parity=(int(sl['old'],16)&~1)%2)
   cache[key]=h[0] if h and len(h)==1 else None
  if cache[key] is not None:new[sl['rel']]=BASE+cache[key]|1
 out=collections.Counter()
 # anchor on every located slot (neighbour or own): the aligned word with that value, at the same spacing
 for rel,v in new.items():
  w=struct.pack('<I',v);i=img.find(w)
  while i>=0:
   if i%4==0:
    base=i-rel;ok=sum(1 for r2,v2 in new.items() if 0<=base+r2<=len(img)-4 and struct.unpack_from('<I',img,base+r2)[0]==v2)
    if ok>=min(2,len(new)):out[base]=max(out[base],ok)
   i=img.find(w,i+1)
 if not out:return []
 top=max(out.values());return [o for o,n in out.items() if n==top]
def find_skeleton(s,index):
 """[(tier, [offsets])] from the instruction skeleton: both sides, then one long side."""
 sk=s.get('skeleton')
 if not sk:return []
 offs,toks,pos,pos1=index;out=[];res=[]
 for i in pos.get(tuple(sk['pre']),()):
  for skip in range(0,len(sk['site'])+4):   # the site itself may have a different instruction count
   j=i+SK+skip
   if toks[j:j+SK]==sk['post']:out.append(offs[i+SK]);break
 if out:res.append(('skeleton',out))
 if sk.get('pre_long'):
  h=[offs[i+SK1] for i in pos1.get(tuple(sk['pre_long']),()) if i+SK1<len(offs)]
  if h:res.append(('skeleton-pre',h))
 if sk.get('post_long'):
  h=[]
  for i in pos1.get(tuple(sk['post_long']),()):
   k=i-len(sk['site'])
   if k>=0:h.append(offs[k])
  if h:res.append(('skeleton-post',h))
 return res
def allowed(c):return not any(lo<=BASE+c<hi for lo,hi in FORBIDDEN)
def locate(doc,img):
 cache={};index=None;rep=[]
 for s in doc['sites']:
  orig=bytes.fromhex(s['original']);size=s['size'];old=int(s['address'],16);parity=old%2;sig=s['signature']
  r=dict(old=s['address'],size=size,feature=s['feature'],purpose=s['purpose'][:90]);found=[] # [(tier, sorted candidates)]
  def add(tier,h):
   h=sorted({c for c in (h or []) if allowed(c) and 0<=c<=len(img)-size})
   if h:found.append((tier,h))
  if s['kind']=='pointer slot':add('pointer',find_pointer(s,img,cache))
  for t in ('exact','context'):add(t,pat(sig,orig,t).find(img,limit=8,parity=parity))
  if not any(len(h)==1 for _,h in found):
   # one-sided context, longest first, never shorter than what identified the site in the source image
   pre=bytes.fromhex(sig['pre']);pm=bytes.fromhex(sig['pre_mask']);post=bytes.fromhex(sig['post']);qm=bytes.fromhex(sig['post_mask']);one={}
   for side,n0 in (('pre',sig.get('pre_unique_len')),('post',sig.get('post_unique_len'))):
    if not n0:continue
    full=len(pre) if side=='pre' else len(post)
    for n in sorted({x for x in ONE_SIDED+(full,) if n0<=x<=full},reverse=True):
     p=Pattern(pre[-n:],pm[-n:],n) if side=='pre' else Pattern(post[:n],qm[:n],-size)
     h=[c for c in (p.find(img,limit=8,parity=parity) or []) if allowed(c)]
     if h:one[side]=(n,sorted(set(h)));break
   if 'pre' in one and 'post' in one and len(one['pre'][1])==1 and len(one['post'][1])==1 and one['pre'][1]!=one['post'][1]:
    r['note']='the context before the site and the context after it are both found, %d bytes apart instead of %d: bytes were inserted or removed at the site'%(one['post'][1][0]-one['pre'][1][0]+size,size)
    add('pre|post',one['pre'][1]+one['post'][1])
   else:
    if 'pre' in one and 'post' in one and one['pre'][1]==one['post'][1]:add('pre+post',one['pre'][1])
    for side in ('pre','post'):
     if side in one:add('%s:%d'%(side,one[side][0]),one[side][1])
  if not any(len(h)==1 for _,h in found) and s['kind']!='pointer slot':add('pointer',find_pointer(s,img,cache))
  if not any(len(h)==1 for _,h in found):
   if index is None:
    offs,toks=code_tokens(img,CODE(img));pos=collections.defaultdict(list);pos1=collections.defaultdict(list)
    for i in range(len(toks)-SK):pos[tuple(toks[i:i+SK])].append(i)
    for i in range(len(toks)-SK1):pos1[tuple(toks[i:i+SK1])].append(i)
    index=(offs,toks,pos,pos1)
   for t,h in find_skeleton(s,index):add(t,h)
  # where the surroundings moved to (landmarks before/after the site)
  lm={}
  for side,l in (s.get('landmarks') or {}).items():
   h=Pattern(bytes.fromhex(l['code']),bytes.fromhex(l['mask']),0).find(img,limit=3)
   if h and len(h)==1 and allowed(h[0]):lm[side]=h[0]-l['rel']   # implied site offset
  if lm:r['landmark_sites']={k:'%08x'%(BASE+v) for k,v in lm.items()}
  implied=sorted(set(lm.values()))
  # decision: the first tier with exactly one candidate; else an ambiguous tier narrowed by another tier's set
  tier=None;cand=[]
  for t,h in found:
   if len(h)==1:tier,cand=t,h;break
  if not cand and found and 'note' not in r:
   t0,h0=found[0]
   for t,h in found[1:]:
    x=sorted(set(h0)&set(h))
    if len(x)==1:tier,cand='%s+%s'%(t0,t),x;break
  if not cand and found:
   t0,h0=found[0];x=[c for c in h0 if c in implied]
   if len(x)==1:tier,cand=t0+'+landmark',x
   else:tier,cand=found[0]
  sm_=bytes.fromhex(sig['site_mask']);same=lambda c:0<=c<=len(img)-size and band(img[c:c+size],sm_)==band(orig,sm_)
  def near(c):
   """The implied position, or the one place within 32 bytes of it that still holds the original bytes."""
   if same(c):return c
   h=[x for x in range(c-32,c+33,2) if x%2==parity and same(x)]
   return h[0] if len(h)==1 else c
  if not found and implied:
   # no signature tier matched: only the surroundings say where the site went
   x=sorted({near(c) for c in implied if 0<=c<=len(img)-size})
   tier,cand=('landmark' if len(lm)==2 else 'landmark-'+next(iter(lm))),x
   if len(x)>1:r['note']='no signature tier matched; the surroundings place the site between %08x and %08x (code or data was inserted, removed or rewritten here)'%(BASE+x[0],BASE+x[-1])
   elif not same(x[0]):
    # the neighbourhood is known, the site is not: a hint, not a proposal
    r['hint']='%08x'%(BASE+x[0]);r['note']='no signature tier matched and the original bytes are not there; the surroundings place the site near %08x'%(BASE+x[0]);tier,cand=None,[]
  elif len(cand)==1 and tier not in('exact','pointer') and not same(cand[0]) and any(c!=cand[0] for c in implied):
   # found by a weak tier, the bytes there differ, and the surroundings point elsewhere: keep every candidate
   r['note']='the bytes at the %s candidate differ from the original and the surroundings place the site at %s'%(tier,', '.join('%08x'%(BASE+c) for c in implied))
   tier,cand=tier+'|landmark',sorted(set(cand)|{near(c) for c in implied})
  r['tier']=tier;r['candidates']=['%08x'%(BASE+c) for c in cand[:8]];r['tiers_seen']={t:len(h) for t,h in found}
  if len(cand)==1:
   c=cand[0];now=img[c:c+size];r['status']='found-unique';r['new']='%08x'%(BASE+c);r['bytes_now']=now.hex()
   sm=bytes.fromhex(sig['site_mask'])
   r['guard']='same-bytes' if now==orig else ('relocated-bytes' if band(now,sm)==band(orig,sm) else 'different-bytes')
   strong=tier in('exact','pointer') or tier.startswith('pointer+') or tier.endswith('+landmark')
   r['confidence']='high' if tier=='exact' and r['guard']!='different-bytes' else ('medium' if r['guard']!='different-bytes' and (strong or tier in('context','pre+post','landmark')) else 'low')
  else:r['status']='ambiguous' if cand else 'missing';r['new']=None;r['confidence']=None
  rep.append(r)
 return rep
def reference(match,overrides):
 ref={}
 if match:
  for p in json.loads(Path(match).read_text())['patches']:
   n=p['match'].get('new');ref[int(p['address'],16)]=dict(new=int(n,16) if n else None,conf=p['match'].get('conf'),guard=p.get('guard'),source='matcher')
 if overrides:
  for k,v in json.loads(Path(overrides).read_text())['addresses'].items():
   k=int(k,16)
   if k in ref:ref[k]=dict(new=int(v,16),conf='manual',guard=None,source='override')
 return ref
def find(a):
 doc=json.loads(a.sites.read_text());img=a.stock.read_bytes();rep=locate(doc,img)
 areas=[]
 for ar in doc['areas']:
  o=int(ar['address'],16)-BASE
  if ar['kind']=='append':areas.append(dict(address=ar['address'],size=ar['size'],kind=ar['kind'],state='beyond this image' if o>=len(img) else 'OVERLAPS this image by %d bytes'%(len(img)-o)))
  else:areas.append(dict(address=ar['address'],size=ar['size'],kind=ar['kind'],state='zero' if not any(img[o:o+ar['size']]) else 'NOT zero in this image'))
 ref=reference(a.match,a.overrides) if (a.match or a.overrides) else None
 c=collections.Counter((r['status'],r['tier']) for r in rep);cmp_=collections.Counter();byconf=collections.Counter()
 if ref is not None:
  for r in rep:
   e=ref.get(int(r['old'],16));want=e and e['new']
   r['reference']=('%08x'%want if want else None);r['reference_source']=e and e['source'];r['reference_conf']=e and e['conf']
   if r['status']=='found-unique':
    r['agrees']=('agree' if want==int(r['new'],16) else ('no reference' if not want else 'DISAGREE'))
   else:r['agrees']=('both without a site' if not want else 'finder has no unique site')
   cmp_[r['agrees']]+=1;byconf[(r['confidence'] or '-',r['agrees'])]+=1
 out=dict(schema=1,sites_from=doc['stock_sha256'],stock_sha256=hashlib.sha256(img).hexdigest(),summary={'%s/%s'%k:v for k,v in sorted(c.items(),key=str)},comparison=dict(cmp_) if ref is not None else None,comparison_by_confidence={'%s: %s'%k:v for k,v in sorted(byconf.items())} if ref is not None else None,sites=rep,areas=areas)
 a.out.write_text(json.dumps(out,indent=1)+'\n')
 if a.md:a.md.write_text(find_md(out,doc))
 print('sites %d: '%len(rep)+', '.join('%s %d'%(k,v) for k,v in out['summary'].items()))
 print('guards at unique sites: '+', '.join('%s %d'%x for x in collections.Counter(r.get('guard') for r in rep if r['status']=='found-unique').most_common()))
 bad=[x for x in areas if x['state'] not in('zero','beyond this image')]
 print('areas %d: %d usable as before%s'%(len(areas),len(areas)-len(bad),'' if not bad else '; NOT usable: '+', '.join(x['address'] for x in bad)))
 if ref is not None:print('against the existing mapping: '+', '.join('%s %d'%x for x in cmp_.most_common()))
 if ref is not None:print('by confidence: '+', '.join('%s %d'%(k,v) for k,v in out['comparison_by_confidence'].items()))
 return 0
# ---------------------------------------------------------------- reports
def sites_md(doc):
 L=['# Hook inventory (generated)','','Generated by `tools/port/hooksig.py build` from build %s (%s) on stock %s. Do not edit by hand.'%(doc['build_label'],(doc['build_sha256'] or '')[:16],doc['stock_sha256'][:16]),
    'Machine-readable table with the context signatures: `hook_sites.json`, written next to the other analysis files (outside Git: it holds excerpts of stock bytes). Regenerate with `tools/port/run_analysis.sh`.','',
    '%d patched stock sites; %d areas (stock-zero caves and the appended block). Self-test: %d of %d signatures find exactly their own site.'%(len(doc['sites']),len(doc['areas']),doc['selftest']['unique_exact_at_own_address'],doc['selftest']['sites']),'']
 by=collections.defaultdict(list)
 for s in doc['sites']:by[s['feature']].append(s)
 L+=['## Sites by owning feature','','| feature | BENTO_DISABLE group | sites | bytes |','|---|---|---|---|']
 for f,l in sorted(by.items(),key=lambda x:-len(x[1])):L.append('| %s | %s | %d | %d |'%(f,l[0]['group'] or '-',len(l),sum(x['size'] for x in l)))
 L+=['','## All patched stock sites','','| address | size | kind | feature | native function | original | replacement | purpose |','|---|---|---|---|---|---|---|---|']
 for s in doc['sites']:
  L.append('| %s | %d | %s | %s | %s | `%s` | `%s` | %s |'%(s['address'],s['size'],s['kind'],s['feature'],s['function'] or '-',s['original'][:24]+('..' if len(s['original'])>24 else ''),s['replacement'][:24]+('..' if len(s['replacement'])>24 else ''),s['purpose'][:110].replace('|','/')))
 L+=['','## Areas the build occupies','','| address | size | kind | purpose |','|---|---|---|---|']
 for ar in doc['areas']:L.append('| %s | %d | %s | %s |'%(ar['address'],ar['size'],ar['kind'],ar['purpose'][:100].replace('|','/')))
 L+=['','## Merge candidates (rule-based hints, not decisions)','']
 for m in doc['merge_candidates']:L.append('- %s: %s%s [%s]'%(m['rule'],', '.join(m['sites']),' in function '+m['function'] if m.get('function') else '',', '.join(m['features'])))
 L+=['','## Drop candidates (rule-based hints, not decisions)','']
 for d in doc['drop_candidates']:L.append('- %s: %s (%s)'%(d['site'],d['rule'],d['feature']))
 if not doc['drop_candidates']:L.append('- none by the current rules')
 return '\n'.join(L)+'\n'
def find_md(out,doc):
 L=['# Signature finder report (generated)','','Sites from stock %s located in stock %s by `tools/port/hooksig.py find`. Do not edit by hand.'%(out['sites_from'][:16],out['stock_sha256'][:16]),'',
    'Summary: '+', '.join('%s %d'%(k,v) for k,v in out['summary'].items())+'.']
 if out['comparison'] is not None:L.append('Against the existing mapping: '+', '.join('%s %d'%(k,v) for k,v in out['comparison'].items())+'.')
 L+=['','A site found by a tier other than `exact`, or whose guard is not `same-bytes`, needs review before use.','','| 1.6.1 | size | status | tier | confidence | proposed | guard | existing mapping | compare | feature |','|---|---|---|---|---|---|---|---|---|---|']
 for r in out['sites']:
  L.append('| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |'%(r['old'],r['size'],r['status'],r['tier'] or '-',r.get('confidence') or '-',r['new'] or (', '.join(r['candidates'][:4]) or ('near '+r['hint'] if r.get('hint') else '-')),r.get('guard') or '-',(r.get('reference') or '-')+(' ('+r['reference_source']+', '+str(r['reference_conf'])+')' if r.get('reference_source') else ''),r.get('agrees') or '-',r['feature']))
 notes=[r for r in out['sites'] if r.get('note')]
 if notes:
  L+=['','## Notes','']
  for r in notes:L.append('- %s: %s%s'%(r['old'],r['note'],' (candidates %s)'%', '.join(r['candidates']) if r['candidates'] else ''))
 L+=['','## Areas','','| address | size | kind | state in this image |','|---|---|---|---|']
 for x in out['areas']:L.append('| %s | %d | %s | %s |'%(x['address'],x['size'],x['kind'],x['state']))
 return '\n'.join(L)+'\n'
def main():
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);sub=p.add_subparsers(dest='cmd',required=True)
 b=sub.add_parser('build');b.add_argument('--build',type=Path,required=True);b.add_argument('--stock',type=Path,required=True);b.add_argument('--out',type=Path,required=True);b.add_argument('--md',type=Path)
 b.add_argument('--features',type=Path,default=Path(__file__).resolve().parent/'hook_features.json')
 f=sub.add_parser('find');f.add_argument('--sites',type=Path,required=True);f.add_argument('--stock',type=Path,required=True);f.add_argument('--out',type=Path,required=True);f.add_argument('--md',type=Path)
 f.add_argument('--match',type=Path);f.add_argument('--overrides',type=Path)
 a=p.parse_args();sys.exit(build(a) if a.cmd=='build' else find(a))
if __name__=='__main__':main()
