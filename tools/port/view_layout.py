"""Layout of a constructed native view in two builds (1.6.8 port evidence).

Runs the native constructor of a view in the emulator through the fixture of a
build's workspace, lists every word of the object that points into the native
vtable/string area, and compares the two lists run by run. Children keep their
order between firmware versions, so the offset differences give the piecewise
map of the object (used for NOFF_SYNTH_* and SYNTH() in native_ids).

  python3 tools/port/view_layout.py --old BUILD_161 --new BUILD_168 --view synth

A recipe names the fixture module and how it builds the view; each build is
dumped in its own process (the fixture modules bind to one image at import).
"""
import argparse,json,os,struct,subprocess,sys
RECIPES={
 'synth':dict(module='test_mod',make='Page()',base='V',size=0x40000),
}
def dump(build,view):
 r=RECIPES[view]
 os.environ.update(BENTO_FX_CANDIDATE=build,BENTO_K16_IMAGE=build+'/baseline/bento1.bin',MOTION_CANDIDATE=build,BENTO_SYNCUSSION='1')
 sys.path[:0]=[build+'/workspace/eu4_work/integration',build+'/workspace/chord_work',build+'/workspace/eu4_work']
 m=__import__(r['module']);p=eval(r['make'],vars(m));base=eval(r['base'],dict(vars(m),p=p))
 mem=bytes(p.u.mem_read(base,r['size']));words=struct.unpack('<%dI'%(len(mem)//4),mem)
 print(json.dumps([(i*4,w) for i,w in enumerate(words) if 0x08180000<=w<0x081c0000 and w%4==0]))
def runs(x):
 out=[];i=0
 while i<len(x):
  j=i
  while j+1<len(x) and x[j+1][1]==x[i][1] and x[j+1][0]-x[j][0]==x[i+1][0]-x[i][0]:j+=1
  out.append((x[i][0],x[i][1],j-i+1,x[i+1][0]-x[i][0] if j>i else 0));i=j+1
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--old');p.add_argument('--new');p.add_argument('--view',choices=sorted(RECIPES),required=True);p.add_argument('--dump');a=p.parse_args()
 if a.dump:return dump(a.dump,a.view)
 got=[runs([tuple(e) for e in json.loads(subprocess.run([sys.executable,__file__,'--dump',b,'--view',a.view],capture_output=True,text=True,check=True).stdout.strip().split('\n')[-1])]) for b in (a.old,a.new)]
 old,new=got;i=j=0;delta=None;pieces=[]
 f=lambda t:'%6x %08x x%-3d +%-3x'%t
 while i<len(old) or j<len(new):
  A=old[i] if i<len(old) else None;B=new[j] if j<len(new) else None
  # children keep their order: same count and stride = the same child; otherwise the new image inserted one
  if A and B and A[2:]==B[2:]:
   d=B[0]-A[0]
   if d!=delta:pieces.append((A[0],d));delta=d
   print('%-30s | %-30s %+x'%(f(A),f(B),d));i+=1;j+=1
  elif B and (not A or len(new)-j>len(old)-i):print('%-30s | %-30s inserted'%('',f(B)));j+=1
  else:print('%-30s | %-30s removed'%(f(A),''));i+=1
 print('piecewise map (from old offset: delta):',', '.join('%x: %+x'%p for p in pieces))
if __name__=='__main__':main()
