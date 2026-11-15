"""P16 native header widgets, view banks, selection gestures and shortcuts."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import gc,struct,unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_melodic_locks import Page,KEEP,EV
from test_integration import UU,IMAGE
from test_perf import Page as PerfPage,LOCK,M
ROOT=0x30034d48;OUT=0x20032000
class Nav(Page):
 def bubble(self,u,a,n,d):
  # Substitute only parent delivery; the native header constructs the action.
  e=u.reg_read(UC_ARM_REG_R1)
  if self.r(e)&65535 in (0x49,0x4a,0x4b,0x1060,0x1061):
   u.reg_write(UC_ARM_REG_R0,self.view);u.reg_write(UC_ARM_REG_PC,0x0815a599)
  else:super().bubble(u,a,n,d)
 def action(self,code):self.w(EV,code);return self.call(0x0815a598,self.view,EV)
 def header(self):
  self.u.mem_write(OUT,IMAGE[0x8199008+8*N.HDR_SIZE-0x8040000:][:N.HDR_SIZE]);self.call(UU['seq_toolbar'],self.model,OUT,0);self.call(0x0817faf8,ROOT,OUT);return OUT
 def init_root(self):self.call(0x08180198,ROOT);return self.header()
 def flags(self):return [self.u.mem_read(OUT+N.HDR(0x74)+i*48+0x21,1)[0] for i in range(5)]
 def menu(self):
  self.call(0x081412ec);self.header();self.call(UU['seq_nav_menus_tick'])
  for m in range(20):
   d=0x30030168+m*0xe0
   if self.r(d)==0xf9:return [(self.r(d+4+i*20),self.text(self.r(d+8+i*20))) for i in range(self.u.mem_read(d+0xcc,1)[0])]
ED=N.CHORD_EDITOR # exp8 (owner, 13 Nov): 1.6.8 builds switch the chord progression editor off (no Chord view)
O=0 if ED else 1 # melodic footer slot of Steps/Seq/Auto (right-aligned 4 views when the Chord view is switched off)
class Tests(unittest.TestCase):
 def test_unchanged_fixed_tabs_do_not_request_another_header_refresh(self):
  p=Nav();p.init_root();label=0x20033000;p.u.mem_write(label,b'Event\0')
  self.assertEqual(p.call(UU['header_fixed_tab'],OUT,0,0x49,label,1),1)
  before=bytes(p.u.mem_read(OUT,N.HDR_SIZE))
  for _ in range(8):self.assertEqual(p.call(UU['header_fixed_tab'],OUT,0,0x49,label,1),0)
  self.assertEqual(bytes(p.u.mem_read(OUT,N.HDR_SIZE)),before)
  self.assertEqual(p.call(UU['header_fixed_tab'],OUT,0,0x49,label,0),1)
  self.assertEqual(p.call(UU['header_fixed_tab'],OUT,0,0x49,label,0),0)

 def test_one_shot_piano_page_shows_the_shared_one_shot_footer(self):
  # R6 (owner spec): one-shot footer is identical on pages 27 and 17.
  p=Nav();p.type=14;p.call(0x081599bc,p.view);p.init_root()
  self.assertEqual([p.text(OUT+N.HDR(0x74)+i*48) for i in range(6)],['','Euclid','Steps','Seq','Auto','Select'])
  self.assertEqual([p.r(ROOT+(N.ROOT_TABS if i<5 else N.ROOT_SLOTS)+i*0xd0+0x14) for i in range(1,6)],[0x1081,0x1082,0x1083,0x4b,0x1051])
  p.action(0x4b);p.header();self.assertEqual(p.u.mem_read(ROOT+N.ROOT_TABS+4*0xd0+0xac,1)[0],1) # Auto lit on the automation tab
  p.u.mem_write(EV,struct.pack('<5I',0x68,0,0x4b,1,0));p.call(UU['header_root_event'],ROOT,EV)
  self.assertEqual(p.u.mem_read(ROOT+N.ROOT_TABS+4*0xd0+0xac,1)[0],1)
  p.action(0x49);before=p.events();p.action(0x1051)
  self.assertEqual(p.call(UU['piano_selecting'],p.view),1);self.assertEqual(p.events(),before)
  self.assertEqual(p.call(UU['piano_eu_event'],p.view,EV),0)

 def test_six_equal_width_slots_are_five_native_tabs_and_select(self):
  # R6 (owner spec): Steps, Piano, Auto, Chord, Euclid tabs, Select rightmost.
  p=Nav();p.init_root();widgets=[ROOT+(N.ROOT_TABS if i<5 else N.ROOT_SLOTS)+i*0xd0 for i in range(6)]
  if not ED: # switched off: Steps, Seq, Auto, Euclid right-aligned in slots 1-4, slot 0 empty (as the one-shot footer)
   self.assertEqual([p.text(OUT+N.HDR(0x74)+i*48) for i in range(6)],['','Steps','Seq','Auto','Euclid','Select'])
   self.assertEqual([p.u.mem_read(OUT+N.HDR(0x74)+i*48+0x22,1)[0] for i in range(6)],[0,1,1,1,1,0])
   self.assertEqual([p.r(w+12) for w in widgets[1:]],[157]*5);self.assertEqual([p.u.mem_read(w+0x30,1)[0] for w in widgets[1:]],[0]*5)
   self.assertEqual([p.r(w+0x14) for w in widgets[1:]],[0x49,0x4a,0x4b,0x1061,0x1051]);self.assertNotIn(0x1060,[p.r(w+0x14) for w in widgets]);return
  self.assertEqual([p.text(OUT+N.HDR(0x74)+i*48) for i in range(6)],['Steps','Seq','Auto','Chord','Euclid','Select'])
  self.assertEqual([p.u.mem_read(OUT+N.HDR(0x74)+i*48+0x22,1)[0] for i in range(6)],[1,1,1,1,1,0])
  self.assertEqual([p.r(w+12) for w in widgets],[157]*6);self.assertEqual([p.u.mem_read(w+0x30,1)[0] for w in widgets],[0]*6)
  self.assertEqual([p.r(w+0x14) for w in widgets],[0x49,0x4a,0x4b,0x1060,0x1061,0x1051])
 def test_tab_activation_follows_actual_native_view_changes(self):
  p=Nav();p.init_root()
  steps=[(0x49,[1,0,0,0,0],0),(0x4a,[0,1,0,0,0],1),(0x1061,[0,0,0,0,1],1),(0x1060,[0,0,0,1,0],1),(0x4b,[0,0,1,0,0],2),(0x49,[1,0,0,0,0],0)] if ED else \
        [(0x49,[0,1,0,0,0],0),(0x4a,[0,0,1,0,0],1),(0x1061,[0,0,0,0,1],1),(0x1060,[0,0,0,0,1],1),(0x4b,[0,0,0,1,0],2),(0x49,[0,1,0,0,0],0)] # switched off: 0x1060 is inert
  for key,flags,tab in steps:
   p.action(key);p.header();self.assertEqual(p.flags(),flags);self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],tab)
   p.call(UU['device_header_prepare'],OUT);p.call(0x0817faf8,ROOT,OUT);self.assertEqual([p.u.mem_read(ROOT+N.ROOT_TABS+i*0xd0+0xac,1)[0] for i in range(5)],flags) # lights on screen
 def test_chord_layer_survives_switching_editor_and_step_locks_remain_editable(self):
  p=Nav();before=p.events();p.action(0x1060);self.assertEqual(p.call(UU['chord_live_active']),1 if ED else 0)
  p.action(0x49);self.assertEqual(p.call(UU['chord_view_visible']),0);self.assertEqual(p.call(UU['chord_live_active']),1 if ED else 0)
  if not ED:self.assertEqual(p.events(),before) # switched off: no chord layer, the clip's notes untouched
  p.select_ids([p.ids()[0]]);p.event(0x32,450);self.assertEqual(p.call(UU['locks_slot'],p.word(),0),0x510405aa)
  p.action(0x1060);self.assertEqual(p.call(UU['chord_view_visible']),1 if ED else 0)
 def test_repeated_euclid_tab_does_not_disable_or_regenerate_pattern(self):
  p=Nav();p.action(0x1061);p.event(N.NKEY(0x192),3);before=p.events()
  p.action(0x1061);self.assertEqual(p.events(),before);self.assertEqual(p.keys()[6:],[N.NKEY(0x194),N.NKEY(0x195)])
  p.action(0x49);self.assertEqual(p.events(),before);p.action(0x1061);self.assertEqual(p.events(),before)
 def test_repeated_chord_tab_only_selects_the_view(self):
  p=Nav();p.action(0x1060);bank=p.keys();p.action(0x1060);self.assertEqual(p.keys(),bank)
 def test_select_button_uses_existing_native_box_selection_flag(self):
  # P18: Select follows its own state (lit = on) and uses the native box mode
  # while on (owner: in edit mode touches wrote/deleted notes).
  p=Nav();grid=p.view+0x38;before=p.events();p.action(0x1051)
  self.assertEqual(p.call(UU['piano_selecting'],p.view),1);self.assertEqual(p.u.mem_read(grid+0xa50,1)[0],1)
  p.action(0x1051);self.assertEqual(p.call(UU['piano_selecting'],p.view),0);self.assertEqual(p.u.mem_read(grid+0xa50,1)[0],0);self.assertEqual(p.events(),before)
 def test_all_native_piano_touch_handlers_are_unchanged(self):
  # P17: touch-down (16) goes through grid_touch_down, which calls the native one.
  self.assertEqual(struct.unpack_from('<I',IMAGE,0x081b2bcc+16-0x08040000)[0],UU['grid_touch_down']|1)
  self.assertEqual(struct.unpack_from('<I',IMAGE,0x081b2bcc+20-0x08040000)[0],UU['grid_touch_move']|1)
  self.assertEqual(struct.unpack_from('<I',IMAGE,0x081b2bcc+24-0x08040000)[0],UU['grid_touch_up']|1)
 def test_drag_rectangle_starts_at_the_finger_without_select(self):
  # P17 (owner): without Select the rectangle opened at a stale anchor.
  p=Nav();g=p.view+0x38;p.u.mem_write(g+0xa50,b'\0');p.w(g+0xa48,640);p.w(g+0xa4c,400);PT=0x2001e000
  p.u.mem_write(PT,struct.pack('<2i',500,150));p.call(p.r(p.r(g)+16),g,PT,0)
  self.assertEqual((p.r(g+0xa48),p.r(g+0xa4c)),(500,150))
  p.u.mem_write(PT,struct.pack('<2i',700,300));p.call(0x08175f39,g,PT,0);p.call(0x08175f39,g,PT,0)
  self.assertEqual(struct.unpack('<4i',p.u.mem_read(g+0xa34,16)),(500,150,200,150))
 def test_seq_menu_has_automation_and_no_proj_pages(self):
  # P17 (owner plan): Projects / Settings / Date-Time only in the Performance burger.
  # W14 HW3 (owner): Select All in the burger of every sequencer.
  # R6 (owner spec): one burger for every sequencer; Select is in the footer.
  p=Nav();p.init_root();p.select_ids([]);menu=p.menu();self.assertEqual(menu,[(N.NUI(0x1041),'Double Seq'),(N.NUI(0x1042),'Halve Seq'),(N.NUI(0x102f),'Cut Seq'),(N.NUI(0x102e),'Copy Seq'),(N.NUI(0x1030),'Paste Seq'),(0x1086,'Clear'),(N.NUI(0x102d),'Clear Auto'),(0x1065,'Select All'),(N.NUI(0x1032),'Undo')])
  self.assertFalse({0x1062,0x1063,0x1064}&{k for k,_ in menu})
  p.select_ids([p.ids()[0]]);self.assertEqual(p.menu()[7],(0x1085,'Select None')) # R6: unselect
  p.call(UU['piano_select_none'],p.view);self.assertEqual(p.menu()[7],(0x1065,'Select All'))
 def test_chord_view_menu_offers_the_second_chord_bank(self):
  # R5: Chord Bank takes the Clear Auto cell; Undo stays last.
  if not ED: # switched off: no Chord view and no Chord Bank entry in any burger
   p=Nav();p.init_root();p.action(0x1060);menu=p.menu();self.assertNotIn(0x1052,[k for k,_ in menu]);self.assertEqual(menu[-1],(N.NUI(0x1032),'Undo'))
   p.action(0x1052);menu=p.menu();self.assertNotIn(0x1052,[k for k,_ in menu]);return
  p=Nav();p.init_root();p.action(0x1060);menu=p.menu();self.assertEqual(menu[6],(0x1052,'Chord Bank 2'));self.assertEqual(menu[-1],(N.NUI(0x1032),'Undo'))
  p.action(0x1052);menu=p.menu();self.assertEqual(menu[6],(0x1052,'Chord Bank 1'))
  p.action(0x49);menu=p.menu();self.assertNotIn(0x1052,[k for k,_ in menu])
 def test_settings_entries_navigate_directly_and_not_by_cycling(self):
  p=Nav()
  for code,page in [(0x1062,0x13),(0x1063,0x1a),(0x1064,0x19)]:p.action(code);self.assertEqual(p.navlog[-1],page)

 def test_auto_tab_opens_native_automation_and_select_is_rightmost(self):
  p=Nav();p.init_root();p.action(0x4b);self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],2)
  p.header();self.assertEqual(p.r(ROOT+N.ROOT_SLOTS+5*0xd0+0x14),0x1051)
  self.assertEqual(p.flags(),[0,0,1,0,0] if ED else [0,0,0,1,0])
 def test_undo_removed_from_footer_but_retained_in_editing_burger(self):
  p=Nav();p.init_root()
  for index in range(38):
   t=IMAGE[0x8199008+index*N.HDR_SIZE-0x8040000:][:N.HDR_SIZE];p.u.mem_write(p.model+0x12c,t[N.HDR(0x1c2):N.HDR(0x1c3)]);p.u.mem_write(OUT,t);p.call(UU['device_header_prepare'],OUT)
   self.assertNotIn('Undo',[p.text(OUT+N.HDR(0x74)+i*48) for i in range(6)])
  p.call(0x081412ec);p.call(UU['seq_nav_menus'],1)
  found=[]
  for m in range(20):
   d=0x30030168+m*0xe0;n=p.u.mem_read(d+0xcc,1)[0]
   if p.r(d)==0xf9:
    ids=[p.r(d+4+i*20) for i in range(n)];self.assertEqual(ids.count(N.NUI(0x1032)),1);self.assertLessEqual(n,9);found.append(d)
  self.assertTrue(found)
 def test_burger_undo_uses_native_piano_undo(self):
  p=Nav();seen=[]
  def undo(u,a,n,d):seen.append(u.reg_read(UC_ARM_REG_R0));p.ret()
  h=p.u.hook_add(UC_HOOK_CODE,undo,begin=0x0815879c,end=0x0815879c)
  p.action(N.NUI(0x1032));p.u.hook_del(h);self.assertEqual(seen,[p.view])
 def test_stale_proj_state_never_turns_plain_left_into_undo(self):
  p=PerfPage();KEEP.append(p);self.assertEqual(p.button(0xaf,0),0);p.w(LOCK+8,1);p.button(0xaf,0)
  self.assertFalse(any(e[0]==N.NUI(0x1032) for e in p.model_events));p.w(LOCK+8,0);self.assertEqual(p.button(0xb0,0),0)

 def test_switching_away_keeps_sequencer_menu_without_settings_leaking(self):
  # R6.10 (owner: the Seq burger showed on the Proj page): away from the
  # sequencers F9 gets its stock entries back; opening a burger (model event
  # F0..100) re-asserts the current page's burger first.
  p=Nav();p.init_root();p.select_ids([]);p.menu();p.call(UU['seq_nav_menus'],0)
  d=0x30030168+0x8c0;keys=lambda:[p.r(d+4+i*20) for i in range(p.u.mem_read(d+0xcc,1)[0])]
  self.assertEqual(keys()[2],N.NUI(0x101d));self.assertEqual(len(keys()),3)
  p.call(UU['analog_model_event'],p.model,self.event(p,0xf9))
  self.assertEqual(keys(),[N.NUI(0x1041),N.NUI(0x1042),N.NUI(0x102f),N.NUI(0x102e),N.NUI(0x1030),0x1086,N.NUI(0x102d),0x1065,N.NUI(0x1032)])
 def event(self,p,code):
  e=0x2001e000;p.u.mem_write(e,struct.pack('<HHIIII',code,0,0,0,0,0));return e
 def selected(self,p):
  g=p.view+0x38;out=0x2001d000;n=p.r(g+0x1254);ids=[]
  for i in range(n):p.call(0x08174d70,g,i,out);ids.append(p.r(out))
  return ids
 def test_left_right_step_through_notes_in_time_order(self):
  # P17 (owner on P16): Left/Right go to the previous/next note, not the next sequence.
  p=Nav();order=[struct.unpack_from('<I',e,12)[0] for e in sorted(p.events(),key=lambda e:(struct.unpack_from('<I',e,4)[0],struct.unpack_from('<H',e,16)[0]))]
  seq=[];h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:seq.append(1),begin=0x0815b3ec,end=0x0815b3ec)
  p.select_ids([order[0]]);E=0x2002e000
  for idx,want in [(9,order[1]),(9,order[2]),(0,order[1])]:
   p.u.mem_write(E,struct.pack('<5I',0xae,0,idx,0,0));p.call(0x0815b548,p.view,E);self.assertEqual(self.selected(p),[want])
  p.u.hook_del(h);self.assertEqual(seq,[])
 def note_point(self,p,ident):
  g=p.view+0x38;base=p.r(g+0x34)
  for i in range(0x9000//0x48):
   w=base+i*0x48
   if p.u.mem_read(w+0x31,1)[0] and p.r(w+0x40)==ident:x,y,wd,h=struct.unpack('<4i',p.u.mem_read(w+4,16));return x+wd//2,y+h//2
 def touch(self,p,native):
  # Touch-down through the patched grid slot (snapshot), then the native result
  # of the touch (fixture: the device selects through its own queue) and E6.
  g=p.view+0x38;PT=0x2001e000;p.u.mem_write(PT,struct.pack('<2i',300,100))
  p.call(p.r(p.r(g)+16),g,PT,0);p.call(p.r(p.r(g)+24),g,PT,0)
  p.call(0x08174bac,g,0)
  for i in native:p.call(0x08174c4e,g,i,0)
  p.action(0xe6)
 def test_select_mode_forces_box_mode_at_every_touch(self):
  # P19 (owner on P18: with Select lit, touches deleted notes like edit mode).
  p=Nav();g=p.view+0x38;p.action(0x1051);p.u.mem_write(g+0xa50,b'\0');PT=0x2001e000
  p.u.mem_write(PT,struct.pack('<2i',300,100));p.call(p.r(p.r(g)+16),g,PT,0)
  self.assertEqual(p.u.mem_read(g+0xa50,1)[0],1);self.assertEqual(struct.unpack('<2i',p.u.mem_read(g+0xa48,8)),(300,100))
 def test_left_right_without_the_view_sequence_handle_use_the_current_sequence(self):
  # P18 (owner on P17: Left/Right still switched sequences).
  p=Nav();order=[struct.unpack_from('<I',e,12)[0] for e in sorted(p.events(),key=lambda e:(struct.unpack_from('<I',e,4)[0],struct.unpack_from('<H',e,16)[0]))]
  seq=p.r(p.view+0x11cd00);p.w(p.model+0x144,seq);p.select_ids([order[0]]);p.w(p.view+0x11cd00,0)
  seen=[];h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:seen.append(1),begin=0x0815b3ec,end=0x0815b3ec);E=0x2002e000
  p.u.mem_write(E,struct.pack('<5I',0xae,0,9,0,0));p.call(0x0815b548,p.view,E);p.u.hook_del(h)
  self.assertEqual(self.selected(p),[order[1]]);self.assertEqual(seen,[])
 def test_stale_native_tab_light_is_cleared_directly(self):
  # P18 (owner on P17: Seq stayed lit beside Chord/Euclid).
  p=Nav();p.init_root();p.action(0x4a);p.header();seqtab=ROOT+N.ROOT_TABS+(1+O)*0xd0
  self.assertEqual(p.u.mem_read(seqtab+0xac,1)[0],1)
  p.action(0x1061);p.u.mem_write(seqtab+0xac,b'\x01') # the native tab keeps its own light
  out=p.header();p.call(UU['device_header_prepare'],OUT);self.assertEqual(p.u.mem_read(seqtab+0xac,1)[0],0)
 def test_native_tab_relight_is_dropped_only_while_chord_or_euclid_is_shown(self):
  # P20 (owner on P18: Step flickered beside Chord): the piano view's own
  # "light tab 49" request (header event 68) must not reach the root then.
  p=Nav();p.init_root();steptab=ROOT+N.ROOT_TABS+O*0xd0;E=0x2002f000
  slot13=struct.unpack_from('<I',IMAGE,0x081b3680+13*4-0x08040000)[0];self.assertEqual(slot13,UU['header_root_event']|1)
  def relight():p.u.mem_write(E,struct.pack('<HH4I',0x68,0,0,0x49,1,0));p.call(slot13,ROOT,E)
  if ED:
   p.action(0x1060);p.call(UU['device_header_prepare'],p.header());p.call(0x0817faf8,ROOT,OUT)
   relight();self.assertEqual(p.u.mem_read(steptab+0xac,1)[0],0)
  else:p.call(UU['device_header_prepare'],p.header());p.call(0x0817faf8,ROOT,OUT) # switched off: no Chord view
  p.action(0x1061)
  if not ED:p.u.mem_write(steptab+0xac,b'\0') # the light left from the Steps view at start (ED: the Chord step cleared it)
  relight();self.assertEqual(p.u.mem_read(steptab+0xac,1)[0],0)
  p.action(0x49);p.u.mem_write(steptab+0xac,b'\0');relight();self.assertEqual(p.u.mem_read(steptab+0xac,1)[0],1) # Step view: native as before
 def note_point(self,p,ident):
  g=p.view+0x38;base=p.r(g+0x34)
  for i in range(0x9000//0x48):
   w=base+i*0x48
   if p.u.mem_read(w+0x31,1)[0] and p.r(w+0x40)==ident:x,y,wd,h=struct.unpack('<4i',p.u.mem_read(w+4,16));return x+wd//2,y+h//2
 def tap(self,p,xy):
  g=p.view+0x38;PT=0x2001e000;p.u.mem_write(PT,struct.pack('<2i',*xy))
  for slot in (16,24):p.call(p.r(p.r(g)+slot),g,PT,0)
 def test_select_taps_select_notes_instead_of_deleting_them(self):
  # P21 (owner on P20: with Select lit, touching a note still deleted it).
  p=Nav();all_=p.ids();ids=all_[3::3];p.select_ids([]);p.action(0x1051);before=len(p.events()) # notes right of the keyboard column
  pts=[self.note_point(p,i) for i in ids[:3]];self.assertNotIn(None,pts,pts)
  at=lambda xy:sorted(i for i in all_ if self.note_point(p,i)==xy) # the fixture stacks a chord's notes on one spot
  self.tap(p,pts[0]);self.assertEqual(sorted(self.selected(p)),at(pts[0]))
  self.tap(p,pts[1]);self.assertEqual(sorted(self.selected(p)),sorted(at(pts[0])+at(pts[1])))
  self.tap(p,pts[0]);self.assertEqual(sorted(self.selected(p)),at(pts[1])) # touching selected notes removes them
  self.assertEqual(len(p.events()),before) # nothing deleted or created

 def test_automation_view_can_be_left_from_view_tabs(self):
  # P22 (owner: no way out of the automation view); R6: no burger entry needed.
  for code,tab in [(0x49,0),(0x4a,1),(0x1060,0 if ED else 2),(0x1061,0)]: # switched off: 0x1060 is inert (no Chord view)
   p=Nav();p.action(0x4b);self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],2)
   p.action(code);self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],tab,hex(code))

 def seq(self,p,code,ms):p.w(0x3001fe2c,ms);return p.call(UU['fx_dispatch'],p.model,code,0,11,0)
 def test_seq_button_cycles_steps_piano_auto_and_reenters_from_chord_or_euclid(self):
  # R6.3 (owner spec): on the melodic SEQ page each press moves through every view.
  p=Nav();p.init_root();p.action(0x49);before=p.events()
  # R6.3 (owner): every view is in the cycle: Steps -> Seq -> Auto -> Chord -> Euclid -> Steps.
  def where():
   return 'Chord' if p.call(UU['chord_view_visible']) else 'Euclid' if p.call(UU['piano_custom_view']) else ('Steps','Seq','Auto')[p.u.mem_read(p.view+0x125dac,1)[0]]
  seen=[]
  for i in range(5 if ED else 4):
   self.assertEqual(self.seq(p,0xaf,1000+i*500),1);self.assertEqual(self.seq(p,0xb0,1050+i*500),1);p.call(UU['nav_tick']);seen.append(where())
  self.assertEqual(seen,['Seq','Auto','Chord','Euclid','Steps'] if ED else ['Seq','Auto','Euclid','Steps']) # switched off: Steps -> Seq -> Auto -> Euclid
  self.assertEqual(p.events(),before)

 def test_first_seq_press_from_another_page_restores_the_tracks_last_view(self):
  # R6 (owner spec): editors remember their last view per track.
  p=Nav();p.init_root();p.action(0x4a);p.call(UU['nav_tick'])
  p.u.mem_write(p.model+0x12c,b'\x02') # leave to Tracks
  self.assertEqual(self.seq(p,0xaf,1000),0);self.assertEqual(self.seq(p,0xb0,1050),0) # native opens SEQ
  p.u.mem_write(p.model+0x12c,b'\x17');p.action(0x49) # the native page comes back on Steps
  p.w(0x3001fe2c,1100);p.call(UU['nav_tick']);self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],1) # Piano restored

 def test_native_automation_tab_light_reaches_the_auto_tab_directly(self):
  p=Nav();p.init_root();p.action(0x4b);p.header();E=0x2002f000
  p.u.mem_write(E,struct.pack('<HH4I',0x68,0,0,0x4b,1,0));p.call(UU['header_root_event'],ROOT,E)
  self.assertEqual(p.u.mem_read(ROOT+N.ROOT_TABS+(2+O)*0xd0+0xac,1)[0],1)
  self.assertEqual(p.r(E+8),0x4b)
 def test_persistent_header_releases_reach_the_view_tabs(self):
  p=Nav();p.init_root();p.action(0x49);p.u.mem_write(p.model+0x14c,b'\0');E=0x2002f000
  for code,tab in ((0x4a,1),(0x49,0),(0x4b,2),(0x49,0)):
   p.u.mem_write(E,struct.pack('<5I',0x7a,0,code,0,0));p.call(0x0817fe70,ROOT,E);p.header()
   self.assertEqual(p.u.mem_read(p.view+0x125dac,1)[0],tab)
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
