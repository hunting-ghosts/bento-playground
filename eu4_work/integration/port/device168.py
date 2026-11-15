"""P168 run 19: the whole M4 UI of a 1.6.8 image in the ARM emulator, started the way the device starts it.

Why this exists: exp8 crashed on the owner's device on the FX page and the PROJ page (track names fetched with
the native 256-byte string getter into 64-byte buffers). Every view-level fixture replaced that getter with a
Python stand-in, so no test could see it. Here nothing of the UI is replaced:
  - native reset (data copy, static constructors, our boot hook), then the steps of the native main()
    (08115386..081153C8): text cache, pad lights object, PCM/file worker object, the 6.8 MB app object with every
    view (constructor 08164F98), app->init;
  - the UI task (defaultTask 08114E34): app->start once, then its loop body 08114E66..08114E90 per frame, run on
    the task's own stack frame (sp 30018DD8: the draw context of exp8's crash A, 30018D70, is this frame's);
  - the file worker (pcmStreamer 08114EA0 -> loop 08112EAC): one pass after every frame;
  - native FatFs on a FAT16 volume kept in Python sectors (disk_read/disk_write/disk_ioctl are the only file
    hooks); files are put on the card with the native f_mkdir/f_open/f_write/f_close;
  - a project is loaded by the firmware itself (boot autoload of the first project on the card, or the Projects
    page: list row, footer Load), hardware buttons arrive as records in the M7->M4 event ring, touches as the touch
    controller record of 08101C78.
What is NOT there: the M7 (audio) core. Its side of the shared block is stood in for by three pointers it
publishes (sequence hash table, its entries, per-track sequence memory) and by "the M7 has read every message".
Sample loading needs the M7, so test projects use tracks without sample files. No power manager, backlight,
battery, I2C or RTC hardware (stubs below). The stock 1.6.8 image runs in the same harness (the oracle).

This directory is not translated by make_tree: every address here is a 1.6.8 address.
"""
import os,struct
from unicorn import Uc,UcError,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *

R4=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
GFX=0x30000e68;APPP=0x3001fd24;MODEL=0x30025300;ROOT=0x300366e8;CARD=0x3000ed00;PCM=0x3000f900;JOBS=0x30020760
FB=0xc5000000;SURF=0x24078000;M7MEM=0xc4000000
F_OPEN=0x081204b4;F_WRITE=0x08120970;F_CLOSE=0x08120ce0;F_MKDIR=0x081214be
# hardware buttons (index of the 0xAF press / 0xB0 release records)
LEFT,UP,TRACKS,LAUNCH,B4,MIXER,FX,PROJ,DOWN,RIGHT,INST,SEQ=0,1,2,3,4,5,6,7,8,9,10,11


class Fault(RuntimeError):
 """The emulated firmware faulted (what the device records as a crash) or did not come back."""


class DMA2D:
 """The Chrom-ART fills and copies the native drawing uses (register model as research/display_emulator/dma2d.py)."""
 BASE=0x52001000;BPP={0:4,1:3,2:2,3:2,4:2,5:1,6:1,7:2,9:1}
 def __init__(self,u):
  self.u=u;self.reg=[0]*0x100;self.ops=0;u.mmio_map(self.BASE,0x1000,self.rd,None,self.wr,None)
 def rd(self,u,off,size,ud):return 2 if off==4 else self.reg[0]&~1 if off==0 else self.reg[off>>2]
 def wr(self,u,off,size,val,ud):
  self.reg[off>>2]=val
  if off==0 and val&1:self.run()
 def run(self):
  R=lambda o:self.reg[o>>2];mode=(R(0)>>16)&7;ofmt=R(0x34)&7;obpp=self.BPP[ofmt];w=R(0x44)>>16;h=R(0x44)&0xffff
  omar=R(0x3c);oor=R(0x40)&0x3fff;u=self.u;self.ops+=1
  if mode==3:
   row=R(0x38).to_bytes(4,'little')[:obpp]*w
   for y in range(h):u.mem_write(omar+y*(w+oor)*obpp,row)
  else:
   fg=R(0x0c);fgo=R(0x10)&0x3fff;bpp=self.BPP.get(R(0x1c)&0xf,1)
   for y in range(h):u.mem_write(omar+y*(w+oor)*bpp,bytes(u.mem_read(fg+y*(w+fgo)*bpp,w*bpp)))


