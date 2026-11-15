"""UI/action id map between two versions from native menu tables (read-only).

Menu entries are 20 bytes: id (0x1000..0x10FF), label pointer (string), 0, 0,
enabled (0/1). Every such entry in both images is collected; ids are mapped
by label where the label maps to exactly one id in each version.
"""
import argparse,json,struct,collections
B=0x08040000
def label(img,v):
 x=v-B
 if not 0<=x<len(img):return None
 e=img.find(b'\0',x,x+40);t=img[x:e]
 return t.decode('latin1') if e>x and all(32<=c<127 for c in t) else None
def entries(img):
 out=collections.defaultdict(set)
 for x in range(0,len(img)-20,4):
  i,l,z1,z2,en=struct.unpack_from('<5I',img,x)
  if 0x1000<=i<0x1100 and z1==0 and z2==0 and en in(0,1):
   t=label(img,l)
   if t:out[t].add(i)
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',required=True);p.add_argument('--new',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 o=entries(open(a.old,'rb').read());n=entries(open(a.new,'rb').read())
 ids={};amb=[]
 for lab,s in o.items():
  if len(s)==1 and len(n.get(lab,()))==1:
   oi,ni=next(iter(s)),next(iter(n[lab]))
   if oi in ids and ids[oi]!=ni:amb.append((hex(oi),lab))
   ids[oi]=ni
 old_ids={i for s in o.values() for i in s};new_ids={i for s in n.values() for i in s}
 res=dict(map={hex(k):hex(v) for k,v in sorted(ids.items())},labels_only_in_new=sorted(set(n)-set(o)),labels_only_in_old=sorted(set(o)-set(n)),
  unmapped_old_ids=sorted(hex(i) for i in old_ids-set(ids)),max_native_id=dict(old=hex(max(old_ids)),new=hex(max(new_ids))),conflicts=amb)
 json.dump(res,open(a.out,'w'),indent=1)
 print(len(ids),'ids mapped by label; max native id',res['max_native_id'],'; new labels',res['labels_only_in_new'][:12],'; conflicts',amb)
if __name__=='__main__':main()
