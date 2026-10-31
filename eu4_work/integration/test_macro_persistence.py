"""Macro persistence through the shipped native save/load wrapper chain."""
import unittest
import struct
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                              UC_ARM_REG_R3, UC_ARM_REG_R4,
                              UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                              UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
                              UC_ARM_REG_R11, UC_ARM_REG_R12, UC_ARM_REG_PC,
                              UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_APSR)

from test_macro import Macros, UU, slot
from test_mod import TRACK, FILT1

OBJECT = 0x20010000
NODE = 0x20011000
PARAMS = 0x20017000
ATTRIBUTE = 'playground_macros_v1'
WORKER = 0x20028000


class ProjectMacros(Macros):
 def __init__(self):
  self.project=0x1000
  super().__init__()

 def model(self,u,a,n,d):
  if a==0x081403ec and getattr(self,'native_model',False):return
  super().model(u,a,n,d)

 def xml(self,u,a,n,d):
  if a==0x08133e54:
   self.w(u.reg_read(UC_ARM_REG_R1),self.project);self.ret(1)
  else:super().xml(u,a,n,d)


class PersistenceTests(unittest.TestCase):
 def blob(self,counts,version=2,sens=None):
  data=bytearray([version])
  for macro in range(8):
   count=counts.get(macro,0)
   data+=bytes([macro+1,count])+(bytes([(sens or {}).get(macro,2)]) if version==3 else b'')+b'Test'.ljust(12,b'\0')
   for target in range(count):
    data+=bytes([0,0xff,0xff])+struct.pack('<Hiiii',0x33+target,0,1000,100,900)
    if version>=2:data+=('Target %d'%target).encode().ljust(12,b'\0')
  return data.hex().upper()

 def mapped(self):
  p=ProjectMacros()
  p.map_resonance(0)
  p.perform();p.arm(0)
  self.assertEqual(p.call(UU['macro_armed']),0)
  return p

 def object(self,p,kind,handle):
  p.u.mem_write(OBJECT,bytes(32))
  p.u.mem_write(OBJECT+4,bytes([kind]));p.w(OBJECT+0x10,handle)

 def save(self,p,kind=21,handle=0xdead):
  self.object(p,kind,handle)
  p.u.reg_write(UC_ARM_REG_R6,OBJECT)
  # Stop only after both extension wrappers and displaced native instructions.
  h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x0812f5ee,end=0x0812f5ee)
  try:p.call(0x0812f5ea,PARAMS)
  finally:p.u.hook_del(h)
  return p.strings.get(ATTRIBUTE)

 def load(self,p,saved,kind=21):
  self.object(p,kind,0xbeef)
  p.attrs.clear();p.strings.clear()
  if saved is not None:p.attrs[ATTRIBUTE]=1;p.strings[ATTRIBUTE]=saved
  h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x0812fab0,end=0x0812fab0)
  try:p.call(0x0812faac,NODE,OBJECT)
  finally:p.u.hook_del(h)

 def worker(self,p,command):
  p.u.mem_write(WORKER,bytes(0x800))
  p.w(WORKER+0x120,17);p.w(WORKER+0x140,18)
  p.u.mem_write(WORKER+0x20+16+4,bytes([command]))
  p.w(WORKER+0x300,19)
  hits=[];diagnostics=[];hooks=[]
  def handler(u,a,n,d):
   hits.append(a);u.reg_write(UC_ARM_REG_PC,0x0812a667)
  def diagnostic(u,a,n,d):
   diagnostics.append(bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),100)).split(b'\0')[0].decode());p.ret()
  # Queue string copying is fixture-owned; command dequeue, jump table,
  # patched integer adapter and native event publication execute unchanged.
  hooks.append(p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x0810778c,end=0x0810778c))
  hooks.append(p.u.hook_add(UC_HOOK_CODE,diagnostic,begin=0x08104c00,end=0x08104c00))
  for address in (0x0812a810,0x0812a824,0x0812a842):
   hooks.append(p.u.hook_add(UC_HOOK_CODE,handler,begin=address,end=address))
  registers=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
             UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
  for i,reg in enumerate(registers):p.u.reg_write(reg,0x12340000+i)
  cursor=p.next
  try:p.call(0x0812a658,WORKER)
  finally:
   for hook in hooks:p.u.hook_del(hook)
  self.assertEqual(p.r(WORKER+0x120),18)
  self.assertEqual([p.u.reg_read(reg) for reg in registers],[0x12340000+i for i in range(8)])
  self.assertEqual(p.next,cursor)
  return hits,diagnostics

 def test_native_save_persists_on_settings_without_live_track_identity(self):
  p=self.mapped();p.values[(FILT1,0x33)]=0;p.turn(0,64)
  saved=self.save(p)
  self.assertIsNotNone(saved)
  self.assertTrue(saved.startswith('02'))
  self.assertEqual(saved[:6],'024001')

 def test_native_round_trip_restores_macro_and_resolves_target(self):
  p=self.mapped();p.values[(FILT1,0x33)]=0;p.turn(0,64)
  saved=self.save(p);self.assertIsNotNone(saved)
  q=ProjectMacros();self.load(q,saved);q.perform()
  self.assertEqual(q.value_text(0),'64')
  q.values[(FILT1,0x33)]=p.values[(FILT1,0x33)]
  q.turn(0,63)
  self.assertEqual(q.cf()[0][1:3],(FILT1,0x33))
  self.assertEqual(q.cf()[0][3],q.r(slot(1)+0x454))

 def test_tracks_and_children_do_not_duplicate_global_attribute(self):
  p=self.mapped()
  for kind in (1,10,14,18,22):
   self.assertIsNone(self.save(p,kind,TRACK))

 def test_empty_macros_write_no_attribute(self):
  self.assertIsNone(self.save(ProjectMacros()))

 def test_legacy_track_attribute_still_loads(self):
  p=self.mapped();saved=self.save(p);self.assertIsNotNone(saved)
  q=ProjectMacros();self.load(q,saved,18);q.perform()
  self.assertEqual(q.name(0),'Resonance')
  q.turn(0,1);self.assertEqual(q.cf()[0][1:3],(FILT1,0x33))

 def test_switch_to_empty_project_clears_and_return_restores(self):
  p=self.mapped();p.call(UU['macro_periodic'],0)
  saved=self.save(p);self.assertIsNotNone(saved)
  self.load(p,None);p.project=0x2000;p.call(UU['macro_periodic'],0)
  p.perform();self.assertEqual(p.name(0),'MACRO 1')
  p.turn(0,1);self.assertEqual(p.cf(),[])
  self.load(p,saved);p.project=0x3000;p.call(UU['macro_periodic'],0)
  if not p.overlay():p.perform()
  self.assertEqual(p.name(0),'Resonance')
  p.turn(0,1);self.assertEqual(p.cf()[0][1:3],(FILT1,0x33))

 def test_load_before_project_change_survives_header_tick(self):
  p=ProjectMacros();p.perform();p.call(UU['macro_periodic'],0)
  source=self.mapped();saved=self.save(source);self.assertIsNotNone(saved)
  self.load(p,saved)
  p.call(UU['macro_periodic'],0)
  p.project=0x2000;p.call(UU['macro_periodic'],0)
  if not p.overlay():p.perform()
  self.assertEqual(p.name(0),'Resonance')

 def test_three_targets_round_trip_all_eight_macros_and_exact_buffer_bound(self):
  saved=self.blob(dict.fromkeys(range(8),3))
  self.assertEqual(len(saved)+1,1811)
  p=ProjectMacros();self.load(p,saved)
  self.assertEqual(self.save(p),saved)
  p.perform();p.turn(0,1)
  self.assertEqual(len(p.cf()),3)

 def test_v3_sensitivity_round_trips_all_eight_macros_at_the_exact_buffer_bound(self):
  saved=self.blob(dict.fromkeys(range(8),3),3,{m:m%5 for m in range(8)})
  self.assertEqual(len(saved)+1,1827)
  p=ProjectMacros();self.load(p,saved)
  self.assertEqual(self.save(p),saved)

 def test_v3_rejects_an_unknown_sensitivity_atomically(self):
  saved=self.blob({0:3},3,{4:5})
  p=self.mapped();state=p.r(p.call(UU['macro_state_slot']))
  before=bytes(p.u.mem_read(state+28,16+8*3*40))
  self.load(p,saved)
  self.assertEqual(bytes(p.u.mem_read(state+28,16+8*3*40)),before)
  self.assertEqual(p.readout(),'! MACRO DATA')
  self.assertEqual(self.save(p),saved)

 def test_v1_three_targets_still_load_and_save_as_v2(self):
  p=ProjectMacros();self.load(p,self.blob({0:3,7:3},1))
  saved=self.save(p)
  self.assertIsNotNone(saved)
  self.assertTrue(saved.startswith('02'))
  q=ProjectMacros();self.load(q,saved)
  self.assertEqual(self.save(q),saved)

 def test_legacy_over_cap_is_atomic_visible_and_preserved_verbatim(self):
  for version in (1,2):
   for macro in (0,7):
    saved=self.blob({macro:8},version)
    p=self.mapped()
    state=p.r(p.call(UU['macro_state_slot']))
    before=bytes(p.u.mem_read(state+28,16+8*3*40))
    self.load(p,saved)
    self.assertEqual(bytes(p.u.mem_read(state+28,16+8*3*40)),before)
    self.assertEqual(p.readout(),'! MACROS MAX 3')
    self.assertEqual(self.save(p),saved)
    p.perform();p.turn(0,1)
    self.assertEqual(p.cf(),[])
    p.arm(0)
    self.assertEqual(p.call(UU['macro_armed']),0)
    self.assertEqual(self.save(p),saved)

 def test_malformed_and_trailing_data_never_partially_load_or_get_rewritten(self):
  good=self.blob({0:3,7:3})
  for saved in (good[:-2],good[:-1],good+'00',good[:180]+'GG'+good[182:]):
   p=self.mapped();self.load(p,saved)
   self.assertEqual(p.readout(),'! MACRO DATA')
   self.assertEqual(self.save(p),saved)

 def test_invalid_target_paths_and_ranges_are_rejected_atomically(self):
  for offset,value in [(15,b'\x10'),(16,b'\x40'),(17,b'\0'),(18,b'\0\0'),
                       (24,struct.pack('<i',0)),(28,struct.pack('<i',-1)),
                       (32,struct.pack('<i',1001))]:
   raw=bytearray.fromhex(self.blob({0:3}))
   raw[offset:offset+len(value)]=value;saved=raw.hex().upper()
   p=self.mapped();state=p.r(p.call(UU['macro_state_slot']))
   before=bytes(p.u.mem_read(state+28,16+8*3*40))
   self.load(p,saved)
   self.assertEqual(bytes(p.u.mem_read(state+28,16+8*3*40)),before)
   self.assertEqual(p.readout(),'! MACRO DATA')
   self.assertEqual(self.save(p),saved)

 def test_full_legacy_eight_by_eight_attribute_is_preserved_exactly(self):
  saved=self.blob(dict.fromkeys(range(8),8));self.assertEqual(len(saved),4450)
  p=ProjectMacros();self.load(p,saved)
  self.assertEqual(p.readout(),'! MACROS MAX 3')
  self.assertEqual(self.save(p),saved)

 def test_full_signed_range_interpolates_without_intermediate_overflow(self):
  raw=bytearray.fromhex(self.blob({0:1}))
  struct.pack_into('<iiii',raw,20,-2147483648,2147483647,-2147483648,2147483647)
  p=ProjectMacros();self.load(p,raw.hex().upper());p.perform()
  p.turn(0,126);self.assertEqual(p.cf()[0][3],2147483647)
  p.turn(0,-127);self.assertEqual(p.cf()[0][3],0x80000000)

 def test_rejected_state_clears_on_new_project_and_valid_load(self):
  p=ProjectMacros();saved=self.blob({7:8})
  self.load(p,saved);p.call(UU['macro_project_reset'])
  p.strings.clear()
  self.assertIsNone(self.save(p))
  self.load(p,saved);good=self.blob({0:3})
  self.load(p,good);self.assertEqual(self.save(p),good)

 def test_fourth_tap_and_turn_mapping_refuse_with_visible_capacity_feedback(self):
  for turning in (False,True):
   p=ProjectMacros();self.load(p,self.blob({0:3}))
   p.w(slot(1)+0x34,FILT1)
   p.perform();p.arm(0);p.leave()
   if turning: # knobs never map: the macro stays as it is
    p.turn(1,4000);p.change(0x33,800);self.assertEqual(p.readout(),'MAP M1 3/3')
   else:p.tap(1);self.assertEqual(p.readout(),'! FULL 3/3')
   self.assertEqual(bytes.fromhex(self.save(p))[2],3)

 def test_repeated_rejected_project_loads_reuse_preservation_storage(self):
  p=ProjectMacros();saved=self.blob({7:8})
  self.load(p,saved);cursor=p.next
  for _ in range(5):
   p.call(UU['macro_project_reset'])
   self.load(p,saved)
   self.assertEqual(self.save(p),saved)
   self.assertEqual(p.next,cursor)

 def test_rejection_without_memory_disables_macros_and_stays_visible(self):
  p=self.mapped();p.w(0x30000048,p.next)
  self.load(p,self.blob({7:8}))
  p.w(0x3001fe2c,60000)
  self.assertEqual(p.readout(),'! MACRO NO MEM')
  p.perform();p.turn(0,1)
  self.assertEqual(p.cf(),[])
  p.arm(0);self.assertEqual(p.call(UU['macro_armed']),0)
  p.strings.clear()
  self.assertIsNone(self.save(p))
  self.assertEqual(p.readout(),'! MACRO NO MEM')
  self.load(p,self.blob({0:3}))
  self.assertIsNotNone(self.save(p))

 def test_exhausted_rejected_data_cancels_dequeued_save_and_save_as(self):
  for command in (0x2d,0x2e):
   p=self.mapped();p.w(0x30000048,p.next);self.load(p,self.blob({7:8}))
   self.assertEqual(p.call(UU['macro_save_blocked']),1)
   hits,diagnostics=self.worker(p,command)
   self.assertEqual(hits,[])
   self.assertEqual(p.r(WORKER+0x300),20)
   self.assertEqual(bytes(p.u.mem_read(WORKER+0x160+24*3,20)),b'\x4c'+bytes(19))
   self.assertIn('project Save cancelled',diagnostics[0])
   self.assertEqual(p.readout(),'! MACRO NO MEM')

 def test_native_save_paths_continue_for_valid_empty_and_preserved_data(self):
  for saved in (None,self.blob({0:3}),self.blob({7:8})):
   for command,handler in ((0x2d,0x0812a810),(0x2e,0x0812a824)):
    p=ProjectMacros()
    if saved is not None:self.load(p,saved)
    hits,diagnostics=self.worker(p,command)
    self.assertEqual(hits,[handler])
    self.assertEqual(diagnostics,[])
    self.assertEqual(p.r(WORKER+0x300),19)

 def test_blocker_does_not_cancel_unrelated_native_request(self):
  p=self.mapped();p.w(0x30000048,p.next);self.load(p,self.blob({7:8}))
  hits,diagnostics=self.worker(p,0x25)
  self.assertEqual(hits,[0x0812a842])
  self.assertEqual(diagnostics,[])
  self.assertEqual(p.r(WORKER+0x300),19)
  self.assertEqual(p.call(UU['macro_save_blocked']),1)

 def test_dispatch_adapter_preserves_registers_stack_and_original_flags(self):
  for blocked in (False,True):
   p=self.mapped()
   if blocked:
    p.w(0x30000048,p.next);self.load(p,self.blob({7:8}))
   p.u.mem_write(WORKER,bytes(0x800));p.u.mem_write(WORKER+0x14,b'\x2d')
   registers=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
              UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
              UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,
              UC_ARM_REG_R12,UC_ARM_REG_LR,UC_ARM_REG_SP)
   before=[0x12340000+i for i in range(len(registers))]
   before[4]=WORKER;before[-2]=p.stop|1;before[-1]=0x2003e000
   for reg,value in zip(registers,before):p.u.reg_write(reg,value)
   p.u.reg_write(UC_ARM_REG_APSR,0xa8000000)
   stop=0x0812a666 if blocked else 0x0812a6c0
   hooks=[p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:u.emu_stop(),begin=stop,end=stop),
          p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x08104c00,end=0x08104c00)]
   try:p.u.emu_start(0x0812a6bd,p.stop,count=100000)
   finally:
    for hook in hooks:p.u.hook_del(hook)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_PC),stop)
   if not blocked:before[3]=0x28
   self.assertEqual([p.u.reg_read(reg) for reg in registers],before)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_APSR)&0xf8000000,0xa8000000 if blocked else 0x28000000)

 def test_native_save_recovers_after_valid_reload_or_project_reset(self):
  for reset in (True,False):
   p=self.mapped();p.w(0x30000048,p.next);self.load(p,self.blob({7:8}))
   if reset:p.call(UU['macro_project_reset'])
   else:self.load(p,self.blob({0:3}))
   hits,diagnostics=self.worker(p,0x2d)
   self.assertEqual(hits,[0x0812a810]);self.assertEqual(diagnostics,[])
   self.assertEqual(p.call(UU['macro_save_blocked']),0)

 def test_load_without_macro_or_mod_allocation_still_blocks_native_save(self):
  for owner in ('macro','mod'):
   p=ProjectMacros()
   if owner=='macro':
    address=p.call(UU['macro_state_slot']);self.assertTrue(address)
    self.assertEqual(p.r(address),0)
   else:self.assertEqual(p.call(UU['macro_existing_slot']),0)
   p.w(0x30000048,p.next)
   diagnostics=[]
   def diagnostic(u,a,n,d):diagnostics.append(a);p.ret()
   hook=p.u.hook_add(UC_HOOK_CODE,diagnostic,begin=0x08104c00,end=0x08104c00)
   try:self.load(p,self.blob({0:3}))
   finally:p.u.hook_del(hook)
   self.assertEqual(len(diagnostics),1)
   self.assertEqual(p.readout(),'! MACRO NO MEM')
   hits,diagnostics=self.worker(p,0x2d)
   self.assertEqual(hits,[]);self.assertEqual(len(diagnostics),1)
   p.w(0x30000048,0xc0200000)
   p.call(UU['macro_view_set'],1)
   self.assertEqual(p.call(UU['macro_save_blocked']),1)
   self.assertEqual(p.readout(),'! MACRO NO MEM')
   self.load(p,self.blob({0:3}))
   self.assertEqual(p.call(UU['macro_save_blocked']),0)

 def test_sd_save_action_is_consumed_before_native_reset_request(self):
  p=self.mapped();p.w(0x30000048,p.next);self.load(p,self.blob({7:8}))
  p.native_model=True
  seen=[];hooks=[]
  def diagnostic(u,a,n,d):seen.append(bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),100)).split(b'\0')[0].decode());p.ret()
  def native(u,a,n,d):seen.append(a);p.ret()
  hooks.append(p.u.hook_add(UC_HOOK_CODE,diagnostic,begin=0x08104c00,end=0x08104c00))
  for address in (0x081403f0,0x081314c4,0x08106bd8):
   hooks.append(p.u.hook_add(UC_HOOK_CODE,native,begin=address,end=address))
  event=0x20015000
  try:
   p.u.mem_write(event,struct.pack('<5I',0x101d,0,0,0,0))
   p.call(0x081403ec,0x30024b00,event)
   self.assertEqual(len(seen),1);self.assertIn('save/SD-card mode cancelled',seen[0])
   self.assertEqual(p.r(0x30024b00+0x36c5)&255,0)
   seen.clear()
   p.u.mem_write(event,struct.pack('<5I',0x101e,0,0,0,0))
   p.call(0x081403ec,0x30024b00,event)
   self.assertEqual(seen,[0x081403f0])
   p.call(UU['macro_project_reset']);seen.clear()
   p.u.mem_write(event,struct.pack('<5I',0x101d,0,0,0,0))
   p.call(0x081403ec,0x30024b00,event)
   self.assertEqual(seen,[0x081403f0])
  finally:
   for hook in hooks:p.u.hook_del(hook)


if __name__=='__main__':unittest.main(verbosity=2)
