"""P27/P29 performance macros. The synth page is built by its native constructor,
so the encoder strip (vtable 081B2838), its eight slots, the native slot turn
08171E44 (through K15's increment hook), label setter 0817E85E and value text
override 08170656 are the real firmware code. Model getters/events, track
lookup and XML attributes are fixtures (test_mod.Page)."""
import struct,unittest
from test_encoder_speed import install_probe
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import *
from test_integration import IMAGE,UU
from test_mod import Page,V,TRACK,FILT1
BAR=V+0x38;PT=0x20031800;OUT=0x20032400;BASE=0x08040000;APP=0x20031a00;PAGES=0x30034430
def slot(i):return BAR+0x38+i*0x468
class Macros(Page):
 def model(self,u,a,n,d):
  if a==0x081403ec:
   event=struct.unpack('<5I',u.mem_read(u.reg_read(UC_ARM_REG_R1),20))
   if event[0] in (0xcf,0xd0):self.values[(event[1],event[2])]=struct.unpack('<i',struct.pack('<I',event[3]))[0]
  super().model(u,a,n,d)
 def __init__(self):
  super().__init__();install_probe(self);self.tracks[0]=TRACK;self.strings={}
  for a in [0x08133e54,0x08109582,0x081094c2,0x08104c08]:self.u.hook_add(UC_HOOK_CODE,self.xml,begin=a,end=a)
  self.shift(0);self.grab=BAR;self.view='other';self.focus=0;self.perf_hooks()
  self.u.mem_write(APP,bytes(0x60));self.w(APP+0x3c,V);self.w(0x3001fe2c,1000)
 def xml(self,u,a,n,d):
  r=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1)]
  if a==0x08104c08:self.w(0x3000004c,self.next) # the native bump allocator moves its cursor
  elif a==0x08133e54:self.ret(0)
  elif a==0x08109582:self.strings[self.handles[r[0]]]=bytes(self.u.mem_read(r[1],6000)).split(b'\0')[0].decode();self.ret()
  elif a==0x081094c2:
   s=self.strings[self.handles[r[0]]].encode()+b'\0';self.u.mem_write(0x20033000,s);self.ret(0x20033000)
 def shift(self,on):self.w(0x24048d68,1 if on else 0)
 # The native synth strip stands in for the Perform macro strip: which page is
 # showing is the fixture's choice ('perform', 'macro', 'edit', 'other').
 # The real Perform page is exercised in test_perform_ui. view None = real code.
 def perf_hooks(self):
  def hook(u,a,n,d):
   if self.view is None:return
   if a in (UU['perf_macro_view'],self.speed_symbols['perf_macro_view']):self.ret(self.view in('perform','macro','edit'))
   elif a in (UU['perf_macro_targets'],self.speed_symbols['perf_macro_targets']):self.ret(self.view=='edit')
   else:
    v=u.reg_read(UC_ARM_REG_R0);v=v-(1<<32) if v>=1<<31 else v
    if 0<=v<8:self.focus=v
    self.ret(self.focus)
  for n in('perf_macro_view','perf_macro_targets','perf_macro_focus'):
   for address in {UU[n],self.speed_symbols[n]}:self.u.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
 def show(self,view):self.view=view;self.tick();self.call(UU['macro_periodic'],0);self.tick();self.call(UU['macro_periodic'],0)
 def perform(self):self.show('perform')
 def leave(self):self.show('other')
 def bar_at(self,x,y):
  self.w(0x3000004c,self.next);self.w(PT,x);self.w(PT+4,y);self.w(0x20031900,0)
  ok=self.call(UU['macro_app_hit'],APP,PT,0x20031900);return self.r(0x20031900) if ok else 0
 def tick(self,bar=BAR,t=None):
  if t is not None:self.w(0x3001fe2c,t)
  self.u.mem_write(0x20031e00,bytes(16));self.call(UU['macro_bar_tick'],bar,0x20031e00)
 def touch(self,fn,x,y,bar=None):self.w(0x3000004c,self.next);self.w(PT,x);self.w(PT+4,y);self.call(UU[fn],bar or self.grab,PT,0)
 def drag(self,x,y,dx,dy,bar=None):
  self.grab=bar or BAR;self.touch('macro_bar_down',x,y)
  for k in range(1,6):self.touch('macro_bar_move',x+dx*k//5,y+dy*k//5)
  self.touch('macro_bar_up',x+dx,y+dy)
 def swipe(self,dx,bar=None):self.tick();self.drag(600,440,dx,0,bar)
 def later(self,ms=500):self.w(0x3001fe2c,self.r(0x3001fe2c)+ms)
 def settle_tap(self):
  self.later() # beyond the 400 ms double tap
  self.tick()
  self.call(UU['macro_periodic'],0)
 def tap(self,i,bar=None,settle=True):
  x=self.r(slot(i)+4)+20;self.grab=bar or BAR;self.touch('macro_bar_down',x,440);self.touch('macro_bar_up',x,440)
  if settle:self.settle_tap()
 def arm(self,i):self.tap(i) # W14 HW4 (owner, 29 Oct): a single tap arms or disarms
 def double(self,i,bar=None):self.tap(i,bar=bar,settle=False);self.later(150);self.tap(i,bar=bar)
 def armed(self):return self.call(UU['macro_armed'])
 def readout(self):
  out=0x20032000;self.u.mem_write(out,bytes(0x1c4));self.call(UU['macro_periodic'],out);self.call(UU['macro_readout'],out);return self.text(out)
 def name(self,i):return self.text(slot(i)+0x3f9)
 def value_text(self,i):return self.text(slot(i)+0x2c8)
 def turn(self,i,delta,raw=False):
  if not raw:delta*=160000//127+1 if self.overlay() else 1
  self.call_turn(i,delta)
 def overlay(self):
  return self.call(UU['macro_overlay'])!=0
 def call_turn(self,i,delta):self.w(0x3000004c,self.next);self.events=[];self.posted=[];self.call(0x08171e44,slot(i),delta)
 def change(self,key,value,h=FILT1):
  # what the page sends the model for a turned encoder: D0 {D0, node, key, value} (P28)
  ev=0x20031c00;self.u.mem_write(ev,struct.pack('<HH4I',0xd0,0,h,key,value,0));self.call(UU['analog_model_event'],0x30024b00,ev);self.values[(h,key)]=value
 def cf(self):return [e for e in self.events if e[0] in (0xcf,0xd0)]
 def map_resonance(self,m=0):
  """Owner flow: tap a macro on Perform, go to a page, tap a parameter."""
  self.perform();self.arm(m);self.leave();self.w(slot(1)+0x34,FILT1);self.tap(1)

class NativeMacroWrites(Macros):
 """Execute the actual CF/D0 handlers and native property writes. Only child
 lookup, selection, Undo and intercore/UI queue services are fixture-backed."""
 TREE=0xc0080000
 OWNER=0xc0080100
 CHILD=0xc0080200
 VT=0xc0080300
 PROP=0xc0080400
 def __init__(self,track_type):
  self.native_writes=False
  super().__init__()
  self.track_type=track_type;self.audio=[]
  self.w(0x30024b00,self.TREE)
  self.w(self.TREE,self.OWNER);self.w(self.TREE+0x30,1)
  for obj,handle,kind in ((self.OWNER,TRACK,track_type),(self.CHILD,FILT1,10)):
   self.w(obj,self.VT);self.w(obj+4,kind);self.w(obj+0x10,handle)
  self.w(self.CHILD+8,self.PROP);self.w(self.CHILD+12,1)
  self.u.mem_write(self.PROP,struct.pack('<iHBB',0,0x33,1,0))
  for offset,address in ((0,0x081ff180),(0x14,0x081ff190),(0x18,0x081ff1a0)):
   self.w(self.VT+offset,address|1)
  for address in (0x0813430c,0x0812d78a,0x08133df8,0x0810b5c8,
                  0x0810b650,0x08173272,0x081ff180,0x081ff190,0x081ff1a0):
   self.u.hook_add(UC_HOOK_CODE,self.service,begin=address,end=address)
 def model(self,u,a,n,d):
  if getattr(self,'native_writes',False):
   if a==0x081403ec:
    self.events.append(struct.unpack('<5I',u.mem_read(u.reg_read(UC_ARM_REG_R1),20)))
    return
   if a==0x08133614 and self.r(u.reg_read(UC_ARM_REG_R1))==FILT1 and u.reg_read(UC_ARM_REG_R2)==0x33:
    self.w(u.reg_read(UC_ARM_REG_R3),self.r(self.PROP));self.ret(1);return
  super().model(u,a,n,d)
 def service(self,u,a,n,d):
  r=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  if a==0x0813430c:self.ret(0)
  elif a==0x0812d78a:
   if r[1]==0:self.w(r[2],self.OWNER);self.ret(1)
   else:self.ret(0)
  elif a==0x08133df8:self.w(r[1],0);self.ret(0)
  elif a in (0x0810b5c8,0x0810b650):self.audio.append(tuple(r));self.ret()
  elif a==0x08173272:self.ret()
  elif a==0x081ff180:self.ret(self.r(r[0]+4))
  elif a==0x081ff190:self.w(r[2],self.CHILD if r[1]==FILT1 else 0);self.ret(int(r[1]==FILT1))
  elif a==0x081ff1a0:
   if r[0]==self.OWNER and r[1]==0:self.w(r[2],self.CHILD);self.ret(1)
   else:self.ret(0)

class MacroTest(unittest.TestCase):
 def visibility_page(self):
  p=Macros()
  parents=[0x20039000+i*0x80 for i in range(3)]
  chain=[BAR]+parents
  for node,parent in zip(chain,parents+[0]):p.w(node+0x2c,parent)
  for node in chain:p.u.mem_write(node+0x30,b'\0')
  # Isolate our strip bookkeeping; native paint and Perform tick are unchanged.
  for address in (0x081703cc,UU['pg_perform_tick']):
   p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=address,end=address)
  return p,chain
 def test_strip_tick_walks_its_visible_parent_chain_only_once(self):
  p,chain=self.visibility_page()
  reads={node+0x2c:0 for node in chain}
  def read(u,access,address,size,value,data):
   if address in reads:reads[address]+=1
  p.u.hook_add(UC_HOOK_MEM_READ,read)
  p.tick()
  for address in reads:reads[address]=0
  for _ in range(20):p.tick()
  self.assertEqual(list(reads.values()),[40]+[20]*(len(chain)-1))
 def test_strip_visibility_is_rechecked_after_each_parent_changes(self):
  p,chain=self.visibility_page()
  p.perform();self.assertTrue(p.overlay())
  for node in chain:
   p.u.mem_write(node+0x30,b'\x01')
   p.tick();p.call(UU['macro_periodic'],0);self.assertFalse(p.overlay())
   p.u.mem_write(node+0x30,b'\0')
   p.tick();p.call(UU['macro_periodic'],0);self.assertTrue(p.overlay())

 def test_sampler_macro_amount_accumulates_through_real_native_model_writes(self):
  for kind in (14,15):
   with self.subTest(track_type=kind):
    p=NativeMacroWrites(kind);p.map_resonance();p.call(UU['macro_disarm']);p.perform();p.native_writes=True
    amounts=[]
    for _ in range(6):
     p.turn(0,4000,raw=True);amounts.append(int(p.value_text(0)))
    self.assertEqual(p.r(p.PROP),150)
    self.assertEqual(amounts,[3,6,9,12,15,19])
    self.assertTrue(all(event[0]==0xcf for event in p.events))
    self.assertEqual(p.audio[-1][1:],(FILT1,0x33,150))
 def test_synth_macro_keeps_native_child_write_and_audio_routing(self):
  for kind in (18,19):
   with self.subTest(track_type=kind):
    p=NativeMacroWrites(kind);p.map_resonance();p.call(UU['macro_disarm']);p.perform();p.native_writes=True
    for _ in range(6):p.turn(0,4000,raw=True)
    self.assertEqual(p.r(p.PROP),150)
    self.assertEqual(p.value_text(0),'19')
    self.assertEqual(p.events[-1][:4],(0xd0,FILT1,0x33,150))
    self.assertEqual(p.audio[-1][1:],(TRACK,0x33,150))
 def test_loading_macros_discards_previous_relative_turn_remainders(self):
  p=Macros();p.map_resonance(0);p.perform()
  p.values[(FILT1,0x33)]=500
  p.turn(0,50,raw=True);self.assertEqual(p.cf(),[])
  obj=0x20010000;p.w(obj+16,TRACK);p.u.mem_write(obj+4,b'\x15')
  p.call(UU['macro_save'],obj,0x20017000)
  p.call(UU['macro_load'],0x20011000,obj)
  p.turn(0,50,raw=True);self.assertEqual(p.cf(),[])
 def test_large_unmapped_turns_clamp_without_fraction_overflow(self):
  p=Macros();p.perform()
  p.turn(0,0x7fffffff,raw=True);self.assertEqual(p.value_text(0),'127')
  p.turn(0,-0x7fffffff,raw=True);self.assertEqual(p.value_text(0),'0')
 def test_amount_starts_from_current_target_and_adopts_external_changes(self):
  p=Macros();p.map_resonance(0);p.perform()
  lo,hi=p.r(slot(1)+0x450),p.r(slot(1)+0x454)
  p.values[(FILT1,0x33)]=lo+(hi-lo)*3//4
  p.turn(0,1600,raw=True)
  self.assertGreater(p.cf()[0][3],lo+(hi-lo)*3//4)
  self.assertLessEqual(p.cf()[0][3],lo+(hi-lo)*3//4+(hi-lo)//100+1)
  p.values[(FILT1,0x33)]=lo+(hi-lo)//4
  p.turn(0,-1600,raw=True)
  self.assertLess(p.cf()[0][3],lo+(hi-lo)//4)
 def test_each_target_keeps_its_own_current_position(self):
  p=Macros();p.map_resonance(0);p.leave();p.tap(0);p.perform()
  keys=[0x33,0xce];before={}
  for i,key in enumerate(keys):
   index=1 if key==0x33 else 0
   low,high=p.r(slot(index)+0x450),p.r(slot(index)+0x454)
   before[key]=low+(high-low)*(i+1)//3;p.values[(FILT1,key)]=before[key]
  p.turn(0,1600,raw=True)
  for event in p.cf():
   self.assertGreater(event[3],before[event[2]])
   self.assertLessEqual(event[3]-before[event[2]],(p.r(slot(1 if event[2]==0x33 else 0)+0x454)-p.r(slot(1 if event[2]==0x33 else 0)+0x450))//100+1)
 def test_vtables(self):
  for k,fn in [(0,'macro_bar_tick'),(4,'macro_bar_down'),(5,'macro_bar_move'),(6,'macro_bar_up'),(7,'macro_bar_takes')]:
   self.assertEqual(struct.unpack_from('<I',IMAGE,0x081b2838+4*k-BASE)[0],UU[fn]|1)
  self.assertEqual(struct.unpack_from('<I',IMAGE,0x081b2838+4-BASE)[0],UU.get('pg_bar_paint',UU.get('nm_bar_paint',0x0816faec))|1)
  self.assertEqual(struct.unpack_from('<I',IMAGE,0x081b2328-BASE)[0],UU['macro_app_hit']|1)
 def test_perform_shows_macros_and_leaving_restores_native_strip(self):
  p=Macros();native=[p.name(i) for i in range(8)]
  p.perform();self.assertEqual([p.name(i) for i in range(8)],['MACRO %d'%(i+1) for i in range(8)]);self.assertEqual(p.value_text(0),'0')
  self.assertEqual(p.r(slot(0)+8),406) # nothing moves (P28 moved rows)
  p.leave();self.assertEqual([p.name(i) for i in range(8)],native);self.assertEqual(p.value_text(0),'');self.assertFalse(p.overlay())
 def test_swipes_no_longer_show_or_hide_macros(self):
  p=Macros();native=p.name(0)
  p.swipe(-200);self.assertFalse(p.overlay());self.assertEqual(p.name(0),native)
  p.perform();p.swipe(200);self.assertTrue(p.overlay());self.assertEqual(p.name(0),'MACRO 1')
 def test_overlay_owns_encoders_and_native_parameter_is_untouched(self):
  p=Macros();p.perform();p.turn(2,5)
  self.assertEqual(p.posted,[]);self.assertEqual(p.cf(),[]);self.assertEqual(p.value_text(2),'5')
  p.turn(2,-9);self.assertEqual(p.value_text(2),'0')
 def test_tap_arms_tap_again_disarms_with_a_steady_readout(self):
  # W14 HW4 (owner, 29 Oct): one tap selects and turns on map mode; a tap on
  # the armed macro ends it; a tap on another macro moves map mode there.
  p=Macros();p.perform()
  p.tap(2);self.assertEqual((p.focus,p.armed()),(2,3));self.assertEqual(p.value_text(2),'MAP')
  for t in (2400,2800,9000):p.tick(BAR,t);self.assertEqual(p.readout(),'MAP M3 0/3') # steady, no blink
  p.tap(4);self.assertEqual((p.focus,p.armed()),(4,5))
  p.tap(4);self.assertEqual((p.focus,p.armed()),(4,0));self.assertEqual(p.readout(),'')
 def test_disarm_ends_mapping_from_any_page(self):
  p=Macros();p.perform();p.arm(0);p.leave();self.assertEqual(p.armed(),1)
  p.call(UU['macro_disarm']);self.assertEqual(p.armed(),0);self.assertEqual(p.readout(),'')
 def test_tap_maps_full_range_double_tap_unmaps_while_encoders_never_map(self):
  p=Macros();p.map_resonance(0)
  self.assertEqual(p.readout(),'+ Resonance')
  p.later(3000);self.assertEqual(p.readout(),'MAP M1 1/3')
  p.turn(1,4000);self.assertIn(0xcf,p.posted) # the native parameter moves
  p.change(0x33,450);p.later(3000);self.assertEqual(p.readout(),'MAP M1 1/3') # and is never captured
  p.perform();self.assertEqual(p.name(0),'Resonance')
  p.turn(0,127);self.assertEqual(p.cf()[0][1:4],(FILT1,0x33,p.r(slot(1)+0x454)))
  p.turn(0,-127);self.assertEqual(p.cf()[0][3],p.r(slot(1)+0x450))
  p.leave();p.tap(1);self.assertNotEqual(p.readout(),'- Resonance') # W14 HW4: a single tap keeps the mapping
  p.later(3000);self.assertEqual(p.readout(),'MAP M1 1/3')
  p.double(1);self.assertEqual(p.readout(),'- Resonance')
  p.later(3000);self.assertEqual(p.readout(),'MAP M1 0/3')
  p.perform();self.assertEqual(p.name(0),'MACRO 1');p.turn(0,10);self.assertEqual(p.cf(),[])
 def test_double_tap_on_a_parameter_unmaps_it_outside_map_mode(self):
  p=Macros();p.map_resonance(0);p.call(UU['macro_disarm']);self.assertEqual(p.armed(),0)
  p.tap(1);p.perform();self.assertEqual(p.name(0),'Resonance') # a single tap is native only
  p.leave();p.double(1);self.assertEqual(p.armed(),0)
  p.perform();self.assertEqual(p.name(0),'MACRO 1');p.turn(0,10);self.assertEqual(p.cf(),[])
 def test_double_tap_on_a_macro_clears_all_its_mappings(self):
  p=Macros();p.map_resonance(4);p.perform()
  self.assertEqual(p.armed(),5) # still armed from mapping
  p.double(4);self.assertEqual(p.armed(),0)
  self.assertEqual(p.name(4),'MACRO 5');p.turn(4,50);self.assertEqual(p.cf(),[])
 def test_macro_page_double_tap_on_one_binding_removes_only_that_binding(self):
  # W14 HW4 (owner, 29 Oct): Macro page double tap on a binding area.
  p=Macros();p.map_resonance(0);p.w(slot(0)+0x34,FILT1);p.later(3000);p.tap(0)
  p.later(3000);self.assertEqual(p.readout(),'MAP M1 2/3')
  p.call(UU['macro_binding_tap'],0,0);p.later(3000);p.call(UU['macro_binding_tap'],0,0)
  self.assertEqual(p.readout(),'MAP M1 2/3') # two separate single taps keep it
  p.later(3000);p.call(UU['macro_binding_tap'],0,1);p.later(150);p.call(UU['macro_binding_tap'],0,0)
  self.assertEqual(p.readout(),'MAP M1 2/3') # different bindings are not a double tap
  p.later(150);p.call(UU['macro_binding_tap'],0,0)
  self.assertEqual(p.readout(),'- Resonance')
  p.later(3000);self.assertEqual(p.readout(),'MAP M1 1/3')
  p.later(3000);p.call(UU['macro_binding_tap'],0,2);p.later(150);p.call(UU['macro_binding_tap'],0,2)
  self.assertEqual(p.readout(),'MAP M1 1/3') # an empty binding area does nothing
 def test_tap_on_header_readout_ends_map_mode(self):
  # W14 HW4 (owner, 29 Oct): leave map mode without going back to PROJ.
  p=Macros();p.perform();p.arm(0);p.leave();root=0x30034d48
  p.call(0x08180198,root);self.assertEqual(p.r(root),0x081b3680)
  for o,v in ((0x10,42),(0x240,6),(0x248,584)):p.w(root+o,v) # native apply 0817FAF8 geometry (emulator)
  p.bar_at(700,20);self.assertEqual(p.armed(),1) # header, right of the readout
  p.bar_at(300,60);self.assertEqual(p.armed(),1) # below the header
  p.w(PT,300);p.w(PT+4,20);p.w(0x20031900,0xffffffff)
  self.assertEqual(p.call(UU['macro_app_hit'],APP,PT,0x20031900),0)
  self.assertEqual((p.armed(),p.r(0x20031900)),(0,0));self.assertEqual(p.readout(),'- MAP OFF')
  p.later(3000);self.assertEqual(p.readout(),'')
  p.call(UU['macro_app_hit'],APP,PT,0x20031900);self.assertEqual(p.armed(),0) # disarmed: native again
 def test_edit_view_edits_ranges_reversed_and_sensitivity(self):
  p=Macros();p.map_resonance(0);p.perform();p.arm(0)
  lo,hi=p.r(slot(1)+0x450),p.r(slot(1)+0x454)
  p.show('edit');p.focus=0;p.call(UU['macro_periodic'],0)
  self.assertEqual([(p.name(i),p.value_text(i)) for i in (0,1,2,6,7)],
   [('Resonance','Min 0%'),('Resonance','Max 100%'),('-',''),('Sensitivity','Normal'),('','')])
  p.turn(1,-80000,raw=True);self.assertEqual(p.value_text(1),'Max 50%')
  self.assertEqual(p.posted,[]) # a range edit is not a native parameter edit
  p.turn(0,160000,raw=True);self.assertEqual(p.value_text(0),'Min 100%') # above Max: reversed
  p.turn(2,160000,raw=True);self.assertEqual(p.value_text(2),'') # no second target
  p.turn(6,10000,raw=True);self.assertEqual(p.value_text(6),'Fast')
  p.turn(6,-50000,raw=True);self.assertEqual(p.value_text(6),'Fine')
  p.values[(FILT1,0x33)]=hi
  p.perform();p.turn(0,8*1260,raw=True)
  self.assertGreater(p.cf()[0][3],hi-10) # Fine: reversed half-range moves fewer than ten native units
  self.assertLess(p.cf()[0][3],hi)
  p.turn(0,-8*1260,raw=True);self.assertEqual(p.cf()[0][3],hi)
 def test_macro_and_edit_views_share_the_page_but_route_encoders_differently(self):
  p=Macros();p.map_resonance(0);p.show('macro')
  for i in range(8):p.turn(i,1260,raw=True)
  values=[]
  for i in range(8):
   p.call(UU['macro_snapshot'],i,0x20032400);values.append(p.r(0x20032400))
  self.assertEqual(values,[64]+[1]*7) # mapped macro adopts the live parameter, not zero
  p.show('edit');p.call(UU['macro_select'],3)
  self.assertEqual((p.focus,p.armed()),(3,1)) # selection alone never changes mapping state
  p.turn(7,1260,raw=True)
  p.call(UU['macro_snapshot'],3,0x20032400)
  self.assertEqual(p.r(0x20032400),2) # selected M4 amount; E8
  p.turn(0,160000,raw=True)
  self.assertEqual(p.posted,[]) # E1 edits the selected Min without posting a native parameter
 def test_hidden_strip_never_takes_the_macros(self):
  p=Macros();p.perform();p.u.mem_write(V+0x30,b'\x01') # whole view hidden (another page)
  p.tick(BAR,1500);p.readout();self.assertFalse(p.overlay()) # nothing visible to show them on: knobs are native again
 def test_redirect_uses_the_real_strip_when_the_page_test_finds_nothing(self):
  p=Macros();p.perform();p.u.mem_write(0x20031c80,bytes(0x40)+b'');p.u.mem_write(0x20031cb0,b'\x01');p.w(APP+0x3c,0x20031c80) # the page's own test finds nothing there
  c=p.bar_at(344,440);self.assertEqual(c,BAR);self.assertEqual(p.r(c),0x081b2838)
  p.tap(2,bar=c);self.assertEqual(p.focus,2)
  self.assertNotEqual(p.bar_at(344,200),c) # elsewhere: not the catcher
 def test_save_and_load_round_trip_by_track_path_with_sensitivity(self):
  p=Macros();p.map_resonance(2);p.perform();p.arm(2);p.turn(2,64)
  obj=0x20010000;p.w(obj+16,TRACK);p.u.mem_write(obj+4,b'\x15');p.call(UU['macro_save'],obj,0x20017000)
  saved=p.strings['playground_macros_v1'];self.assertTrue(saved.startswith('02')) # Normal everywhere: still version 2
  p.show('edit');p.focus=2;p.turn(6,-10000,raw=True);self.assertEqual(p.value_text(6),'Slow')
  p.call(UU['macro_save'],obj,0x20017000);saved=p.strings['playground_macros_v1'];self.assertTrue(saved.startswith('03'))
  q=Macros();q.attrs['playground_macros_v1']=1;q.strings['playground_macros_v1']=saved
  q.u.mem_write(0x20010000,bytes(32));q.w(0x20010010,TRACK)
  q.call(UU['macro_load'],0x20011000,0x20010000)
  q.perform();self.assertEqual(q.value_text(2),'127')
  q.values[(FILT1,0x33)]=500
  q.turn(2,10);self.assertEqual(q.cf()[0][1:3],(FILT1,0x33))
  q.show('edit');q.focus=2;q.call(UU['macro_periodic'],0);self.assertEqual(q.value_text(6),'Slow')
 def test_save_writes_nothing_without_macros(self):
  p=Macros();obj=0x20010000;p.w(obj+16,TRACK);p.call(UU['macro_save'],obj,0x20017000);self.assertNotIn('playground_macros_v1',p.strings)
 def test_a_lost_release_never_blocks_the_strip(self):
  p=Macros();p.perform();p.grab=BAR;p.touch('macro_bar_down',600,440);p.tick(BAR,5000);p.readout()
  p.tap(3);self.assertEqual(p.focus,3)
 def test_native_hit_test_still_finds_the_strip(self):
  p=Macros();out=0x20031900;p.w(PT,344);p.w(PT+4,426);self.assertEqual(p.call(0x0816fa10,V,PT,out),1);self.assertEqual(p.r(out),BAR)
if __name__=='__main__':unittest.main(verbosity=2)
