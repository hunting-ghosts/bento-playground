"""Performance page: direct PROJ navigation (M4), the page rows and
values, tap tempo, per-track fixed velocity, and the M7 pad-press hook.

Runs the built image. Native model calls (getter 08133614, current track
08133CFC, navigation 081420EC, button event 08142AFC, model event 081403EC)
are fixtures; the M7 test runs the real native pad press from the patched call
site 080857D6."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct,unittest,gc,json
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_integration import Fixture,UU,AA,IMAGE,CANDIDATE
M=0x30024b00;PROJECT=0x30030164;PROJ_HANDLE=0x77;SETTINGS=0x55;OUT=0x20034000;EV=0x20035000
LOCK=0x24048d60;MASK=0x24048d70;EC=0x24041fc0
KEEP=[]
class Page(Fixture):
 def __init__(self):
  super().__init__();KEEP.append(self);self.registry()
  self.w(0x3000004c,self.next);self.w(0x30000048,0xc0000000+N.SDRAM_MAP);self.w(PROJECT,PROJ_HANDLE)
  self.proj={0x8c:120,0x8d:0,0x8e:3,0x8f:50,0x131:0};self.track=0x91;self.octave=0;self.navs=[];self.buttons=[];self.model_events=[];self.page(0x17);self.ttype=18
  self.u.hook_add(UC_HOOK_CODE,self.native)
 def page(self,n):self.u.mem_write(M+0x12c,bytes([n]))
 def native(self,u,a,n,d):
  r=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  if a==0x08104c08:
   # The native checked bump allocator publishes its advanced cursor.
   self.w(0x3000004c,self.next)
  elif a==0x08133614:
   # P7: 131 (track index) lives on the selection context 30030164; BPM, Scale,
   # Root and Swing on the project settings node (08133E54), handle SETTINGS.
   if r[2]==N.NKEY(0x178) and self.r(r[1])==self.track:self.w(r[3],self.octave);self.ret(1)
   elif r[1]==PROJECT and r[2]==0x131:self.w(r[3],self.proj[0x131]);self.ret(1)
   elif self.r(r[1])==SETTINGS and r[2] in (0x8c,0x8d,0x8e,0x8f):self.w(r[3],self.proj[r[2]]);self.ret(1)
   else:self.ret(0)
  elif a==0x08133cfc:self.w(r[1],self.track);self.ret(1)
  elif a==0x081420ec:self.navs.append(r[1]);self.page(r[1]);self.ret()
  elif a==0x08142afc:self.buttons.append(struct.unpack('<3I',u.mem_read(r[1],12)));self.ret()
  elif a==0x081403ec:
   e=struct.unpack('<4I',u.mem_read(r[1],16));self.model_events.append(e)
   if e[0]==0xcf and e[1]==SETTINGS:self.proj[e[2]]=e[3]
   if e[0]==0xcf and e[1]==self.track and e[2]==N.NKEY(0x178):self.octave=struct.unpack('<i',struct.pack('<I',e[3]))[0]
   self.ret(0)
  elif a in (0x08145cf4,0x08139138):self.ret()
  elif a==0x08133f7c:self.ret(self.ttype if self.r(r[1])==self.track else getattr(self,'types',{}).get(self.r(r[1]),0))
  elif a==0x08133e54:self.w(r[1],SETTINGS);self.ret(1)
 def button(self,code,index):return self.call(UU['fx_dispatch'],M,code,0,index)
 def open(self):
  self.button(0xaf,7);self.button(0xb0,7)
 def header(self):
  self.u.mem_write(OUT,bytes(0x54));return self.call(UU['fx_header'],M,0,OUT,0,0x08145f22)
 def keys(self,rows=2):return [list(struct.unpack('<8H',self.u.mem_read(OUT+0x14+16*row,16))) for row in range(rows)]
 def mail(self):
  b=self.r(EC+4)
  if not b:return None
  m=b+44576;serial,active=self.r(m),self.r(m+4);count=list(self.u.mem_read(m+16,12))
  off=[list(struct.unpack('<6b',self.u.mem_read(m+32+pc*6,6)))[:count[pc]] for pc in range(12)]
  return active,off,self.r(m+8)
 def get(self,key,handle=0x20036000):self.w(0x20036100,0xdead);self.call(UU['fx_get'],M,handle,key,0x20036100);return self.r(0x20036100)
 def edit(self,key,value):self.u.mem_write(EV,struct.pack('<4I',0xcf,self.track,key,value));return self.call(UU['fx_event'],OUT-0x93c4,EV)
 def fixed(self):return self.r(EC+20)
class Tests(unittest.TestCase):
 def test_proj_opens_the_page_and_clears_modifier_state(self):
  p=Page();p.w(LOCK+8,1);p.open()
  self.assertEqual(p.navs,[0x1a]);self.assertEqual(p.buttons,[])
  self.assertEqual(p.r(MASK),0);self.assertEqual(p.r(LOCK+8),0)
 def test_single_proj_cycles_perform_macro_settings_projects(self):
  # P168 exp5 (owner, 12 Nov): Perform -> Macro -> Settings -> Projects -> Perform (was Perform <-> Macro).
  p=Page()
  for tick,rows,page in [(1000,3,0x1a),(2000,1,0x1a),(3000,3,0x1a),(4000,None,0x13),(5000,3,0x1a),(6000,1,0x1a)]:
   p.w(0x3001fe2c,tick);p.open();self.assertEqual(p.navs[-1],page)
   if rows is not None:p.header();self.assertEqual(p.u.mem_read(OUT,1)[0],rows)
  self.assertEqual(p.navs,[0x1a,0x1a,0x1a,0x13,0x1a,0x1a])
 def test_double_proj_opens_projects_and_long_hold_does_not(self):
  p=Page();p.open();p.open();self.assertEqual(p.navs,[0x1a,0x13])
  q=Page();q.button(0xaf,7);q.w(0x3001fe2c,q.r(0x3001fe2c)+500);q.button(0xb0,7)
  q.button(0xaf,7);self.assertEqual(q.navs,[0x1a,0x1a]);q.header();self.assertEqual(q.u.mem_read(OUT,1)[0],1)
 def test_double_proj_survives_first_tap_navigation_from_every_project_view(self):
  for view in (None,0x1071,0x1072,0x1074,0x1075):
   with self.subTest(view=view):
    p=Page()
    if view is not None:
     p.open();p.u.mem_write(EV,struct.pack('<5I',view,0,0,0,0));p.call(UU['perf_navigation'],EV)
    p.w(0x3001fe2c,1000);p.button(0xaf,7)
    self.assertEqual(p.u.mem_read(M+0x12c,1)[0],0x13 if view==0x1074 else 0x1a) # exp5 cycle: Settings -> Projects
    p.w(0x3001fe2c,1050);p.button(0xb0,7)
    p.w(0x3001fe2c,1200);p.open();self.assertEqual(p.navs[-1],0x13)
    p.w(0x3001fe2c,2200);p.open();p.header()
    self.assertEqual(p.navs[-1],0x1a);self.assertEqual(p.u.mem_read(OUT,1)[0],3)
 def test_repeat_and_chorded_proj_do_not_create_double_taps(self):
  for code,index in [(0xaf,15),(0xac,0),(0xab,0),(0xfe,0)]:
   with self.subTest(code=code):
    p=Page();p.w(0x3001fe2c,1000);p.button(0xaf,7)
    p.button(0xaf,7);self.assertEqual(p.navs,[0x1a])
    p.button(code,index);p.button(0xb0,7)
    p.w(0x3001fe2c,1200);p.open();p.header()
    self.assertEqual(p.navs,[0x1a,0x1a]);self.assertEqual(p.u.mem_read(OUT,1)[0],1)
 def test_left_is_native_without_shift_undo(self):
  p=Page();p.open();self.assertEqual(p.button(0xaf,0),0);self.assertEqual(p.button(0xb0,0),0)
  self.assertEqual(p.model_events,[])
 def burger(self,p):
  p.call(0x081412ec);t=IMAGE[0x8199008+20*N.HDR_SIZE-0x8040000:][:N.HDR_SIZE];p.page(0x1a);p.u.mem_write(OUT,t);p.call(UU['device_header_prepare'],OUT)
  for m in range(20):
   d=0x30030168+m*0xe0
   if p.r(d)==0xf9:return struct.unpack('<H',p.u.mem_read(OUT+N.HDR(0x194),2))[0],[(p.r(d+4+i*20),p.text(p.r(d+8+i*20))) for i in range(p.u.mem_read(d+0xcc,1)[0])]
 def test_piano_burger_is_the_sequencer_burger_even_without_a_header_apply(self):
  # R5 (owner: the piano-roll burger showed Projects/Settings/SD-card mode).
  # F9 is shared with the Performance page; the per-message tick restores it.
  p=Page();p.open();self.burger(p) # leaves F9 with the Performance cells
  p.page(0x17);p.call(UU['seq_nav_menus_tick'])
  stock=[(N.NUI(0x1041),'Double Seq'),(N.NUI(0x1042),'Halve Seq'),(N.NUI(0x102f),'Cut Seq'),(N.NUI(0x102e),'Copy Seq'),(N.NUI(0x1030),'Paste Seq'),(0x1086,'Clear'),(N.NUI(0x102d),'Clear Auto'),(0x1065,'Select All'),(N.NUI(0x1032),'Undo')]
  for m in range(20):
   d=0x30030168+m*0xe0
   if p.r(d)==0xf9:self.assertEqual([(p.r(d+4+i*20),p.text(p.r(d+8+i*20))) for i in range(p.u.mem_read(d+0xcc,1)[0])],stock)
  p.page(0x1a);p.call(UU['seq_nav_menus_tick']);self.assertEqual(self.burger(p)[1][:3],[(0x1062,'Projects'),(0x1063,'Settings'),(N.NUI(0x101d),'SD-card mode')])
 def test_up_keeps_octave_control_without_shift_disk_mode(self):
  p=Page();p.open();self.assertEqual(p.button(0xaf,1),1);self.assertEqual(p.button(0xb0,1),1)
  self.assertEqual(p.model_events,[(0xcf,p.track,N.NKEY(0x178),1)])
 def test_performance_burger_holds_sd_mode_and_tabs_navigate(self):
  p=Page();popup,menu=self.burger(p);self.assertEqual(popup,0)
  p=Page();p.open();popup,menu=self.burger(p);self.assertEqual(popup,0xf9)
  expected=[(0x1062,'Projects'),(0x1063,'Settings'),(N.NUI(0x101d),'SD-card mode')]
  diagnostic=CANDIDATE/'DIAGNOSTIC_MANIFEST.json'
  if diagnostic.exists() and json.loads(diagnostic.read_text()).get('matched_candidate'):
   expected.append((0x107e,'Diagnostics'))
  self.assertEqual(menu,expected)
  for code,page in [(0x1075,0x13),(0x1074,0x1a),(0x1072,0x1a)]:
   q=Page();q.open();q.header();n=len(q.navs);q.u.mem_write(EV,struct.pack('<5I',code,0,0,0,0));self.assertEqual(q.call(UU['fx_event'],OUT-0x93c4,EV),1);self.assertEqual(q.navs[n:][-1],page)
  q=Page();q.open();q.header();n=len(q.navs);q.u.mem_write(EV,struct.pack('<5I',0x1071,0,0,0,0));self.assertEqual(q.call(UU['fx_event'],OUT-0x93c4,EV),1);self.assertEqual(q.navs[n:],[])
 def test_tracks_hold_paints_the_track_colours_inside_every_native_flush(self):
  # P168 exp3 (owner on exp2: TRACKS hold first showed the instrument pads of the selected track).
  # Oracle: what reaches the native pad-light flush (081257F0, entered at its body 081257F8).
  # The native page change rewrites the pad colours and the native loop flushes on every pass;
  # whatever it wrote, a flush during the hold must send the track colours.
  p=Page();pads=M+N.MODEL_PADS;objs={0:0x20010100,1:0x20010200,2:0x20010300};base=p.selected
  def selected(self):
   r0,r1=self.u.reg_read(UC_ARM_REG_R0),self.u.reg_read(UC_ARM_REG_R1)
   return [k for k,v in objs.items() if v==r0][0] if r1==0x73 and r0 in objs.values() else base
  p.__class__=type('TrackPage',(Page,),{'selected':property(selected)});p.__dict__.pop('selected',None)
  root=0x20010000;p.w(M,root);p.w(root+0x54,3)
  for k,v in objs.items():p.w(root+0x34+4*k,v)
  sent=[]
  def body(u,a,n,d): # native flush body: record the pads, then return as its epilogue would
   sp=u.reg_read(UC_ARM_REG_SP);sent.append([p.r(pads+i*16) for i in range(16)]);saved=struct.unpack('<9I',u.mem_read(sp+44,36))
   for reg,v in zip((UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11),saved):u.reg_write(reg,v)
   u.reg_write(UC_ARM_REG_SP,sp+80);u.reg_write(UC_ARM_REG_PC,saved[8]|1)
  p.u.hook_add(UC_HOOK_CODE,body,begin=0x081257f8,end=0x081257f8)
  p.button(0xaf,2);p.page(2)
  col=lambda i:p.call(0x08140f50,i);off=p.call(0x08140fbc,0);want=[col(0),col(1),col(2)]+[off]*5+[col(0),col(1),col(2)]+[off]*5
  for i in range(16):p.w(pads+i*16,0x00123456) # the page change repainted the pads for its own page
  p.call(UU['play_mute_flush'],pads);self.assertEqual(sent[-1],want)
  p.button(0xb0,2);n=len(sent)
  for i in range(16):p.w(pads+i*16,0x00123456)
  p.call(UU['play_mute_flush'],pads);self.assertEqual(sent[-1],[0x00123456]*16);self.assertEqual(len(sent),n+1) # released: native colours pass
 def test_exp3_mixer_hold_keeps_the_native_mixer_pad_mode_at_every_flush(self):
  # P168 exp3 (owner: while MIXER is held the pads fall back to the instrument's pads within a split second).
  # The hold sets the native pad mode once at the press. Oracle: the native pad mode function 0813BC24 itself
  # (it writes the mode byte and calls the native pad rebuild 08139138): after anything set the mode back, the
  # next flush during the hold must have run it again with "on", before the pads reach the native flush body.
  p=Page();pads=M+N.MODEL_PADS;order=[]
  def rebuild(u,a,n,d):order.append(('rebuild',p.u.mem_read(M+N.MODEL_PADMODE,1)[0]));p.ret()
  def body(u,a,n,d):
   sp=u.reg_read(UC_ARM_REG_SP);order.append(('flush',p.u.mem_read(M+N.MODEL_PADMODE,1)[0]));saved=struct.unpack('<9I',u.mem_read(sp+44,36))
   for reg,v in zip((UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11),saved):u.reg_write(reg,v)
   u.reg_write(UC_ARM_REG_SP,sp+80);u.reg_write(UC_ARM_REG_PC,saved[8]|1)
  p.u.hook_add(UC_HOOK_CODE,rebuild,begin=0x08139138,end=0x08139138);p.u.hook_add(UC_HOOK_CODE,body,begin=0x081257f8,end=0x081257f8)
  p.w(0x24048cc0,0x354d5442);p.w(0x24048cc0+4,5);p.w(0x24048d40,1) # hold controls: MIXER down, their pad lights active
  ev=0x20010400;p.u.mem_write(ev,struct.pack('<5I',0,0,0,0,0));p.call(0x0813bc24,M,ev);order.clear() # the mode was set back (native function, "off")
  self.assertEqual(p.u.mem_read(M+N.MODEL_PADMODE,1)[0],0)
  p.call(UU['play_mute_flush'],pads);self.assertEqual(order,[('rebuild',1),('flush',1)])
  order.clear();p.call(UU['play_mute_flush'],pads);self.assertEqual(order,[('flush',1)]) # nothing to repair: no rebuild
  p.w(0x24048d40,0);p.call(0x0813bc24,M,ev);order.clear() # hold lights over: the mode is not ours any more
  p.call(UU['play_mute_flush'],pads);self.assertEqual(order,[('flush',0)])
 def test_pad_led_colours_of_tracks_1_and_2_are_the_recorded_calibration(self):
  # P168 exp3 (owner on exp2, hardware: track 1 too cyan, track 2 not violet enough on the pads).
  # The pad colour functions the native pad painters call (bright 08140EF0, dim 08140F50) must
  # return the values recorded in tools/playground_palette.py; the screen colours are not touched.
  # Software check of the numbers only: how the LEDs look is judged by the owner on the device.
  p=Page();split=lambda v:((v>>16)&255,(v>>8)&255,v&255)
  bright=[split(p.call(0x08140ef0,i)) for i in range(8)];dim=[split(p.call(0x08140f50,i)) for i in range(8)]
  self.assertEqual(bright[:2],[(0x12,0x34,0xd0),(0x44,0x18,0xd0)]) # recorded choice, exp4 (exp3 had 00 14 D8 and 48 00 E8, exp2 00 38 E0 and 2A 18 F0)
  self.assertEqual(dim,[tuple(round(x*100/255) for x in c) for c in bright]) # dim = 100/255 of bright, as before
  # run 5 (owner: all tracks evenly bright): tracks 3, 6, 7, 8 scaled down to the drive level of tracks 4 and 5
  # (rule and reason in tools/playground_palette.py); hue kept (channel ratios), 4 and 5 unchanged.
  self.assertEqual(bright[2:],[(0xaa,0x44,0xc0),(0xff,0x54,0x67),(0xff,0x7c,0x12),(0xc7,0xab,0x1d),(0x51,0xcb,0x6a),(0x0c,0xc2,0xba)])
  drive=lambda c:c[0]+1.3*c[1]+c[2];self.assertLess(max(drive(c) for c in bright)/drive(bright[4]),1.08) # no track far above the level of track 5
  self.assertEqual((p.call(0x08140ef0,8),p.call(0x08140f50,8)),(0xffffff,0x64ffff)) # stock defaults beyond the eight tracks
  t1,t2=bright[0],bright[1]
  # exp4 (owner on exp3): track 1 a little more cyan than 00 14 D8, track 2 darker and bluer than 48 00 E8 but still
  # clearly violet, both with a trace of every LED (the pastel feel of tracks 3-8)
  hue=lambda c:__import__('colorsys').rgb_to_hsv(*[x/255 for x in c])[0]*360
  self.assertTrue(all(t1)and all(t2))
  self.assertGreater(t1[1],0x14);self.assertLess(t1[1],0x7c);self.assertGreater(t1[2],0xc0)   # track 1: blue, a little green
  self.assertGreater(t2[0],t2[1]);self.assertLess(t2[2],0xe8);self.assertLess(hue(t2),hue((0x48,0,0xe8))) # track 2: violet, bluer, darker
  self.assertGreater(hue(t2)-hue(t1),20)                                                        # clearly apart
  # Screen colours of tracks 1 and 2 (CLUT 7 and 8 in the UI data image) are not part of this change.
  import struct as _st;i=IMAGE.find(_st.pack('<2I',0xff699fd8,0xffab9bf0));self.assertGreaterEqual(i,0)
 def test_holding_tracks_shows_track_colours_on_the_pads_and_restores_them(self):
  # P20 (owner): while TRACKS is held, each track's pads show its colour.
  p=Page();pads=M+N.MODEL_PADS;objs={0:0x20010100,1:0x20010200,2:0x20010300}
  # The fixture answers 0812DC74 with .selected; answer property 73 (track number) for our tracks.
  base=p.selected
  def selected(self):
   r0,r1=self.u.reg_read(UC_ARM_REG_R0),self.u.reg_read(UC_ARM_REG_R1)
   return [k for k,v in objs.items() if v==r0][0] if r1==0x73 and r0 in objs.values() else base
  p.__class__=type('TrackPage',(Page,),{'selected':property(selected)});p.__dict__.pop('selected',None)
  flushes=[]
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(flushes.append(1),p.ret()),begin=0x081257f0,end=0x081257f0)
  root=0x20010000;p.w(M,root);p.w(root+0x54,3) # native 0812D78A: count +54, tracks +34
  for k,v in objs.items():p.w(root+0x34+4*k,v)
  before=bytes(p.u.mem_read(pads,256));p.button(0xaf,2);p.page(2) # K16 opens the Tracks page
  col=lambda i:p.call(0x08140f50,i);off=p.call(0x08140fbc,0)
  got=[p.r(pads+i*16) for i in range(16)]
  self.assertEqual(got,[col(0),col(1),col(2)]+[off]*5+[col(0),col(1),col(2)]+[off]*5);self.assertEqual(len(flushes),1)
  p.button(0x8f,99);self.assertEqual(len(flushes),1) # unchanged: no extra flush
  p.button(0xb0,2);self.assertEqual(bytes(p.u.mem_read(pads,256)),before);self.assertEqual(len(flushes),2)
  # P22 (owner): pressing TRACKS on another page jumps to the Tracks page (2); colours still show.
  p.page(0x17);p.button(0xaf,2);p.page(2);p.u.mem_write(pads,bytes(256));p.button(0x8f,99)
  self.assertEqual([p.r(pads+i*16) for i in range(3)],[col(0),col(1),col(2)]);p.button(0xb0,2);p.page(2)
  # P21 (owner): picking a track during the hold leaves the new page's pads alone.
  p.button(0xaf,2);n=len(flushes);p.page(0x07);p.u.mem_write(pads,b'\x11'*256);p.button(0x8f,99)
  self.assertEqual(bytes(p.u.mem_read(pads,256)),b'\x11'*256)
  p.button(0xb0,2);self.assertEqual(bytes(p.u.mem_read(pads,256)),b'\x11'*256)
 def test_plain_play_stays_native(self):
  p=Page();self.assertEqual(p.button(0xaf,15),0);self.assertEqual(p.navs,[])
 def test_page_rows(self):
  p=Page();self.assertEqual(p.header(),0) # not open
  p.open();self.assertEqual(p.header(),1);self.assertEqual(p.u.mem_read(OUT,1)[0],3)
  self.assertEqual(p.keys(1),[[0]*8])
  p.u.mem_write(EV,struct.pack('<5I',0x1069,0,0,0,0));self.assertEqual(p.call(UU['perf_navigation'],EV),0);p.header()
  self.assertEqual(p.keys(3),[[0]*8,[0x104,0x132,N.NKEY(0x14a),N.NKEY(0x144),0,0x11c,0x102,0],[0xa6,0xa7,0xaa,0xb2,0xb3,0xb6,0x8f,0x8c]])  # R6.14: Ratchet amount beside the arp; run 18 (native_perform.png): Velocity/Fixed Vel in the Chord row, Swing/BPM end the Arp row
  self.assertEqual(p.text(p.r(OUT+12)),'Arp / Track 1')
  p.proj[0x131]=3;p.header();self.assertEqual(p.text(p.r(OUT+12)),'Arp / Track 4')
  r=p.r(0x30031484)
  for k,name in [(0x101,'Tap Tempo'),(0x102,'Fixed Vel'),(0x11c,'Velocity')]:self.assertEqual(p.text(p.r(r+k*32+4)),name)
  self.assertEqual(p.text(p.r(r+0x8c*32+4)),'BPM') # native descriptors untouched
 def test_tempo_and_key_are_the_project_values(self):
  p=Page();p.open();p.header()
  self.assertEqual([p.get(k) for k in (0x8c,0x8d,0x8e,0x8f)],[120,0,3,50])
  p.edit(0x8c,98);self.assertEqual(p.model_events[-1],(0xcf,SETTINGS,0x8c,98));self.assertEqual(p.get(0x8c),98)
  p.edit(0x8f,62);self.assertEqual(p.proj[0x8f],62);p.edit(0x8e,5);self.assertEqual(p.proj[0x8e],5)
 def test_closed_page_leaves_native_keys_alone(self):
  p=Page();self.assertEqual(p.get(0x8c),0xdead)
  p.open();p.header();p.call(UU['fx_nav'],M,0x27);self.assertEqual(p.get(0x8c),0xdead) # any other navigation closes it
 def test_tap_tempo(self):
  p=Page();p.open();p.header()
  for t in [1000,1500,2000,2500]:p.w(0x3001fe2c,t);p.edit(0x101,1)
  self.assertEqual(p.proj[0x8c],120)
  p.w(0x3001fe2c,2900);p.edit(0x101,1);self.assertEqual(p.proj[0x8c],126) # avg of 500,500,500,400
  p.w(0x3001fe2c,9000);n=len(p.model_events);p.edit(0x101,1);self.assertEqual(len(p.model_events),n) # long pause starts over
  p.w(0x3001fe2c,9250);p.edit(0x101,1);self.assertEqual(p.proj[0x8c],240)
  self.assertEqual(p.get(0x101),0)
 def test_fixed_velocity_is_per_track(self):
  p=Page();p.open();p.header()
  self.assertEqual((p.get(0x102),p.get(0x11c)),(0,100));self.assertEqual(p.fixed(),0)
  p.edit(0x11c,90);p.edit(0x102,1);self.assertEqual(p.fixed(),0x56454c00|90)
  p.track=0x92;p.button(0xfe,3);self.assertEqual(p.fixed(),0);self.assertEqual((p.get(0x102),p.get(0x11c)),(0,100))
  p.edit(0x11c,300);self.assertEqual(p.get(0x11c),127)
  p.track=0x91;p.button(0xfe,3);self.assertEqual(p.fixed(),0x56454c00|90)
  p.edit(0x102,0);self.assertEqual(p.fixed(),0)
 def test_fixed_velocity_saved_with_the_track(self):
  p=Page();p.open();p.header();p.edit(0x11c,64);p.edit(0x102,1);obj=0x20031200;p.w(obj+0x10,0x91);p.u.mem_write(obj+4,b'\x12')
  p.call(UU['fx_save'],obj,0x20017000);self.assertEqual(p.attrs['bento_perf_velocity'],0x100|64)
  p.edit(0x102,0);p.edit(0x11c,100);p.attrs.clear();p.call(UU['fx_save'],obj,0x20017000);self.assertNotIn('bento_perf_velocity',p.attrs)
  p.attrs['bento_perf_velocity']=0x100|33;p.call(UU['fx_load'],0x20017100,obj);self.assertEqual((p.get(0x102),p.get(0x11c)),(1,33))
  del p.attrs['bento_perf_velocity'];p.call(UU['fx_load'],0x20017100,obj);self.assertEqual((p.get(0x102),p.get(0x11c)),(0,100))
 def test_fixed_velocity_loads_before_the_page_was_ever_opened(self):
  p=Page();obj=0x20031200;p.w(obj+0x10,0x91);p.u.mem_write(obj+4,b'\x12');p.attrs['bento_perf_velocity']=0x100|20
  p.call(UU['fx_load'],0x20017100,obj);p.button(0xfe,3);self.assertEqual(p.fixed(),0x56454c00|20)
class Ratchet(unittest.TestCase):
 """R6.14 per-track Ratchet amount (key B6) beside the arp, saved with the track,
 published into the RtBlock config, reachable as a macro target."""
 BLOCK=0xc01f0000
 def page(self):
  p=Page();p.open();p.header();p.u.mem_write(self.BLOCK,bytes(2048));p.w(self.BLOCK,0x31425452);p.w(0x24041fdc,self.BLOCK)
  # Native track-by-index (08133960): two tracks 0x91, 0x92.
  def tracks(u,a,n,d):
   i=u.reg_read(UC_ARM_REG_R1);out=u.reg_read(UC_ARM_REG_R2)
   if i<2:p.w(out,0x91+i);p.ret(1)
   else:p.ret(0)
  p.u.hook_add(UC_HOOK_CODE,tracks,begin=0x08133960,end=0x08133960);return p
 def cfg(self,p):
  raw=bytes(p.u.mem_read(self.BLOCK,64));return list(struct.unpack_from('<8I',raw,8)),list(raw[40:48])
 def amount(self,p,track):
  owner,amount=self.cfg(p);return amount[owner.index(track)] if track in owner else None
 def test_row_slot_and_default(self):
  p=self.page();self.assertEqual(p.keys(3)[2][5],0xb6);self.assertEqual(p.get(0xb6),100)
 def test_edit_is_per_track_clamped_and_published(self):
  p=self.page();p.edit(0xb6,40);self.assertEqual(p.get(0xb6),40);self.assertEqual(self.amount(p,0x91),40)
  p.track=0x92;p.button(0xfe,3);self.assertEqual(p.get(0xb6),100)
  p.edit(0xb6,250);self.assertEqual(p.get(0xb6),100);p.edit(0xb6,0xffffffff);self.assertEqual(p.get(0xb6),0);self.assertEqual(self.amount(p,0x92),0)
  p.track=0x91;p.button(0xfe,3);self.assertEqual(p.get(0xb6),40)
 def test_periodic_republishes_after_the_block_was_cleared(self):
  p=self.page();p.edit(0xb6,25);p.u.mem_write(self.BLOCK+8,bytes(56))
  p.call(UU['perf_tick']);self.assertEqual(self.amount(p,0x91),25)
 def test_saved_with_the_track_only_when_not_100(self):
  p=self.page();obj=0x20031200;p.w(obj+0x10,0x91);p.u.mem_write(obj+4,b'\x12')
  p.call(UU['fx_save'],obj,0x20017000);self.assertNotIn('bento_perf_ratchet',p.attrs)
  p.edit(0xb6,30);p.attrs.clear();p.call(UU['fx_save'],obj,0x20017000);self.assertEqual(p.attrs['bento_perf_ratchet'],1<<28|30)
  p.edit(0xb6,0);p.attrs.clear();p.call(UU['fx_save'],obj,0x20017000);self.assertEqual(p.attrs['bento_perf_ratchet'],1<<28|0)
  p.attrs['bento_perf_ratchet']=1<<28|65;p.call(UU['fx_load'],0x20017100,obj);self.assertEqual(p.get(0xb6),65)
  del p.attrs['bento_perf_ratchet'];p.call(UU['fx_load'],0x20017100,obj);self.assertEqual(p.get(0xb6),100)
  p.attrs['bento_perf_ratchet']=2<<28|65;p.call(UU['fx_load'],0x20017100,obj);self.assertEqual(p.get(0xb6),100) # unknown version ignored
  p.attrs['bento_perf_ratchet']=1<<28|101;p.call(UU['fx_load'],0x20017100,obj);self.assertEqual(p.get(0xb6),100)
 def test_load_before_the_page_was_opened(self):
  p=Page();obj=0x20031200;p.w(obj+0x10,0x91);p.u.mem_write(obj+4,b'\x12');p.attrs['bento_perf_ratchet']=1<<28|10
  p.call(UU['fx_load'],0x20017100,obj);p.open();p.header();self.assertEqual(p.get(0xb6),10)
 def test_macro_model_event_reaches_the_named_track_on_any_page(self):
  p=self.page();p.button(0xaf,7);p.button(0xb0,7);p.page(0x27)
  for code in (0xcf,0xd0):
   p.u.mem_write(EV,struct.pack('<4I',code,0x92,0xb6,20 if code==0xcf else 70))
   self.assertEqual(p.call(UU['perf_ratchet_event'],EV),1)
   self.assertEqual(self.amount(p,0x92),20 if code==0xcf else 70)
  self.assertEqual(self.amount(p,0x91),None)
  p.u.mem_write(EV,struct.pack('<4I',0xcf,0x92,0xb3,5));self.assertEqual(p.call(UU['perf_ratchet_event'],EV),0)
  # unknown handle: the current track
  p.u.mem_write(EV,struct.pack('<4I',0xcf,0x5555,0xb6,55));p.call(UU['perf_ratchet_event'],EV);self.assertEqual(self.amount(p,0x91),55)
 def test_macro_getter_reads_the_named_track(self):
  p=self.page();p.u.mem_write(EV,struct.pack('<4I',0xcf,0x92,0xb6,33));p.call(UU['perf_ratchet_event'],EV)
  p.w(0x20036000,0x92);self.assertEqual(p.get(0xb6,0x20036000),33);p.w(0x20036000,0);self.assertEqual(p.get(0xb6,0x20036000),100)
class SourceTests(unittest.TestCase):
 """Source contracts only; these do not execute newly edited ARM code."""
 def setUp(self):
  self.source=Path(__file__).with_name('perf_ui.c').read_text()
 def section(self,start,end):
  return self.source.split(start,1)[1].split(end,1)[0]
 def test_single_proj_cycles_only_from_the_active_view(self):
  body=self.section('static void toggle(void *m){','/* Before every other')
  self.assertIn('want=s->active&&s->mview<4&&page==(s->mview==3?0x13u:0x1au)?(s->mview+1)&3u:0',body)
  self.assertIn('nav(s,m,want==3?0x13:0x1a)',body)
  self.assertIn('s->mview=want',body);self.assertIn('macro_view_set(0)',body)
 def test_double_tap_is_not_gated_by_the_page_changed_by_first_press(self):
  body=self.section('int perf_dispatch(', 'void perf_nav(')
  second=body.split('u32 second=',1)[1].split(';',1)[0]
  self.assertEqual(second,'s->proj_armed&&TICK-s->proj_up<=350u')
  self.assertIn('s->proj_pressed==1&&TICK-s->proj_down<=300u',body)
  self.assertIn('if(s->proj_pressed)return 1',body)
  self.assertIn('if(s->proj_pressed)s->proj_pressed=2',body)
  self.assertNotIn('proj_armed',self.section('void perf_nav(', 'int perf_macro_view('))
 def test_four_view_tabs_then_the_view_actions(self):
  # P168 exp6 (owner): slots 0..3 = Perform | Macro | Settings | Projects on every PROJ view, actions next to
  # them; the four tabs without the native divider while this footer is up, restored when Perform is left.
  body=self.section('int perf_toolbar(', 'static void copy(')
  self.assertIn('static const u16 tabs[4]={PERF_TAB,MACRO_TAB,SETTINGS_TAB,PROJECT_TAB}',body)
  self.assertIn('changed|=header_fixed_tab(out,i,tabs[i],names[i],s->mview==i);B(PROJ_TAB_WIDGETS,i*0xd0u)=0;',body)
  for text in ['header_fixed_action(out,4,0x8f,"Save",0)','header_fixed_action(out,5,0x8b,"Load",0)',
               'header_fixed_action(out,4,0x36,"Set Time",0)','header_fixed_action(out,5,MOTION_TOGGLE,"Motion",s->motion.enabled)']:
   self.assertIn(text,body)
  self.assertNotIn('FW_LABEL',body)  # the label is plain footer text, not a button
  # exp7 (owner, 12 Nov): Settings keeps slot 5 EMPTY (no Motion there); Motion only on Perform and Macro
  self.assertIn('empty=5',body)
  self.assertIn('return empty==5?changed:changed|header_fixed_action(out,5,MOTION_TOGGLE,"Motion",s->motion.enabled);',body)
  self.assertIn('for(u32 i=0;i<4;i++)B(PROJ_TAB_WIDGETS,i*0xd0u)=1;',self.section('void perf_nav(', 'int perf_macro_view('))
 def test_only_native_clock_child_is_hidden_outside_settings(self):
  layout=self.section('void perf_rows_layout(', 'static void descriptor(')
  self.assertIn('if(s->view&&(u32)group==s->view+0x9018u)',layout)
  self.assertIn('B((u8*)group+(0x9558u-0x9018u),0x30)=s->mview!=2',layout)
  readout=self.source.split('void perf_readout(',1)[1]
  self.assertIn('s->motion.enabled||s->motion.error',readout)
  # Run 18 (native_perform.png): the played chord's name is drawn big on the Perform page (playground_ui.c
  # perform_top), no longer copied into the footer label (the footer shows the build label there).
  self.assertNotIn('copy((char*)out,s->name,0)',readout)
  self.assertIn('perf_notes_name(s->keys_root,s->keys_notes,s->keys_name)',(Path(__file__).resolve().parent/'playground_ui.c').read_text())

class Chord(unittest.TestCase):
 def page(self):p=Page();p.open();p.header();p.w(0x3000004c,p.next);return p
 def test_row_and_names(self):
  p=self.page()
  self.assertEqual(p.text(p.r(OUT+8)),'Chord / Track 1');r=p.r(0x30031484)
  for k,name in [(0x104,'Chord'),(0x132,'Type'),(N.NKEY(0x14a),'Voicing'),(N.NKEY(0x144),'Inversion')]:self.assertEqual(p.text(p.r(r+k*32+4)),name)
  t=r+N.NKEY(0x132)*32;self.assertEqual([p.text(p.r(p.r(t+8)+4*i)) for i in (0,1,15,16)],['Major','Minor','Diatonic','Diatonic 7']);self.assertEqual(p.r(t+12),17)
  self.assertEqual([p.get(k) for k in (0x104,0x132,N.NKEY(0x14a),N.NKEY(0x144))],[0,15,0,0]) # off, Diatonic
 def test_chord_on_plays_the_shape_on_every_pad_pitch_and_off_stops(self):
  p=self.page();p.edit(0x132,0);p.edit(0x104,1)
  active,off,vel=p.mail();self.assertEqual(active,1);self.assertEqual(off,[[0,4,7]]*12);self.assertEqual(vel,127)
  p.edit(0x132,7);self.assertEqual(p.mail()[1],[[0,3,7,10]]*12) # Min7
  p.edit(N.NKEY(0x144),1);self.assertEqual(p.mail()[1][0],[3,7,10,12]) # first inversion
  p.edit(0x132,0);p.edit(N.NKEY(0x144),3);self.assertEqual(p.mail()[1][0],[7,12,16]) # triad: second inversion is the highest
  p.edit(N.NKEY(0x144),0);p.edit(N.NKEY(0x14a),2);self.assertEqual(p.mail()[1][0],[0,7,16]) # triad Drop 2 -> Open
  p.edit(0x104,0);self.assertEqual(p.mail()[0],0)
 def test_diatonic_follows_the_key(self):
  p=self.page();p.edit(0x104,1);off=p.mail()[1] # C major (fixture default)
  self.assertEqual([off[pc] for pc in (0,2,4,5,7,9,11)],[[0,4,7],[0,3,7],[0,3,7],[0,4,7],[0,4,7],[0,3,7],[0,3,6]])
 def test_only_pitched_tracks_and_per_track(self):
  p=self.page();p.ttype=14;p.edit(0x104,1);self.assertIn(p.mail(),[None]) if p.mail() is None else self.assertEqual(p.mail()[0],0)
  p.ttype=18;p.button(0xfe,3);self.assertEqual(p.mail()[0],1)
  p.track=0x92;p.button(0xfe,3);self.assertEqual(p.mail()[0],0);self.assertEqual(p.get(0x104),0) # other track: its own setting (off)
  p.track=0x91;p.button(0xfe,3);self.assertEqual(p.mail()[0],1)
 def test_republishes_when_someone_else_changed_the_mail(self):
  p=self.page();p.edit(0x104,1);p.call(UU['chord_audition_publish'],0,0,0,0);self.assertEqual(p.mail()[0],0)
  p.button(0xfe,3);self.assertEqual(p.mail()[0],1)
 def test_saved_with_the_track(self):
  p=self.page();p.edit(0x104,1);p.edit(0x132,8);p.edit(N.NKEY(0x14a),2);p.edit(N.NKEY(0x144),3);obj=0x20031200;p.w(obj+0x10,0x91);p.u.mem_write(obj+4,b'\x12')
  p.call(UU['fx_save'],obj,0x20017000);self.assertEqual(p.attrs['bento_perf_chord'],1<<24|3<<16|2<<12|8<<4|1)
  p.edit(0x104,0);p.call(UU['fx_load'],0x20017100,obj);self.assertEqual([p.get(k) for k in (0x104,0x132,N.NKEY(0x14a),N.NKEY(0x144))],[1,8,2,3])
  del p.attrs['bento_perf_chord'];p.call(UU['fx_load'],0x20017100,obj);self.assertEqual([p.get(k) for k in (0x104,0x132,N.NKEY(0x14a),N.NKEY(0x144))],[0,15,0,0])
class RealPage(unittest.TestCase):
 """1.6P5 reset on PROJ+PLAY (owner, 24 Oct): with the page open, every
 property read went through perf_get, which asked for the current track, whose
 own read (project property 131) came back to perf_get: endless recursion.
 This runs the real native GenericProperties page (constructor 08145B7C,
 handle/header 08145EFC) with the real getter path; only navigation is a
 fixture."""
 def test_open_page_builds_without_recursion(self):
  p=Fixture();KEEP.append(p);p.registry();p.w(0x3000004c,p.next);p.w(0x30000048,0xc0000000+N.SDRAM_MAP)
  navs=[];depth=[0,0]
  def nav(u,a,n,d):navs.append(u.reg_read(UC_ARM_REG_R1));p.ret()
  def get(u,a,n,d):depth[0]+=1;depth[1]=max(depth[1],0x2003e000-u.reg_read(UC_ARM_REG_SP))
  p.u.hook_add(UC_HOOK_CODE,nav,begin=0x081420ec,end=0x081420ec)
  p.u.hook_add(UC_HOOK_CODE,get,begin=0x08133614,end=0x08133614)
  # The fixture model has no property tree: the native getter body (after our
  # adapter at 08133614) answers 0. Our hook chain and 08133CFC stay real.
  def body(u,a,n,d):
   # Entered after the adapter replayed "push {r4-r7,lr}; sub sp,#12": undo it.
   sp=u.reg_read(UC_ARM_REG_SP);p.w(u.reg_read(UC_ARM_REG_R3),0);u.reg_write(UC_ARM_REG_SP,sp+32);u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_PC,p.r(sp+28))
  p.u.hook_add(UC_HOOK_CODE,body,begin=0x08133618,end=0x08133618)
  def track(u,a,n,d):
   # 08133CFC after its own property-131 read (the recursion path): answer
   # track 0x91 instead of walking the absent project tree; pop its frame.
   sp=u.reg_read(UC_ARM_REG_SP);p.w(u.reg_read(UC_ARM_REG_R9),0x91)
   for i,r in enumerate((UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9)):u.reg_write(r,p.r(sp+12+4*i))
   u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_SP,sp+40);u.reg_write(UC_ARM_REG_PC,p.r(sp+36))
  p.u.hook_add(UC_HOOK_CODE,track,begin=0x08133d26,end=0x08133d26)
  def settings(u,a,n,d):p.w(u.reg_read(UC_ARM_REG_R1),0x55);p.ret(1)
  p.u.hook_add(UC_HOOK_CODE,settings,begin=0x08133e54,end=0x08133e54)
  self.assertEqual(p.call(UU['fx_dispatch'],M,0xaf,0,7),1);self.assertEqual(navs,[0x1a])
  v=0xc0000000;p.call(0x08145b7c,v);arg=0x20016000;p.w(arg,42)
  p.call(0x08145efc,v,arg) # raised (stack overflow) before the fix
  self.assertLess(depth[1],0x1000);self.assertGreater(depth[0],0)
  out=0x20016100;p.w(out,7);p.call(UU['fx_get'],M,arg,0,out);self.assertEqual(p.r(out),0) # empty slot
  p.call(UU['fx_dispatch'],M,0xfe,0,3) # per-message tick with the page open
class P7(unittest.TestCase):
 """P7 owner report on 1.6P6."""
 def page(self):p=Chord().page();return p
 def press(self,p,pad,pitch):
  # A pad press (UI message AC) and the pitch the audio core publishes for it.
  bank=p.r(EC+4);pub=bank+44576+128;p.button(0xac,pad)
  p.u.mem_write(pub+4+pad,bytes([0x80|pitch]));p.w(pub,p.r(pub)+2);p.w(0x3001fe2c,p.r(0x3001fe2c)+10);p.button(0xfe,3)
 def test_tap_field_flips_and_sets_the_project_bpm(self):
  p=self.page();vals=[]
  for t in [1000,1500,2000,2500]:p.w(0x3001fe2c,t);p.edit(0x101,1);vals.append(p.get(0x101))
  self.assertEqual(vals,[1,0,1,0]);self.assertEqual(p.proj[0x8c],120);self.assertEqual(p.get(0x8c),120)
 def test_pitch_only_publication_does_not_invent_a_played_chord_name(self):
  p=self.page();p.edit(0x132,7);p.edit(0x104,1) # Min7
  def name():
   out=0x20036500;p.call(UU['perf_display_state'],out);return p.text(out)
  self.press(p,3,50);self.assertEqual(name(),'')
  p.edit(0x132,0);p.edit(N.NKEY(0x144),1);self.press(p,4,52);self.assertEqual(name(),'')
  p.edit(0x132,15);p.edit(N.NKEY(0x144),0);self.press(p,5,50);self.assertEqual(name(),'')
  p.track=0x92;self.assertEqual(name(),'')
 def test_smooth_voicing_follows_the_last_chord(self):
  p=self.page();p.edit(0x132,0);p.edit(N.NKEY(0x14a),3);p.edit(0x104,1) # Major, Smooth
  self.assertEqual(p.text(p.r(p.r(0x30031484)+N.NKEY(0x14a)*32+8+0) and p.r(p.r(p.r(0x30031484)+N.NKEY(0x14a)*32+8)+12)),'Smooth')
  self.assertEqual(p.mail()[1][0],[0,4,7]) # nothing played yet: close
  self.press(p,0,48) # C major 48 52 55
  off=p.mail()[1]
  self.assertEqual(off[5],[-5,0,4]) # F major after C-E-G: C-F-A (F pad near the chord)
  self.assertEqual(off[7],[-8,-5,0]) # G major after C-E-G: B-D-G, the textbook voice leading
 def test_version_tells_seq_chord_mode_about_changes(self):
  p=self.page();out=0x20036300
  self.assertEqual(p.call(UU['perf_chord_shared'],0x91,out,out+4,out+8),0) # never set
  p.edit(0x132,7);v1=p.call(UU['perf_chord_shared'],0x91,out,out+4,out+8);self.assertGreater(v1,0)
  p.edit(N.NKEY(0x14a),3);v2=p.call(UU['perf_chord_shared'],0x91,out,out+4,out+8);self.assertGreater(v2,v1)
  self.assertEqual([p.r(out),p.r(out+4)],[7,0]) # Smooth reads as Close in SEQ
  p.call(UU['perf_chord_share'],0x91,8,0,1);self.assertEqual(p.call(UU['perf_chord_shared'],0x91,out,out+4,out+8),v2) # SEQ edits keep the version
  self.assertEqual([p.get(k) for k in (0x132,N.NKEY(0x14a),N.NKEY(0x144))],[8,3,1]) # and keep Smooth
class Shared(unittest.TestCase):
 """P5/P7: the chord shared with SEQ chord mode (the header symbol is gone)."""
 def test_shared_chord_store(self):
  p=Chord().page();out=0x20036300
  self.assertEqual(p.call(UU['perf_chord_shared'],0x92,out,out+4,out+8),0)
  p.call(UU['perf_chord_share'],0x91,9,2,3);self.assertEqual([p.get(k) for k in (0x132,N.NKEY(0x14a),N.NKEY(0x144))],[9,2,3])
  p.call(UU['perf_chord_share'],0x91,40,0,0);self.assertEqual(p.get(0x132),9) # invalid ignored
class Pads(Fixture):
 """M7: the patched pad-module call site, then the real native press."""
 def __init__(self):
  super().__init__();KEEP.append(self);self.posts=[];self.mod=0x20030000;self.rec=0x20032000
  self.u.mem_write(self.mod,bytes(0x600));self.u.mem_write(self.mod+N.PADMOD(0x490),b'\x03')
  self.w(self.mod+N.PADMOD(0x2cc),0x55);self.w(self.mod+N.PADMOD(0x2ec),0x55);self.w(self.mod+N.PADMOD(0xc4),1000)
  self.w(self.mod+N.PADMOD(0x424),0x20031000);self.w(0x20031010,12);self.u.mem_write(self.mod+N.PADMOD(0x428),struct.pack('<hh',3,4))
  self.u.hook_add(UC_HOOK_CODE,self.post,begin=0x0809eca0,end=0x0809eca0)
 def post(self,u,a,n,d):
  t,_,h,pitch,v,_=struct.unpack('<6I',u.mem_read(u.reg_read(UC_ARM_REG_R1),24));self.posts.append((t&255,v));self.ret()
 def press(self,pressure):
  self.u.mem_write(self.rec,struct.pack('<6I',0xac,0,0xfffffffe,8,pressure,0));self.posts=[]
  self.u.reg_write(UC_ARM_REG_R0,self.mod);self.u.reg_write(UC_ARM_REG_R1,self.rec);self.u.reg_write(UC_ARM_REG_R2,0x20033000);self.u.reg_write(UC_ARM_REG_R5,self.mod)
  self.u.reg_write(UC_ARM_REG_SP,0x2003e000);self.u.emu_start(0x080857d6|1,0x080857da,count=2000000)
  return [v for t,v in self.posts if t==2]
class Audio(unittest.TestCase):
 def test_off_keeps_pressure(self):
  p=Pads();self.assertEqual(p.press(0x8000),[78]);self.assertEqual(p.press(0x2000),[19])
  p.w(EC+20,0x12345600|90);self.assertEqual(p.press(0x8000),[78]) # wrong tag
 def test_every_fixed_velocity_is_exact(self):
  p=Pads()
  for v in [1,2,50,64,78,100,126,127]:
   p.w(EC+20,0x56454c00|v)
   for pr in [0x100,0x8000,0xffff,0x30000]:self.assertEqual(p.press(pr),[v],(v,pr))
 def play_scan(self,proj_down):
  # P7: the audio core's button scan (loop at 0808D2C0) for button 15 = PLAY,
  # pressed now (new 1, old 0). Button states: new at base+i, old at base+0x10+i.
  p=Fixture();KEEP.append(p);base=0x20034000;p.u.mem_write(base,bytes(0x40))
  p.u.mem_write(base+15,b'\x01');p.u.mem_write(base+7,bytes([proj_down]));p.u.mem_write(base+0x17,bytes([proj_down]))
  fp=0x20035000;p.u.mem_write(fp,bytes(0x900));sb=0x20036000;p.w(sb,0x20037000)
  posts=[]
  def ret(u,a,n,d):p.ret()
  def transport(u,a,n,d):posts.append(u.mem_read(u.reg_read(UC_ARM_REG_R1),1)[0]);p.ret()
  for a in (0x080a04a0,0x08082220):p.u.hook_add(UC_HOOK_CODE,ret,begin=a,end=a)
  p.u.hook_add(UC_HOOK_CODE,transport,begin=0x08058600,end=0x08058600)
  for r,v in [(UC_ARM_REG_R6,15),(UC_ARM_REG_R8,base+14),(UC_ARM_REG_R9,sb),(UC_ARM_REG_R11,fp),(UC_ARM_REG_SP,0x2003d000)]:p.u.reg_write(r,v)
  p.u.emu_start(0x0808d2c0|1,0x0808d2e2,count=2000)
  return posts,p.u.reg_read(UC_ARM_REG_PC)
 def test_play_starts_transport_even_while_proj_is_held(self):
  posts,pc=self.play_scan(0);self.assertEqual(posts,[0x8f]) # native: transport play
  posts,pc=self.play_scan(1);self.assertEqual(posts,[0x8f]);self.assertEqual(pc,0x0808d2e2)
 def test_call_site_is_patched(self):
  self.assertIn('perf_press',AA)
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
