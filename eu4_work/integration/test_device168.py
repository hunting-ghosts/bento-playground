"""P168 run 19: the pages of the device, entered the way the owner enters them, on the whole emulated M4 UI. 1.6.8 only.

Emulator evidence, not hardware evidence. port/device168.py starts the image as the device does (native reset,
the steps of main, the UI task loop, the file worker, native FatFs on an emulated card) and loads a project with
the firmware's own loader; hardware buttons arrive as records of the M7->M4 event ring and touches as touch
controller records. Nothing of the UI or the model is replaced by Python, so the native string getter, the native
draw context on the UI task's stack and the native navigation are the real ones. The M7 is not emulated: projects
here have tracks without sample files.

Why (owner, hardware, 14 Nov 2026, P168 exp8 3e130da0...): crashes on entering the FX page and the PROJ page
(black box: pc=08169CF6 with r2=0, and pc=00000000), "mixer hold + pad ... left me stranded on an old weird
settings page", frame A around the single row of Track FX. On the exp8 image the first two test classes fail with
the device's own crash record: `pc=08169cf6 lr=30037c48 ... r1=30018be0 r5=300378f8 r7=30018d70` on the FX button.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N
import os,sys,unittest
from pathlib import Path
KEEP=[]
if N.BENTO_FW==168:
 sys.path.insert(0,str(Path(__file__).resolve().parent/'port'));import device168 as D;sys.path.pop(0)
 FX,PROJ,MIXER,TRACKS,INST,SEQ,LAUNCH=D.FX,D.PROJ,D.MIXER,D.TRACKS,D.INST,D.SEQ,D.LAUNCH
# One track of every type that loads without sample files; one name longer than the 31 characters the UI shows.
TRACKS8=[('samtrack','Kit'),('wttrack','A Long Track Name 0123456789 abcdefgh'),('samtrack','Drums'),('multisamtrack','Keys'),
         ('wttrack','Wave'),('grtrack','Grain'),('slicertrack','Slice'),('looptrack','Loop')]
NAMES=[n for _,n in TRACKS8]
FX_FOOTER=['Mod FX','Send FX','XY Pads']
PROJ_FOOTER=['Perform','Macro','Settings','Projects']
BG=0xf1;FRAME_A=0xa6

def image():return Path(D.image_path()).read_bytes()
def device(files):
 d=D.Device168(image(),files);KEEP.append(d);return d.boot()
def footer(d):return [f[0] for f in d.footer()]
def state(d):return (d.page(),footer(d))


class Booted(unittest.TestCase):
 """One device per class, booted with the project on the card (the firmware autoloads it); every test starts from
 a snapshot of that state."""
 FILES=None
 @classmethod
 def setUpClass(cls):
  if N.BENTO_FW!=168:return   # (every test class below is skipped on 1.6.1)
  cls.d=device(cls.FILES if cls.FILES is not None else {'Projects/Demo/project.xml':D.project(TRACKS8)})
  cls.prepare(cls.d);cls.snap=cls.d.snapshot()
 @classmethod
 def prepare(cls,d):pass
 def setUp(self):self.d.restore(self.snap)
 def fx_views(self):
  d=self.d
  d.press(FX);self.assertEqual(state(d),(0x0b,FX_FOOTER))            # Mod FX view (track toggles with their names)
  d.footer_tap('Send FX');self.assertEqual(state(d),(0x0b,FX_FOOTER))
  d.footer_tap('XY Pads');self.assertEqual(state(d),(0x0c,FX_FOOTER))
  d.footer_tap('Mod FX');self.assertEqual(state(d),(0x0b,FX_FOOTER))
  d.run(30);d.press(FX);d.run(30);d.press(FX);self.assertIn(d.page(),(0x0b,0x0c))   # the FX button's own cycle
 def proj_views(self):
  d=self.d
  d.press(PROJ);self.assertEqual(state(d),(0x1a,PROJ_FOOTER+['Tap','Motion']))      # Perform (track name strip)
  d.footer_tap('Macro');self.assertEqual(state(d),(0x1a,PROJ_FOOTER+['Motion']))
  d.footer_tap('Settings');self.assertEqual(state(d),(0x1a,PROJ_FOOTER+['Set Time']))
  d.footer_tap('Projects');self.assertEqual(state(d),(0x13,PROJ_FOOTER+['Save','Load']))
  d.footer_tap('Perform');self.assertEqual(state(d),(0x1a,PROJ_FOOTER+['Tap','Motion']))
  for want in (PROJ_FOOTER+['Motion'],PROJ_FOOTER+['Set Time'],PROJ_FOOTER+['Save','Load'],PROJ_FOOTER+['Tap','Motion']):
   d.run(40);d.press(PROJ);self.assertEqual(footer(d),want)                         # PROJ cycles (not a double press)


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Exp8CrashPagesAfterBoot(Booted):
 """Fresh boot, the project on the card autoloaded: crash A/B of exp8."""
 def test_the_project_is_the_one_on_the_card_with_its_real_names(self):
  self.assertEqual([n for _,n in self.d.tracks()],NAMES);self.assertEqual(self.d.page(),0x02)
  self.assertIn(('Projects\\Demo\\project.xml',1),self.d.opens)
 def test_native_name_getter_always_writes_256_bytes(self):
  # the property behind the crashes, measured on the native getter itself (key 82, "Kit")
  d=self.d;buf=0x20012000;d.u.mem_write(buf,b'\xaa'*0x200)
  self.assertEqual(d.getter_raw(d.tracks()[0][0],0x82,buf),1);b=bytes(d.u.mem_read(buf,0x200))
  self.assertEqual(b[:4],b'Kit\0');self.assertEqual(b[:0x100].count(0xaa),0);self.assertEqual(b[0x100:],b'\xaa'*0x100)
 def test_fx_button_and_its_three_views(self):self.fx_views()
 def test_proj_button_and_its_four_views(self):self.proj_views()
 def test_perform_shows_the_track_names(self):
  d=self.d;d.press(PROJ);strip=d.screen()[2:30,:]
  for i in range(8):self.assertGreater(int((strip[:,160*i:160*i+160]!=BG).sum()),40,'no name over column %d'%i)
 def test_mod_fx_shows_the_track_names_under_the_toggles(self):
  d=self.d;d.press(FX);row=d.screen()[392:422,:]
  for i in range(8):self.assertGreater(int((row[:,160*i:160*i+160]!=0).sum()),40,'no name under toggle %d'%i)
 def test_one_shot_kit_and_pad_footer_label(self):
  # the third 64-byte buffer of exp8: the one-shot INST footer label "<Kit>: Pad <n>"
  d=self.d;d.press(INST);self.assertEqual(d.page(),0x07);self.assertEqual(footer(d),['Kit','Pad','Recording','Mute'])
  self.assertEqual(d.title(),'Kit: Pad 1')
  d.footer_tap('Pad');d.run(4);self.assertIn(d.page(),(0x08,0x14))   # the pad's view; an empty pad opens the browser (page 14)


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Exp8CrashPagesAfterProjectLoad(Booted):
 """Two projects on the card. The boot loads the first ("Aaa"); "Demo" is then loaded the way the owner loads a
 project: PROJ, footer Projects, the list row, footer Load."""
 @classmethod
 def setUpClass(cls):
  if N.BENTO_FW==168:cls.FILES={'Projects/Aaa/project.xml':D.project([('samtrack','First Kit'),('wttrack','First Wave')]),
                                'Projects/Demo/project.xml':D.project(TRACKS8)}
  super().setUpClass()
 @classmethod
 def prepare(cls,d):
  assert [n for _,n in d.tracks()]==['First Kit','First Wave'],d.tracks()
  d.opens.clear();d.load_project(1)
 def test_the_loaded_project(self):
  self.assertEqual([n for _,n in self.d.tracks()],NAMES);self.assertIn(('Projects\\Demo\\project.xml',1),self.d.opens)
  self.assertEqual(state(self.d),(0x02,['Tracks','Track FX']))
 def test_fx_button_and_its_three_views(self):self.fx_views()
 def test_proj_button_and_its_four_views(self):self.proj_views()


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class HoldReturn(Booted):
 """Owner, exp8: "mixer hold + pad for soloing a track did solo but also left me stranded on an old weird settings
 page". The K16 hold controls return to the page NUMBER they saved; Perform, Macro, Settings, Projects and Track FX
 are views of ours over pages 1A/13, so the return showed the bare native Project Settings page (no footer)."""
 def pad(self,pad,action):   # the record our M7 pad hook posts while a hold is active (5 solo, 6 mute; 3/4 launch)
  self.d.event(0xfe,pad,0xfffffffe,0x314d5442,action,0x31525442);self.d.run(4)
 def hold(self,button,action,enter):
  d=self.d;enter(d);before=state(d);self.assertNotIn(before[0],(0x1e,0x1f))
  d.down(button);self.assertEqual(d.page(),0x1f if button==MIXER else 0x1e)
  self.pad(1,action);d.up(button);self.assertEqual(state(d),before)
 def test_mixer_hold_and_pad_returns_to_perform(self):self.hold(MIXER,5,lambda d:d.press(PROJ))
 def test_mixer_hold_and_pad_returns_to_macro(self):self.hold(MIXER,5,lambda d:(d.press(PROJ),d.footer_tap('Macro')))
 def test_mixer_hold_and_pad_returns_to_settings(self):self.hold(MIXER,6,lambda d:(d.press(PROJ),d.footer_tap('Settings')))
 def test_mixer_hold_and_pad_returns_to_projects(self):self.hold(MIXER,6,lambda d:(d.press(PROJ),d.footer_tap('Projects')))
 def test_mixer_hold_and_pad_returns_to_track_fx(self):self.hold(MIXER,5,lambda d:d.press(TRACKS))
 def test_mixer_hold_and_pad_returns_to_the_fx_page(self):self.hold(MIXER,5,lambda d:d.press(FX))
 def test_mixer_hold_and_pad_returns_to_tracks(self):self.hold(MIXER,6,lambda d:None)
 def test_launch_hold_and_pad_returns_to_perform(self):self.hold(LAUNCH,3,lambda d:d.press(PROJ))
 def test_mute_and_solo_reach_the_track(self):
  d=self.d;h=d.tracks()[1][0];get=lambda key:d.prop(h,key)
  d.press(PROJ);d.down(MIXER);self.pad(1,6);self.assertEqual(get(N.NKEY(0x13d)),1);self.pad(1,5);self.assertEqual(get(N.NKEY(0x13e)),1)
  d.up(MIXER)
 def test_a_plain_mixer_press_from_perform_stays_on_the_mixer(self):
  d=self.d;d.press(PROJ);d.press(MIXER);self.assertEqual(d.page(),0x1f)
 def test_starting_on_the_mixer_the_hold_stays_on_the_mixer_like_stock(self):
  d=self.d;d.press(MIXER);d.run(30);before=state(d);d.down(MIXER);self.pad(2,5);d.up(MIXER);self.assertEqual(state(d),before)
 def test_perform_is_whole_again_after_the_return(self):
  d=self.d;d.press(PROJ);a=d.screen().copy();d.down(MIXER);self.pad(1,5);d.up(MIXER);self.pad(1,5) # (the second pad record is ignored: no hold)
  d.down(MIXER);self.pad(1,5);d.up(MIXER);d.run(6)                                                  # solo off again
  self.assertEqual(int((d.screen()[0:430,:]!=a[0:430,:]).sum()),0)


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Pages(Booted):
 def test_footer_tab_track_fx_on_the_tracks_page_opens_track_fx(self):
  # found by this harness: the tap arrives as a model event, the Tracks view's event slot never sees it
  d=self.d;self.assertEqual(state(d),(0x02,['Tracks','Track FX']));d.footer_tap('Track FX')
  self.assertEqual(state(d),(0x1a,['Tracks','Track FX']));d.footer_tap('Tracks');self.assertEqual(d.page(),0x02)
 def frame_pixels(self,top,bottom):
  s=self.d.screen();return int((s[top:bottom,:]==FRAME_A).sum())
 def test_no_frame_a_around_the_only_row_of_track_fx(self):
  # owner rule: the row frame only shows when there are several rows to choose from
  d=self.d;d.press(TRACKS);self.assertEqual(d.page(),0x1a);s=d.screen()
  self.assertEqual(int((s[4,8:1270]==FRAME_A).sum()),0);self.assertEqual(int((s[68,8:1270]==FRAME_A).sum()),0)
  self.assertGreater(int((s[76,8:630]==FRAME_A).sum()),500)   # the EQ | Compressor | Saturator choice keeps its frame
 def test_no_frame_a_in_the_mod_fx_view_but_around_the_active_send_fx_row(self):
  # frame A is 1 px, 1272 wide: a full line of colour A6. (The dim labels use A6 too, never as a full line.)
  line=lambda s:max(int((s[y,4:1276]==FRAME_A).sum()) for y in range(0,430))
  d=self.d;d.press(FX);d.run(4);self.assertLess(line(d.screen()),200)
  d.footer_tap('Send FX');d.run(4);self.assertGreater(line(d.screen()),1200)   # two rows to choose from: Delay / Reverb
  d.footer_tap('Mod FX');d.run(4);self.assertLess(line(d.screen()),200)
 def test_settings_and_perform_keep_their_row_frames(self):
  line=lambda s:max(int((s[y,4:1276]==FRAME_A).sum()) for y in range(0,430))
  d=self.d;d.press(PROJ);self.assertGreater(line(d.screen()),1200)                 # Chord / Arp rows
  d.footer_tap('Settings');d.run(4);self.assertGreater(line(d.screen()),1200)      # several sections


@unittest.skipUnless(N.BENTO_FW==168,'1.6.8 build')
class Sweep(Booted):
 def test_every_button_footer_button_and_burger_from_the_loaded_project(self):
  """Every hardware button (twice: the cycling buttons), in every state every visible footer button and the
  burger menu. Nothing may fault. (tools/port/sweep168.py runs the long form with arrows for the reports.)"""
  res=D.sweep(self.d,repeats=2,arrows=False)
  faults=['%s: %s'%(' > '.join('%s %s'%x for x in p),r) for p,r in res if r.startswith('FAULT')]
  self.assertGreater(len(res),60);self.assertEqual(faults,[])


if __name__=='__main__':unittest.main()
