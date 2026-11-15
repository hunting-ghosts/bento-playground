"""EU9 device-feedback regressions: actual widget turns and persistent header."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import gc,struct,unittest
import test_eu8
from test_editable_eu import Edit
from test_live import UU
from unicorn.arm_const import *
from unicorn import UC_HOOK_CODE
KEEP=[]
TEMPLATES=0x08199008;ROOT=0x30034d48
class Native(Edit):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);KEEP.append(self);self.call(0x081412ec)
 def ui(self,u,a,n,d):
  if a!=0x0815c27c:self.ret()
 def bubble(self,u,a,n,d):
  ptr=u.reg_read(UC_ARM_REG_R1);code=self.r(ptr)&65535
  if code in [0xcf,0x1051]:
   u.reg_write(UC_ARM_REG_R0,self.seqview);u.reg_write(UC_ARM_REG_PC,0x0815d601);return
  super().bubble(u,a,n,d)
class Tests(unittest.TestCase):
 def view(self):
  p=Native();test_eu8.Tests().full_view(p);p.select(0);p.call(0x0815c27c,p.seqview);return p
 def view_clear(self):
  # R6.10: nothing selected (the fixture's select(0) would make Select read Deselect).
  p=self.view();p.w(0x24048d80+20,0)
  for i in range(32):p.w(p.seqview+0x11420+i*4,0)
  p.call(0x0815c27c,p.seqview);return p
 def turn(self,p,index,delta):
  # Space turns so native acceleration cannot skip an enum value.
  p.w(0x30035f40,p.r(0x30035f40)+10000)
  return p.call(0x08171e44,p.seqview+0xebf0+0x38+index*0x468,delta&0xffffffff)
 def test_r614_ratchet_ticks_on_the_step_cell_in_track_colour(self):
  # Playground Steps cell (pg_cell_paint, vtable slot 1): one 2x5 tick per hit
  # on the step's top row, track colour; none without a ratchet. Text is stubbed
  # (no native surface here); the native grid refresh that sets 'on' is a fixture.
  from test_euclidean import note
  p=Native(notes=[note(0),note(1)]);test_eu8.Tests().full_view(p);p.call(0x0815c27c,p.seqview)
  fills=[]
  def fill(u,a,n,d):r=u.reg_read(UC_ARM_REG_R0);fills.append((tuple(p.r(r+i*4) for i in range(4)),u.reg_read(UC_ARM_REG_R1)));p.ret()
  p.u.hook_add(UC_HOOK_CODE,fill,begin=0x08166ef6,end=0x08166ef6)
  t=UU['textf_']&~1;p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=t,end=t)
  ctx=0x2002f000;p.w(ctx,1);p.w(ctx+4,0x20020000);cell=p.seqview+0x34;p.u.mem_write(cell+0x6ed,b'\1');p.u.mem_write(cell+0x6ec,b'\x37')
  def paint():p.w(0x3001fe2c,p.r(0x3001fe2c)+1);fills.clear();p.call(UU['pg_cell_paint'],cell,ctx);return list(fills)
  plain=paint();x=p.r(cell+4);bottom=p.r(cell+8)+p.r(cell+16)-4-5
  for n in (1,2,4,8):
   r=p.call(UU['locks_ratchet_pack'],n,2,50,0);w=p.call(UU['locks_ratchet_word'],0,r) if n>1 else 0;p.w(p.container+20,w)
   self.assertEqual([f for f in paint() if f not in plain],[((x+48+k*3,bottom,2,5),0x37) for k in range(n if n>1 else 0)])
 def test_condition_can_be_set_before_any_lock_and_entire_range_is_reachable_by_native_turns(self):
  p=self.view();slot=p.seqview+0xebf0+0x38+5*0x468
  before=p.events();p.call(UU['locks_encoder'],p.seqview,N.NKEY(0x199),0)
  p.call(0x0815c27c,p.seqview)
  for value in range(113): # exp5 picker order: %, Always, A:B up to 4:4, 1ST..!PRE (codes 135..138)
   if value:self.turn(p,5,12800)
   after=p.events();word=struct.unpack_from('<I',after[0],20)[0]
   self.assertEqual(p.call(UU['locks_condition_get'],word),0 if value==99 else value+1 if value<99 else value if value<109 else value+26)
   self.assertEqual([p.call(UU['locks_slot'],word,i) for i in range(2)],[0,0])
   self.assertEqual([e[:20] for e in after],[e[:20] for e in before])
   self.assertEqual(after[1:],before[1:])
   p.call(0x0815c27c,p.seqview)
   self.assertEqual(p.r(slot+0xa0),value)
 def test_adding_lock_retains_previously_selected_condition_and_xml_roundtrips(self):
  p=self.view();p.call(UU['locks_proj'],p.model,1);p.call(UU['locks_encoder'],p.seqview,N.NKEY(0x198),103);p.call(UU['locks_proj'],p.model,0)
  word=struct.unpack_from('<I',p.events()[0],20)[0];self.assertEqual(p.call(UU['locks_condition_get'],word),103)
  raw=0x2002e000;p.u.mem_write(raw,p.events()[0]);p.call(UU['locks_save'],0x20017000,raw)
  self.assertEqual(p.attrs['bento_lock_condition_v1'],103)
  p.call(UU['locks_load'],0x20017000,raw);self.assertEqual(p.call(UU['locks_condition_get'],p.r(raw+20)),103)
  p.call(UU['locks_encoder'],p.seqview,2,(-18000)&0xffffffff)
  word=struct.unpack_from('<I',p.events()[0],20)[0];self.assertEqual(p.call(UU['locks_condition_get'],word),103);self.assertNotEqual(p.call(UU['locks_slot'],word,0),0)
 def header_data(self,p,page=0x27):
  # Real native header templates (table 08199008). Page 27 (one-shot step grid,
  # entry 36): Step/Sequence tabs, Undo last. Page 17 (piano roll, entry 8):
  # Event/Sequence/Automation tabs, Clear, Undo; only slot 0 is free.
  index={0x27:36,0x17:8}[page]
  out=0x20028000;p.u.mem_write(out,bytes(p.u.mem_read(TEMPLATES+index*N.HDR_SIZE,N.HDR_SIZE)))
  assert p.u.mem_read(out+N.HDR(0x1c2),1)[0]==page and p.text(out+N.HDR(0x74)+5*48)=='Undo'
  return out
 def slot(self,out,i):return out+N.HDR(0x74)+i*48
 def native_header(self,p,out):
  # Native copy and patched return run; clock/metronome display is a fixture.
  p.u.mem_write(p.model+N.MODEL(0x3a00),bytes(p.u.mem_read(out,N.HDR_SIZE)))
  p.u.mem_write(p.model+0x14c,b'\x01');p.w(p.model+N.MODEL(0xb19c),1);p.w(p.model+N.MODEL(0x3c60),1)
  def after_copy(u,a,n,d):u.reg_write(UC_ARM_REG_R6,1);u.reg_write(UC_ARM_REG_PC,0x081349dd)
  h=p.u.hook_add(UC_HOOK_CODE,after_copy,begin=0x081348dc,end=0x081348dc)
  self.assertEqual(p.call(0x08134800,p.model,out,0,0),1);p.u.hook_del(h)
 def test_actual_header_entry_inserts_persistent_select_and_preserves_other_actions(self):
  p=self.view_clear();out=self.header_data(p);native=bytes(p.u.mem_read(out,N.HDR_SIZE))
  self.native_header(p,out)
  # R6 (owner spec): Euclid, Steps, Piano, Auto tabs, then Select rightmost.
  self.assertEqual(p.text(self.slot(out,5)),'Select');self.assertEqual(struct.unpack('<H',p.u.mem_read(self.slot(out,5)+44,2))[0],0x1051)
  self.assertEqual(p.u.mem_read(self.slot(out,5)+0x20,3),b'\0\0\0')
  # P17 (owner): slot 0 stays free for the on-screen pad selector; the row moved
  # right: Euclidean, Step, Sequence tabs, Select, Clear (native Clear Seq).
  self.assertEqual(p.text(self.slot(out,0)),'');self.assertEqual(p.u.mem_read(self.slot(out,0)+0x20,1)[0],1)
  self.assertEqual([p.text(self.slot(out,i)) for i in [1,2,3,4]],['Euclid','Steps','Seq','Auto'])
  self.assertEqual([p.u.mem_read(self.slot(out,i)+0x22,1)[0] for i in range(6)],[0,1,1,1,1,0])
  for i in [2,3]:self.assertEqual(bytes(p.u.mem_read(self.slot(out,i)+32,16)),native[N.HDR(0x74)+(i-1)*48+32:N.HDR(0x74)+(i-1)*48+48],i) # native tab ids kept
  self.assertEqual(struct.unpack('<H',p.u.mem_read(self.slot(out,4)+44,2))[0],0x1084) # Auto crosses to the piano page
  self.assertEqual(p.call(UU['seq_toolbar'],p.model,out,0),0)
  event=0x2002e000;p.w(event,0x1051);p.call(0x0815d600,p.seqview,event)
  self.assertEqual(p.call(UU['seq_toolbar'],p.model,out,0),1);self.assertEqual(p.text(self.slot(out,5)),'Select ON')
 def test_select_added_after_first_apply_is_visible_in_real_header_root(self):
  # Native apply only updates visibility while root+117C is armed (page change).
  # Reproduces the hardware report: Select must still appear when the SEQ view
  # becomes supported after the first header tick.
  p=self.view_clear();view=p.r(0x24048004);p.call(0x08180198,ROOT)
  p.w(0x24048004,0);out=self.header_data(p);self.native_header(p,out)
  self.assertEqual(p.text(self.slot(out,5)),'');p.call(0x0817faf8,ROOT,out) # Undo removed, Select not yet
  self.assertEqual(p.u.mem_read(ROOT+N.ROOT_LAYOUT,1)[0],0)
  select=ROOT+N.ROOT_SLOTS+5*0xd0
  p.w(0x24048004,view);out=self.header_data(p);self.native_header(p,out)
  self.assertEqual(p.u.mem_read(ROOT+N.ROOT_LAYOUT,1)[0],1);p.call(0x0817faf8,ROOT,out)
  self.assertEqual(p.u.mem_read(ROOT+N.ROOT_LAYOUT,1)[0],0)
  self.assertEqual(p.text(select+0x3c+0x31),'Select');self.assertEqual(p.u.mem_read(select+0x30,1)[0],0)
  # Unchanged header on the next tick does not re-arm layout.
  out=self.header_data(p);self.native_header(p,out);self.assertEqual(p.u.mem_read(ROOT+N.ROOT_LAYOUT,1)[0],0)
 def test_drum_footer_is_identical_in_step_and_sequence_with_native_banks_preserved(self):
  p=self.view();layouts=[];banks=[]
  for mode in [0,1,0,1]:
   p.u.mem_write(p.seqview+0x113e0,bytes([mode]));p.call(0x0815c27c,p.seqview)
   banks.append(bytes(p.u.mem_read(p.seqview+0x113ac,16)))
   out=self.header_data(p);self.native_header(p,out)
   layouts.append([(p.text(self.slot(out,i)),p.u.mem_read(self.slot(out,i)+32,1)[0],p.u.mem_read(self.slot(out,i)+34,1)[0]) for i in range(6)])
  self.assertEqual(layouts,[layouts[0]]*4)
  self.assertNotEqual(banks[0],banks[1]);self.assertEqual(banks[0],banks[2]);self.assertEqual(banks[1],banks[3])
  p.w(0x24048004,0);p.call(0x0815c27c,p.seqview)
  out=self.header_data(p);self.native_header(p,out);self.assertEqual(p.text(self.slot(out,1)),'Euclid')
 def test_miniature_selector_and_hit_rectangle_are_centred_in_free_column(self):
  p=self.view();widget=p.seqview+0xe0f4
  for offset in [0,0x434,0x470,0x4b4]:
   self.assertEqual(tuple(p.r(widget+offset+j) for j in [4,8,12,16]),(190,8,106,42))
  out=self.header_data(p);self.native_header(p,out)
  p.u.mem_write(out,b'Kit and sequence name\0');p.u.mem_write(out+0x60,b'Seq 1\0')
  p.call(0x08180198,ROOT);p.call(0x0817faf8,ROOT,out)
  end=p.r(ROOT+N.ROOT(0x240))+p.r(ROOT+N.ROOT(0x248))
  self.assertEqual(190-end,322-(190+106))
 def test_select_on_lights_button_through_native_selected_state(self):
  # Owner request: Select ON needs a visible indication. Native apply sets the
  # selected state (+AC) from record +21 only while layout is armed.
  p=self.view_clear();p.call(0x08180198,ROOT);out=self.header_data(p);self.native_header(p,out);p.call(0x0817faf8,ROOT,out)
  select=ROOT+N.ROOT_SLOTS+5*0xd0;self.assertEqual(p.u.mem_read(select+0xac,1)[0],0)
  event=0x2002e000;p.w(event,0x1051);p.call(0x0815d600,p.seqview,event)
  out=self.header_data(p);self.native_header(p,out);self.assertEqual(p.u.mem_read(self.slot(out,5)+0x21,1)[0],1)
  self.assertEqual(p.u.mem_read(ROOT+N.ROOT_LAYOUT,1)[0],1);p.call(0x0817faf8,ROOT,out)
  self.assertEqual(p.text(select+0x3c+0x31),'Select ON');self.assertEqual(p.u.mem_read(select+0xac,1)[0],1)
  p.call(0x0815d600,p.seqview,event);out=self.header_data(p);self.native_header(p,out);p.call(0x0817faf8,ROOT,out)
  self.assertEqual(p.u.mem_read(select+0xac,1)[0],0)
 def test_native_persistent_header_renders_select_and_touch_action_reaches_selection(self):
  p=self.view_clear();out=self.header_data(p);self.native_header(p,out)
  root=0xc00d0000;p.call(0x08180198,root);p.call(0x0817faf8,root,out)
  # Native normal header buttons are +54C, each D0 bytes; R6: Select is the rightmost slot.
  select=root+N.ROOT_SLOTS+5*0xd0
  self.assertEqual(p.text(select+0x3c+0x31),'Select');self.assertEqual(p.u.mem_read(select+0x30,1)[0],0)
  self.assertEqual(p.r(select+0x14)&65535,0x1051)
  # Header routes the native release to the active SEQ view; parent is a fixture.
  p.u.mem_write(p.model+0x14c,b'\x00');event=0x2002e000;p.w(event,0x7a);p.w(event+8,0x1051)
  # W14 HW3 (owner): the one-shot burger cell is now Select All, so the toggle
  # is observed on the rebuilt persistent header button itself.
  p.call(0x0817fe70,root,event);out=self.header_data(p);self.native_header(p,out);p.call(0x0817faf8,root,out)
  self.assertEqual(p.text(select+0x3c+0x31),'Select ON');self.assertEqual(p.r(select+0x14)&65535,0x1051)

 def seq(self,p,code,ms):p.w(0x3001fe2c,ms);return p.call(UU['fx_dispatch'],p.model,code,0,11,0)
 def drum_view_name(self,p):
  return 'Euclid' if p.call(UU['seq_eu_mode'],p.seqview) else ('Seq' if p.u.mem_read(p.seqview+0x113e0,1)[0] else 'Steps')
 def test_r6_seq_button_cycles_euclid_steps_piano_on_one_shots(self):
  # R6.3 (owner spec): one-shot SEQ presses cycle Euclid -> Steps -> Seq -> Auto -> Euclid.
  p=self.view();p.call(UU['nav_tick']);p.call(UU['seq_eu_leave'],p.seqview);p.u.mem_write(p.seqview+0x113e0,b'\0');p.call(0x0815c27c,p.seqview)
  self.assertEqual(self.drum_view_name(p),'Steps');seen=[]
  # R6.3 (owner): the cycle includes Auto (the one-shot piano page 17).
  navs=[];p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(navs.append(u.reg_read(UC_ARM_REG_R1)),p.ret()),begin=0x081420ec,end=0x081420ec)
  self.assertEqual(self.seq(p,0xaf,1000),1);self.assertEqual(self.seq(p,0xb0,1050),1);seen.append(self.drum_view_name(p))
  self.assertEqual(seen,['Seq'])
  self.assertEqual(self.seq(p,0xaf,1500),1);self.assertEqual(self.seq(p,0xb0,1550),1)
  self.assertEqual(navs[-1:],[0x17]) # Seq -> Auto leaves for the piano page
 def test_r6_one_shot_view_is_remembered_per_pad(self):
  p=self.view();p.call(UU['nav_tick']);p.call(UU['seq_eu_leave'],p.seqview);p.u.mem_write(p.seqview+0x113e0,b'\1');p.call(0x0815c27c,p.seqview)
  self.assertEqual(self.drum_view_name(p),'Seq');p.call(UU['nav_tick'])
  p.u.mem_write(p.model+0x12c,b'\x02');self.assertEqual(self.seq(p,0xaf,1000),0);self.seq(p,0xb0,1050) # from Tracks: native
  p.u.mem_write(p.model+0x12c,b'\x27');p.u.mem_write(p.seqview+0x113e0,b'\0');p.call(0x0815c27c,p.seqview) # native page back on Steps
  p.w(0x3001fe2c,1100);p.call(UU['nav_tick']);self.assertEqual(self.drum_view_name(p),'Seq')
 def test_r6_drum_burger_is_the_shared_sequencer_burger_with_select_none(self):
  p=self.view();p.call(0x081412ec);p.call(UU['seq_nav_menus_tick'])
  menu=lambda:[(p.r(d+4+i*20),p.text(p.r(d+8+i*20))) for d in [0x30030168+m*0xe0 for m in range(20)] if p.r(d)==0xfa for i in range(p.u.mem_read(d+0xcc,1)[0])]
  self.assertEqual(menu(),[(N.NUI(0x1041),'Double Seq'),(N.NUI(0x1042),'Halve Seq'),(N.NUI(0x102f),'Cut Seq'),(N.NUI(0x102e),'Copy Seq'),(N.NUI(0x1030),'Paste Seq'),(0x1086,'Clear'),(N.NUI(0x102d),'Clear Auto'),(0x1065,'Select All'),(N.NUI(0x1032),'Undo')])
  event=0x2002e000;p.w(event,0x1065);p.call(0x0815d600,p.seqview,event);p.call(UU['seq_nav_menus_tick'])
  self.assertEqual(menu()[7],(0x1085,'Select None'))
  p.w(event,0x1085);p.call(0x0815d600,p.seqview,event);self.assertEqual(p.call(UU['seq_selection_active'],p.seqview),0)
  p.call(UU['seq_nav_menus_tick']);self.assertEqual(menu()[7],(0x1065,'Select All'))
 def test_shared_f9_burger_binds_its_current_cells_at_every_opening(self):
  # P168 exp3 (owner on exp2: the SEQ burger showed the PROJ burger). The oracle is the native
  # header: 0817FFF8(root, header record, 1) opens the popup and binds the RAM menu's cells
  # (0817818C, cell count to popup +904) only when the menu index differs from the one it
  # bound last (root +FE0). F9 is one menu for the Projects/Perform pages and the piano roll.
  p=self.view();p.call(0x08180198,ROOT)
  popup=0x30034430;p.call(0x08177d48,popup);p.w(ROOT+N.ROOT(0xfdc),popup) # the native popup, as the app start 0816E390/0816E256 wires it
  menus=0x30030168;f9=next(m for m in range(20) if p.r(menus+m*0xe0)==0xf9);ram=menus+f9*0xe0
  rec=0x2002e400;p.u.mem_write(rec,bytes(N.HDR_SIZE));p.u.mem_write(rec+N.HDR(0x1b0),struct.pack('<H',f9))
  def opened():
   p.call(0x0817fff8,ROOT,rec,1);n=p.r(popup+0x904);p.call(0x0817fff8,ROOT,rec,2);return n
  count=lambda:p.u.mem_read(ram+0xcc,1)[0]
  p.u.mem_write(p.model+0x12c,b'\x13');p.call(UU['seq_nav_menus_tick']) # Projects page: Projects, Settings, SD-card mode
  self.assertEqual(count(),3);self.assertEqual(opened(),3)
  p.u.mem_write(p.model+0x12c,b'\x17');p.call(UU['seq_nav_menus_tick']) # piano roll: the sequencer actions
  self.assertEqual(count(),9);self.assertEqual(opened(),count())
  p.u.mem_write(p.model+0x12c,b'\x13');p.call(UU['seq_nav_menus_tick'])
  self.assertEqual(count(),3);self.assertEqual(opened(),count())
 def test_exp3_one_shot_burger_shows_the_shared_list_with_undo_after_an_earlier_opening(self):
  # P168 exp3 (owner: an Undo entry in the one-shot SEQ burger). FA (page 27) gets the shared sequencer
  # list, Undo last; the native popup kept the cells of FA's FIRST opening (native binding cache, root +FE0),
  # which at boot are the native ones without Undo. Oracle: native header 0817FFF8 and native popup.
  p=self.view();p.call(0x08180198,ROOT);p.call(0x081412ec) # native menus as after boot
  popup=0x30034430;p.call(0x08177d48,popup);p.w(ROOT+N.ROOT(0xfdc),popup)
  menus=0x30030168;fa=next(m for m in range(20) if p.r(menus+m*0xe0)==0xfa);ram=menus+fa*0xe0
  count=lambda:p.u.mem_read(ram+0xcc,1)[0];cell=lambda i:(p.r(ram+4+i*20),p.text(p.r(ram+8+i*20)))
  rec=0x2002e400;p.u.mem_write(rec,bytes(N.HDR_SIZE));p.u.mem_write(rec+N.HDR(0x1b0),struct.pack('<H',fa))
  def opened():
   p.call(0x0817fff8,ROOT,rec,1);n=p.r(popup+0x904);p.call(0x0817fff8,ROOT,rec,2);return n
  native=count();self.assertLess(native,9)
  self.assertEqual(opened(),native) # opened once with the native cells
  p.u.mem_write(p.model+0x12c,b'\x27');p.call(UU['seq_nav_menus_tick'])
  self.assertEqual(count(),9);self.assertEqual(cell(8),(N.NUI(0x1032),'Undo'))
  p.call(0x0817fff8,ROOT,rec,1);self.assertEqual(p.r(popup+0x904),9) # the popup holds the nine cells now
  ninth=popup+0x34+8*0xd0;x,y,w,h=(p.r(ninth+4+4*i) for i in range(4)) # native popup layout: where it puts the ninth cell (Undo)
  self.assertGreater(w,0);self.assertGreater(h,0);self.assertLessEqual(x+w,1280);self.assertLessEqual(y+h,480)
  self.assertEqual(p.u.mem_read(ninth+0x30,1)[0],0) # shown (the unused tenth cell is hidden: +30 = 1)
  self.assertEqual(p.u.mem_read(popup+0x34+9*0xd0+0x30,1)[0],1)
  p.call(0x0817fff8,ROOT,rec,2)
 def test_exp3_a_pad_without_a_remembered_view_opens_on_steps(self):
  # P168 exp3 (owner: opening a pad shows Steps by default; it was Euclid).
  p=self.view();p.call(UU['seq_eu_leave'],p.seqview);p.u.mem_write(p.model+0x12c,b'\x02')
  self.assertEqual(self.seq(p,0xaf,1000),0);self.seq(p,0xb0,1050) # SEQ from Tracks: the native page change opens the sequencer
  p.u.mem_write(p.model+0x12c,b'\x27');p.u.mem_write(p.seqview+0x113e0,b'\0');p.call(0x0815c27c,p.seqview)
  p.w(0x3001fe2c,1100);p.call(UU['nav_tick']);self.assertEqual(self.drum_view_name(p),'Steps')
  p.w(0x3001fe2c,1200);p.call(UU['nav_tick']);self.assertEqual(self.drum_view_name(p),'Steps')
 def test_depth_increment_is_five_times_faster_without_speeding_other_controls(self):
  p=self.view();slot=p.seqview+0xebf0+0x38+5*0x468
  p.u.mem_write(slot+0x9c,struct.pack('<H',N.NKEY(0x195)))
  self.assertEqual(p.call(UU['kick_ui_increment'],slot,160),800)
  self.assertEqual(p.call(UU['kick_ui_increment'],slot,(-160)&0xffffffff),(-800)&0xffffffff)
  p.u.mem_write(slot+0x9c,struct.pack('<H',N.NKEY(0x191)));self.assertEqual(p.call(UU['kick_ui_increment'],slot,160),160)
 def test_glyph_replaces_value_text_at_native_size_white_on_black(self):
  p=self.view();p.call(UU['seq_selection_reset'],p.seqview);p.w(0x24048d80+20,0)
  for i in range(32):p.w(p.seqview+0x11420+i*4,0)
  p.call(UU['seq_eu_tab'],p.seqview);event=0x2002e000;p.call(0x0815c27c,p.seqview)
  paints=[]
  def fill(u,a,n,d):
   ptr=u.reg_read(UC_ARM_REG_R0);paints.append((tuple(p.r(ptr+i*4) for i in range(4)),u.reg_read(UC_ARM_REG_R1)));p.ret()
  for address in (0x08166e9e,0x08166ef6):p.u.hook_add(UC_HOOK_CODE,fill,begin=address,end=address)
  ctx=0x2002f000;p.w(ctx,1);p.w(ctx+4,0x20020000);p.call(UU['eu_glyph_paint'],p.seqview,ctx)
  self.assertEqual(len(paints),6);self.assertEqual([c for r,c in paints],[0xf1]+[0xf2]*5)
  self.assertEqual(paints[0][0][3],16)
 def test_clear_with_selected_steps_removes_only_those_notes(self):
  # P20 (owner plan: Clear acts on the selection; header Clear = native Clear Seq 102C).
  p=Native();p.generated(7,3);test_eu8.Tests().full_view(p);p.call(0x0815c27c,p.seqview);ev=0x2002e000;pad=p.r(p.seqview+0x11400)
  mine=lambda:sorted(struct.unpack_from('<I',e,4)[0]//960 for e in p.events() if struct.unpack_from('<H',e,2)[0]==pad)
  steps=mine();self.assertGreaterEqual(len(steps),2,steps)
  p.w(ev,0x1051);p.call(0x0815d600,p.seqview,ev)
  for st in steps[:2]:
   if not p.call(UU['seq_selection_match'],p.seqview,st):p.select(st)
  sel=[st for st in steps if p.call(UU['seq_selection_match'],p.seqview,st)];self.assertTrue(sel,'nothing selected')
  others=[e for e in p.events() if struct.unpack_from('<H',e,2)[0]!=pad]
  p.w(ev,N.NUI(0x102c));p.call(0x0815d600,p.seqview,ev)
  self.assertEqual(mine(),[st for st in steps if st not in sel])
  self.assertEqual([e for e in p.events() if struct.unpack_from('<H',e,2)[0]!=pad],others)
  self.assertFalse(p.call(UU['seq_selection_active'],p.seqview))
 def test_one_shot_euclidean_view_drops_native_tab_relight(self):
  # P21 (owner on P20: Step/Sequence flickered while Euclidean was selected).
  p=self.view();p.call(0x08180198,ROOT);out=self.header_data(p);self.native_header(p,out);p.call(0x0817faf8,ROOT,out)
  ev=0x2002e000;p.w(ev,0x1055);p.call(0x0815d600,p.seqview,ev)
  out=self.header_data(p);self.native_header(p,out);p.call(UU['device_header_prepare'],out);p.call(0x0817faf8,ROOT,out)
  step=ROOT+N.ROOT_TABS+2*0xd0;self.assertEqual(p.u.mem_read(step+0xac,1)[0],0)
  slot13=p.r(0x081b3680+13*4);E=0x2002f000;p.u.mem_write(E,struct.pack('<HH4I',0x68,0,0,0x49,1,0));p.call(slot13,ROOT,E)
  self.assertEqual(p.u.mem_read(step+0xac,1)[0],0)
  p.call(UU['seq_eu_leave'],p.seqview);p.call(slot13,ROOT,E);self.assertEqual(p.u.mem_read(step+0xac,1)[0],1) # Euclidean left: native
class PadsSeq(unittest.TestCase):
 view=Tests.view;header_data=Tests.header_data;slot=Tests.slot;native_header=Tests.native_header
 """R6.2 (owner spec): Pads/Seq on the one-shot SEQ page, per track and shared
 with INST. The M7 Kit/Seq gate (K16 state 24048CA0 +14) owns the pads there."""
 STATE=0x24048ca0
 def seq_page(self):
  p=self.view();p.u.mem_write(p.model+0x12c,b'\x27')
  p.posted=[]
  def post(u,a,n,d):p.posted.append(struct.unpack('<5I',u.mem_read(u.reg_read(UC_ARM_REG_R1),20)));p.ret(1)
  p.u.hook_add(UC_HOOK_CODE,post,begin=0x081403ec,end=0x081403ec) # native model event: captured
  p.call(UU['fx_dispatch'],p.model,0x3f,0,0);return p
 def press(self,p,pad,kind=12):
  rec=0x2002d000;epoch=p.u.mem_read(self.STATE+15,1)[0]
  p.u.mem_write(rec,struct.pack('<6I',0xfe,0x314d5442,0x3151534b,pad,kind,0x31525400|epoch))
  return p.call(UU['fx_dispatch'],p.model,0xfe,0,pad,rec)
 def tap(self,p,pad):self.press(p,pad);return self.press(p,pad,13) # R6.4: a tap toggles on release
 def test_pads_mode_arms_gate_and_selects_silently(self):
  p=self.seq_page();self.assertEqual(p.u.mem_read(self.STATE+14,1)[0],1)
  repaint=[];p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:repaint.append(u.reg_read(UC_ARM_REG_R0)),begin=0x0815b82a,end=0x0815b82a)
  before=p.events();self.assertEqual(self.press(p,5),1)
  self.assertEqual(repaint,[p.seqview]) # R6.5 (owner): the footer pad selector follows the pads (native refresh)
  self.assertEqual(p.r(p.seqview+0x11400),5);self.assertEqual(p.events(),before)
  # R6.3: one shared selection: the track's selected pad (property 0x74) follows
  self.assertTrue(any(e[0]==0xcf and e[2]==0x74 and e[3]==5 for e in p.posted),p.posted)
 def test_tracks_hold_owns_the_pads_over_pads_mode_lights(self):
  # R6.4 (owner: holding TRACKS showed the one-shot's sounds): while TRACKS is
  # held (and nothing picked), play_mute_flush skips kit_seq_lights.
  p=self.seq_page();self.assertEqual(p.call(UU['tracks_hold_active']),0)
  p.w(0x3001fe2c,9000);p.call(UU['fx_dispatch'],p.model,0xaf,0,2) # TRACKS down
  self.assertEqual(p.call(UU['tracks_hold_active']),1)
  p.w(0x3001fe2c,9300);p.call(UU['fx_dispatch'],p.model,0xb0,0,2)
  self.assertEqual(p.call(UU['tracks_hold_active']),0)
 def test_r614_lone_arrow_with_a_selected_step_switches_the_ratchet_page_combo_stays(self):
  # Real fx_dispatch order: kit_seq_arrows owns the SEQ page arrows (Left+Right
  # combo); a lone arrow's release with a selected step switches encoders 5..8.
  p=self.seq_page()
  for at in (0x0813130c,0x081257f0):p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=at,end=at)
  keys=lambda:[struct.unpack('<H',p.u.mem_read(p.seqview+0xebf0+0x38+i*0x468+0x9c,2))[0] for i in range(4,8)]
  arrow=lambda i:(p.call(UU['fx_dispatch'],p.model,0xaf,0,i),p.call(UU['fx_dispatch'],p.model,0xb0,0,i),p.call(0x0815c27c,p.seqview))
  p.call(0x0815c27c,p.seqview);native=keys();self.assertNotIn(0x9f,native)
  arrow(9);self.assertEqual(keys(),[0x9f,0xa0,0xa1,0xa5])
  arrow(0);self.assertEqual(keys(),native)
  mode=p.call(UU['kit_seq_track_mode'])
  p.call(UU['fx_dispatch'],p.model,0xaf,0,0);p.call(UU['fx_dispatch'],p.model,0xaf,0,9);p.call(UU['fx_dispatch'],p.model,0xb0,0,9);p.call(UU['fx_dispatch'],p.model,0xb0,0,0)
  p.call(0x0815c27c,p.seqview);self.assertNotEqual(p.call(UU['kit_seq_track_mode']),mode);self.assertNotIn(0x9f,keys()) # combo: mode toggles, no ratchet page
  p.call(UU['fx_dispatch'],p.model,0xaf,0,0);p.call(UU['fx_dispatch'],p.model,0xaf,0,9);p.call(UU['fx_dispatch'],p.model,0xb0,0,9);p.call(UU['fx_dispatch'],p.model,0xb0,0,0)
  self.assertEqual(p.call(UU['kit_seq_track_mode']),mode)
  # nothing selected: the lone arrow keeps its old action, no ratchet page
  p.w(0x24048d80+20,0)
  for i in range(32):p.w(p.seqview+0x11420+i*4,0)
  arrow(9);self.assertNotIn(0x9f,keys())
 def test_seq_mode_taps_steps_and_left_right_page(self):
  p=self.seq_page()
  for at in (0x0813130c,0x081257f0):p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=at,end=at) # native redraw / LED flush: fixture
  p.call(UU['fx_dispatch'],p.model,0xaf,0,0);p.call(UU['fx_dispatch'],p.model,0xaf,0,9) # R6.3: Left+Right toggles
  p.call(UU['fx_dispatch'],p.model,0xb0,0,9);p.call(UU['fx_dispatch'],p.model,0xb0,0,0)
  self.assertEqual(p.call(UU['kit_seq_track_mode']),1)
  ev=0x2002e000;p.w(ev,0x107e);p.w(ev+4,0)
  # R6.7b (owner: R6.4 + releasing a held step deselects it). R6.4: a tap
  # toggles on release; a hold >=350 ms opens the step natively (0815D1EC).
  calls=[];p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(calls.append((a,u.reg_read(UC_ARM_REG_R1))),p.ret()),begin=0x0815d1ec,end=0x0815d1ec)
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:(calls.append((a,u.reg_read(UC_ARM_REG_R1))),p.ret()),begin=0x0815d23c,end=0x0815d23c)
  pad=p.r(p.seqview+0x11400);before=len(p.events());self.press(p,2)
  self.assertEqual(len(p.events()),before) # R6.4: nothing on press
  self.press(p,2,13);self.assertNotEqual(len(p.events()),before);self.tap(p,2);self.assertEqual(len(p.events()),before)
  t=p.r(0x3001fe2c);self.press(p,3);p.w(0x3001fe2c,t+400);p.call(UU['kit_seq_periodic'])
  self.assertEqual(calls,[(0x0815d1ec,3)])
  slot=3+p.r(p.seqview+0x11404)-p.r(p.seqview+0x113f4);p.w(p.seqview+0x11420+slot*4,t+400) # native press slot (hook skipped the native write)
  n=len(p.events());self.press(p,3,13)
  self.assertEqual([i for i in range(32) if p.r(p.seqview+0x11420+i*4)],[]) # deselected: no press slot left (R6.8b)
  self.assertEqual(p.call(0x081b6840,p.seqview,3),0)
  self.assertEqual(len(p.events()),n);self.assertEqual(calls,[(0x0815d1ec,3)]) # no toggle, no native release
  self.assertEqual(p.r(p.seqview+0x11400),pad) # Seq mode never changes the sound
  self.assertEqual(p.call(UU['fx_dispatch'],p.model,0xaf,0,9),1);self.assertEqual(p.call(UU['fx_dispatch'],p.model,0xb0,0,9),1) # Right pages (on release), not next pad
  self.assertEqual(p.r(p.seqview+0x11400),pad)
  p.call(UU['kit_seq_event'],0,ev);self.assertEqual(p.call(UU['kit_seq_track_mode']),0)
 def test_gate_released_when_leaving_the_page(self):
  p=self.seq_page();p.call(UU['kit_seq_nav']);self.assertEqual(p.u.mem_read(self.STATE+14,1)[0],0)
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
