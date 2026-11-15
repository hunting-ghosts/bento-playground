"""P168 exp8: the FX button views "Mod FX | Send FX | XY Pads" (owner decisions 13 Nov 2026). 1.6.8 only.

Emulator evidence, not hardware evidence. The native FX Settings page view (ctor 08149014) is built in the ARM
emulator on the built candidate, with its five patched vtable slots (port/fxv_168.py) running our code; the native
model getters/setters and the native section-group layout/paint are hooked or run as the oracle. On 1.6.1 none of it
is in the build.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N
import os,struct,sys,unittest
from pathlib import Path
import numpy as np
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_LR,UC_ARM_REG_SP
from test_integration import Fixture,UU,IMAGE,MANIFEST,CANDIDATE
# 1.6.8 native flash addresses come from the untranslated port module (like test_xy_send), so make_tree does not
# re-translate them as if they were 1.6.1 addresses.
if N.BENTO_FW==168:
 sys.path.insert(0,str(Path(__file__).resolve().parent/'port'));import fxv_168 as FXV;sys.path.pop(0)
 CTOR=FXV.VIEW_CTOR;SETUP=FXV.VIEW_SETUP;SET_SECTION=FXV.SET_SECTION;GET=FXV.UI_GET;THANDLE=FXV.TRACK_HANDLE
 POST=FXV.MODEL_POST;COLOUR=FXV.TRACK_COLOUR;REGBUILD=FXV.REGISTRY_BUILD;NAV=FXV.FX_PAGE_NAV;COMMIT=FXV.SLOT_COMMIT
 NAME=FXV.NAME_GET;TURN=FXV.CELL_TURN;FILL=FXV.FILL;CHILD_PAINT=FXV.CHILD_PAINT;TAB_FLAGS=FXV.ROOT_TAB_FLAGS

FV=0x240416bc;FV_TAG=0x46560000   # RAM state word (not address-translated)
SG=0x9180;VIEW=0xc0010000  # inside the mapped SDRAM window (0xc0000000+0x400000), below the fixture allocator cursor
# native type value <-> list index: Flanger+Dist 0, Chorus 1, Phaser 2  (list order Chorus, Phaser, Flanger+Dist)
LIST=[1,2,0]           # list index -> native type
KEEP=[]

def stock_1_6_1():
 s=os.environ.get('BENTO_STOCK_IMAGE')
 if not s or N.BENTO_FW!=161:raise unittest.SkipTest('1.6.1 build only')
 return Path(s)


class FxView(Fixture):
 """Build the native FX Settings view (page 0B) with its three/four sections and drive our slots."""
 def __init__(self,outs,ntype=1,section=0,vals=None):
  super().__init__();KEEP.append(self);self.outs=list(outs);self.ntype=ntype;self.posts=[];self.navs=[]
  self.vals={0x103:ntype,0x15c:450,0x15d:600,0x15e:550,0x163:400,0x36:280,0x37:0,
             0x167:450,0x168:300,0x164:600,0x165:500,0x166:350,  # run 16: chorus/phaser keys (1.6.8)
             0xe7:400,0xd1:1,0xcf:600,0xf3:500,0xec:1,0xeb:1,0xea:7,0xe9:500,
             0x1b6:0,0x1a1:2,0x1a9:620,0x1aa:450,0x1a6:800,0x1a5:100,0x18c:30,0x19a:0,0x1ad:0,0x1ac:400}
  self.vals.update(vals or {}) # run 17: e.g. Reverb mode Shimmer before the native page is built
  self.u.hook_add(UC_HOOK_CODE,self.fxhook)
  self.force_registry=True;self.call(REGBUILD,0);self.force_registry=False
  self.v=VIEW;self.call(CTOR,self.v)
  for i,x in enumerate((0,0,1280,480)):self.w(self.v+4+4*i,x)
  tbl=[[0x103,0,0,0,0,0,0x36,0x37],[0xe7,0xd1,0xcf,0xf3,0xec,0xeb,0xe9,0],
       [0x1b6,0x1a1,0x1a9,0x1aa,0x1a6,0x1a5,0x18c,0x19a],[0x1ad,0x1ac,0,0,0,0,0,0]]
  for i,row in enumerate(tbl):
   self.u.mem_write(self.v+0x9538+16*i,struct.pack('<8H',*row))
   if i:self.u.mem_write(self.v+0x9060+0x50*i,struct.pack('<8H',*row))
  for fb in range(4):
   for i in range(8):self.w(self.v+0x9040+0x50*fb+4*i,0x20001000)
  self.call(SETUP,self.v)
  if section:self.call(SET_SECTION,self.v+SG,section)
  self.w(FV,FV_TAG|(section&3))
 def fxhook(self,u,a,n,d):
  r=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  if a==GET:
   key=r[2];out=r[3]
   if key==0x2d:
    t=struct.unpack('<I',u.mem_read(r[1],4))[0]-1;self.w(out,self.outs[t] if 0<=t<8 else 9);self.ret(1)
   elif key in self.vals:self.w(out,self.vals[key]);self.ret(1)
   else:self.ret(0)
  elif a==THANDLE:self.w(r[2],r[1]+1);self.ret(1)
  elif a==POST:
   e=struct.unpack('<5I',u.mem_read(r[1],20));self.posts.append(e)
   if e[0]==0xcf and e[2]==0x2d:self.outs[e[1]-1]=e[3]  # the toggle writes the native output setting
   elif e[2] in self.vals:self.vals[e[2]]=e[3]            # run 16: the model stores a committed FX value
   self.ret(0)
  elif a==NAME:
   t=struct.unpack('<I',u.mem_read(r[1],4))[0]-1;u.mem_write(r[3],N.native_string(('Track %d'%(t+1)).encode()));self.ret(1)
  elif a==NAV:self.navs.append(r[1]);self.ret()
  elif a==COMMIT:  # run 16: a D4 leaving the view is what the device's model stores (the getter then returns it)
   e=struct.unpack('<5I',u.mem_read(r[1],20))
   if e[0]==0xd4 and e[2] in self.vals:self.vals[e[2]]=e[3]
 def bar(self,i):return self.r(self.v+SG+0x34+4*i)
 def hidden(self,w):return self.u.mem_read(w+0x30,1)[0]
 def tick(self):self.u.mem_write(0x24078100,struct.pack('<II',0x101,0x24078000));self.call(UU['fxv_tick'],self.v,0x24078100)
 def section(self):return self.r(self.v+SG+0x39c)
 def point(self,x,top):self.w(0x20036000,x);self.w(0x20036004,480-top);return 0x20036000
 def top(self,w):return 480-self.r(w+8)-self.r(w+16)
 def commit(self,key,value):
  """The native encoder path: turn the Mod FX row cell that holds the key (native cell turn, 160 units per step);
  the native cell sends CF, the native FX view turns it into the D4 that leaves the view for the model."""
  b=self.bar(0)
  for c in range(8):
   cell=b+0x38+c*0x468
   if struct.unpack('<H',self.u.mem_read(cell+0x9c,2))[0]==key:break
  else:raise AssertionError('no cell for key %x'%key)
  cur=struct.unpack('<i',self.u.mem_read(cell+0xa0,4))[0];self.call(TURN,cell,((value-cur)*160)&0xffffffff)
  self.report()
 def report(self):
  """The model's change report (event C3) to the view's event slot: the native handler re-reads every value
  through the getter (native setup 081490F4, as on the device after a stored change)."""
  ev=0x20037200;self.u.mem_write(ev,struct.pack('<5I',0xc3,0,0,0,0));self.call(UU['fxv_arrows'],self.v,ev)
 def set_type(self,ntype):
  """Left/Right (the view's arrow events, committed natively as D4 type) until the native type is ntype."""
  ev=0x20037000
  for _ in range(3):
   i=LIST.index(self.vals[0x103]);j=LIST.index(ntype)
   if i==j:return
   self.u.mem_write(ev,struct.pack('<5I',0xaa,0,9 if j>i else 0,0,0));self.call(UU['fxv_arrows'],self.v,ev);self.report();self.tick()
 def picture(self):
  """Run 16: paint our part of the view (native children skipped) and return the picture's column fills
  (x, top, bottom, colour) inside the picture box, plus the track texts."""
  fills=[];texts=[]
  def fill(u,a,n,d):
   x,y,w,h=struct.unpack('<4i',u.mem_read(u.reg_read(UC_ARM_REG_R0),16));fills.append((x,480-y-h,w,h,u.reg_read(UC_ARM_REG_R1)));self.ret()
  def child(u,a,n,d):self.ret()
  def text(u,a,n,d):
   sp=u.reg_read(UC_ARM_REG_SP);st=struct.unpack('<3I',u.mem_read(sp,12))
   texts.append((u.reg_read(UC_ARM_REG_R1),bytes(u.mem_read(st[1],32)).split(b'\0')[0].decode(),st[2]));self.ret()
  hs=[self.u.hook_add(UC_HOOK_CODE,fill,begin=FILL,end=FILL),self.u.hook_add(UC_HOOK_CODE,child,begin=CHILD_PAINT,end=CHILD_PAINT),
      self.u.hook_add(UC_HOOK_CODE,text,begin=UU['pg_text']&~1,end=UU['pg_text']&~1)]
  self.u.mem_write(0x24078100,struct.pack('<II',0x101,0x24078000))
  try:self.call(UU['fxv_paint'],self.v,0x24078100)
  finally:
   for h in hs:self.u.hook_del(h)
  self.texts=texts;self.allfills=fills
  return [(x,t,t+h,c) for x,t,w,h,c in fills if w==2 and 60<=x<1220 and 92<=t<308]
 def mod(self,**values):
  """Set Mod FX values through the native encoder path, tick (the native tick reads them back) and paint."""
  keys={1:dict(amount=0x167,rate=0x168),2:dict(amount=0x164,rate=0x166,feedback=0x165),
        0:dict(amount=0x15c,rate=0x15d,feedback=0x15e,distortion=0x163)}
  if 'type' in values:self.set_type(values.pop('type'))
  for k,v in values.items():self.commit(keys[self.vals[0x103]][k],v);self.tick()
  self.tick();return self.picture()


def colours(cols):return sorted({c for x,t,b,c in cols})
def front(cols):
 """Top edge per x of the white (front) voice."""
 d={}
 for x,t,b,c in cols:
  if c==0xf2:d[x]=min(d.get(x,999),t)
 return [d[x] for x in sorted(d)]
def peaks(cols):
 """Upward peaks of the white voice (local minima of its top edge, plateaus counted once)."""
 f=front(cols);y=[f[0]]+[v for a,v in zip(f,f[1:]) if v!=a]
 return sum(1 for i in range(1,len(y)-1) if y[i]<y[i-1] and y[i]<y[i+1])
def extent(cols):
 w=[(t,b) for x,t,b,c in cols if c==0xf2];return max(b for t,b in w)-min(t for t,b in w)
def flat(cols):
 """Columns of the white voice at its highest point (a clipped wave has long flat tops)."""
 f=front(cols);return sum(1 for v in f if v==min(f))


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class FxViewsNav(unittest.TestCase):
 def rec(self,out,i):return self.u.mem_read(out+N.HDR(0x74)+i*48,48) if False else None
 def header(self,page):
  p=Fixture();KEEP.append(p);p.registry();p.u.mem_write(0x30024b00+0x12c,bytes([page]))
  out=0x20034000;p.u.mem_write(out,bytes(0x200));p.call(UU['fxv_toolbar'],out,page)
  recs=[]
  for i in range(6):
   r=p.u.mem_read(out+N.HDR(0x74)+i*48,48)
   recs.append((r[:31].split(b'\0')[0].decode('latin1'),r[0x21],r[44]|r[45]<<8))
  return p,recs
 def test_footer_three_views_in_mixing_desk_order(self):
  _,recs=self.header(0x0b)  # FX Settings page, section 0 = Mod FX view
  self.assertEqual([recs[i] for i in (3,4,5)],[('Mod FX',1,0x1066),('Send FX',0,0x1067),('XY Pads',0,0x1068)])
 def test_footer_marks_xy_on_the_xy_page(self):
  _,recs=self.header(0x0c)  # XY page
  self.assertEqual([(recs[i][0],recs[i][1]) for i in (3,4,5)],[('Mod FX',0),('Send FX',0),('XY Pads',1)])
 def test_fx_button_cycles_send_fx_and_xy(self):
  # from the Send FX view (page 0B) the FX button goes to XY (0C); from XY back to Mod FX (0B)
  p=Fixture();KEEP.append(p);p.registry();navs=[]
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(navs.append(u.reg_read(UC_ARM_REG_R1)),u.reg_write(UC_ARM_REG_R0,0),u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))) and None,begin=NAV,end=NAV)
  p.w(FV,FV_TAG|1);p.u.mem_write(0x30024b00+0x12c,b'\x0b')      # Send FX view
  self.assertEqual(p.call(UU['fxv_go'],0x30024b00,3),1);self.assertEqual(navs[-1],0x0c)
  p.u.mem_write(0x30024b00+0x12c,b'\x0c')
  self.assertEqual(p.call(UU['fxv_go'],0x30024b00,3),1);self.assertEqual(navs[-1],0x0b)
 def test_fx_button_is_inert_off_the_fx_pages(self):
  p=Fixture();KEEP.append(p);p.registry();p.u.mem_write(0x30024b00+0x12c,b'\x02')
  self.assertEqual(p.call(UU['fxv_go'],0x30024b00,3),0)
 def test_footer_taps_select_the_tapped_view(self):
  p=Fixture();KEEP.append(p);p.registry();navs=[]
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(navs.append(u.reg_read(UC_ARM_REG_R1)),u.reg_write(UC_ARM_REG_R0,0),u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))) and None,begin=NAV,end=NAV)
  p.u.mem_write(0x30024b00+0x12c,b'\x0b')
  for tap,page in ((0,0x0b),(1,0x0b),(2,0x0c)):  # Mod FX, Send FX, XY Pads
   p.call(UU['fxv_go'],0x30024b00,tap);self.assertEqual(navs[-1],page)


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class FxViewsMod(unittest.TestCase):
 def test_mod_fx_view_hides_delay_and_reverb(self):
  f=FxView([1,0,2,1,1,0,1,3],ntype=1,section=0);f.tick()
  self.assertEqual(f.hidden(f.bar(0)),0)
  self.assertEqual(f.hidden(f.bar(1)),1);self.assertEqual(f.hidden(f.bar(2)),1)
 def test_send_fx_view_hides_mod_fx_only(self):
  f=FxView([0]*8,ntype=1,section=1);f.tick()
  self.assertEqual(f.hidden(f.bar(0)),1)
  self.assertEqual(f.hidden(f.bar(1)),0);self.assertEqual(f.hidden(f.bar(2)),0)
 def test_mod_fx_view_has_no_effect_list_and_shows_the_type_in_encoder_1(self):
  # owner correction (13 Nov): no Chorus/Phaser/Flanger list; the type shows in encoder 1 (native cell) and the picture
  for ntype,label in ((1,b'Chorus'),(2,b'Phaser'),(0,b'Flanger+Dist')):
   f=FxView([0]*8,ntype=ntype,section=0);f.tick()
   for i in range(3):self.assertEqual(f.hidden(f.v+SG+0x44+i*0x70),1,i)   # every section title hidden
   cell=f.bar(0)+0x38
   self.assertEqual(struct.unpack('<i',f.u.mem_read(cell+0xa0,4))[0],ntype)
   self.assertEqual(f.u.mem_read(cell+0xa8+0x31,14).split(b'\0')[0],label)
   f.picture();self.assertFalse([1 for x,t,w,h,c in f.allfills if x==16 and w==180])  # no list frame
 def test_toggle_switches_native_output_1_and_1_w_mod_fx(self):
  f=FxView([0,1,2,3,0,1,2,3],ntype=1,section=0);f.tick()
  # tap track 0 (output "1" = 0): routes it through Mod FX -> output 1 ("1 w/ Mod FX")
  f.call(UU['fxv_up'],f.v,f.point(80,360),0)
  self.assertIn((0xcf,1,0x2d,1,0),f.posts)
  # tap track 1 (output "1 w/ Mod FX" = 1): back to "1" = 0
  f.posts.clear();f.call(UU['fxv_up'],f.v,f.point(80+160,360),0)
  self.assertIn((0xcf,2,0x2d,0,0),f.posts)
 def test_toggle_leaves_outputs_2_and_3_unchanged(self):
  f=FxView([2,3,2,3,2,3,2,3],ntype=1,section=0);f.tick()
  f.call(UU['fxv_up'],f.v,f.point(80,360),0)       # track 0 output "2": not a Mod FX toggle
  self.assertEqual(f.posts,[])
 def test_toggle_does_not_create_a_new_save_format(self):
  # the toggle writes the native output setting (key 0x2d) only; nothing else is posted
  f=FxView([0]*8,ntype=1,section=0);f.tick()
  f.call(UU['fxv_up'],f.v,f.point(80,360),0)
  self.assertEqual([e[:3] for e in f.posts],[(0xcf,1,0x2d)])
 def test_left_right_select_the_mod_fx_type(self):
  f=FxView([0]*8,ntype=1,section=0);f.tick()  # Chorus (list index 0)
  ev=0x20037000
  f.u.mem_write(ev,struct.pack('<5I',0xaa,0,9,0,0))   # Right (button 9): Chorus -> Phaser
  posts=[];f.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:posts.append(struct.unpack('<5I',u.mem_read(u.reg_read(UC_ARM_REG_R1),20))),begin=COMMIT,end=COMMIT)
  f.call(UU['fxv_arrows'],f.v,ev)
  self.assertTrue(any(e[0]==0xd4 and e[2]==0x103 and e[3]==LIST[1] for e in posts))  # native type for Phaser = 2
 def test_left_stops_at_the_first_type(self):
  f=FxView([0]*8,ntype=1,section=0);f.tick()  # Chorus = list index 0
  ev=0x20037000;f.u.mem_write(ev,struct.pack('<5I',0xaa,0,0,0,0))  # Left at the first entry: no change
  posts=[];f.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:posts.append(1),begin=COMMIT,end=COMMIT)
  f.call(UU['fxv_arrows'],f.v,ev);self.assertEqual(posts,[])


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class FxViewsLayout(unittest.TestCase):
 """Run 16: rows placed as design/native/native_modfx.png and native_sendfx.png; thin frame A on the active row."""
 def test_mod_fx_row_at_the_top_without_a_frame(self):
  # Run 19 (owner, exp8 hardware): the row frame only shows when there are several rows to choose from; the Mod FX
  # view has one row. (Runs 16-18 drew frame A around it: test_mod_fx_row_at_the_top_in_the_frame.)
  f=FxView([0]*8,ntype=1,section=0);f.tick()
  self.assertEqual(f.top(f.bar(0)+0x38),8)                        # first cell top
  fr=f.v+SG+0x208;self.assertEqual((f.top(fr),f.r(fr+16)),(4,70));self.assertNotEqual(f.hidden(fr),0)
 def test_the_frame_comes_back_in_the_send_fx_view_and_goes_again_in_mod_fx(self):
  f=FxView([0]*8,ntype=1,section=0);f.tick();fr=f.v+SG+0x208;self.assertNotEqual(f.hidden(fr),0)
  f.call(SET_SECTION,f.v+SG,1);f.w(FV,FV_TAG|1);f.tick();f.tick();self.assertEqual(f.hidden(fr),0)   # Delay | Reverb rows
  f.call(SET_SECTION,f.v+SG,0);f.w(FV,FV_TAG|0);f.tick();f.tick();self.assertNotEqual(f.hidden(fr),0)
 def test_send_fx_delay_top_reverb_above_the_footer_and_frame_follows_up_down(self):
  f=FxView([0]*8,ntype=1,section=1);f.tick()
  self.assertEqual((f.top(f.bar(1)+0x38),f.top(f.bar(2)+0x38)),(8,354))
  for i in (1,2):                                                    # the labels moved with their rows
   c=f.bar(i)+0x38;self.assertTrue(f.top(c)<=f.top(c+0x3c8)<f.top(c+0xa8)<f.top(c)+70,i)
  fr=f.v+SG+0x208;self.assertEqual(f.top(fr),4);self.assertEqual(f.hidden(fr),0)   # two rows: the frame shows
  for i,name in ((1,b'Delay'),(2,b'Reverb')):
   t=f.v+SG+0x44+i*0x70;self.assertEqual(f.hidden(t),0);self.assertEqual(f.top(t),80)
   self.assertEqual(f.u.mem_read(t+0x31,8).split(b'\0')[0],name)
  f.call(SET_SECTION,f.v+SG,2);f.tick()                             # native Down: Reverb row active
  self.assertEqual((f.top(fr),f.top(f.bar(2)+0x38)),(350,354))
  f.tick();self.assertEqual(f.top(f.bar(2)+0x38),354)                # idempotent
 def test_toggles_and_track_names_at_native_size_above_the_footer(self):
  f=FxView([0,1,2,3,0,1,0,1],ntype=1,section=0);f.tick();f.picture()
  self.assertEqual([(i,n) for i,n,_ in f.texts],[(t,'Track %d'%(t+1)) for t in range(8)])
  squares=[(x,t,w,h,c) for x,t,w,h,c in f.allfills if t==334 and w==48 and h==2]  # top edges
  self.assertEqual([x for x,*_ in squares],[56+160*t for t in range(8)])
  inner=[x for x,t,w,h,c in f.allfills if w==32 and h==32 and t==342]
  self.assertEqual(inner,[56+160*t+8 for t in (1,5,7)])            # "1 w/ Mod FX" tracks are filled
 def test_footer_has_no_dividers_and_navigation_restores_them(self):
  p=Fixture();KEEP.append(p);p.registry();out=0x20034000;p.u.mem_write(out,bytes(0x200))
  for i in range(3,6):p.u.mem_write(TAB_FLAGS+i*0xd0,b'\1')
  p.call(UU['fxv_toolbar'],out,0x0b)
  self.assertEqual([p.u.mem_read(TAB_FLAGS+i*0xd0,1)[0] for i in range(3,6)],[0,0,0])


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class FxViewsPicture(unittest.TestCase):
 """Run 16 (owner, FX views v2): the Mod FX picture is computed live from the native values and reacts to every
 parameter. Each test changes one parameter through the native encoder path (event D4 -> native slot commit ->
 model post; the native tick reads it back through the getter) and checks the picture as specified in fxv_ui.c."""
 def view(self,ntype,**v):
  f=FxView([0]*8,ntype=ntype,section=0);f.tick();base=f.mod(**v);return f,base
 # Run 17 (owner go-ahead 13 Nov, supersedes run 16's phaser ripple / flanger comb copies): Flanger+Dist and
 # Phaser are live, animated frequency-response curves (fxv_ui.c, references flanger_pages_v2.png / phaser_pages.png):
 # two dim curves = the sweep range, the white one = where the sweep is now; Chorus keeps its three waves.
 def curves(self,f,at=1000):
  """The picture's curves as drawn by the shared curve helper: (colour, ys) per call, at UI time 'at' ms."""
  out=[]
  def curve(u,a,n,d):
   cnt=u.reg_read(UC_ARM_REG_R2);sp=u.reg_read(UC_ARM_REG_SP);ys_at,colour=struct.unpack('<2I',u.mem_read(sp,8))
   out.append((colour,struct.unpack('<%dh'%cnt,u.mem_read(ys_at,2*cnt))))
  f.w(0x3001fe2c,at);h=f.u.hook_add(UC_HOOK_CODE,curve,begin=UU['pg_curve']&~1,end=UU['pg_curve']&~1)
  try:cols=f.picture()
  finally:f.u.hook_del(h)
  return out,cols
 @staticmethod
 def dips(ys,top):
  """Notches of a response curve: separate runs of columns in its lower third (y grows downwards)."""
  y=list(ys);cut=min(y)+(max(y)-min(y))*2//3;runs=0;inside=False
  for v in y:
   if v>cut and not inside:runs+=1
   inside=v>cut
  return runs
 @staticmethod
 def teeth(ys):
  """Peaks of a response curve: separate runs of columns in its upper third."""
  y=list(ys);cut=min(y)+(max(y)-min(y))//3;runs=0;inside=False
  for v in y:
   if v<cut and not inside:runs+=1
   inside=v<cut
  return runs
 def test_type_chorus_waves_phaser_and_flanger_response_curves(self):
  f,chorus=self.view(1)
  self.assertEqual(colours(chorus),[0x52,0x92,0xf2])
  f.mod(type=2);c,_=self.curves(f);self.assertEqual(f.vals[0x103],2);self.assertEqual([k for k,_ in c],[0x52,0x52,0xf2]) # range + now
  f.mod(type=0);c,cols=self.curves(f);self.assertEqual(f.vals[0x103],0);self.assertEqual([k for k,_ in c],[0x52,0x52,0xf2,0xf2]) # + distortion strip
  self.assertTrue(all(262<=y<=313 for y in c[3][1]))
 def test_phaser_and_flanger_are_clearly_distinguishable(self):
  f,_=self.view(2);ph=self.curves(f)[0][2][1];f.mod(type=0);fl=self.curves(f)[0][2][1]
  self.assertLessEqual(self.dips(ph,0),4);self.assertGreaterEqual(self.dips(fl,0),5) # a few broad dips vs a dense comb
  wide=lambda ys:sum(1 for y in ys if y>min(ys)+(max(ys)-min(ys))*2//3) # columns in the lower third (the dips)
  self.assertGreater(wide(ph)/max(1,self.dips(ph,0)),wide(fl)/self.dips(fl,0)*1.5)
 def test_amount_sets_the_sweep_range_and_the_chorus_height(self):
  f,_=self.view(1);self.assertGreater(extent(f.mod(amount=900)),extent(f.mod(amount=100))+120)
  f,_=self.view(0);f.mod(amount=100);n=self.curves(f)[0];f.mod(amount=900);w=self.curves(f)[0]
  span=lambda c:self.teeth(c[1][1])-self.teeth(c[0][1]) # flanger: teeth of the longest minus the shortest delay
  self.assertGreater(span(w),span(n)+3)
  f,_=self.view(2);f.mod(amount=100);n=self.curves(f)[0];f.mod(amount=900);w=self.curves(f)[0]
  gap=lambda c:sum(abs(a-b) for a,b in zip(c[0][1],c[1][1]))
  self.assertGreater(gap(w),gap(n)*2)
  f,_=self.view(2);f.mod(amount=200);shallow=self.curves(f)[0][2][1];f.mod(amount=1000);deep=self.curves(f)[0][2][1]
  self.assertGreater(max(deep)-min(deep),max(shallow)-min(shallow)+30) # phaser: deeper dips
 def test_rate_sets_the_cycles_and_the_sweep_speed(self):
  f,_=self.view(1);self.assertEqual(peaks(f.mod(rate=0)),1);self.assertGreaterEqual(peaks(f.mod(rate=1000)),7)
  for ntype in (2,0):
   f,_=self.view(ntype)
   moved=[]
   for rate in (0,1000):
    f.mod(rate=rate);a=self.curves(f,1000)[0][2][1];b=self.curves(f,1050)[0][2][1];moved.append(sum(abs(x-y) for x,y in zip(a,b)))
   self.assertGreater(moved[1],moved[0]*3,(ntype,moved)) # in 50 ms a fast sweep moves much further
   self.assertNotEqual(self.curves(f,1000)[0][2][1],self.curves(f,1700)[0][2][1]) # it animates
 def test_chorus_amount_spreads_the_voices(self):
  f,_=self.view(1)
  def spread(cols):
   a=[x for x,t,b,c in cols if c==0xf2 and t==min(t2 for x2,t2,b2,c2 in cols if c2==0xf2)]
   d=[x for x,t,b,c in cols if c==0x52 and t==min(t2 for x2,t2,b2,c2 in cols if c2==0x52)]
   return abs(d[0]-a[0])
  self.assertGreater(spread(f.mod(amount=900,rate=0)),spread(f.mod(amount=100,rate=0)))
 def test_phaser_feedback_adds_resonance_next_to_the_dips(self):
  f,_=self.view(2);f.mod(rate=0,feedback=0);calm=self.curves(f)[0][2][1];f.mod(feedback=1000);res=self.curves(f)[0][2][1]
  self.assertLess(min(res),min(calm)-10)              # resonant peaks rise above the plain response
  self.assertLessEqual(self.dips(res,0),4)             # still a few dips, never a comb
 def test_flanger_feedback_sharpens_the_comb(self):
  f,_=self.view(0);f.mod(feedback=0);soft=self.curves(f)[0][2][1];f.mod(feedback=1000);sharp=self.curves(f)[0][2][1]
  high=lambda ys:sum(1 for y in ys if y<96+140//3)     # columns in the upper third (the peaks)
  self.assertLess(high(sharp),high(soft))              # narrower peaks
 def test_flanger_distortion_makes_the_strip_squarer_at_constant_height(self):
  f,_=self.view(0);f.mod(distortion=0);clean=self.curves(f)[0][3][1];f.mod(distortion=1000);dirty=self.curves(f)[0][3][1]
  self.assertLessEqual(abs((max(dirty)-min(dirty))-(max(clean)-min(clean))),2)
  flat=lambda ys:sum(1 for y in ys if y<=min(ys)+1)
  self.assertGreater(flat(dirty),flat(clean)*3)
 def test_send_levels_and_outputs_do_not_change_the_picture_but_a_value_change_requests_a_repaint(self):
  f,base=self.view(1)
  f.commit(0x36,900);f.tick();self.assertEqual(f.picture(),base)
  f.mod(amount=200)
  f.u.mem_write(0x24078100,struct.pack('<II',0,0x24078000));f.call(UU['fxv_tick'],f.v,0x24078100)
  self.assertEqual(f.u.mem_read(0x24078101,1)[0],0)                   # unchanged values: no repaint request
  f.commit(0x167,300);f.u.mem_write(0x24078100,struct.pack('<II',0,0x24078000));f.call(UU['fxv_tick'],f.v,0x24078100)
  self.assertEqual(f.u.mem_read(0x24078101,1)[0],1)                   # a changed value asks for a full repaint
  self.assertNotEqual(f.picture(),base)


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class FxViewsSendPicture(unittest.TestCase):
 """Run 17 (owner, FX views v3 FINAL): the Send FX pictures (delay rings, reverb tail per style, Shimmer sparks) are
 computed live from the native values and react to every parameter. Each test turns one cell of the Delay / Reverb /
 Shimmer row through the native encoder path (native cell turn -> CF -> D4 -> model; the native setup reads every
 value back) and checks the picture as specified in fxv_ui.c. The rings are recorded at the shared curve helper
 (pg_curve: one call per half ellipse), the tail as the native fills in the Reverb area."""
 DELAY=dict(feedback=0xe7,filter=0xd1,cutoff=0xcf,width=0xf3,pingpong=0xec,sync=0xeb,time=0xe9)
 REVERB=dict(mode=0x1b6,style=0x1a1,rtime=0x1a9,level=0x1aa,hicut=0x1a6,lowcut=0x1a5,predelay=0x18c,freeze=0x19a,shift=0x1ad,sfeedback=0x1ac)
 def view(self):f=FxView([0]*8,ntype=1,section=1);f.tick();f.tick();return f
 def turn(self,f,key,value):
  """Native cell turn: 160 units per value step on 0..1000 controls and ms; whole numbers (Shift), choices and
  switches move one 12800-unit detent per step (not on smaller turns), repeated until the value is reached."""
  for row in range(1,4):
   b=f.bar(row) if row<f.r(f.v+SG+0x204) else 0
   if not b:continue
   for c in range(8):
    cell=b+0x38+c*0x468
    if struct.unpack('<H',f.u.mem_read(cell+0x9c,2))[0]==key:
     detent=f.u.mem_read(0x20020000+key*32+2,1)[0] in (2,6,7) # the cell's registry descriptor type (fixture registry)
     for _ in range(64):
      cur=struct.unpack('<i',f.u.mem_read(cell+0xa0,4))[0]
      if cur==value:break
      f.call(TURN,cell,((12800 if value>cur else -12800) if detent else (value-cur)*160)&0xffffffff)
      if not detent:break
     f.report();f.tick();f.tick();return
  raise AssertionError('no cell for key %x'%key)
 def paint(self,f,**v):
  for k,x in v.items():self.turn(f,{**self.DELAY,**self.REVERB}[k],x)
  curves=[]
  def curve(u,a,n,d):
   x,cnt,step=[u.reg_read(r) for r in (UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)];sp=u.reg_read(UC_ARM_REG_SP)
   ys_at,colour=struct.unpack('<2I',u.mem_read(sp,8));ys=struct.unpack('<%dh'%cnt,u.mem_read(ys_at,2*cnt))
   if x<640:curves.append((struct.unpack('<i',struct.pack('<I',x))[0],step,ys,colour))
  h=f.u.hook_add(UC_HOOK_CODE,curve,begin=UU['pg_curve']&~1,end=UU['pg_curve']&~1)
  try:f.picture()
  finally:f.u.hook_del(h)
  rings=[(curves[i],curves[i+1]) for i in range(0,len(curves),2)] # upper, lower half per ring
  tail=[(x,t,w,hh,c) for x,t,w,hh,c in f.allfills if 660<=x<1260 and 100<=t<340]
  ticks=[(x,t,w,hh,c) for x,t,w,hh,c in f.allfills if x<640 and w==1 and hh==5]
  return dict(rings=rings,tail=tail,ticks=ticks)
 @staticmethod
 def radius(ring):up,dn=ring;return len(up[2])  # half-width / 2 px steps
 @staticmethod
 def centre(ring):up,dn=ring;return up[0]+len(up[2])  # x of the centre (x0 + n*step/2 with step 2)
 @staticmethod
 def alpha(ring):return ring[0][3]>>4
 # ---- Delay
 def test_feedback_sets_how_many_rings_and_how_slowly_they_fade(self):
  f=self.view();low=self.paint(f,feedback=100)['rings'];high=self.paint(f,feedback=900)['rings']
  self.assertGreater(len(high),len(low));self.assertLessEqual(len(low),3)
  self.assertGreater(self.alpha(high[2]),self.alpha(low[min(2,len(low)-1)]))
 def test_time_sets_the_ring_spacing(self):
  f=self.view();short=self.paint(f,feedback=900,sync=0,time=0)['rings'];long=self.paint(f,time=1000)['rings']
  self.assertGreater(self.radius(long[1])-self.radius(long[0]),self.radius(short[1])-self.radius(short[0])+10)
 def test_ping_pong_alternates_the_rings_left_and_right(self):
  f=self.view();on=self.paint(f,pingpong=1,feedback=800)['rings'];off=self.paint(f,pingpong=0)['rings']
  self.assertEqual(len({self.centre(r) for r in off}),1)
  c=[self.centre(r) for r in on];self.assertEqual(c[1]-c[0],-12);self.assertEqual(c[2]-c[0],12)
 def test_filter_and_cutoff_darken_the_rings(self):
  f=self.view();off=self.paint(f,feedback=900,filter=0)['rings'];on=self.paint(f,filter=1,cutoff=1000)['rings'];dark=self.paint(f,cutoff=0)['rings']
  self.assertGreater(self.alpha(off[0]),self.alpha(dark[0]));self.assertGreater(self.alpha(on[0]),self.alpha(dark[0]))
  self.assertGreaterEqual(self.alpha(off[0]),self.alpha(on[0]))
 def test_width_stretches_the_rings(self):
  f=self.view();narrow=self.paint(f,width=0)['rings'];wide=self.paint(f,width=1000)['rings']
  self.assertGreater(self.radius(wide[-1]),self.radius(narrow[-1]))
 def test_beat_sync_draws_grid_ticks(self):
  f=self.view();self.assertEqual(len(self.paint(f,sync=1)['ticks']),7);self.assertEqual(len(self.paint(f,sync=0)['ticks']),0)
 # ---- Reverb
 @staticmethod
 def end(tail):return max(x+w for x,t,w,h,c in tail)
 @staticmethod
 def height(tail):return max(h for x,t,w,h,c in tail)
 def test_every_style_has_its_own_tail_shape(self):
  f=self.view();shapes={}
  for style in range(15):shapes[style]=tuple(self.paint(f,style=style)['tail'])
  self.assertEqual(len(set(shapes.values())),15)
  grain=[t for t in shapes[14] if t[2]==3 and t[3]==3];self.assertGreater(len(grain),50) # Clouds = dots
  self.assertGreater(self.end(list(shapes[11])),self.end(list(shapes[0]))+150)        # Arena far longer than Tight Amb
 def test_time_sets_the_tail_length(self):
  f=self.view();self.assertGreater(self.end(self.paint(f,style=9,rtime=1000)['tail']),self.end(self.paint(f,rtime=0)['tail'])+100)
 def test_level_sets_height_and_brightness(self):
  f=self.view();lo=self.paint(f,style=9,level=0)['tail'];hi=self.paint(f,level=1000)['tail']
  self.assertGreater(self.height(hi),self.height(lo));self.assertGreater(max(c>>4 for *_,c in hi),max(c>>4 for *_,c in lo))
 def test_hi_cut_darkens_the_end_of_the_tail(self):
  f=self.view();bright=self.paint(f,style=11,rtime=1000,hicut=1000)['tail'];dark=self.paint(f,hicut=0)['tail']
  e=lambda t:sum(c>>4 for x,tt,w,h,c in t if w==1) # darker towards the end: the whole tail sums dimmer
  self.assertGreater(e(bright),e(dark))
 def test_low_cut_thins_the_end_of_the_tail(self):
  f=self.view();full=self.paint(f,style=11,rtime=1000,lowcut=0)['tail'];thin=self.paint(f,lowcut=1000)['tail']
  e=lambda t:sum(h for x,tt,w,h,c in t if x>self.end(t)-150 and w==1)
  self.assertGreater(e(full),e(thin))
 def test_pre_delay_moves_the_first_reflection(self):
  f=self.view();first=lambda t:min(x for x,tt,w,h,c in t)
  self.assertGreater(first(self.paint(f,predelay=1000)['tail']),first(self.paint(f,predelay=0)['tail'])+50)
 def test_freeze_runs_to_the_edge_with_an_end_mark(self):
  f=self.view();off=self.paint(f,style=0,freeze=0)['tail'];on=self.paint(f,freeze=1)['tail']
  self.assertIn(0xf2,[c for x,t,w,h,c in on if x==680+570-8 and w==2]);self.assertNotIn(0xf2,[c for *_,c in off])
  self.assertGreater(self.end([t for t in on if t[2]==1]),self.end(off)+300)
 def test_shimmer_mode_rises_sparks_shift_sets_height_feedback_sets_count(self):
  room=self.paint(self.view(),mode=0)['tail']
  self.assertEqual([t for t in room if t[3]==5 and t[2]==1],[])
  f=FxView([0]*8,ntype=1,section=1,vals={0x1b6:1});f.tick();f.tick() # Shimmer: the native page builds the fourth (Shimmer) section
  self.assertEqual(f.r(f.v+SG+0x204),4)
  sparks=lambda t:[x for x in t if x[2]==1 and x[3]==5]
  few=sparks(self.paint(f,sfeedback=0)['tail']);many=sparks(self.paint(f,sfeedback=1000)['tail'])
  self.assertGreater(len(many),len(few)+20)
  low=sparks(self.paint(f,shift=-24)['tail']);high=sparks(self.paint(f,shift=24)['tail']) # Shift -24..+24 semitones
  self.assertLess(min(t for x,t,w,h,c in high),min(t for x,t,w,h,c in low)-20)
 def test_balanced_brightness_the_tail_is_dimmer_than_the_rings(self):
  p=self.paint(self.view(),feedback=600,level=450,filter=0) # the brightest ring: filter off
  self.assertLessEqual(max(c>>4 for x,t,w,h,c in p['tail'] if w==1),10);self.assertEqual(self.alpha(p['rings'][0]),15)
 def test_a_send_fx_value_change_requests_a_repaint(self):
  f=self.view();self.paint(f)
  f.u.mem_write(0x24078100,struct.pack('<II',0,0x24078000));f.call(UU['fxv_tick'],f.v,0x24078100);self.assertEqual(f.u.mem_read(0x24078101,1)[0],0)
  b=f.bar(2);cell=b+0x38+1*0x468;f.call(TURN,cell,12800);f.report() # Style one detent on, no tick yet
  f.u.mem_write(0x24078100,struct.pack('<II',0,0x24078000));f.call(UU['fxv_tick'],f.v,0x24078100)
  self.assertEqual(f.u.mem_read(0x24078101,1)[0],1)


class FxViews161(unittest.TestCase):
 @unittest.skipUnless(N.BENTO_FW==161,'1.6.1 build')
 def test_1_6_1_has_no_fx_views_symbols(self):
  for n in ('fxv_tick','fxv_paint','fxv_toolbar','fxv_go','fxv_up','fxv_arrows'):
   self.assertNotIn(n,UU,n)


if __name__=='__main__':unittest.main()
