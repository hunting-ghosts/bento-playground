"""P14 real native note selection, encoder widgets, Undo and lock payloads.
Audio checks run the new guarded ARM paths with real native filter parameters.
Device timing and hardware playback remain outside these fixtures.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import unittest,struct,gc,json,os
from pathlib import Path
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import *
from test_device import Device
from test_integration import UU,AA,Fixture
KEEP=[]
EV=0x2002e000
class Page(Device):
 def __init__(self):
  super().__init__();KEEP.append(self);self.insert();self.call(0x0815abb8,self.view,0,0)
  self.u.mem_write(self.view+0x125dac,b'\0');self.call(0x081599bc,self.view)
  self.select_ids([self.ids()[0]])
 def ids(self):return [struct.unpack_from('<I',e,12)[0] for e in self.events()]
 def select_ids(self,ids):
  self.call(0x08174bac,self.view+0x38,0)
  for ident in ids:self.call(0x08174c4e,self.view+0x38,ident,0)
  self.call(0x081599bc,self.view)
 def event(self,key,value):
  self.u.mem_write(EV,struct.pack('<5I',0xcf,0,key,value&0xffffffff,0));return self.call(UU['piano_event'],self.view,EV)
 def shift(self,down):return self.call(UU['locks_proj'],self.model,down)
 def keys(self):return list(struct.unpack('<8H',self.u.mem_read(self.view+0x11bcc0,16)))
 def word(self,i=0):return struct.unpack_from('<I',self.events()[i],20)[0]
 def slot(self,i):return self.view+0x55f0+0x38+i*0x468
 def title(self,i):return self.text(self.slot(i)+0x3c8+0x31)
 def label(self,i):return self.text(self.slot(i)+0x2c8)
 def pick_lock(self,index,title):
  assert self.call(UU['locks_touch'],self.slot(index),0)==1
  self.call(0x081599bc,self.view);key=self.keys()[index]
  descriptor=self.r(0x30031484)+key*32
  labels=[self.text(self.r(self.r(descriptor+8)+i*4)) for i in range(self.r(descriptor+12))]
  self.event(key,labels.index(title))
  assert self.call(UU['locks_touch'],self.slot(index),0)==1
  self.call(0x081599bc,self.view)
class Audio(Fixture):
 def hook(self,u,a,n,d):
  super().hook(u,a,n,d)
  if a==0x08104c08:self.w(0x3000004c,self.next)
 def __init__(self):
  super().__init__();KEEP.append(self);self.u.mem_map(0,0x1000);self.owner=80;self.root=0xc00a0000;self.voice=0xc00b0000;self.other=0xc00b1000;self.record=0x20026000
  self.w(0x3000004c,self.next);self.w(0x30000048,0xc0000000+N.SDRAM_MAP);self.call(UU['mel_audio_prepare'],self.owner);self.bank=self.r(0x24041fc4);self.state=self.r(self.bank+16)
  self.w(self.root,0x080ac798);self.w(self.root+12,101)
  for v in [self.voice,self.other]:self.call(0x0807f3c0,v)
 def pack(self,a,b=0):return self.call(UU['locks_pack'],a,b)
 def note(self,word,voice=None):
  self.u.mem_write(self.record,struct.pack('<BBH5I',0x12,0xb8,0x4d4c,0,101,60,100,word))
  self.call(AA['mel_note'],self.root,self.record);self.call(AA['mel_attach'],self.root,voice or self.voice)
 def context(self,voice=None):self.call(AA['mel_context'],self.root,voice or self.voice)
 def evaluate(self,offset=0x5c4,voice=None):
  ptr=(voice or self.voice)+offset;self.call(0x0809fd80,ptr);return struct.unpack('<f',self.u.mem_read(ptr+0x3c,4))[0]
 def gain(self,values):
  buf=0x20027000;data=0x20028000;self.w(buf,len(values));self.w(buf+4,len(values));self.w(buf+8,data);self.w(buf+12,0x20029000);self.u.mem_write(buf+16,b'\0\0')
  self.u.mem_write(data,struct.pack('<%df'%len(values),*values));self.call(AA['mel_level'],self.voice,buf)
  return struct.unpack('<%df'%len(values),self.u.mem_read(data,4*len(values)))
 def lock_counts(self):
  value=self.r(self.state+0x68);return (value&255,(value>>8)&255,(value>>16)&255)
 def expected_lock_counts(self):
  entries=struct.iter_unpack('<10I',self.u.mem_read(self.state+128,128*40))
  words=[e for e in entries]
  return (sum(bool(e[2]) for e in words),sum(bool(e[8] or e[9]) for e in words),sum(bool(e[6] or e[7]) for e in words))
class Tests(unittest.TestCase):
 def test_r66_no_selection_shows_transpose_and_mode_on_encoders_7_8(self):
  # R6.6/R6.7b (owner): Berlin-school transpose on the free encoders 7/8 of the
  # Seq view (native Sequence tab 1), whatever is selected.
  p=Page();p.select_ids([p.ids()[0]]);p.u.mem_write(p.view+0x125dac,b'\x01');p.call(0x081599bc,p.view);keys=p.keys()
  self.assertEqual(keys[6:8],[0x9d,0x9e]);self.assertEqual((p.title(6),p.title(7)),('Transpose','Mode'))
  p.event(0x9d,1);p.event(0x9e,1);keys=p.keys()
  bank=p.r(0x24041fc0+4);arp=p.r(bank+28);self.assertTrue(arp)
  tr=p.r(arp+60);self.assertEqual(p.r(tr),0x31505254)
  owner=p.r(tr+8);self.assertTrue(owner)
  self.assertEqual(bytes(p.u.mem_read(tr+40,1)),b'\1');self.assertEqual(bytes(p.u.mem_read(tr+48,1)),b'\1')
  # Fixture: this page has no native keyboard layout object; pad n plays 48+n.
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(48+u.reg_read(UC_ARM_REG_R0)),begin=UU['chord_pad_pitch'],end=UU['chord_pad_pitch'])
  # Fixture: no project settings node here; the project is C major.
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(u.mem_write(u.reg_read(UC_ARM_REG_R0),bytes([0,2,4,5,7,9,11])),p.ret(0)),begin=UU['chord_project_scale'],end=UU['chord_project_scale'])
  flushes=[];p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(flushes.append(1),p.ret()),begin=0x081257f0,end=0x081257f0) # LED flush: fixture
  p.call(UU['tr_tick']);self.assertEqual(p.r(tr+4),1) # selected pitched track: pads armed
  self.assertEqual(len(flushes),1);p.call(UU['tr_tick']);self.assertEqual(len(flushes),1) # R6.8b: refresh only on change
  p.w(tr+104,p.r(tr+104)+1);p.call(UU['tr_tick']);self.assertEqual(len(flushes),2) # M7 offserial bump -> LEDs + encoder row
  root=p.u.mem_read(tr+57,1)[0];base=p.u.mem_read(tr+56,1)[0]
  self.assertEqual((root,base),(0,48)) # lowest pad playing the project root (C)
  pads=0x2002c000;p.u.mem_write(pads,bytes(256));self.assertEqual(p.call(UU['tr_lights'],pads),1)
  lit=[p.r(pads+i*16) for i in range(16)];self.assertTrue(lit[0] and lit[12]) # C pads (48, 60)
  self.assertEqual([i for i in range(16) if lit[i]],[0,12]);self.assertNotEqual(lit[0],0)
  p.event(0x9d,0);p.call(UU['tr_tick']);self.assertEqual(p.r(tr+4),0)
  self.assertEqual(p.keys()[4],N.NKEY(0x177)) # Bars stays on encoder 5
  p.u.mem_write(p.view+0x125dac,b'\0');p.call(0x081599bc,p.view);self.assertNotEqual(p.keys()[6],0x9d) # Event tab: locks
 def test_one_shot_event_condition_keeps_note_probability_and_lock_values(self):
  p=Page();p.type=14;p.select_ids(p.ids()[:2]);self.assertEqual(p.keys()[7],N.NKEY(0x198))
  before=p.events();undo=len(p.undo);self.assertEqual(p.event(N.NKEY(0x198),49),1)
  for i in range(2):
   self.assertEqual(p.events()[i][:20],before[i][:20])
   self.assertEqual(p.call(UU['locks_condition_get'],p.word(i)),50)
  self.assertEqual(p.events()[2:],before[2:]);self.assertEqual(len(p.undo),undo+1)
  self.assertEqual(p.event(N.NKEY(0x198),99),1);self.assertEqual(p.events(),before)
 def test_one_shot_sequence_e8_is_native_automation_overlay_not_condition(self):
  p=Page();p.type=14;p.call(0x081599bc,p.view);self.assertEqual(p.keys()[7],N.NKEY(0x198))
  e=0x2002e000;p.w(e,0x4a);p.call(0x0815a598,p.view,e)
  self.assertEqual(p.keys()[7],N.NKEY(0x1df));before=p.events()
  for value in (1,0):
   p.u.mem_write(EV,struct.pack('<5I',0xcf,p.r(p.view+0x11cd00),N.NKEY(0x1df),value,0))
   p.call(0x0815a598,p.view,EV);self.assertEqual(p.r(p.view+0x125da8),value);self.assertEqual(p.events(),before)
 def test_filter2_registry_coexists_with_track_fx_in_both_entry_orders(self):
  for first in [True,False]:
   p=Fixture();KEEP.append(p);p.registry()
   if first:self.assertEqual(p.call(UU['melodic_lock_registry'],1),1)
   p.registry=lambda:None
   p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x081420ec,end=0x081420ec)
   p.open()
   if not first:self.assertEqual(p.call(UU['melodic_lock_registry'],1),1)
   r=p.r(0x30031484)
   self.assertEqual(p.text(p.r(r+N.NKEY(0x1d0)*32+4)),'Track')
   self.assertEqual(p.text(p.r(r+0xb4*32+4)),'Filter 2')
   self.assertEqual(p.text(p.r(r+0xb5*32+4)),'Resonance 2')
 def test_event_encoders_7_and_8_are_locks_and_native_first_six_stay(self):
  p=Page();self.assertEqual(p.keys(),[N.NKEY(0x17e),N.NKEY(0x181),N.NKEY(0x185),N.NKEY(0x182),N.NKEY(0x183),N.NKEY(0x184),0x32,0x33]);self.assertIn('Filter',p.title(6));self.assertIn('Resonance',p.title(7))
 def test_two_locks_are_note_owned_and_keep_ids_pitches_and_other_notes(self):
  p=Page();before=p.events();undo=len(p.undo);p.event(0x32,500);p.event(0x33,750)
  self.assertEqual(p.call(UU['locks_slot'],p.word(),0),0x510405dc);self.assertEqual(p.call(UU['locks_slot'],p.word(),1),0x510502ee)
  self.assertEqual(p.events()[0][:20],before[0][:20]);self.assertEqual(p.events()[1:],before[1:]);self.assertEqual(len(p.undo),undo+2);self.assertTrue(p.title(6).endswith('*'))
 def test_native_multi_selection_locks_only_selected_chord_tones(self):
  p=Page();p.select_ids(p.ids()[:2]);p.event(0x32,350);self.assertTrue(p.word(0));self.assertTrue(p.word(1));self.assertEqual(p.word(2),0)
 def test_inline_picker_and_remove_one_lock_preserve_the_other(self):
  p=Page();p.event(0x32,500);p.event(0x33,700);before=p.events();undo=len(p.undo)
  p.pick_lock(6,'Filter');self.assertEqual(p.events(),before);self.assertEqual(p.keys()[6:],[0x32,0x33])
  self.assertEqual(p.call(UU['locks_touch'],p.slot(6),1),1);p.call(0x081599bc,p.view)
  self.assertEqual(p.call(UU['locks_slot'],p.word(),0),0);self.assertEqual(p.call(UU['locks_slot'],p.word(),1),0x510502bc)
  self.assertEqual(p.events()[0][:20],before[0][:20]);self.assertEqual(p.events()[1:],before[1:]);self.assertEqual(len(p.undo),undo+1)
 def test_choosing_partner_target_without_stored_locks_never_swaps_encoders(self):
  p=Page();before=p.events()
  p.pick_lock(6,'Resonance');self.assertEqual(p.keys()[6:],[0x32,0x33])
  p.pick_lock(7,'Filter');self.assertEqual(p.keys()[6:],[0x32,0x33])
  self.assertEqual(p.events(),before)
 def test_filter2_targets_are_independent_picker_choices(self):
  p=Page();before=p.events();registry=p.r(0x30031484)
  for key,title,kind in [(0xb4,'Filter 2',12),(0xb5,'Resonance 2',10)]:
   d=registry+key*32;self.assertEqual(p.text(p.r(d+4)),title);self.assertEqual(p.u.mem_read(d+2,1)[0],kind);self.assertEqual((p.r(d+16),p.r(d+20)),(0,1000))
  p.pick_lock(6,'Filter 2');self.assertEqual(p.keys()[6],0xb4);p.event(0xb4,500)
  p.pick_lock(7,'Resonance 2');self.assertEqual(p.keys()[7],0xb5);p.event(0xb5,750)
  self.assertEqual(p.call(UU['locks_slot'],p.word(),0),0x511e01f4)
  self.assertEqual(p.call(UU['locks_slot'],p.word(),1),0x511f02ee)
  self.assertEqual(p.events()[0][:20],before[0][:20])
 def test_filter2_pair_codec_roundtrips_all_partner_kinds_at_value_boundaries(self):
  p=Fixture();KEEP.append(p)
  counts=[1,1081,48001,2001,2001]+[1001]*7+[156]+[101]*17+[1001]*2
  for new in [30,31]:
   for partner in range(32):
    if partner==new:continue
    for maximum in [False,True]:
     a=0x51000000|(new<<16)|(counts[new]-1 if maximum else 0)
     b=(0x51000000|(partner<<16)|(counts[partner]-1 if maximum else 0)) if partner else 0
     for first,second in [(a,b),(b,a)]:
      word=p.call(UU['locks_pack'],first,second)
      self.assertNotEqual(word,0xffffffff,(new,partner,maximum))
      self.assertEqual([p.call(UU['locks_slot'],word,i) for i in [0,1]],[first,second])
 def test_picker_targets_level_and_pan_and_keeps_base_values(self):
  p=Page();before=p.events();p.pick_lock(6,'Level');p.pick_lock(7,'Pan')
  self.assertEqual(p.events(),before);self.assertEqual(p.keys()[6:],[2,4]);p.event(2,-6000);p.event(4,-500)
  self.assertEqual(p.call(UU['locks_slot'],p.word(),0),0x51010384);self.assertEqual(p.call(UU['locks_slot'],p.word(),1),0x510301f4)
 def test_no_note_selection_does_not_mutate_and_has_clear_prompt(self):
  # R6.7b (owner): transpose lives in the Seq view; the Event tab keeps its prompt.
  p=Page();p.select_ids([]);before=p.events();p.event(0x32,500);self.assertEqual(p.events(),before);self.assertEqual(p.label(6),'Select note')
 def test_sequence_and_euclidean_banks_keep_their_encoders(self):
  p=Page();p.u.mem_write(p.view+0x125dac,b'\x01');p.call(0x081599bc,p.view);self.assertNotEqual(p.keys()[6:], [0x32,0x33])
  p.u.mem_write(EV,struct.pack('<5I',0x1054,0,0,0,0));p.call(UU['piano_event'],p.view,EV);self.assertEqual(p.keys()[6:],[N.NKEY(0x194),N.NKEY(0x195)])
 def test_saved_lock_payload_roundtrip_is_exact(self):
  p=Page();p.event(0x32,620);p.event(0x33,420);word=p.word();p.u.mem_write(EV,p.events()[0]);p.call(UU['locks_save'],0x20017000,EV);p.w(EV+20,0);p.call(UU['locks_load'],0x20017000,EV);self.assertEqual(p.r(EV+20),word)
 def test_burger_moves_automation_toggle_without_losing_actions(self):
  p=Page();p.call(0x081412ec);p.call(UU['melodic_locks_menu'],1)
  menus=[]
  for m in range(20):
   d=0x30030168+m*0xe0
   if p.r(d)==0xf9:
    n=p.u.mem_read(d+0xcc,1)[0];ids=[p.r(d+4+i*20) for i in range(n)];self.assertIn(0x1059,ids);self.assertIn(N.NUI(0x1032),ids);self.assertLessEqual(n,9);menus.append(d)
  self.assertTrue(menus);p.call(UU['melodic_locks_menu'],0)
  for d in menus:self.assertNotIn(0x1059,[p.r(d+4+i*20) for i in range(p.u.mem_read(d+0xcc,1)[0])])
 def test_per_voice_filter_and_resonance_run_native_evaluator(self):
  p=Audio();p.note(p.pack(0x510405dc,0x510502ee));p.context();self.assertAlmostEqual(p.evaluate(),.5,places=5);self.assertAlmostEqual(p.evaluate(0x60c),.75,places=5)
 def test_filter2_cutoff_and_resonance_locks_run_native_evaluator(self):
  p=Audio();p.note(p.pack(0x511e01f4,0x511f02ee));p.context()
  self.assertAlmostEqual(p.evaluate(0x69c),.5,places=5)
  self.assertAlmostEqual(p.evaluate(0x6e4),.75,places=5)
 def test_overlapping_voice_has_independent_values_and_unlocked_reuse_clears(self):
  p=Audio();p.note(0x510405dc);p.note(0x510406a4,p.other);p.context();self.assertAlmostEqual(p.evaluate(),.5,places=5)
  p.context(p.other);self.assertAlmostEqual(p.evaluate(voice=p.other),.7,places=5)
  p.note(0);p.context();self.assertNotEqual(p.evaluate(),.5)
 def test_m7_lock_counts_follow_voice_reuse_and_root_reassignment(self):
  p=Audio();self.assertEqual(p.lock_counts(),(0,0,0))
  for voice,word in [(p.voice,0),(p.voice,0x510405dc),(p.other,p.pack(0x510a03e8,0x510701f4)),
                     (p.voice,0x510b0000),(p.other,0),(p.voice,0),(p.voice,0x510902ee)]:
   p.note(word,voice);self.assertEqual(p.lock_counts(),p.expected_lock_counts())
  self.assertEqual(p.lock_counts(),(1,0,1))
  other_root=0xc00d0000;p.w(other_root,0x080ac798);p.w(other_root+12,102)
  p.u.mem_write(p.record,struct.pack('<BBH5I',0x12,0xb8,0x4d4c,0,102,60,100,0x510a03e8))
  p.call(AA['mel_note'],other_root,p.record);p.call(AA['mel_attach'],other_root,p.voice)
  self.assertEqual(p.lock_counts(),(1,1,0));self.assertEqual(p.lock_counts(),p.expected_lock_counts())
  p.note(0,p.voice);self.assertEqual(p.lock_counts(),(0,0,0));self.assertEqual(p.lock_counts(),p.expected_lock_counts())
 def test_empty_lock_paths_skip_a_full_unlocked_voice_table(self):
  p=Audio()
  for voice in [p.voice]+[0xc0100000+i*0x800 for i in range(127)]:
   p.note(0x510405dc,voice);p.note(0,voice)
  self.assertEqual(p.lock_counts(),(0,0,0));self.assertEqual(p.lock_counts(),p.expected_lock_counts())
  reads=[];hook=p.u.hook_add(UC_HOOK_MEM_READ,lambda u,a,addr,size,value,data:reads.append(addr),
                            begin=p.state+128,end=p.state+128+128*40-1)
  p.context();self.assertEqual(p.call(AA['mel_envelope'],p.voice+0x200,7),0);p.u.hook_del(hook)
  self.assertEqual(reads,[]);self.assertEqual(p.r(p.state+0x50),0);self.assertEqual(p.r(p.state+0x54),0)
  p.note(0x510405dc,p.voice);p.context();self.assertAlmostEqual(p.evaluate(),.5,places=5)
 def test_unlocked_notes_do_not_fill_the_lock_table(self):
  p=Audio()
  for i in range(129):p.note(0,0xc0100000+i*0x800)
  self.assertEqual(bytes(p.u.mem_read(p.state+128,128*40)),bytes(128*40))
  p.note(0x510405dc,p.voice);p.context();self.assertAlmostEqual(p.evaluate(),.5,places=5)
 def test_level_scales_audio_without_changing_velocity_or_other_voice(self):
  p=Audio();p.note(0x51010384);p.context();out=p.gain([1.,-.5,.25,0.]);self.assertAlmostEqual(out[0],10**(-6/20),places=5);self.assertAlmostEqual(out[1],-.5*out[0],places=6)
  p.note(0,p.other);p.context(p.other);self.assertEqual(p.gain([1.,.5]),(1.,.5))
 def test_pan_is_native_voice_local(self):
  p=Audio();p.note(0x510301f4);self.assertAlmostEqual(struct.unpack('<f',p.u.mem_read(p.voice+0x18,4))[0],.25);self.assertNotEqual(p.u.mem_read(p.voice+0x18,4),p.u.mem_read(p.other+0x18,4))
 def test_queue_payload_is_only_written_to_the_primary_destination(self):
  p=Audio();seq=0xc00c0000;router=0xc00d0000;queue=0xc00e0000
  p.w(seq+12,p.owner);p.u.mem_write(seq+0x10,struct.pack('<H',101));p.w(seq+0x86dc,0xffffff00)
  p.w(router+4,queue);p.w(router+8,101);p.w(router+12,0);p.w(router+0x508,1)
  word=p.pack(0x510405dc,0x510502ee);p.call(AA['mel_pending'],seq,router,0,word)
  for q,expected in [(queue+0x604,0),(queue,word)]:
   p.u.mem_write(p.record,struct.pack('<6I',0x12,0,101,60,100,0));p.call(AA['mel_queue'],q,p.record);self.assertEqual(p.r(p.record+20),expected)
  p.call(AA['mel_pending_clear']);p.u.mem_write(p.record,struct.pack('<6I',0x12,0,101,60,100,0));p.call(AA['mel_queue'],queue,p.record);self.assertEqual(p.r(p.record+20),0)
 def test_physical_encoder_path_edits_the_selected_note(self):
  p=Page();p.call(0x08171e44,p.slot(6),(-12800)&0xffffffff)
  self.assertEqual(p.call(UU['locks_slot'],p.word(),0)>>16&255,4)
 def test_auto_footer_tab_opens_native_automation_editor(self):
  # R6: Auto is the native Automation tab (4B) in the footer.
  p=Page();p.w(EV,0x4b);p.call(UU['piano_event'],p.view,EV) or p.call(0x0815a598,p.view,EV);self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],2)
 def test_installed_native_wavetable_note_entry_attaches_filter_lock(self):
  p=Audio();p.call(0x0809bf20,p.root);p.w(p.root+12,101)
  p.u.mem_write(p.record,struct.pack('<BBH5I',0x12,0xb8,0x4d4c,0,101,60,100,0x510405dc))
  router=0x20029000;clock=0x2002a000;p.w(router,clock);p.f(clock+0x18,120);p.f(clock+0x14c,.5);p.u.reg_write(UC_ARM_REG_S1,0x3f000000)
  p.call(0x0807ebe0,p.root,p.record,router,fp=0.0);voice=p.r(p.root+0x14)
  p.call(AA['mel_context'],p.root,voice);self.assertAlmostEqual(p.evaluate(voice=voice),.5,places=5)
 def test_locked_note_edits_are_kept_when_selecting_another_note(self):
  p=Page();p.event(0x32,500);old=p.word();p.select_ids([p.ids()[1]]);p.event(0x33,700)
  self.assertEqual(p.word(0),old);self.assertNotEqual(p.word(1),0);self.assertEqual(p.word(2),0)
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
