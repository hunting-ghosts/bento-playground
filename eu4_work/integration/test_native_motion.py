"""Toggle recorder: shipped ARM producers, writer, evaluator and transport.

Model identity/routing and the intercore queue are fixtures. Native A-D write,
clear, signed arrays, evaluator, RECORD toggle and the extension code execute.
These checks do not substitute for an SD-project/device round trip.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_LR, UC_ARM_REG_PC
from test_native_automation import Automation, MODEL, HANDLE, NODE, NODE_BYTES, SEQUENCE, TIME
from test_integration import AA, UU, IMAGE

KEEP = []
OWNER = 100
CLIP = 55
FILTER = 0x205
SLOT = 0xc0040038
BAR = SLOT - 0x38
EVENT = 0x20032000
OUT = 0x20033000
ROOT = 0xc0020000
REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)


class Recorder(Automation):
 def __init__(self,initialize=True):
  super().__init__();KEEP.append(self)
  self.nodes={CLIP:NODE}
  self.routes = {};self.selected_owner = OWNER;self.selected_row=0;self.clip_rows={CLIP:0};self.clip_steps = 16
  self.grid = 10;self.absolute = 0;self.notifications = [];self.added_snapshots = [];self.posted=[]
  self.types={OWNER:18,FILTER:10,CLIP:24}
  self.children={OWNER:[CLIP,FILTER]};self.paths={}
  self.registry()
  self.w(0x3000004c, self.next);self.w(0x30000048, 0xc0200000)
  for address in (0x08133cfc, 0x0813391a, 0x08133f7c, 0x08133614,
                  0x08131244, 0x08131238, 0x08133388, 0x08124a7e,
                  0x08065600, 0x0809eca0, 0x0816fc34,0x0813390e):
   self.u.hook_add(UC_HOOK_CODE, self.model, begin=address, end=address)
  self.call(0x08062a80, SEQUENCE)
  self.w(SEQUENCE+12, OWNER);self.w(SEQUENCE+0x14, 0)
  self.w(SEQUENCE+0x86c0, SEQUENCE+0x240)
  self.w(SEQUENCE+0x244, 16);self.u.mem_write(SEQUENCE+0x20, b'\1')
  self.u.mem_write(SEQUENCE+0x260, bytes(8));self.f(SEQUENCE+0x8764, 1)
  self.w(BAR, 0x081b2838)
  self.bind()
  self.w(0x3001fe2c, 1000)
  if initialize:
   self.call(UU['nm_set_enabled'],1)
   for _ in range(32):self.call(UU['nm_status'])
  self.audio(0)

 def hook(self,u,a,n,d):
  if a==0x08104c08 and not self.force_registry:
   size=u.reg_read(UC_ARM_REG_R0);address=self.next
   self.next+=(size+31)&~31;self.w(0x3000004c,self.next);self.ret(address)
  else:super().hook(u,a,n,d)

 def service(self,u,a,n,d):
  if a==0x0812ea72 and hasattr(self,'nodes'):
   seq=u.reg_read(UC_ARM_REG_R1);out=u.reg_read(UC_ARM_REG_R2)
   self.lookups.append((seq,u.reg_read(UC_ARM_REG_R3)))
   node=self.nodes.get(seq)
   if node and self.present:self.w(out,node);self.ret(1)
   else:self.ret(0)
  else:super().service(u,a,n,d)

 def model(self,u,a,n,d):
  r=[u.reg_read(reg) for reg in REGS]
  if a==0x08133cfc:self.w(r[1],self.selected_owner);self.ret(1)
  elif a==0x0813391a:
   children=self.children.get(self.r(r[1]),[])
   if r[2]<len(children):self.w(r[3],children[r[2]]);self.ret(1)
   else:self.ret(0)
  elif a==0x08133f7c:self.ret(self.types.get(self.r(r[1]),0))
  elif a==0x08133614:
   h=self.r(r[1]);value={0x62:self.clip_steps,0x60:self.grid,0x61:self.absolute,0x73:self.clip_rows.get(h,16),0x133:self.selected_row}.get(r[2],500)
   self.w(r[3],value);self.ret(1)
  elif a==0x08131244:
   out=self.r(u.reg_read(UC_ARM_REG_SP));route=self.routes.get((self.r(r[1]),r[2],r[3]))
   if route:
    source,amount=route;self.w(out,amount);self.w(out+4,source|(r[2]<<16));self.w(out+8,r[3]);self.ret(1)
   else:self.ret(0)
  elif a==0x08131238:
   routes=[(key,slot,value) for (h,key,slot),value in self.routes.items() if h==self.r(r[1])]
   if r[2]<len(routes):
    key,slot,(source,amount)=routes[r[2]];self.w(r[3],amount);self.w(r[3]+4,source|(key<<16));self.w(r[3]+8,slot);self.ret(1)
   else:self.ret(0)
  elif a==0x08133388:
   _,h,key,source,amount=struct.unpack('<5I',u.mem_read(r[1],20))
   self.routes[h,key&65535,source>>16]=(source&65535,amount);self.ret(1)
  elif a==0x08124a7e:self.added_snapshots.append(r[2]);self.ret(1)
  elif a==0x0816fc34:self.posted.append(tuple(struct.unpack('<5I',u.mem_read(r[1],20))));self.ret()
  elif a==0x0813390e:u.mem_write(r[3],self.paths.get(self.r(r[1]),'').encode()+b'\0');self.ret(1)
  else:self.ret()

 def bind(self,key=0x33,handle=FILTER,lo=0,hi=1000,value=500):
  self.w(SLOT+0x34,handle);self.u.mem_write(SLOT+0x9c,struct.pack('<H',key))
  self.w(SLOT+0xa0,value);self.w(SLOT+0x450,lo);self.w(SLOT+0x454,hi)
  self.u.mem_write(SLOT+0x3f9,b'Resonance\0')
  self.w(SLOT+4,0);self.w(SLOT+8,80);self.w(SLOT+12,160);self.w(SLOT+16,70)

 def state(self):
  slot=self.call(UU['native_motion_state_slot'],0);return self.r(slot)

 def shared(self):return self.r(self.state()+4)

 def audio(self,tick):
  self.u.mem_write(TIME,struct.pack('<q',tick))
  self.call(AA['nm_audio_automation'],SEQUENCE,TIME)

 def turn(self,value,time=1000):
  self.w(0x3001fe2c,time);self.call(UU['nm_increment'],SLOT,100)
  self.u.mem_write(EVENT,struct.pack('<5I',0xd0,self.r(SLOT+0x34),struct.unpack('<H',self.u.mem_read(SLOT+0x9c,2))[0],value&0xffffffff,0))
  result=self.call(UU['nm_model_event'],EVENT)
  self.w(SLOT+0xa0,value);return result

 def lengths(self):
  return struct.unpack('<4H',self.u.mem_read(self.shared()+32+16,8))

 def show(self):
  self.u.mem_write(OUT,bytes(0x1c4));self.call(UU['nm_readout'],OUT);return self.text(OUT)

 def deliver(self):
  # Transport fixture copies the signed values of the native writer's packets.
  # The packet itself is asserted by test_native_automation.
  for command in self.commands:
   lane=struct.unpack_from('<H',command,2)[0]
   step=struct.unpack_from('<I',command,4)[0]//960
   value=struct.unpack_from('<i',command,20)[0]
   self.u.mem_write(SEQUENCE+0x240+0x3a+lane*0x202+step*2,struct.pack('<h',value))
   self.u.mem_write(SEQUENCE+0x240+0x23a+lane*0x202,b'\1')
  self.commands.clear()


class Tests(unittest.TestCase):
 def test_transport_stop_invalidates_clock_before_another_encoder_event(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  p.w(SEQUENCE+0x14,0xffffffff);p.call(AA['nm_audio_restart'],SEQUENCE)
  self.assertEqual(p.call(UU['nm_status']),1)
  p.turn(700,1050)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(p.undo,1);self.assertEqual(p.show(),'! NO PLAYING CLIP')
  self.assertEqual(p.call(UU['nm_enabled']),1)

 def test_negative_audio_time_cannot_leave_a_recordable_stale_clock(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  p.audio(-1);p.turn(700,1050)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(p.call(UU['nm_status']),1)

 def test_restart_at_same_tick_starts_a_new_take_and_undo_transaction(self):
  p=Recorder();p.audio(240);p.turn(600)
  p.w(SEQUENCE+0x14,0xffffffff);p.call(AA['nm_audio_restart'],SEQUENCE)
  p.w(SEQUENCE+0x14,0);p.u.mem_write(SEQUENCE+0x260,struct.pack('<q',240))
  p.audio(240);p.turn(700,1050)
  self.assertEqual(p.undo,2)
  self.assertEqual(p.read(0,0),100);self.assertEqual(p.read(0,1),100)

 def test_restart_with_unchanged_origin_still_ends_the_old_take(self):
  p=Recorder();p.turn(600)
  p.w(SEQUENCE+0x14,0xffffffff);p.call(AA['nm_audio_restart'],SEQUENCE)
  p.w(SEQUENCE+0x14,0);p.audio(0);p.turn(700,1050)
  self.assertEqual(p.undo,2);self.assertEqual(p.read(0,0),200)

 def test_stopped_wait_does_not_grow_or_erase_the_existing_lane(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  p.u.mem_write(SEQUENCE+0x20,b'\0');p.audio(3840)
  for i in range(10):
   p.w(0x3001fe2c,1200+i*100);self.assertEqual(p.call(UU['nm_status']),1)
  self.assertEqual(p.lengths()[0],16)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(p.call(UU['nm_enabled']),1)

 def test_selection_change_between_encoder_and_model_event_is_not_a_new_clip_take(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  clip2=56;p.nodes[clip2]=NODE-0x1000;p.clip_rows[clip2]=1
  p.children[OWNER].insert(0,clip2)
  p.call(UU['nm_increment'],SLOT,100)
  p.selected_row=1
  p.w(SEQUENCE+0x86c0,SEQUENCE+0x240+0x848);p.w(SEQUENCE+0x240+0x848+4,16);p.audio(240)
  p.u.mem_write(EVENT,struct.pack('<5I',0xd0,FILTER,0x33,700,0))
  self.assertEqual(p.call(UU['nm_model_event'],EVENT),1)
  self.assertEqual(p.undo,1)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(bytes(p.u.mem_read(NODE-0x1000,NODE_BYTES)),bytes(NODE_BYTES))
  self.assertEqual(p.show(),'! CLIP CHANGED')

 def test_toggle_touch_does_not_allocate_and_partial_initialization_is_resumable(self):
  p=Recorder(initialize=False);cursor=p.next
  for _ in range(4):
   p.call(UU['nm_set_enabled'],1);p.call(UU['nm_set_enabled'],0)
  self.assertEqual(p.next,cursor);self.assertEqual(p.r(0x24041984),0)
  p.call(UU['nm_set_enabled'],1);self.assertEqual(p.call(UU['nm_status']),1)
  allocated=p.next;self.assertGreater(allocated,cursor)
  self.assertEqual(p.r(0x24041998),1024);self.assertEqual(p.r(0x24041984),0)
  p.call(UU['nm_set_enabled'],0);p.call(UU['nm_status'])
  self.assertEqual(p.next,allocated);self.assertEqual(p.r(0x24041998),1024)
  p.call(UU['nm_set_enabled'],1)
  for _ in range(32):p.call(UU['nm_status'])
  self.assertEqual(p.next,allocated);self.assertNotEqual(p.r(0x24041984),0)
  p.audio(0);p.turn(600);self.assertEqual(p.read(0,0),100)

 def test_circle_reports_waiting_writing_empty_and_saved_motion(self):
  p=Recorder();self.assertEqual(p.call(UU['nm_enabled']),1)
  self.assertEqual(p.call(UU['nm_status']),1)
  p.turn(600);self.assertEqual(p.call(UU['nm_status']),2)
  p.w(0x3001fe2c,1161);self.assertEqual(p.call(UU['nm_status']),1)
  p.call(UU['nm_set_enabled'],0);self.assertEqual(p.call(UU['nm_status']),3)
  p.u.mem_write(NODE+0x80a,b'\0')
  self.assertEqual(p.call(UU['nm_status']),0)

 def test_toggle_is_idempotent_and_normal_page_changes_do_not_end_take(self):
  p=Recorder();p.turn(600);cursor=p.next
  for page in (0x1a,0x17,0x27,0):
   p.u.mem_write(MODEL+0x12c,bytes([page]))
   p.call(UU['nm_set_enabled'],1);p.call(UU['nm_status'])
   self.assertEqual(p.call(UU['nm_enabled']),1)
  p.audio(240);p.turn(700,1100)
  self.assertEqual(p.undo,1);self.assertEqual(p.next,cursor)

 def test_clip_switch_keeps_enabled_and_preserves_prior_native_take(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  clip2=56;node2=NODE-0x1000;p.nodes[clip2]=node2
  p.clip_rows[clip2]=1;p.types[clip2]=24;p.children[OWNER].insert(0,clip2)
  p.selected_row=1
  # Selection differs from the playing row: don't write to either clip.
  self.assertEqual(p.call(UU['nm_status']),1)
  p.turn(700,1050);self.assertEqual(p.undo,1)
  p.w(SEQUENCE+0x86c0,SEQUENCE+0x240+0x848);p.w(SEQUENCE+0x240+0x848+4,16);p.audio(240)
  p.turn(800,1100)
  self.assertEqual(p.call(UU['nm_enabled']),1);self.assertEqual(p.undo,2)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(struct.unpack('<h',p.u.mem_read(node2+12,2))[0],100)
  p.call(UU['nm_set_enabled'],0);self.assertEqual(p.call(UU['nm_status']),3)
  p.u.mem_write(node2+0x80a,b'\0')
  self.assertEqual(p.call(UU['nm_status']),0)
  p.selected_row=0;self.assertEqual(p.call(UU['nm_status']),3)

 def test_selected_track_switch_starts_new_take_without_toggling_off(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  owner2=101;filter2=0x206;clip2=56;node2=NODE-0x1000
  p.nodes[clip2]=node2;p.clip_rows[clip2]=0;p.types.update({owner2:18,filter2:10,clip2:24})
  p.children[owner2]=[clip2,filter2];p.selected_owner=owner2
  p.w(SEQUENCE+12,owner2);p.audio(240);p.bind(handle=filter2);p.turn(650)
  self.assertEqual(p.call(UU['nm_enabled']),1);self.assertEqual(p.undo,2)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(p.routes[filter2,0x33,0],(9,1000))

 def test_project_finish_disarms_without_erasing_native_samples(self):
  p=Recorder();p.turn(600);before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  p.call(UU['nm_finish'])
  self.assertEqual(p.call(UU['nm_enabled']),0)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(p.r(p.shared()+20),0)

 def test_disabled_parameter_turns_and_record_buttons_cannot_capture(self):
  p=Recorder();p.call(UU['nm_set_enabled'],0)
  before=bytes(p.u.mem_read(NODE,NODE_BYTES));cursor=p.next
  for pressed in (0xaf,0xb0):p.call(UU['nm_dispatch'],pressed,14)
  p.turn(600)
  self.assertEqual(p.call(UU['nm_enabled']),0);self.assertEqual(p.next,cursor)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
  self.assertEqual(p.routes,{})

 def test_off_status_uses_selected_clip_not_prior_capture(self):
  p=Recorder();p.turn(600);p.call(UU['nm_set_enabled'],0)
  p.selected_row=1
  self.assertEqual(p.call(UU['nm_status']),0)
  p.selected_row=0
  self.assertEqual(p.call(UU['nm_status']),3)

 def test_virtual_macro_target_is_explicitly_refused_without_writing(self):
  p=Recorder()
  h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(1),
                 begin=UU['macro_overlay'],end=UU['macro_overlay'])
  try:p.turn(600)
  finally:p.u.hook_del(h)
  self.assertEqual(p.show(),'! NOT A TARGET')
  self.assertEqual(p.routes,{});self.assertEqual(p.undo,0)
  self.assertEqual(p.call(UU['nm_status']),1)

 def test_reenable_preserves_samples_and_opens_a_new_undo_transaction(self):
  p=Recorder();p.turn(600);p.write(0,7,789)
  p.call(UU['nm_set_enabled'],0);p.call(UU['nm_set_enabled'],1)
  p.turn(700)
  self.assertEqual(p.read(0,7),789);self.assertEqual(p.undo,2)
  self.assertEqual(p.read(0,0),200)

 def test_turn_assigns_first_free_lane_and_uses_native_signed_writer(self):
  p=Recorder();self.assertEqual(p.turn(600),1)
  self.assertEqual(p.routes,{(FILTER,0x33,0):(9,1000)})
  self.assertEqual(p.read(0,0),100);self.assertEqual(p.lengths(),(16,0,0,0))
  self.assertEqual(p.undo,1);self.assertEqual(p.added_snapshots,[FILTER])
  p.audio(240);p.turn(650,1050)
  self.assertEqual(p.read(0,1),150);self.assertEqual(p.undo,1)
  self.assertEqual(p.u.mem_read(NODE+NODE_BYTES,16),b'\xa5'*16)

 def test_actual_native_encoder_hook_reaches_the_shipped_model_interceptor(self):
  p=Recorder();v=BAR-0x38;p.call(0x0815e228,v)
  p.call(0x08171c1c,SLOT,0x33,500,1);p.w(SLOT+0x34,FILTER)
  p.call(0x08171e44,SLOT,4000)
  self.assertEqual(len(p.posted),1)
  event=p.posted[0];self.assertEqual(event[0],0xcf);self.assertEqual(event[2],0x33)
  # The native page-to-model event queue is the transport fixture boundary.
  p.u.mem_write(EVENT,struct.pack('<5I',0xd0,FILTER,event[2],event[3],0))
  self.assertEqual(p.call(UU['analog_model_event'],MODEL,EVENT),1)
  self.assertEqual(p.read(0,0),event[3]-500)
  self.assertEqual(p.routes[FILTER,0x33,0],(9,1000))

 def test_existing_lanes_and_routes_are_not_stolen(self):
  p=Recorder();p.routes[OWNER,2,0]=(9,1000);p.write(1,0,50)
  p.turn(600);self.assertEqual(p.routes[FILTER,0x33,0],(11,1000))
  self.assertEqual(p.read(1,0),50)

 def test_full_refuses_without_changing_samples_routes_or_parameter(self):
  p=Recorder()
  for lane in range(4):p.write(lane,0,lane+10)
  before=bytes(p.u.mem_read(NODE,NODE_BYTES));p.undo=0;p.commands.clear()
  p.turn(600)
  self.assertEqual(p.show(),'! FULL');self.assertEqual(p.routes,{})
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before);self.assertEqual(p.undo,0)

 def test_signed_scaling_uses_parameter_range_and_existing_route_depth(self):
  p=Recorder();p.bind(lo=25,hi=180,value=100)
  p.routes[FILTER,0x33,1]=(11,500);p.write(2,0,-200);p.undo=0
  p.turn(131)
  self.assertEqual(p.read(2,0),200)
  self.assertEqual(p.routes[FILTER,0x33,1],(11,500))

 def test_punch_in_does_not_overwrite_unmoved_gaps(self):
  p=Recorder();p.routes[FILTER,0x33,0]=(9,1000)
  for step in range(16):p.write(0,step,step*10)
  p.undo=0;p.turn(600);p.audio(4*240);p.turn(650,1500)
  self.assertEqual([p.read(0,i) for i in range(1,4)],[10,20,30])
  self.assertEqual(p.read(0,4),150);self.assertEqual(p.undo,1)

 def test_continuous_movement_interpolates_only_crossed_steps(self):
  p=Recorder();p.turn(500);p.audio(4*240);p.turn(900,1100)
  self.assertEqual([p.read(0,i) for i in range(5)],[0,100,200,300,400])
  self.assertEqual(p.read(0,5),0)

 def test_length_grows_2x_4x_8x_then_caps_at_256(self):
  p=Recorder();p.clip_steps=64;p.turn(600)
  for steps,length in ((63,64),(64,128),(127,128),(128,256),(256,256),(512,256)):
   p.audio(steps*240);p.show();self.assertEqual(p.lengths()[0],length)
  self.assertIn('16b',p.show())

 def test_independent_playback_does_not_restart_when_the_clip_wraps(self):
  p=Recorder();p.turn(600);p.audio(16*240);p.show();p.turn(900,1300);p.deliver()
  self.assertEqual(p.lengths()[0],32)
  for step,expected in ((0,.1),(16,.4),(32,.1),(48,.4)):
   p.w(SEQUENCE+0x14,step%16)
   # Native clip origin changes on a normal loop; motion origin must not.
   p.u.mem_write(SEQUENCE+0x260,struct.pack('<q',(step//16)*3840))
   p.audio(step*240)
   self.assertAlmostEqual(struct.unpack('<f',p.u.mem_read(SEQUENCE+0x8720,4))[0],expected,places=5)

 def test_clip_switch_and_explicit_restart_reset_motion_phase(self):
  p=Recorder();p.turn(600);p.audio(3840);p.show();p.turn(900,1300);p.deliver()
  p.audio(3840);self.assertAlmostEqual(struct.unpack('<f',p.u.mem_read(SEQUENCE+0x8720,4))[0],.4,places=5)
  p.w(SEQUENCE+0x14,0xffffffff);p.call(AA['nm_audio_restart'],SEQUENCE)
  p.u.mem_write(SEQUENCE+0x260,struct.pack('<q',3840));p.w(SEQUENCE+0x14,0);p.audio(3840)
  self.assertAlmostEqual(struct.unpack('<f',p.u.mem_read(SEQUENCE+0x8720,4))[0],.1,places=5)
  p.w(SEQUENCE+0x86c0,SEQUENCE+0x240+0x848);p.audio(4000)
  self.assertEqual(struct.unpack('<f',p.u.mem_read(SEQUENCE+0x8720,4))[0],0)

 def test_motion_toggle_never_changes_native_recording_in_either_mode(self):
  for mode in (0,1):
   for recording in (0,1):
    p=Recorder();p.u.mem_write(ROOT+0x40,bytes([mode]));state=ROOT+(0x14b if mode else 0x8be9)
    p.u.mem_write(state,bytes([recording]))
    p.turn(600);p.call(UU['nm_set_enabled'],0);p.call(UU['nm_set_enabled'],1)
    self.assertEqual(p.u.mem_read(state,1),bytes([recording]))

 def test_ordinary_record_press_and_release_keeps_native_toggle(self):
  p=Recorder();p.call(0x08058500,ROOT,1);p.call(0x08058500,ROOT,0)
  p.call(UU['nm_dispatch'],0xb0,14)
  self.assertEqual(p.u.mem_read(ROOT+0x8be9,1),b'\1')

 def test_refused_target_never_changes_native_recording(self):
  p=Recorder();p.call(0x08058500,ROOT,1)
  for lane in range(4):p.write(lane,0,1)
  p.turn(600);p.call(UU['nm_set_enabled'],0)
  p.call(0x08058500,ROOT,0)
  self.assertEqual(p.u.mem_read(ROOT+0x8be9,1),b'\1')

 def test_parameter_tap_does_not_clear_under_toggle_mode(self):
  p=Recorder();p.turn(600);p.write(1,7,111)
  point=OUT;p.w(point,80);p.w(point+4,100)
  self.assertEqual(p.call(UU['nm_tap'],BAR,point),0)
  self.assertEqual(p.read(0,0),100);self.assertEqual(p.read(1,7),111)
  self.assertEqual(p.lengths()[0],16)
  self.assertEqual(p.undo,1)
  p.turn(650);self.assertEqual(p.read(0,0),150);self.assertEqual(p.undo,1)

 def test_small_turns_accumulate_without_fractional_loss(self):
  p=Recorder();p.bind(hi=10000)
  for i in range(1,11):p.turn(500+i)
  self.assertEqual(p.read(0,0),1)
  for i in range(9,-1,-1):p.turn(500+i)
  self.assertEqual(p.read(0,0),0)

 def test_lane_duration_uses_native_step_length_and_absolute_time_mode(self):
  for grid,absolute,expected in ((10,0,16),(8,0,32),(6,0,64),(10,1,64),(14,0,4)):
   p=Recorder();p.grid=grid;p.absolute=absolute;p.turn(600)
   self.assertEqual(p.lengths()[0],expected)

 def test_sampler_parameters_use_the_actual_native_matrix_key_table(self):
  p=Recorder();p.types[FILTER]=1;p.bind(key=2);p.turn(600)
  self.assertEqual(p.routes[FILTER,2,0],(9,1000));self.assertEqual(p.read(0,0),100)

 def test_drum_synth_targets_reuse_the_existing_engine_and_native_matrix_routes(self):
  for path in ('bento_kick.wav','bento_synth_snare.wav','bento_synth_hihat.wav'):
   p=Recorder();file=123;p.children[OWNER].append(file)
   p.types[FILTER]=1;p.types[file]=5;p.types[OWNER]=14;p.paths[file]='\\P\\'+path
   matrix=0xc0000000+0x8a000;frame=0x20037000
   p.w(matrix+0xc44,FILTER);p.w(frame+0x338,OWNER)
   p.call(UU['mod_rows'],0xc0000000,frame)
   p.bind(key=0x1a1,lo=0,hi=100,value=50);p.turn(60)
   self.assertEqual(p.routes[FILTER,0x1a1,0],(9,1000));self.assertEqual(p.read(0,0),100)

 def test_parameter_tap_preserves_multiple_assigned_lanes(self):
  p=Recorder();p.routes[FILTER,0x33,0]=(9,1000);p.routes[FILTER,0x33,1]=(10,1000)
  p.write(0,3,200);p.write(1,7,-400);p.undo=0
  p.w(OUT,80);p.w(OUT+4,100)
  p.call(UU['nm_tap'],BAR,OUT)
  self.assertEqual(p.read(0,3),200);self.assertEqual(p.read(1,7),-400);self.assertEqual(p.undo,0)

 def test_turn_outside_the_selected_track_is_refused(self):
  p=Recorder();p.bind(handle=999);p.turn(600)
  self.assertEqual(p.routes,{});self.assertEqual(p.show(),'! NOT A TARGET')

 def test_metadata_survives_the_shipped_native_save_load_wrapper_chain(self):
  from unicorn.arm_const import UC_ARM_REG_R6
  p=Recorder();p.turn(600);p.audio(3840);p.show()
  obj=0x20010000;p.w(obj+0x10,CLIP);p.u.mem_write(obj+4,b'\x18')
  p.u.reg_write(UC_ARM_REG_R6,obj)
  h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x0812f5ee,end=0x0812f5ee)
  try:p.call(0x0812f5ea,0x20017000)
  finally:p.u.hook_del(h)
  self.assertEqual({k:v for k,v in p.attrs.items() if k.startswith('bento_motion')},
                   {'bento_motion_v1_A':32,'bento_motion_v1_B':0,'bento_motion_v1_C':0,'bento_motion_v1_D':0})
  q=Recorder();q.attrs=dict(p.attrs);q.w(obj+0x10,CLIP);q.u.mem_write(obj+4,b'\x18')
  h=q.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:q.ret(),begin=0x0812fab0,end=0x0812fab0)
  try:q.call(0x0812faac,0x20011000,obj)
  finally:q.u.hook_del(h)
  q.call(UU['nm_finish']);self.assertEqual(q.lengths()[0],32)

 def test_native_xml_encoder_includes_the_256th_sample_not_only_clip_length(self):
  p=Recorder();p.turn(600);p.write(0,255,-1234)
  obj=0x20010000;p.w(obj+0x10,CLIP)
  self.assertEqual(p.call(UU['nm_serialized_steps'],obj,0x62),256)
  p.u.reg_write(UC_ARM_REG_R8,obj);p.u.reg_write(UC_ARM_REG_R6,NODE)
  stop=p.stop;p.stop=0x0812f88e
  p.call(0x0812f860)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_R7),256)
  scratch=p.r(0x0812fa88);p.w(scratch,0xc0064000)
  p.u.reg_write(UC_ARM_REG_R2,0);p.stop=0x0812f91a
  p.call(0x0812f890);p.stop=stop
  encoded=bytes(p.u.mem_read(0xc0064000,1537)).split(b'\0')[0].decode()
  # Native codec: repeat-count byte, signed sample word, both hexadecimal.
  values=[]
  for i in range(0,len(encoded),6):
   count=int(encoded[i:i+2],16);value=int(encoded[i+2:i+6],16)
   if value>=32768:value-=65536
   values.extend([value]*count)
  self.assertEqual(len(values),256);self.assertEqual(values[0],100);self.assertEqual(values[255],-1234)
  q=Recorder();q.attrs={'idx':0,'slide':1};q.u.mem_write(0x20034000,encoded.encode()+b'\0')
  def xml(u,a,n,d):
   if a==0x0812dfc0:q.w(u.reg_read(UC_ARM_REG_R3),NODE);q.ret(1)
   elif a==0x08109cc4:q.ret(0x20034000)
   else:q.ret(0)
  for address in (0x0812dfc0,0x08109cc4,0x081092aa):
   q.u.hook_add(UC_HOOK_CODE,xml,begin=address,end=address)
  q.call(0x0812ffa8,0x20011000,0xc0070000,0x20010000)
  self.assertEqual([q.read(0,i) for i in range(256)],values)
  self.assertEqual(q.u.mem_read(NODE+0x80e,1),b'\1')

 def test_clone_wrapper_preserves_native_stack_argument_and_callee_saved_registers(self):
  p=Recorder();p.turn(600);p.audio(3840);p.show()
  source=0xc0060000;dest=source+0x100;vt=source+0x200;out=OUT
  for obj,handle in ((source,CLIP),(dest,56)):
   p.w(obj,vt);p.w(obj+0x10,handle)
  p.u.mem_write(0x081ff110,bytes.fromhex('00207047'));p.w(vt+0x18,0x081ff111)
  observed=[]
  def clone(u,a,n,d):
   sp=u.reg_read(UC_ARM_REG_SP)
   observed.append(tuple(u.reg_read(reg) for reg in REGS)+(p.r(sp+24),))
   p.w(p.r(sp+24),dest)
   for reg,off in ((UC_ARM_REG_R4,8),(UC_ARM_REG_R5,12),(UC_ARM_REG_R6,16)):u.reg_write(reg,p.r(sp+off))
   u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_SP,sp+24);u.reg_write(UC_ARM_REG_PC,p.r(sp+20))
  h=p.u.hook_add(UC_HOOK_CODE,clone,begin=0x0812ea2e,end=0x0812ea2e)
  saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8]
  for i,reg in enumerate(saved):p.u.reg_write(reg,0x123400+i)
  try:self.assertEqual(p.call(0x0812ea2a,0xc0070000,24,OWNER,source,out),1)
  finally:p.u.hook_del(h)
  self.assertEqual(observed,[(0xc0070000,24,OWNER,source,out)])
  self.assertEqual([p.u.reg_read(reg) for reg in saved],[0x123400+i for i in range(5)])
  p.call(UU['nm_rebuild'],56,OWNER);self.assertEqual(p.lengths()[0],32)

 def test_length_descriptor_is_preflighted_and_restored_byte_for_byte(self):
  p=Recorder();p.turn(600);p.call(UU['nm_set_enabled'],0)
  p.u.mem_map(0xc0400000,0x140000);v=0xc0400000
  p.call(0x0815930c,v)
  p.u.mem_write(MODEL+0x12c,b'\x17');p.w(v+0x11cd00,CLIP);p.w(v+0x11cd08,OWNER)
  p.u.mem_write(v+0x125dac,b'\2');p.w(v+0x125d34,0)
  registry=p.r(0x30031484);d=registry+0x176*32;before=bytes(p.u.mem_read(d,32))
  p.call(0x081599bc,v)
  self.assertEqual(p.text(p.r(d+4)),'Lane Steps')
  self.assertEqual(list(struct.unpack('<8H',p.u.mem_read(v+0x11bcc0,16))),
                   [0x1dd,0x1de,0x176,0,0,0,0x1db,0x1dc])
  p.call(UU['nm_header_before'],0)
  self.assertEqual(bytes(p.u.mem_read(d,32)),before)
  p.w(d+4,0xdeadbeef);p.call(UU['nm_header_after'],v)
  self.assertEqual(p.r(d+4),0xdeadbeef);self.assertEqual(p.show(),'! LENGTH OWNER')

 def test_editable_length_changes_neither_clip_nor_recorded_tail(self):
  p=Recorder();p.turn(600);p.write(0,200,777);p.call(UU['nm_set_enabled'],0)
  v=0xc0400000;p.u.mem_map(v,0x140000);p.call(0x0815930c,v)
  p.u.mem_write(MODEL+0x12c,b'\x17');p.w(v+0x11cd00,CLIP);p.w(v+0x11cd08,OWNER)
  p.u.mem_write(v+0x125dac,b'\2');p.w(v+0x125d34,0)
  before=bytes(p.u.mem_read(NODE,NODE_BYTES))
  for length in (8,256,33):
   p.u.mem_write(EVENT,struct.pack('<5I',0xcf,CLIP,0x176,length,0))
   self.assertEqual(p.call(UU['nm_view_event'],v,EVENT),1)
   self.assertEqual(p.lengths()[0],length);self.assertEqual(p.clip_steps,16)
   self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),before)
   p.w(HANDLE,CLIP)
   self.assertEqual(p.call(UU['nm_get'],MODEL,HANDLE,0x62,OUT,0x08159a1b),1)
   self.assertEqual(p.r(OUT),length)
  self.assertEqual(p.undo,4)

 def test_loading_an_empty_project_discards_old_motion_lengths(self):
  p=Recorder();p.turn(600);p.audio(3840);p.show()
  p.call(UU['nm_finish']);self.assertEqual(p.lengths()[0],0)
  obj=0x20010000;p.w(obj+0x10,CLIP)
  self.assertNotEqual(p.call(UU['nm_serialized_steps'],obj,0x62),256)

 def test_shared_runtime_slots_are_reusable_after_project_load(self):
  p=Recorder()
  for i in range(8):
   seq=SEQUENCE+i*0x9000
   p.call(0x08062a80,seq);p.w(seq+12,OWNER+i);p.w(seq+0x86c0,seq+0x240)
   p.u.mem_write(seq+0x20,b'\1');p.call(AA['nm_audio_automation'],seq,TIME)
  p.call(UU['nm_finish'])
  seq=SEQUENCE+8*0x9000;p.call(0x08062a80,seq);p.w(seq+12,OWNER)
  p.w(seq+0x86c0,seq+0x240);p.u.mem_write(seq+0x20,b'\1');p.call(AA['nm_audio_automation'],seq,TIME)
  base=p.shared()+32+128*32
  self.assertIn(seq,[p.r(base+i*64+4) for i in range(8)])

 def test_discarded_clone_metadata_does_not_exhaust_the_recorder(self):
  p=Recorder();p.turn(600)
  source=0xc0060000;dest=source+0x100;vt=source+0x200
  for obj in (source,dest):p.w(obj,vt)
  p.w(source+0x10,CLIP);p.w(OUT,dest)
  p.u.mem_write(0x081ff110,bytes.fromhex('00207047'));p.w(vt+0x18,0x081ff111)
  cursor=p.next
  for i in range(600):
   p.w(dest+0x10,56+i)
   p.call(UU['nm_clone'],0xc0070000,source,OUT,1)
  p.call(UU['nm_rebuild'],655,OWNER)
  self.assertEqual(p.lengths()[0],16);self.assertEqual(p.next,cursor)

 def test_no_motion_hook_ever_changes_native_node_size_or_protected_program(self):
  from pathlib import Path
  from test_integration import K16_IMAGE
  base=K16_IMAGE.read_bytes()
  for lo,hi in ((0x080e0000,0x08100000),(0x0812e8c6,0x0812e8e0)):
   self.assertEqual(IMAGE[lo-0x08040000:hi-0x08040000],base[lo-0x08040000:hi-0x08040000])


if __name__=='__main__':unittest.main(verbosity=2)
