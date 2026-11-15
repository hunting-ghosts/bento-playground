"""R6 TRACKS single press (owner spec): on the Tracks page a short TRACKS press opens
Track FX; from any other page TRACKS stays native. Native page construction is tested separately."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R1
from test_integration import Fixture,UU,KEYS
class Gesture(Fixture):
 def __init__(self):
  super().__init__();self.registry();self.m=0x30024b00
  self.u.mem_write(self.m+0x12c,b'\x17')
  def nav(u,a,n,d):
   page=u.reg_read(UC_ARM_REG_R1);self.navlog.append(page);self.u.mem_write(self.m+0x12c,bytes([page]));self.ret()
  self.u.hook_add(UC_HOOK_CODE,nav,begin=0x081420ec,end=0x081420ec)
 def evt(self,code,index,ms):
  self.w(0x3001fe2c,ms)
  result=self.call(UU['fx_dispatch'],self.m,code,0,index)
  if code==0xaf and index==2 and not result:self.u.mem_write(self.m+0x12c,b'\x02')
  return result
 def tap(self,start):
  self.assert_pass=self.evt(0xaf,2,start)
  return self.evt(0xb0,2,start+50)
import test_perf
class Tabs(test_perf.Page):
 """R6.2 MIXER / INST cycles on the Perform fixture (heap, model stubs). The native
 root header (0x30034d48) is simulated: footer taps (0817FE70) are logged and
 light the tapped tab."""
 R=0x30034d48
 def __init__(self):
  super().__init__();self.taps=[];self.m=test_perf.M
  def tap(u,a,n,d):
   e=u.reg_read(UC_ARM_REG_R1);i=int.from_bytes(u.mem_read(e+8,2),'little');self.taps.append(i)
   self.root(self.page_id,self.ids,self.ids.index(i));self.ret()
  self.u.hook_add(UC_HOOK_CODE,tap,begin=0x0817fe70,end=0x0817fe70)
 def evt(self,code,index,ms):self.w(0x3001fe2c,ms);return self.button(code,index)
 def root(self,page,ids,lit):
  self.page_id,self.ids=page,ids;self.u.mem_write(self.m+0x12c,bytes([page]))
  self.w(self.R,0x081b3680);h=self.R+0x34;self.u.mem_write(h,bytes(N.HDR_SIZE));self.u.mem_write(h+N.HDR(0x1c2),bytes([page]))
  for i,t in enumerate(ids):
   r=h+N.HDR(0x74)+i*48;self.u.mem_write(r+0x20,bytes([0,int(i==lit),1]));self.u.mem_write(r+44,t.to_bytes(2,'little'))
 def press(self,index,ms):
  self.evt(0xaf,index,ms);return self.evt(0xb0,index,ms+50)
 def tick(self,ms):self.evt(0x3f,0,ms)
MIX=[N.NUI(0x108),0x1087,N.NUI(0x109),N.NUI(0x10a),N.NUI(0x10b)];GRAIN=[0x16,0xee,0xef]
class Tests(unittest.TestCase):
 def test_mixer_cycles_tabs_and_wraps(self):
  p=Tabs();p.root(0x1f,MIX,0)
  for want,ms in zip([0x1087,N.NUI(0x109),N.NUI(0x10a),N.NUI(0x10b),N.NUI(0x108)],range(5000,10000,1000)):p.press(5,ms)
  self.assertEqual(p.taps,[0x1087,N.NUI(0x109),N.NUI(0x10a),N.NUI(0x10b),N.NUI(0x108)])
 def test_mixer_from_another_page_starts_at_level(self):
  p=Tabs();p.root(0x17,[],0);p.press(5,5000)
  p.root(0x1f,MIX,3);p.tick(5100);self.assertEqual(p.taps,[N.NUI(0x108)])
  p.tick(5200);self.assertEqual(p.taps,[N.NUI(0x108)]) # armed once
 def test_long_mixer_hold_keeps_native_tab(self):
  p=Tabs();p.root(0x17,[],0);p.evt(0xaf,5,5000);p.evt(0xb0,5,5600)
  p.root(0x1f,MIX,3);p.tick(5700);self.assertEqual(p.taps,[])
 def test_inst_cycles_and_remembers_per_track(self):
  p=Tabs();p.root(0x09,GRAIN,0);p.press(10,5000);self.assertEqual(p.taps,[0xee])
  p.tick(5100) # remembers Grain 1
  p.root(0x17,[],0);p.press(10,6000) # native INST opens the instrument at its first tab
  p.root(0x09,GRAIN,0);p.tick(6100);self.assertEqual(p.taps,[0xee,0xee])
 def test_mixer_cycle_is_level_track_pan_delay_reverb_on_the_mixer_page(self):
  # R6.4 (owner): Track is an overlay on the Mixer page; MIXER cycles in place.
  p=Tabs()
  for lit,want in ((0,0x1087),(1,N.NUI(0x109)),(2,N.NUI(0x10a)),(3,N.NUI(0x10b)),(4,N.NUI(0x108))):
   p.taps.clear();p.root(0x1f,MIX,lit);p.press(5,5000+lit*1000);self.assertEqual(p.taps,[want],lit)
  self.assertEqual(p.navs,[])
 def test_inst_cycle_skips_tabs_hidden_on_screen(self):
  p=Tabs();p.root(0x09,GRAIN,0);p.u.mem_write(Tabs.R+N.ROOT_TABS+2*0xd0+0x30,b'\x01') # Wavetable: Grain 2 hidden on screen
  p.press(10,5000);p.u.mem_write(Tabs.R+N.ROOT_TABS+2*0xd0+0x30,b'\x01');p.press(10,6000)
  self.assertEqual(p.taps,[0xee,0x16])
 def test_inst_side_page_returns_home_first_tab(self):
  p=Tabs();p.root(0x08,[0x3,0x8,0x44],1);p.tick(5000) # visit: home page 08 remembered
  p.root(0x07,[0x43,0x44],1);p.press(10,6000) # on the Mix side page, Mix (last) lit
  self.assertEqual(p.navs[-1],0x08)
  p.root(0x08,[0x3,0x8,0x44],2);p.tick(6100);self.assertEqual(p.taps,[0x3])
 def test_inst_without_memory_stays_native(self):
  p=Tabs();p.root(0x17,[],0);p.press(10,5000);p.root(0x09,GRAIN,0);p.tick(5100);self.assertEqual(p.taps,[])
 def test_short_press_on_tracks_opens_fx_on_release_other_pages_stay_native(self):
  p=Gesture();self.assertEqual(p.tap(1000),0);self.assertEqual(p.assert_pass,0);self.assertEqual(p.navlog,[]) # from page 17: native Tracks
  self.assertEqual(p.tap(3000),0);self.assertEqual(p.navlog,[0x1a]) # on Tracks: Track FX
 def test_long_press_on_tracks_does_not_switch(self):
  p=Gesture();p.tap(1000);p.evt(0xaf,2,3000);p.evt(0xb0,2,3500);self.assertEqual(p.navlog,[])
 def test_pad_use_other_button_or_page_change_cancel(self):
  for action in ['pad','fe','used','button','page']:
   p=Gesture();p.tap(1000);p.evt(0xaf,2,3000)
   if action=='pad':p.evt(0xac,0,3020)
   if action=='fe':p.evt(0xfe,0,3020)
   if action=='used':p.w(0x24048cc8,1)
   if action=='button':p.evt(0xaf,5,3020)
   if action=='page':p.u.mem_write(p.m+0x12c,b'\x07')
   p.evt(0xb0,2,3050);self.assertEqual(p.navlog,[],action)
 def test_tick_wrap_and_non_user_messages(self):
  p=Gesture();p.tap(1000);p.evt(0xaf,2,0xffffffb0);p.evt(0x3f,0,0xfffffff0)
  p.evt(0xb0,2,30);self.assertEqual(p.navlog,[0x1a])
 def test_registry_refuses_collision_without_altering_existing_definition(self):
  p=Gesture();key=KEYS[0];p.w(0x20020000+key*32,0xabcd);p.w(0x20020000+key*32+4,0x12345678)
  p.tap(1000);self.assertEqual(p.tap(3000),0);self.assertEqual(p.navlog,[])
  self.assertEqual(p.r(0x20020000+key*32+4),0x12345678)
if __name__=='__main__':unittest.main(verbosity=2)