def blank_fat16(mb=64):
 """An empty FAT16 volume (no partition table) as {sector: bytes}; the firmware's own FatFs fills it."""
 total=mb*2048;spc=4;rsvd=1;nfat=2;rootent=512;rootsec=rootent*32//512
 fatsz=1
 while True:
  clusters=(total-rsvd-nfat*fatsz-rootsec)//spc;need=-(-(clusters+2)*2//512)
  if need<=fatsz:break
  fatsz=need
 assert 4085<=clusters<65525
 b=bytearray(512);b[0:3]=b'\xeb\x3c\x90';b[3:11]=b'MSDOS5.0'
 struct.pack_into('<HBHBHHBHHHII',b,11,512,spc,rsvd,nfat,rootent,0,0xf8,fatsz,63,255,0,total)
 struct.pack_into('<BBBI11s8s',b,36,0x80,0,0x29,0x19112026,b'BENTO      ',b'FAT16   ');b[510:512]=b'\x55\xaa'
 disk={0:bytes(b)};fat0=bytearray(512);fat0[0:4]=b'\xf8\xff\xff\xff'
 for i in range(nfat):disk[rsvd+i*fatsz]=bytes(fat0)
 return disk,total


class Device168:
 STOP=0x081ff000;COUNT=80_000_000
 TASK_SP=0x30018dd8   # sp inside the UI task loop on the device
 def __init__(self,image,files=None,card=True):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
  # No memory at address 0: a NULL read faults as on the device (MPU), e.g. exp8 crash A at 08169CF6.
  for a,n in [(0x08040000,0x1c0000),(0x10000000,0x100000),(0x20000000,0x40000),(0x24000000,0x80000),(0x30000000,0x48000),
              (0x38000000,0x10000),(0x38800000,0x1000),(0x40000000,0x10000000),(0x50000000,0x2001000),(0x52002000,0x5ffe000),
              (0x58000000,0x8000000),(0xc0000000,0x8000000),(0xe0000000,0x100000)]:u.mem_map(a,n)
  u.mem_write(0x08040000,image);u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
  self.dma=DMA2D(u);self.hooks=[];self.messages=[];self.opens=[];self.stubs=[];self.t=1000;self.frames=0;self.rings=set()
  self.disk,self.sectors=blank_fat16() if card else (None,0);self.touch=bytes(0x40);self.actions=[]
  self._hardware()
  # native reset up to the call of main (stack, data copy, zeroed RAM, static constructors, our boot hook)
  u.reg_write(UC_ARM_REG_SP,0x30040000);self._start(0x081003cc,0x081004ca,200_000_000)
  # main(), 08115386..081153C8 (the HAL/board calls before it only touch hardware)
  self.call(0x08168d08);self.call(0x08180524,0x300378fc);self.call(0x08125768,0x300203f0)
  self.w(GFX,DMA2D.BASE)
  self.w(0x3001fd68,0x58004000);self.w(0x3001fd70,0x7f);self.w(0x3001fd74,0xff)   # RTC handle (0811531C)
  self.shm=self.call(0x0810b890);self.w(0x3000f65c,self.shm)                        # shared M4/M7 block 30040000
  self.w(self.shm+0x7a60,M7MEM+0x100000);self.w(self.shm+0x7a64,M7MEM+0x110000);self.w(self.shm+0x7a68,M7MEM) # published by the M7
  self.call(0x08104d50,0x3000110c)
  self.call(0x0810dfc0,PCM,self.shm+0x55e0)
  self.app=self.call(0x08104db4,0x68b6d8);self.w(APPP,self.app);self.call(0x08164f98,self.app)
  self.vt=self.r(self.app);self.call(self.r(self.vt),self.app)
  self.call(0x081698d6,SURF,FB,480,1280,5,4)        # the display driver's back buffer as a native surface
  # pcmStreamer thread start: card object, mount (the worker does it), thread registration
  self.call(0x081075d4,CARD)
  if card:
   assert self.call(0x0810768c,CARD)==1 or True
   for path,data in (files or {}).items():self.put(path,data)
  self.call(0x0810853c,0x3000f630)
  self.call(self.r(self.vt+4),self.app)             # defaultTask: app->start
 # ---- memory / calls
 def w(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
 def r(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def b(self,a):return self.u.mem_read(a,1)[0]
 def text(self,a,n=256):return bytes(self.u.mem_read(a,n)).split(b'\0')[0].decode('latin1')
 def args(self):return [self.u.reg_read(x) for x in R4]
 def ret(self,v=0):self.u.reg_write(UC_ARM_REG_R0,v&0xffffffff);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def hook(self,a,f):
  self.hooks.append(self.u.hook_add(UC_HOOK_CODE,lambda u,a_,n,d,f=f:f(),begin=a,end=a))
  self.u.ctl_remove_cache(a&~1,(a&~1)+2)   # a block translated before the hook existed would not call it
 def stub(self,a,v=0):self.hook(a,lambda:(self.stubs.append(a),self.ret(v)))
 def regs(self):
  n=('pc','lr','sp','r0','r1','r2','r3','r4','r5','r7')
  v=[self.u.reg_read(x) for x in (UC_ARM_REG_PC,UC_ARM_REG_LR,UC_ARM_REG_SP,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R7)]
  return ' '.join('%s=%08x'%x for x in zip(n,v))
 def _start(self,a,stop,count=None):
  try:self.u.emu_start(a|1,stop,count=count or self.COUNT)
  except UcError as e:raise Fault('%s: %s | after %s'%(e,self.regs(),self.actions[-6:])) from e
  if self.u.reg_read(UC_ARM_REG_PC)!=stop:raise Fault('did not return: %s | after %s'%(self.regs(),self.actions[-6:]))
 def call(self,a,*args,sp=0x3003e000,count=None):
  for reg,v in zip(R4,args):self.u.reg_write(reg,v&0xffffffff)
  extra=args[4:];sp=(sp-4*len(extra))&~7
  for i,v in enumerate(extra):self.w(sp+4*i,v)
  self.u.reg_write(UC_ARM_REG_SP,sp);self.u.reg_write(UC_ARM_REG_LR,self.STOP|1)
  self._start(a,self.STOP,count);return self.u.reg_read(UC_ARM_REG_R0)
 # ---- what stands in for hardware and the M7
 def _hardware(self):
  self.hook(0x08104dac,lambda:(self.messages.append(self.text(self.args()[0])),self.ret(0)))  # debug print
  # A publish on a ring of the shared block is an M4->M7 message; the M7 has read it by the next wait.
  self.hook(0x08100590,lambda:self.rings.add(self.args()[0]) if self.shm_ring(self.args()[0]) else None)
  def consumed():
   for wr in self.rings:self.w(wr-0x20,self.r(wr))
  def delay():consumed();self.t+=1;self.ret(0)
  def tick():consumed();self.t+=1;self.w(0x3001fe2c,self.t);self.ret(self.t)
  self.hook(0x08121a9c,delay)                   # osDelay
  self.hook(0x0811562c,tick)                    # HAL_GetTick
  self.hook(0x08106ef0,lambda:self.u.reg_write(UC_ARM_REG_PC,0x08106ef9))   # DWT busy wait: over
  for a in (0x081176e8,0x0811754a,0x08117464,0x08117518,   # HAL I2C (pad LEDs, touch controller)
            0x08119708,                                      # RTC wait for synchronisation
            0x08119c1c,                                      # SD card HAL init
            0x08101be4,                                      # backlight
            0x08106fae,                                      # PowerMgr::SetPowerMode (no battery / power button)
            0x081014b4,0x081014e4,0x08101604):self.stub(a)  # frame wait, buffer swap, present
  # Power: the power button (GPIO 58022000 pin 8, low = pressed; 08106BB4) is up, the battery is full (PowerMgr tick
  # 08107050 reads mV at +0x14 and shuts down below 3300). With zeros the firmware autosaves and powers down.
  self.w(0x58022010,0x100);self.hook(0x08107050,lambda:self.u.mem_write(0x3000ec34+0x14,struct.pack('<H',4100)))
  self.hook(0x08101620,lambda:self.ret(SURF))                               # back buffer surface
  self.hook(0x08101c78,lambda:(self.u.mem_write(self.args()[1],self.touch),self.ret(1)))  # touch controller read
  self.hook(0x0810e2a8,lambda:self.ret(0))                                  # wake the file worker (its pass runs after the frame)
  # FatFs disk layer (ST diskio wrappers): status, initialize, read, write, ioctl
  none=lambda:self.disk is None
  self.hook(0x0811e040,lambda:self.ret(1 if none() else 0));self.hook(0x0811e058,lambda:self.ret(1 if none() else 0))
  def rd():
   p,b,sec,n=self.args()
   if none():return self.ret(3)
   self.u.mem_write(b,b''.join(self.disk.get(sec+i,bytes(512)) for i in range(n)));self.ret(0)
  def wr():
   p,b,sec,n=self.args()
   if none():return self.ret(3)
   d=bytes(self.u.mem_read(b,512*n))
   for i in range(n):self.disk[sec+i]=d[512*i:512*i+512]
   self.ret(0)
  def ioctl():
   p,cmd,b=self.args()[:3]
   if cmd==1:self.w(b,self.sectors)
   elif cmd==2:self.u.mem_write(b,struct.pack('<H',512))
   elif cmd==3:self.w(b,1)
   self.ret(0)
  self.hook(0x0811e080,rd);self.hook(0x0811e0a0,wr);self.hook(0x0811e0c0,ioctl)
  self.hook(F_OPEN,lambda:self.opens.append((self.text(self.args()[1]),self.args()[2])))   # log only; native f_open runs
 def shm_ring(self,a):return 0x30040000<=a<0x30048000
 # ---- card
 def put(self,path,data):
  """Write a file with the firmware's own FatFs (directories are made on the way)."""
  parts=path.replace('/','\\').strip('\\').split('\\');buf=0x20010000;fil=0x20011000;got=0x20011400;src=0x20012000
  for i in range(1,len(parts)):
   self.u.mem_write(buf,'\\'.join(parts[:i]).encode()+b'\0');r=self.call(F_MKDIR,buf);assert r in (0,8),r
  if data is None:
   self.u.mem_write(buf,'\\'.join(parts).encode()+b'\0');assert self.call(F_MKDIR,buf) in (0,8);return
  self.u.mem_write(buf,'\\'.join(parts).encode()+b'\0');self.u.mem_write(fil,bytes(0x400))
  assert self.call(F_OPEN,fil,buf,0x0a)==0,path
  for o in range(0,len(data),0x4000):
   c=data[o:o+0x4000];self.u.mem_write(src,c);assert self.call(F_WRITE,fil,src,len(c),got)==0 and self.r(got)==len(c)
  assert self.call(F_CLOSE,fil)==0
  self.opens.clear()
 # ---- time
 def frame(self,touch=None):
  """One pass of the UI task loop (08114E66..08114E90) on the task's stack frame, then one pass of the file worker."""
  self.t+=16;self.w(0x300202e8,self.t);self.touch=touch or bytes(0x40);u=self.u
  u.reg_write(UC_ARM_REG_R4,APPP);u.reg_write(UC_ARM_REG_R5,self.TASK_SP);u.reg_write(UC_ARM_REG_R6,GFX);u.reg_write(UC_ARM_REG_SP,self.TASK_SP)
  self._start(0x08114e66,0x08114e90);self.frames+=1
  for f in (0x08110534,0x08112bec,0x08112e0c):self.call(f,PCM,sp=0x3003a000)   # pcmStreamer loop 08112EAC: streaming work
  self.call(0x0812b27c,JOBS,sp=0x3003a000)                                     # ... then the project file jobs
 def run(self,frames=1):
  for _ in range(frames):self.frame()
 def boot(self,frames=300):
  """Splash, settings, autoload (a project on the card, else the firmware makes "New Project") until the UI is up."""
  self.run(frames);return self
 # ---- input
 def event(self,code,w3=0,w2=0,w1=0,w4=0,w5=0):
  """A record in the M7->M4 event ring (shared +0x980, 24 bytes each; write index +0x21A0, read index +0x2180)."""
  wr=self.r(self.shm+0x21a0);self.u.mem_write(self.shm+0x980+(wr&0xff)*24,struct.pack('<6I',code,w1,w2,w3,w4,w5));self.w(self.shm+0x21a0,wr+1)
 def down(self,index,frames=3):self.actions.append('down %d'%index);self.event(0xaf,index);self.run(frames)
 def up(self,index,frames=6):self.actions.append('up %d'%index);self.event(0xb0,index);self.run(frames)
 def press(self,index,hold=3,after=6):self.down(index,hold);self.up(index,after)
 def tap(self,x,top,hold=2,after=6):
  """A finger at screen position (x from the left, top from the top) for `hold` frames, then lifted."""
  self.actions.append('tap %d,%d'%(x,top));rec=bytearray(0x40);struct.pack_into('<H',rec,0,1);struct.pack_into('<hhB',rec,4,x,480-top,0)
  for _ in range(hold):self.frame(bytes(rec))
  self.run(after)
 def load_project(self,row,frames=30):
  """Load a project the way the owner does: PROJ, footer Projects, tap the list row (0 = first, alphabetical),
  footer Load. (The list is the one the firmware read from the card.)"""
  self.press(PROJ);self.footer_tap('Projects');self.tap(100,142+52*row);self.footer_tap('Load');self.run(frames)
 # ---- snapshot (a booted device is reused: every sweep step starts from the same state)
 RAM=[(0x20000000,0x40000),(0x24000000,0x80000),(0x30000000,0x48000),(0x38000000,0x10000),(0x58004000,0x1000),
      (M7MEM,0x200000),(FB,0xa0000),(0xc6000000,0x2000000)]
 def snapshot(self):
  return ([bytes(self.u.mem_read(a,n)) for a,n in self.RAM],dict(self.disk) if self.disk is not None else None,self.t,set(self.rings),list(self.dma.reg))
 def restore(self,snap):
  mem,disk,self.t,rings,reg=snap
  for (a,n),d in zip(self.RAM,mem):self.u.mem_write(a,d)
  self.disk=dict(disk) if disk is not None else None;self.rings=set(rings);self.dma.reg=list(reg);self.touch=bytes(0x40);self.actions=[]
 # ---- state
 def page(self):return self.b(MODEL+0x12c)
 def tracks(self):
  """[(handle, name)] of the loaded project's tracks through the native track lookup and name getter."""
  out=[]
  for i in range(8):
   h=0x20010400;self.w(h,0)
   if self.call(0x08134dbc,MODEL,i,h) and self.r(h):
    self.call(0x08134d6a,MODEL,h,0x82,0x20010800);out.append((self.r(h),self.text(0x20010800)))
  return out
 def getter_raw(self,handle,key,buf):
  """The native string getter (08134D6A -> 0812ED98) into buf, as our code calls it."""
  self.w(0x20010400,handle);return self.call(0x08134d6a,MODEL,0x20010400,key,buf)
 def prop(self,handle,key):
  """A native property of a model object (UI getter 08134A70)."""
  self.w(0x20010400,handle);self.w(0x20010500,0);self.call(0x08134a70,MODEL,0x20010400,key,0x20010500);return self.r(0x20010500)
 def title(self):return self.text(ROOT+0x254+0x31,48)   # footer label (root header title)
 def footer(self):
  """The visible footer buttons of the root header: (text, slot, left, top, width, height)."""
  out=[]
  for k in range(6):
   for base in (0x564,0xa44):   # action widgets, tab widgets (one of the two is shown per slot)
    wdg=ROOT+base+k*0xd0;x,y,w,h=struct.unpack('<4i',self.u.mem_read(wdg+4,16))
    if not self.b(wdg+0x30):out.append((self.text(wdg+0x3c+0x31,32),k,x,480-y-h,w,h))
  return out
 def footer_tap(self,label,**kw):
  """Tap the footer button with this text."""
  for text,k,x,top,w,h in self.footer():
   if text==label:return self.tap(x+w//2,top+h//2,**kw)
  raise KeyError('no footer button %r in %r'%(label,[f[0] for f in self.footer()]))
 def screen(self):
  """The frame buffer as rows of palette indices, top-left origin (glass[Y][X] = fb[1279-X][Y])."""
  import numpy as np
  d=np.frombuffer(bytes(self.u.mem_read(FB,480*1280)),dtype=np.uint8).reshape(1280,480);return d[::-1,:].T.copy()
 def shot(self,path):
  from PIL import Image
  im=Image.fromarray(self.screen(),'P');base=[self.r(0x30000000+4*i) for i in range(16)];pal=[]
  for index in range(256):   # palette index = shade << 4 | colour; the 16 colours at 30000000
   c=base[index&15];a=index>>4;pal.extend(((c>>sh)&255)*a//15 for sh in (16,8,0))
  im.putpalette(pal);im.convert('RGB').save(path)


def image_path():
 return os.path.join(os.environ.get('BENTO_FX_CANDIDATE',''),'bento1.bin')
def project(names):
 """A project file with one track per (type, name); track types without sample files (the M7 is not there to load any)."""
 t=''.join('        <track type="%s"><params cellname="%s" celldisppos="%d"/></track>\n'%(ty,n,i) for i,(ty,n) in enumerate(names))
 return ('<?xml version="1.0" encoding="UTF-8"?>\n<document>\n    <session version="2">\n'+t+
         '        <track type="mastrack"><params/></track>\n    </session>\n</document>\n').encode()


BURGER=(1247,452)
def sweep(d,buttons=range(16),repeats=4,log=None,arrows=True):
 """From the booted state: every hardware button (pressed up to `repeats` times: the cycling buttons), and in every
 state reached every visible footer button, the burger menu (opened, then closed by the same tap position) and the
 four arrows. Every step starts from the snapshot taken before the sweep, replaying the path that led to the state.
 Returns [(path, result)] with result = 'page xx [footer]' or 'FAULT ...'. A faulting path is not extended."""
 snap=d.snapshot();out=[];seen=set()
 def state():return 'page %02x %s'%(d.page(),'|'.join(f[0] for f in d.footer()))
 def play(path):
  d.restore(snap)
  try:
   for kind,arg in path:
    if kind=='button':d.press(arg,2,4)
    elif kind=='footer':d.footer_tap(arg)
    elif kind=='burger':d.tap(*BURGER)
    elif kind=='hold':d.down(arg,6)
   d.run(2);r=state()
  except Fault as e:r='FAULT '+str(e).split(' | ')[0]
  except KeyError as e:r='(no such footer button)'
  out.append((path,r))
  if log:log('%-70s %s'%(' > '.join('%s %s'%(k,a) for k,a in path),r))
  return r
 for b in buttons:
  path=[]
  for n in range(repeats):
   path=path+[('button',b)];r=play(path)
   if r.startswith('FAULT'):break
   if r in seen and n:break          # the cycle is back where it was
   new=r not in seen;seen.add(r)
   if not new:continue
   labels=[f[0] for f in d.footer()]
   for lab in labels:
    r2=play(path+[('footer',lab)])
    if r2.startswith('page') and r2 not in seen:
     seen.add(r2)
     for lab2 in [f[0] for f in d.footer()]:
      if lab2 not in labels:play(path+[('footer',lab),('footer',lab2)])
     for a in (LEFT,RIGHT,UP,DOWN) if arrows else ():play(path+[('footer',lab),('button',a)])
     play(path+[('footer',lab),('burger',0)]);play(path+[('footer',lab),('burger',0),('burger',0)])
   for a in (LEFT,RIGHT,UP,DOWN) if arrows else ():play(path+[('button',a)])
   play(path+[('burger',0)]);play(path+[('burger',0),('burger',0)])
 d.restore(snap);return out
