"""P168 exp8: XY per-track send (owner design, 12 Nov 2026). 1.6.8 only.

Emulator evidence, not hardware evidence. The native per-track mixer function, the summer and the master
compressor's first instructions run in the ARM emulator, on the stock image and on the candidate (Track FX at
its defaults). The LiveA/LiveB effects (in place on the master between the summer and the compressor) are
modelled by negating the master there, so every sample shows on which side of the XY effects it was added.
On 1.6.1 the candidate must contain none of it.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import os,struct,sys,unittest
from pathlib import Path
import numpy as np
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
from test_integration import Fixture,IMAGE,UU,MANIFEST,CANDIDATE
if N.BENTO_FW==168:
 sys.path.insert(0,str(Path(__file__).resolve().parent/'port'));import xy_168 as XY;sys.path.pop(0)
WORD,BLOCK,PROJECT=0x240416ac,0x240416b0,0x240416b4
TAG=0x58590000;RETURNS_OFF=0x100;MAGIC=0x58585858;FRAMES=128
KEEP=[]
def stock():
 s=os.environ.get('BENTO_STOCK_IMAGE')
 if not s:raise unittest.SkipTest('BENTO_STOCK_IMAGE (stock image of this version) is not set')
 return Path(s).read_bytes()

class Chain:
 """Eight tracks through the native mixer, the summer and the compressor entry of one image."""
 def __init__(self,image):
  self.p=p=Fixture(image);KEEP.append(p);p.mixer();p.mailbox({})
  self.root,self.ctx,self.out=p.root,p.ctx,p.out
 def bus(self,i):return self.p.ctx+0x5ac+i*20
 def put(self,i,left,right=None):
  p=self.p;b=self.bus(i)
  p.u.mem_write(p.r(b+8),np.asarray(left,dtype='float32').tobytes())
  if right is not None:p.u.mem_write(p.r(b+12),np.asarray(right,dtype='float32').tobytes())
  p.w(b+4,FRAMES);p.u.mem_write(b+0x10,bytes([0,int(right is not None)]))
 def get(self,i):
  p=self.p;b=self.bus(i);silent,stereo=p.u.mem_read(b+0x10,2)
  left=np.frombuffer(p.u.mem_read(p.r(b+8),FRAMES*4),dtype='float32').copy()
  right=np.frombuffer(p.u.mem_read(p.r(b+12),FRAMES*4),dtype='float32').copy() if stereo else left.copy()
  return silent,stereo,left,right
 def block(self):
  """The bypass block exactly as port/xy_ui.c xy_tick writes it."""
  p=self.p;b=0xc0300000;p.u.mem_write(b,bytes(0x420))
  for o,v in ((0,128),(8,b+0x20),(12,b+0x220),(16,1),(0x14,MAGIC),(0x18,b)):p.w(b+o,v)
  p.w(BLOCK,b);return b
 def state(self,v):self.p.w(WORD,TAG|v)
 def run(self,signals,returns):
  p=self.p
  for t in range(8):
   strip=self.root+0x18+t*0x108
   assert p.u.mem_read(strip+0xa,2)==b'\x0f\x00','track %d output is the master'%t
   self.put(0,signals[t]);p.call(XY.PER_TRACK,self.root,self.bus(0),t,strip,self.out,self.ctx)
  for i,sig in returns.items():self.put(i,sig)
  vt,node=0x20030000,0x20030100;p.u.mem_write(vt,bytes(0x40))
  p.w(vt+0x30,p.r(XY.SUMMER_GETTER_LIT));p.w(node,vt);p.u.mem_write(node+0x12,b'\x0f\x00')
  p.call(XY.SUMMER,node,self.ctx);self.after_summer=self.get(15)
  _,stereo,left,right=self.after_summer  # the XY effects: in place on the master (modelled: negate)
  self.put(15,-left,-right if stereo else None)
  p.u.reg_write(UC_ARM_REG_R0,node);p.u.reg_write(UC_ARM_REG_R1,self.ctx);p.u.reg_write(UC_ARM_REG_SP,0x2003e000);p.u.reg_write(UC_ARM_REG_LR,p.stop|1)
  p.u.emu_start(XY.SITE_COMP|1,XY.SITE_COMP+4,count=2000000)
  assert p.u.reg_read(UC_ARM_REG_PC)==XY.SITE_COMP+4
  self.regs=(p.u.reg_read(UC_ARM_REG_R0),p.u.reg_read(UC_ARM_REG_R1),p.u.reg_read(UC_ARM_REG_SP))
  return self.get(15)

SIGNALS=[(0.05*(t+1)*np.sin(np.arange(FRAMES)*(0.07+0.03*t))).astype('float32') for t in range(8)]
RETURNS={0x11:np.linspace(-0.3,0.2,FRAMES,dtype='float32'),0x15:np.linspace(0.25,-0.1,FRAMES,dtype='float32'),0x13:np.full(FRAMES,0.01,dtype='float32')}
def same(a,b):return all(np.array_equal(np.asarray(x).view('uint32'),np.asarray(y).view('uint32')) if isinstance(x,np.ndarray) else x==y for x,y in zip(a,b))

@unittest.skipUnless(N.BENTO_FW==161,'1.6.1 build')
class Absent161(unittest.TestCase):
 def test_161_has_no_xy_code_or_hooks(self):
  self.assertFalse([w for w in MANIFEST['writes'] if 'XY' in w['reason']])
  for name in ('xy_bar','xy_receive','xy_state','xy_tick','xy_toggle_track'):self.assertNotIn(name,UU)

@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Audio(unittest.TestCase):
 def test_all_tracks_on_returns_on_is_bit_identical_to_stock(self):
  ref=Chain(stock()).run(SIGNALS,RETURNS)
  self.assertEqual(ref[:2],(0,1));self.assertGreater(float(np.abs(ref[2]).max()),1.0) # a real stereo mix
  for setup in ('untagged','tagged, no block','tagged with block'):
   c=Chain(IMAGE)
   if setup!='untagged':c.state(0)
   if setup=='tagged with block':c.block()
   out=c.run(SIGNALS,RETURNS)
   self.assertTrue(same(out,ref),setup)
   self.assertEqual(c.regs[:2],(0x20030100,c.ctx))
 def test_xy_words_without_a_block_change_nothing(self):
  ref=Chain(stock()).run(SIGNALS,RETURNS)
  c=Chain(IMAGE);c.state(0x1ff);self.assertTrue(same(c.run(SIGNALS,RETURNS),ref))
 def test_deselected_track_bypasses_the_xy_effects(self):
  for k in (0,3,7):
   quiet=[s if t!=k else np.zeros(FRAMES,dtype='float32') for t,s in enumerate(SIGNALS)]
   ref=Chain(stock());ref.run(quiet,RETURNS)
   only=Chain(stock());only.run([s if t==k else np.zeros(FRAMES,dtype='float32') for t,s in enumerate(SIGNALS)],{})
   c=Chain(IMAGE);c.state(1<<k);b=c.block();out=c.run(SIGNALS,RETURNS)
   self.assertTrue(same(c.after_summer,ref.after_summer),k) # before the XY effects: all but track k
   self.assertGreater(float(np.abs(only.after_summer[2]).max()),0.05)       # track k is audible on its own
   _,stereo,l,r=ref.after_summer;_,_,kl,kr=only.after_summer
   self.assertTrue(np.array_equal(out[2].view('uint32'),(-l+kl).view('uint32')),k)  # after: track k joins
   self.assertTrue(np.array_equal(out[3].view('uint32'),(-r+kr).view('uint32')),k)
   self.assertEqual(c.p.u.mem_read(b+0x10,1),b'\x01') # bypass bus cleared for the next block
 def test_returns_off_adds_delay_and_reverb_after_the_xy_effects(self):
  ref=Chain(stock());ref.run(SIGNALS,{0x13:RETURNS[0x13]})
  c=Chain(IMAGE);c.state(RETURNS_OFF);b=c.block();out=c.run(SIGNALS,RETURNS)
  self.assertTrue(same(c.after_summer,ref.after_summer))  # summer: tracks and bus 13 only
  _,_,l,r=ref.after_summer
  self.assertTrue(np.array_equal(out[2].view('uint32'),((-l+RETURNS[0x11])+RETURNS[0x15]).view('uint32')))
  self.assertEqual(c.p.r(b+0x1c),0)
 def test_one_track_off_and_returns_off(self):
  quiet=[s if t!=5 else np.zeros(FRAMES,dtype='float32') for t,s in enumerate(SIGNALS)]
  ref=Chain(stock());ref.run(quiet,{0x13:RETURNS[0x13]})
  only=Chain(stock());only.run([s if t==5 else np.zeros(FRAMES,dtype='float32') for t,s in enumerate(SIGNALS)],{})
  c=Chain(IMAGE);c.state(RETURNS_OFF|1<<5);c.block();out=c.run(SIGNALS,RETURNS)
  _,_,l,_=ref.after_summer;_,_,kl,_=only.after_summer
  self.assertTrue(np.array_equal(out[2].view('uint32'),(((-l+kl)+RETURNS[0x11])+RETURNS[0x15]).view('uint32')))
 def test_m7_startup_clears_the_xy_words(self):
  p=Fixture(IMAGE);KEEP.append(p)
  h1,h2=struct.unpack_from('<HH',IMAGE,XY.STARTUP_SITE-0x08040000)
  S=(h1>>10)&1;J1=(h2>>13)&1;J2=(h2>>11)&1
  o=(S<<24)|((1-(J1^S))<<23)|((1-(J2^S))<<22)|((h1&0x3ff)<<12)|((h2&0x7ff)<<1);o-=(S<<25)
  adapter=XY.STARTUP_SITE+4+o
  for a in (WORD,BLOCK,PROJECT):p.w(a,0xdeadbeef)
  p.u.reg_write(UC_ARM_REG_SP,0x2003e000);p.u.emu_start(adapter|1,XY.STARTUP_NEXT,count=200000)
  self.assertEqual([p.r(a) for a in (WORD,BLOCK,PROJECT)],[0,0,0])
  self.assertEqual(p.r(0x24040000),0)

@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Tracks(unittest.TestCase):
 def tracks(self):
  from test_tracks import Tracks as T
  p=T();KEEP.append(p);return p
 def square(self,p,i):
  """outline (top-left), fill (centre), gap between them, column ground above the square"""
  px=p.pixels();x=6+159*i
  return px[378,x+66],px[390,x+78],px[380,x+68],px[372,x+20]
 def test_squares_c2_on_by_default_tap_toggles(self):
  p=self.tracks();p.paint()
  for i in range(8):
   colour=p.call(0x08140ebc,i);outline,fill,gap,ground=self.square(p,i)
   self.assertEqual((outline,fill,gap),(colour,(colour&15)|0xc0,ground),i)
  p.events.clear();p.tap(2,390,tick=5000)
  self.assertEqual(p.call('xy_state'),1<<2)
  self.assertNotIn(0x37,[e[0] for e in p.events]) # the square toggles only; no track selection (0x37)
  p.tap(6,385,tick=9000);self.assertEqual(p.call('xy_state'),1<<2|1<<6)
  p.paint();outline,fill,gap,ground=self.square(p,2)
  self.assertEqual((outline,fill,gap),(p.call(0x08140ebc,2),ground,ground))
  self.assertEqual(self.square(p,1)[1],(p.call(0x08140ebc,1)&15)|0xc0)
  p.save()
  import shutil;shutil.copy(Path(os.environ.get('BENTO_FX_CANDIDATE',CANDIDATE))/'screens'/'tracks.png',Path(os.environ.get('BENTO_FX_CANDIDATE',CANDIDATE))/'screens'/'xy_squares.png')
  p.tap(2,390,tick=13000);self.assertEqual(p.call('xy_state'),1<<6)
 def test_rest_of_the_lower_zone_keeps_select_and_double_tap(self):
  p=self.tracks();p.events.clear()
  p.tap(4,420,tick=5000);self.assertIn(0x37,[e[0] for e in p.events]);self.assertEqual(p.call('xy_state'),0)
 def test_new_project_without_load_is_stock_and_block_is_allocated_once(self):
  p=self.tracks();p.call('xy_toggle_track',1);p.call('xy_tick')
  b=p.e.r(BLOCK);self.assertTrue(b and not b&31)
  self.assertEqual([p.e.r(b+o) for o in (0,4,8,12,16,0x14,0x18)],[128,0,b+0x20,b+0x220,1,MAGIC,b])
  p.call('xy_tick');self.assertEqual(p.e.r(BLOCK),b)
  self.assertEqual(p.call('xy_state'),2)

@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Persistence(unittest.TestCase):
 def master(self,p):
  obj=0x20031200;p.u.mem_write(obj,bytes(0x40));p.u.mem_write(obj+4,b'\x15');p.w(obj+0x10,300);return obj
 def test_saved_on_the_master_track_only_when_not_stock(self):
  p=Fixture();KEEP.append(p);obj=self.master(p)
  p.call(UU['kick_ui_save'],obj,0x20017000);self.assertNotIn('bento_xy_v1',p.attrs)
  p.call(UU['xy_toggle_track'],3);p.w(WORD,p.r(WORD)|RETURNS_OFF)
  p.call(UU['kick_ui_save'],obj,0x20017000);self.assertEqual(p.attrs['bento_xy_v1'],RETURNS_OFF|1<<3)
  track=0x20031300;p.u.mem_write(track,bytes(0x40));p.u.mem_write(track+4,b'\x0e');p.attrs.clear()
  p.call(UU['kick_ui_save'],track,0x20017000);self.assertNotIn('bento_xy_v1',p.attrs)
 def test_load_restores_and_absent_means_stock(self):
  p=Fixture();KEEP.append(p);obj=self.master(p)
  p.attrs['bento_xy_v1']=RETURNS_OFF|1<<1|1<<7
  p.call(UU['kick_ui_load'],0x20017100,obj);self.assertEqual(p.call(UU['xy_state']),RETURNS_OFF|1<<1|1<<7)
  del p.attrs['bento_xy_v1'];p.call(UU['kick_ui_load'],0x20017100,obj);self.assertEqual(p.call(UU['xy_state']),0)

@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class XyPage(unittest.TestCase):
 def page(self):
  sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'research').exists())/'research/display_emulator'))
  import emu,render
  from unicorn import UC_HOOK_CODE
  e=emu.Emu(IMAGE);render.boot_gfx(e);KEEP.append(e);nxt=[0x20020000]
  def alloc(u,a,n,d):
   r0=u.reg_read(UC_ARM_REG_R0);u.reg_write(UC_ARM_REG_R0,nxt[0]);nxt[0]+=(r0+31)&~31;u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  hs=[e.u.hook_add(UC_HOOK_CODE,alloc,begin=a,end=a) for a in (0x0809f940,0x0809f960,0x08104c08)]
  e.call(XY.REGISTRY_BUILD,0)
  for h in hs:e.u.hook_del(h)
  v=0xc1800000;e.call(XY.XY_VIEW_CTOR,v);e.w(v+4,0);e.w(v+8,0);e.w(v+12,1280);e.w(v+16,480)
  return e,render,v
 def slot(self,v,i):return v+0x48+0x38+i*0x468
 def test_encoder_4_is_returns_thru_xy_native_slots_unchanged(self):
  e,render,v=self.page();e.call(XY.XY_VIEW_UPDATE,v)
  rows=[(e.h(self.slot(v,i)+0x9c),e.text(self.slot(v,i)+0x3f9),e.text(self.slot(v,i)+0xd9)) for i in range(8)]
  self.assertEqual(rows,[(0xfc,'LiveA FX','Repeater'),(0xf1,'Hold A','Off'),(0,'',''),(0x9a,'Returns thru XY','On'),(0,'',''),(0,'',''),(0xf2,'Hold B','Off'),(0xfd,'LiveB FX','Bitcrusher')])
  e.w(WORD,TAG|RETURNS_OFF);e.call(XY.XY_VIEW_UPDATE,v);self.assertEqual(e.text(self.slot(v,3)+0xd9),'Off')
  e.u.mem_write(render.CTX,struct.pack('<II',257,render.SURF));render.paint(e,v);render.paint(e,v+0x48)
  from PIL import Image
  im=Image.fromarray(render.ui(e),'P');base=[e.r(0x30000000+4*i) for i in range(16)];pal=[]
  for index in range(256):pal.extend(((base[index&15]>>s)&255)*(index>>4)//15 for s in (16,8,0))
  im.putpalette(pal);out=Path(os.environ.get('BENTO_FX_CANDIDATE',CANDIDATE))/'screens';out.mkdir(exist_ok=True);im.convert('RGB').save(out/'xy_page.png')
 def test_encoder_events_toggle_returns_and_stay_off_the_model(self):
  e,render,v=self.page();e.call(XY.XY_VIEW_UPDATE,v)
  from unicorn import UC_HOOK_CODE
  native=[]
  e.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:native.append(a),begin=XY.XY_RECEIVE_NATIVE,end=XY.XY_RECEIVE_NATIVE)
  ev=0x24070000
  e.u.mem_write(ev,struct.pack('<5I',0xcf,0xfffffffe,0x9a,0,0));self.assertEqual(e.call(UU['xy_receive'],v,ev),1)
  self.assertEqual(e.r(WORD)&0x1ff,RETURNS_OFF);self.assertEqual(e.text(self.slot(v,3)+0xd9),'Off');self.assertFalse(native)
  e.u.mem_write(ev,struct.pack('<5I',0xcf,0xfffffffe,0x9a,1,0));e.call(UU['xy_receive'],v,ev)
  self.assertEqual(e.r(WORD)&0x1ff,0);self.assertEqual(e.text(self.slot(v,3)+0xd9),'On')
  e.u.mem_write(ev,struct.pack('<5I',0xcf,0xffffffef,0xf1,1,0));e.call(UU['xy_receive'],v,ev);self.assertEqual(native,[XY.XY_RECEIVE_NATIVE])
  out=0x24070100;e.w(out+0x100,0xfffffffe);self.assertEqual(e.call(UU['fx_get'],0x30024b00,out+0x100,0x9a,out),1);self.assertEqual(e.r(out),1) # getter: On
 def test_view_receive_slot_and_bar_site_point_at_ours(self):
  self.assertEqual(struct.unpack_from('<I',IMAGE,XY.XY_VIEW_VT+48-0x08040000)[0],UU['xy_receive']|1)
  reasons=[w['reason'] for w in MANIFEST['writes'] if 'XY' in w['reason']]
  self.assertEqual(len(reasons),7,reasons)

if __name__=='__main__':unittest.main()
