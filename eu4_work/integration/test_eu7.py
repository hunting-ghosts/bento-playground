"""EU7 native selected-note editing and immutable conditional payloads."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import unittest,struct,gc
from test_editable_eu import Edit
from test_live import UU,note
from unicorn.arm_const import UC_ARM_REG_R0
class Tests(unittest.TestCase):
 def event(self,p):
  e=0x2002e000;p.w(e,0x1051);return p.call(UU['seq_select_event'],p.seqview,e)
 def selected(self,p,n):return p.call(0x0815b9c0,p.seqview,n)
 def test_select_mode_taps_never_toggle_notes_and_persist_after_release(self):
  p=Edit(notes=[]);p.generated();before=p.events();self.assertEqual(self.event(p),1)
  for n in [0,3]:
   p.call(0x0815d1ec,p.seqview,n);p.call(0x0815d23c,p.seqview,n)
  self.assertEqual(p.events(),before);self.assertEqual([self.selected(p,n) for n in [0,1,3,5]],[1,0,1,0])
  p.call(0x0815d1ec,p.seqview,0);p.call(0x0815d23c,p.seqview,0)
  self.assertEqual(self.selected(p,0),0);self.assertEqual(self.selected(p,3),1)
  p.call(0x0815d1ec,p.seqview,1);p.call(0x0815d23c,p.seqview,1)
  self.assertEqual(p.events(),before);self.assertEqual(self.selected(p,1),0)
 def test_r610_select_reads_deselect_and_clears_a_held_step(self):
  # R6.10 (owner): with a step selected the Select button is Deselect and only clears it.
  p=Edit(notes=[]);p.generated();p.call(0x0815d1ec,p.seqview,2) # a held/opened step
  self.assertTrue(any(p.r(p.seqview+0x11420+i*4) for i in range(32)))
  self.assertEqual(p.call(UU['steps_selected'],p.seqview),1)
  self.assertEqual(self.event(p),1)
  self.assertEqual([i for i in range(32) if p.r(p.seqview+0x11420+i*4)],[]);self.assertEqual(p.call(UU['steps_selected'],p.seqview),0)
  # Not switched into Select mode: the next press is Select again (taps then select, never toggle).
  before=p.events();self.assertEqual(self.event(p),1);p.call(0x0815d1ec,p.seqview,0);p.call(0x0815d23c,p.seqview,0)
  self.assertEqual(p.events(),before);self.assertEqual(self.selected(p,0),1)
  # Select ON switches the mode off and keeps the picks; then it reads Deselect and clears them.
  self.event(p);self.assertEqual(self.selected(p,0),1);self.event(p);self.assertEqual(self.selected(p,0),0)
 def test_multi_selection_native_velocity_and_locks_edit_only_selected_notes(self):
  p=Edit(notes=[]);p.generated();self.event(p)
  for n in [0,3]:p.call(0x0815d1ec,p.seqview,n);p.call(0x0815d23c,p.seqview,n)
  p.call(0x0815c7c4,p.seqview,39);p.call(UU['locks_header_before'],p.seqview)
  p.call(UU['locks_encoder'],p.seqview,2,(-18000)&0xffffffff)
  self.assertEqual([struct.unpack_from('<H',e,18)[0] for e in p.events()],[39,39,100])
  self.assertEqual([struct.unpack_from('<I',e,20)[0] for e in p.events()],[0x5101030c,0x5101030c,0])
 def test_conditional_lock_on_every_second_cycle_keeps_all_notes(self):
  w=0x5101030c;p=Edit(notes=[]);p.generated();token=p.call(UU['locks_condition_word'],w,101)
  self.assertEqual(p.call(UU['locks_condition_get'],token),101)
  # Select one generated note, then use actual PROJ+encoder3 handler.
  p.select(0);p.call(UU['locks_header_before'],p.seqview);p.call(UU['locks_encoder'],p.seqview,2,(-18000)&0xffffffff)
  p.call(UU['locks_proj'],p.model,1);p.call(UU['locks_encoder'],p.seqview,N.NKEY(0x198),101);p.call(UU['locks_proj'],p.model,0)
  self.assertEqual(p.call(UU['locks_condition_get'],struct.unpack_from('<I',p.events()[0],20)[0]),101)
  p.sync();p.across(21)
  hits=[(round(t/6000),p.locktrace[i]) for i,(pad,t) in enumerate(p.absolute) if pad==2 and round(t/6000)%7==0]
  self.assertEqual(hits[:3],[(0,0),(7,w),(14,0)])
 def test_immutable_payloads_preserve_prior_values_and_deduplicate(self):
  p=Edit();a=p.call(UU['locks_condition_word'],0x5101030c,100);b=p.call(UU['locks_condition_word'],0x5101030d,100)
  self.assertNotEqual(a,b);self.assertEqual(p.call(UU['locks_condition_word'],0x5101030c,100),a)
  self.assertEqual(p.call(UU['locks_slot'],a,0),0x5101030c);self.assertEqual(p.call(UU['locks_slot'],b,0),0x5101030d)
  self.assertEqual(p.call(UU['locks_condition_word'],a,0),0x5101030c)
 def test_native_manual_condition_filter_uses_native_loop_and_keeps_hit(self):
  p=Edit();w=0x5101030c;t=p.call(UU['locks_condition_word'],w,101)
  import json,os
  from pathlib import Path
  aa=json.loads((Path(os.environ['BENTO_FX_CANDIDATE'])/'manifest.json').read_text())['audio_symbols']
  c=0x24048a60
  for off,val in [(0,p.audioseq),(4,p.r(p.audioseq+12)),(8,p.clip),(12,0)]:p.w(c+off,val)
  self.assertEqual(p.call(aa['locks_native_filter'],p.audioseq,t),0);p.w(c+12,1)
  self.assertEqual(p.call(aa['locks_native_filter'],p.audioseq,t),w)
 def test_selection_survives_mode_off_but_context_change_resets_it(self):
  p=Edit(notes=[]);p.generated();self.event(p);p.call(0x0815d1ec,p.seqview,0);p.call(0x0815d23c,p.seqview,0);self.event(p)
  self.assertEqual(self.selected(p,0),1);p.w(p.seqview+0x11400,3);self.assertEqual(self.selected(p,0),0)
 def test_native_undo_menu_has_select_next_to_undo_without_losing_actions(self):
  p=Edit();p.call(0x081412ec);d=0x30030168+0xfc0
  self.assertEqual([p.r(d+4+i*20) for i in range(5)],[N.NUI(0x1032),N.NUI(0x1041),N.NUI(0x1042),N.NUI(0x102c),0x1051])
  self.assertEqual(p.text(p.r(d+88)),"Select")
  event=0x2002e000;p.w(event,0x1051);self.assertEqual(p.call(0x0815d600,p.seqview,event),0)
  self.assertEqual(p.text(p.r(d+88)),"Select ON")
 def test_touch_select_uses_native_hitboxes_without_editing_notes(self):
  p=Edit(notes=[]);p.generated();self.event(p);before=p.events()
  for i in range(7):p.u.mem_write(p.seqview+0x38+i*0x704,struct.pack('<4I',i*100,319,95,80))
  point=0x2002e040;p.w(point,320);p.w(point+4,340)
  p.call(0x0815d29c,p.seqview,point);p.call(0x0815d444,p.seqview)
  self.assertEqual(self.selected(p,3),1);self.assertEqual(p.events(),before)
 def test_save_reload_condition_and_both_locks_without_pointer_serialization(self):
  p=Edit();a=0x5101030c;b=0x51030025;pair=p.call(UU['locks_pack'],a,b)
  token=p.call(UU['locks_condition_word'],pair,103);raw=0x2002d000;p.u.mem_write(raw,note(0,lock=token))
  p.call(UU['locks_save'],0x20017000,raw)
  self.assertEqual(p.attrs,{'bento_lock1_v1':a,'bento_lock2_v1':b,'bento_lock_condition_v1':103})
  p.w(raw+20,0);p.call(UU['locks_load'],0x20017000,raw);w=p.r(raw+20)
  self.assertEqual(p.call(UU['locks_condition_get'],w),103);self.assertEqual(p.call(UU['locks_slot'],w,1),b)
  del p.attrs['bento_lock_condition_v1'];p.w(raw+20,0);p.call(UU['locks_load'],0x20017000,raw)
  self.assertEqual(p.r(raw+20),pair)
 def test_condition_memory_failure_does_not_change_selected_notes(self):
  p=Edit(notes=[note(0,lock=0x5101030c),note(3,lock=0x5101030d,ident=2)]);self.event(p)
  for n in [0,3]:p.call(0x0815d1ec,p.seqview,n);p.call(0x0815d23c,p.seqview,n)
  before=p.events();p.w(0x30000048,p.r(0x3000004c));p.call(UU['locks_proj'],p.model,1);p.call(UU['locks_encoder'],p.seqview,N.NKEY(0x198),101)
  self.assertEqual(p.events(),before)
 def test_native_accepted_note_adapter_resolves_only_payload_and_preserves_stack(self):
  from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R8,UC_ARM_REG_LR,UC_ARM_REG_PC
  p=Edit();w=0x5101030c;token=p.call(UU['locks_condition_word'],w,100)
  sp=0x2003d000;p.w(sp+60,token)
  p.u.reg_write(UC_ARM_REG_R8,p.audioseq);p.u.reg_write(UC_ARM_REG_SP,sp);p.u.reg_write(UC_ARM_REG_LR,p.stop|1)
  p.u.emu_start(0x08060b9b,0x080d3000,count=100000)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_PC),0x080d3000);self.assertEqual(p.r(sp+60),w);self.assertEqual(p.u.reg_read(UC_ARM_REG_SP),sp)

 # R6.11 ratchet storage: ratchet word in the record's spare half (+16, check +20).
 MAGIC=0x37434c42
 def rec(self,p,token):a=0xc0000000|(token&0x0fffffff);return a,[p.r(a+i*4) for i in range(8)]
 def rt(self,p,count,shape=0,depth=0,prob=0):return p.call(UU['locks_ratchet_pack'],count,shape,depth,prob)
 def audio(self):
  import json,os
  from pathlib import Path
  return json.loads((Path(os.environ['BENTO_FX_CANDIDATE'])/'manifest.json').read_text())['audio_symbols']
 def test_r611_ratchet_word_packing_and_ranges(self):
  p=Edit()
  self.assertEqual(self.rt(p,1,2,100,134),0) # count 1 = off = no word
  self.assertEqual(self.rt(p,4,1,50,101),0x52000000|3|1<<3|50<<8|101<<16)
  self.assertEqual(self.rt(p,8,2,100,134),0x52000000|7|2<<3|100<<8|134<<16)
  for bad in [(9,0,0,0),(2,3,0,0),(2,0,101,0),(2,0,0,139)]:self.assertEqual(self.rt(p,*bad),0xffffffff,bad)
  self.assertEqual(p.call(UU['locks_ratchet_word'],0x5101030c,0x53000001),0xffffffff) # wrong tag refused
 def test_r611_old_condition_records_stay_byte_for_byte(self):
  p=Edit();w=0x5101030c;t=p.call(UU['locks_condition_word'],w,100);a,r=self.rec(p,t)
  self.assertEqual(r,[self.MAGIC,w,100,self.MAGIC^a^w^100,0,0,0,0])
  self.assertEqual(p.call(UU['locks_ratchet_get'],t),0);self.assertEqual(p.call(UU['locks_slot'],t,0),w)
  # An EU7-format record written by hand (old firmware layout) is accepted on M4 and M7.
  b=a+0x4000;p.u.mem_write(b,struct.pack('<8I',self.MAGIC,w,101,self.MAGIC^b^w^101,0,0,0,0));old=0x60000000|(b&0x0fffffff)
  self.assertEqual(p.call(UU['locks_condition_get'],old),101);self.assertEqual(p.call(UU['locks_slot'],old,0),w)
  aa=self.audio();c=0x24048a60
  for off,val in [(0,p.audioseq),(4,p.r(p.audioseq+12)),(8,p.clip),(12,1)]:p.w(c+off,val)
  self.assertEqual(p.call(aa['locks_native_filter'],p.audioseq,old),w)
  # Condition 0 without a ratchet stays invalid (unchanged rule).
  p.u.mem_write(b,struct.pack('<8I',self.MAGIC,w,0,self.MAGIC^b^w,0,0,0,0));self.assertEqual(p.call(UU['locks_slot'],old,0),0)
 def test_r611_ratchet_only_record_resolves_on_m4_and_m7(self):
  p=Edit();w=0x5101030c;r=self.rt(p,3,2,40,0);t=p.call(UU['locks_ratchet_word'],w,r);a,rec=self.rec(p,t)
  self.assertEqual(t>>28,6);self.assertEqual(rec,[self.MAGIC,w,0,self.MAGIC^a^w,r,(~(rec[3]^r))&0xffffffff,0,0])
  self.assertEqual(p.call(UU['locks_condition_get'],t),0);self.assertEqual(p.call(UU['locks_ratchet_get'],t),r)
  self.assertEqual(p.call(UU['locks_slot'],t,0),w)
  aa=self.audio();c=0x24048a60
  for off,val in [(0,p.audioseq),(4,p.r(p.audioseq+12)),(8,p.clip),(12,0)]:p.w(c+off,val)
  self.assertEqual(p.call(aa['locks_native_filter'],p.audioseq,t),w) # M7 (LOCK_M7) accepts condition 0 + ratchet
  # Native accepted-note adapter (M7) resolves it like any record.
  from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R8,UC_ARM_REG_LR,UC_ARM_REG_PC
  sp=0x2003d000;p.w(sp+60,t)
  p.u.reg_write(UC_ARM_REG_R8,p.audioseq);p.u.reg_write(UC_ARM_REG_SP,sp);p.u.reg_write(UC_ARM_REG_LR,p.stop|1)
  p.u.emu_start(0x08060b9b,0x080d3000,count=100000)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_PC),0x080d3000);self.assertEqual(p.r(sp+60),w)
  # A broken ratchet check makes the whole record invalid on both cores.
  p.w(a+20,rec[5]^1);self.assertEqual(p.call(UU['locks_slot'],t,0),0);self.assertEqual(p.call(UU['locks_ratchet_get'],t),0)
  self.assertNotEqual(p.call(aa['locks_native_filter'],p.audioseq,t),w)
 def test_r611_dedupe_and_immutability(self):
  p=Edit();w=0x5101030c;r=self.rt(p,4,1,50,0);r2=self.rt(p,4,1,51,0)
  plain=p.call(UU['locks_condition_word'],w,101);both=p.call(UU['locks_ratchet_word'],plain,r)
  self.assertNotEqual(both,plain);self.assertEqual(p.call(UU['locks_ratchet_word'],plain,r),both)
  self.assertEqual(p.call(UU['locks_condition_word'],both,101),both)
  other=p.call(UU['locks_ratchet_word'],plain,r2);self.assertNotIn(other,(plain,both))
  snap={t:self.rec(p,t)[1] for t in (plain,both,other)}
  # Setting/removing ratchet or condition keeps the other value; old records never change.
  self.assertEqual(p.call(UU['locks_ratchet_word'],both,0),plain)
  only=p.call(UU['locks_condition_word'],both,0);self.assertEqual((p.call(UU['locks_condition_get'],only),p.call(UU['locks_ratchet_get'],only)),(0,r))
  self.assertEqual(p.call(UU['locks_condition_word'],only,101),both)
  self.assertEqual(p.call(UU['locks_ratchet_word'],only,0),w) # nothing left: plain word, no record
  self.assertEqual({t:self.rec(p,t)[1] for t in snap},snap)
  self.assertEqual(p.call(UU['locks_condition_get'],both),101);self.assertEqual(p.call(UU['locks_ratchet_get'],both),r)
 def test_r611_lock_and_condition_edits_keep_the_ratchet_and_old_token(self):
  p=Edit(notes=[]);p.generated();r=self.rt(p,6,0,100,103)
  p.select(0);p.call(UU['locks_header_before'],p.seqview);p.call(UU['locks_encoder'],p.seqview,2,(-18000)&0xffffffff)
  first=struct.unpack_from('<I',p.events()[0],20)[0];self.assertEqual(first,0x5101030c)
  t=p.call(UU['locks_ratchet_word'],first,r);raw=bytearray(p.events()[0]);struct.pack_into('<I',raw,20,t)
  # put the ratchet token on the selected note through the native note update
  e=0x2002d100;p.u.mem_write(e,bytes(raw));p.call(0x0810d1aa,p.r(p.seqview+0x113dc),e)
  self.assertEqual(struct.unpack_from('<I',p.events()[0],20)[0],t);old=self.rec(p,t)[1]
  p.call(UU['locks_encoder'],p.seqview,2,(-12000)&0xffffffff) # new Level value
  w=struct.unpack_from('<I',p.events()[0],20)[0];self.assertNotEqual(w,t)
  self.assertEqual(p.call(UU['locks_ratchet_get'],w),r);self.assertEqual(p.call(UU['locks_slot'],w,0),0x51010348)
  p.call(UU['locks_proj'],p.model,1);p.call(UU['locks_encoder'],p.seqview,N.NKEY(0x198),101);p.call(UU['locks_proj'],p.model,0)
  w2=struct.unpack_from('<I',p.events()[0],20)[0]
  self.assertEqual((p.call(UU['locks_condition_get'],w2),p.call(UU['locks_ratchet_get'],w2),p.call(UU['locks_slot'],w2,0)),(101,r,0x51010348))
  self.assertEqual(self.rec(p,t)[1],old) # Undo/copy still hold t: exact old lock and ratchet
  self.assertEqual((p.call(UU['locks_slot'],t,0),p.call(UU['locks_ratchet_get'],t)),(0x5101030c,r))
 def test_r611_xml_round_trip_and_unchanged_files_without_ratchets(self):
  p=Edit();a=0x5101030c;b=0x51030025;pair=p.call(UU['locks_pack'],a,b);r=self.rt(p,5,2,77,120)
  raw=0x2002d000
  for cond in (103,0):
   token=p.call(UU['locks_ratchet_word'],p.call(UU['locks_condition_word'],pair,cond),r);p.u.mem_write(raw,note(0,lock=token))
   p.attrs.clear();p.call(UU['locks_save'],0x20017000,raw)
   self.assertEqual(p.attrs,{'bento_lock1_v1':a,'bento_lock2_v1':b,'bento_lock_condition_v1':cond,'bento_ratchet_v1':r&0xffffff})
   p.w(raw+20,0);p.call(UU['locks_load'],0x20017000,raw);w=p.r(raw+20)
   self.assertEqual(w,token) # deduplicated to the same immutable record
   self.assertEqual([p.call(UU['locks_condition_get'],w),p.call(UU['locks_ratchet_get'],w),p.call(UU['locks_slot'],w,0),p.call(UU['locks_slot'],w,1)],[cond,r,a,b])
  # No ratchet: exactly the EU7 attributes (saved files unchanged).
  p.u.mem_write(raw,note(0,lock=p.call(UU['locks_condition_word'],pair,103)));p.attrs.clear();p.call(UU['locks_save'],0x20017000,raw)
  self.assertEqual(p.attrs,{'bento_lock1_v1':a,'bento_lock2_v1':b,'bento_lock_condition_v1':103})
  # Invalid stored ratchet values are ignored on load (the note keeps locks/condition).
  for bad in (0x000080|0x01,0x1000001,3<<3|1):
   p.attrs['bento_ratchet_v1']=bad;p.w(raw+20,0);p.call(UU['locks_load'],0x20017000,raw);w=p.r(raw+20)
   self.assertEqual((p.call(UU['locks_ratchet_get'],w),p.call(UU['locks_condition_get'],w),p.call(UU['locks_slot'],w,1)),(0,103,b),hex(bad))
  # Ratchet only, no locks at all.
  p.attrs={'bento_lock_condition_v1':0,'bento_ratchet_v1':r&0xffffff};p.w(raw+20,0);p.call(UU['locks_load'],0x20017000,raw);w=p.r(raw+20)
  self.assertEqual((p.call(UU['locks_ratchet_get'],w),p.call(UU['locks_slot'],w,0)),(r,0))
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
