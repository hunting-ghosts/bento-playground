"""Free-space map of the new stock image and new homes for every Playground cave."""
import argparse,json,struct
from pathlib import Path
B=0x08040000
GUARD=16
def runs(img,lo,hi,minlen):
 img=img+bytes(max(0,hi-B-len(img)));out=[];i=lo
 while i<hi:
  if img[i-B]==0:
   j=i
   while j<hi and img[j-B]==0:j+=1
   if j-i>=minlen:out.append((i,j))
   i=j
  else:i+=1
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 old=a.old.read_bytes();new=a.new.read_bytes();img=(a.build/'bento1.bin').read_bytes();man=json.loads((a.build/'FULL_MANIFEST.json').read_text())
 oend,nend=B+len(old),B+len(new)
 # M7 part of bank 1 ends where the trailing zero run before 080E0000 starts
 def m7end(img):
  i=0x080E0000-B-1
  while img[i]==0:i-=1
  return B+i+1
 m7o,m7n=m7end(old),m7end(new)
 free=dict(bank1=dict(start=hex(m7n),usable_from=hex((m7n+GUARD+15)&~15),end='0x80e0000'),bank2=dict(start=hex(nend),usable_from=hex((nend+GUARD+15)&~15),end='0x81e0000'))
 free['bank1']['bytes']=0x080E0000-int(free['bank1']['usable_from'],16);free['bank2']['bytes']=0x081E0000-int(free['bank2']['usable_from'],16)
 small=[(hex(x),hex(y),y-x) for x,y in runs(new,0x08100000,nend,256)]+[(hex(x),hex(y),y-x) for x,y in runs(new,B,m7n,256)]
 homes=[];need_b1=need_b2=0
 for w in man['writes']:
  lo=w['address'];hi=lo+w['size'];orig=bytes.fromhex(w['original_hex'])
  if lo<oend and any(orig):continue
  body=img[lo-B:hi-B]
  nz=len(body.rstrip(b'\0'))
  if lo<0x080E0000:
   zero_new=not any(new[lo-B:hi-B]) and lo>=int(free['bank1']['usable_from'],16)
   st='same address (zero in 1.6.8, after the new M7 end + guard)' if zero_new else 'MUST MOVE (1.6.8 native code/data now occupies %s..%s)'%(hex(max(lo,m7o)),hex(min(hi,m7n)))
   need_b1+=hi-lo
  else:
   st='MUST MOVE: 1.6.8 main image now ends %s; append must start >= %s'%(hex(nend),free['bank2']['usable_from']);need_b2+=nz
  homes.append(dict(old=(hex(lo),hex(hi)),size=hi-lo,payload=nz,status=st,reason=w['reason'][:120]))
 # payload accounting with 32-byte zero gaps squeezed out
 def payload(lo,hi):
  data=img[lo-B:min(hi,B+len(img))-B];return len(data)-sum(y-x for x,y in runs(img,lo,min(hi,B+len(img)),32))
 p1=payload(0x080cf4a0,0x080e0000);p2=payload(oend,0x081e0000)
 budget=dict(r615_payload_bank1=p1,r615_payload_bank2=p2,free_bank1=free['bank1']['bytes'],free_bank2=free['bank2']['bytes'],
  margin_bank1=free['bank1']['bytes']-p1,margin_bank2=free['bank2']['bytes']-p2,margin_total=free['bank1']['bytes']+free['bank2']['bytes']-p1-p2,
  stock_growth=dict(main=len(new)-len(old),m7=m7n-m7o,m4=(nend-oend)-(m7n-m7o)))
 json.dump(dict(stock_end=dict(old=hex(oend),new=hex(nend)),m7_end=dict(old=hex(m7o),new=hex(m7n)),free=free,native_zero_runs_not_usable=small,budget=budget,homes=homes),a.out.open('w'),indent=1)
 print(json.dumps(budget))
if __name__=='__main__':main()
