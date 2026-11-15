"""P168 run 19: page sweep of a 1.6.8 image on the whole emulated M4 UI (eu4_work/integration/port/device168.py).

From a loaded project (8 tracks, one of every type that loads without sample files): every hardware button, pressed
up to four times (the cycling buttons); in every state reached every visible footer button, the four arrows and the
burger menu (opened, then tapped again). Every step replays its path from the same booted snapshot, so a fault is
recorded and the sweep goes on. Emulator evidence only: the M7 is not emulated (see device168.py).

  python3 tools/port/sweep168.py --image BUILD/bento1.bin [--out report.txt] [--stock]
`--stock`: the image is a stock image (same sweep; our footers are then absent) - the oracle for a fault that is
the harness's or the test project's, not ours.
"""
import argparse,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'eu4_work/integration/port'))
import device168 as D
TRACKS8=[('samtrack','Kit'),('wttrack','A Long Track Name 0123456789 abcdefgh'),('samtrack','Drums'),('multisamtrack','Keys'),
         ('wttrack','Wave'),('grtrack','Grain'),('slicertrack','Slice'),('looptrack','Loop')]
p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--stock',action='store_true')
p.add_argument('--repeats',type=int,default=4);a=p.parse_args()
t=time.time();d=D.Device168(a.image.read_bytes(),{'Projects/Demo/project.xml':D.project(TRACKS8)}).boot()
lines=['image %s'%a.image,'project: %s'%', '.join(n for _,n in d.tracks())]
def log(x):
 lines.append(x);print(x,flush=True)
res=D.sweep(d,repeats=a.repeats,log=log)
faults=[(path,r) for path,r in res if r.startswith('FAULT')]
log('steps %d, faults %d, %.0f s'%(len(res),len(faults),time.time()-t))
for path,r in faults:log('FAULT after %s: %s'%(' > '.join('%s %s'%x for x in path),r))
if a.out:a.out.write_text('\n'.join(lines)+'\n')
sys.exit(1 if faults and not a.stock else 0)
