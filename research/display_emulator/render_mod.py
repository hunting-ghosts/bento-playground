"""Render the synth page in mod mode, optionally Analog with Filter 2 selected.
The view is built by its native
constructor; mod mode is driven through the hooked vtable entries and the
header through mod_toolbar + the native header apply (0817FAF8). Model reads,
the route store and the track tree are fixtures."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import argparse,json,struct
from pathlib import Path
import emu,render
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--analog',action='store_true');p.add_argument('--filter',type=int,choices=(1,2),default=1);a=p.parse_args()
uu=json.loads((a.build/'manifest.json').read_text())['ui_symbols']
e=emu.Emu(str(a.build/'bento1.bin'));render.boot_gfx(e);e.call(0x08180198,render.ROOT)
TRACK=0x91;V=0xc0400000;KEEP=[]
KIDS=[(0x200,6),(0x201,6),(0x202,8),(0x203,9),(0x204,9),(0x205,10),(0x206,10),(0x207,11),(0x208,11)]
routes={}
def service(address,fn):
 def cb(u,addr,size,data):
  r=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)];v=fn(r)
  u.reg_write(UC_ARM_REG_R0,(v or 0)&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 KEEP.append(cb);e.u.hook_add(UC_HOOK_CODE,cb,begin=address,end=address)
def track(r):e.w(r[1],TRACK);return 1
service(0x08133cfc,track)
service(0x08133f7c,lambda r:18 if e.r(r[1])==TRACK else dict(KIDS).get(e.r(r[1]),0))
def kids(r):
 if e.r(r[1])==TRACK and r[2]<len(KIDS):e.w(r[3],KIDS[r[2]][0]);return 1
 return 0
service(0x0813391a,kids)
def lookup(r):
 x=routes.get((e.r(r[1]),r[2]&0xffff,r[3]))
 if not x:return 0
 out=e.r(e.u.reg_read(UC_ARM_REG_SP));e.w(out,x[1]);e.w(out+4,x[0]);e.w(out+8,r[3]);return 1
service(0x08131244,lookup)
def model_event(r):
 ev=struct.unpack('<5I',e.u.mem_read(r[1],20))
 if ev[0]==0xd1:
  src=ev[3]&0xffff;key=(ev[1],ev[2]&0xffff,ev[3]>>16)
  if src:routes[key]=(src,struct.unpack('<i',struct.pack('<I',ev[4]))[0])
  else:routes.pop(key,None)
 return 0
service(0x081403ec,model_event)
service(0x08133614,lambda r:(e.w(r[3],0 if r[2]==0x131 else 500),1)[1])
service(0x0813130c,lambda r:0)
e.call(0x0815e228,V);e.w(V+0x2430,TRACK);e.w(0x30034430+0x18,V)
for off,hidden in [(0x2e90,1),(0x31f0,1),(0x3550,0),(N.SYNTH_KNOB2,0)]:e.u.mem_write(V+off+0x30,bytes([hidden]))
e.u.mem_write(V+4,struct.pack('<4i',0,0,1280,480))
e.u.mem_write(V+0x38+4,struct.pack('<4i',0,410,1280,70))
if a.analog:
 K=0x24043500;e.w(K,0x35424e4b);e.w(K+4,2);e.w(K+32,2);e.w(K+36,TRACK);e.u.mem_write(K+47,bytes([13]))
 e.call(0x0817e85e,V+0x29c0,0x0818cc40)
 e.call(0x0817e85e,V+0x2a30,0x0818cc48)
e.u.mem_write(V+N.SYNTH_TILE,bytes([4+a.filter]))
e.w(V+0x2734+(4+a.filter)*0x40,0xf2);e.w(V+0x2738+(4+a.filter)*0x40,2)
# Registry for slot keys (native descriptors).
e.call(0x081639a8,0)
for i,k in enumerate([0xce,0x33]):e.call(0x08171c1c,V+0x70+i*0x468,k,500,1)
for pane in (V+0x3550,V+N.SYNTH_KNOB2):
 e.call(e.r(e.r(pane)),pane,0x24071000)
EV=0x24070800
def event(code,a1=0,a2=0,a3=0):e.u.mem_write(EV,struct.pack('<HH4I',code,0,a1,a2,a3&0xffffffff,0));return e.call(uu['mod_view_event'],V,EV)
def tick(t):e.w(0x3001fe2c,t);e.call(uu['mod_view_tick'],V,0x24071000)
tick(1000);event(0x1057);event(0x79,0,8);event(0x79,0,3);tick(1010)
shown=V+0x70
state=None
event(0xcf,0x204+a.filter,0xce,750) # cutoff encoder: +50%
tick(1020)
assert {key[0] for key in routes}=={0x204+a.filter}
assert {value[0] for value in routes.values()}=={1,4}
# Header: synth template 10 through mod_toolbar, then the native apply.
buf=0x24070000;e.u.mem_write(buf,render.tpl(e,10))
if a.analog:
 for index,text in ((3,b'WT 1\0'),(4,b'WT 2\0')):
  e.u.mem_write(buf+N.HDR(0x74)+48*index,text+bytes(32-len(text)))
e.call(uu['mod_toolbar'],0x30024b00,buf)
render.page_reset(e);e.call(0x0817FAF8,render.ROOT,buf)
render.clear(e,0xf1);e.u.mem_write(render.CTX,struct.pack('<II',1,render.SURF))
render.paint(e,V)
for i in range(2):
 e.u.mem_write(render.CTX,struct.pack('<II',1,render.SURF));render.paint(e,V+0x70+i*0x468)
if a.analog:
 for pane in (V+0x3550,V+N.SYNTH_KNOB2):
  e.u.mem_write(render.CTX,struct.pack('<II',1,render.SURF));e.call(uu['analog_wave_paint'],pane,render.CTX)
render.paint(e,render.ROOT)
for i in range(2):
 for label in (V+0x438+i*0x468,V+0x118+i*0x468):
  # The isolated graphics fixture loads the standard native font.
  e.u.mem_write(label+0x52,b'\0')
  e.u.mem_write(render.CTX,struct.pack('<II',1,render.SURF));e.call(0x0817e780,label,render.CTX)
a.out.mkdir(parents=True,exist_ok=True);open(str(a.out/'mod_mode.raw'),'wb').write(render.ui(e).tobytes())
from PIL import Image
image=Image.frombytes('P',(1280,480),render.ui(e).tobytes());palette=[]
base=[e.r(0x30000000+4*i) for i in range(16)]
for index in range(256):
 alpha,colour=index>>4,base[index&15]
 palette.extend(((colour>>shift)&255)*alpha//15 for shift in (16,8,0))
image.putpalette(palette);image.convert('RGB').save(a.out/'mod_mode.png')
print('routes',routes)
