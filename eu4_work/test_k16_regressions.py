"""Exercise inherited synth/lock/LED/condition paths on the combined TF2 image."""
from pathlib import Path
import os,sys,unittest,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'k16_work'));sys.path.insert(0,str(ROOT/'k16_work/bento_controls'))
import release
stock=Path(os.environ['BENTO_STOCK_IMAGE']).read_bytes()
# Compile K16 symbol maps needed by the inherited compiled-code fixtures.
base,_=release.candidate(stock)
out=Path(os.environ['BENTO_FX_CANDIDATE']);image=(out/'bento1.bin').read_bytes()
UU=json.loads((out/'manifest.json').read_text())['ui_symbols']
writes=json.loads((out/'FULL_MANIFEST.json').read_text())['writes']
release.native.candidate=lambda stock:(image,writes)
import importlib.util, kick_build
spec=importlib.util.spec_from_file_location('optimized_kick', ROOT/'eu4_work/drums/kick_build.py')
optimized=importlib.util.module_from_spec(spec);spec.loader.exec_module(optimized);optimized.compile_kick()
kick_build.SYMS.clear();kick_build.SYMS.update(optimized.SYMS)
import unicorn
native_map=unicorn.Uc.mem_map
def full_application_map(self,address,size,*args,**kwargs):
 # Legacy fixture's 1.5 MiB flash window ended five KiB before the new UI.
 # Model the declared application region, without changing any firmware limit.
 if address==0x08040000 and size==0x180000:size=0x1c0000
 return native_map(self,address,size,*args,**kwargs)
unicorn.Uc.mem_map=full_application_map
import types
original_test=ROOT/'k16_work/bento_controls/test_k16.py'
module=types.ModuleType('test_k16');module.__file__=str(original_test)
source=original_test.read_text().replace("struct.unpack('<2H',p.u.mem_read(0x300000bc+8,4))","struct.unpack('<2H',p.u.mem_read(0x300000bc+12,4))")
source=source.replace('(1,12,20),(3,20,17),(5,25,17)','(1,12,16),(3,20,13),(5,25,13)').replace('p.encoder(0x1da,12)','p.encoder(0x1da,8)').replace('p.encoder(0x1e4,13)','p.encoder(0x1e4,9)')
# P10: the 909 Snare's Tune readout is 140 Hz x 2^(v/50): the default 10 shows 160 Hz (was 80+12v = 200 Hz).
source=source.replace("self.assertEqual(p.text(slot+0x2c8),'200 Hz')","self.assertEqual(p.text(slot+0x2c8),'160 Hz')")
exec(compile(source,str(original_test),'exec'),module.__dict__);sys.modules['test_k16']=module
# Translate the historical fixture's modifier calls to actual inline taps.
# The production PROJ path stays a no-op; historical source is left untouched.
def inline_targets(self,down=True):
 self.display()
 for which in range(2):
  key=self.word(0x300000bc+(6+which)*2)&65535;picker=0x1e4 if which else 0x1da
  if (key==picker)==bool(down):continue
  slot=self.view+0xebf0+0x38+(6+which)*0x468
  self.u.mem_write(slot+0x9c,key.to_bytes(2,'little'))
  self.call(UU['locks_touch'],slot,0)
  assert self.u.reg_read(module.UC_ARM_REG_R0)==1
  self.display()
module.SynthUI.shift=inline_targets
# P17 (owner plan): hold-INST on SEQ is removed, so its light-restoring return
# (test_inst_lights) no longer applies; stock INST is checked in test_previous_controls.
modules=['test_k16','test_l8','test_holdstep','test_conditions','test_mixer_lights','test_drum_mute']
modules=[m for m in modules if (ROOT/'k16_work/bento_controls'/(m+'.py')).exists()]
import test_drum_mute
class ShiftFreeDrumMute(test_drum_mute.Tests):
 def test_receiver_all_sixteen_pads_create_one_silent_mute_request(self):
  for pad in range(16):
   p=test_drum_mute.DrumInput();levels=[0]*16;levels[pad]=1000;p.packet(0x100,levels)
   self.assertEqual(p.custom(),[]);self.assertEqual(p.events(),[(172,pad,1000),(174,pad,1000)])
 def test_receiver_pressure_and_both_release_orders_are_consumed(self):
  for proj_first in [False,True]:
   p=test_drum_mute.DrumInput();p.packet(0x100,[1000]+[0]*15);p.packet(0x100,[1500]+[0]*15)
   self.assertEqual(p.custom(),[]);self.assertEqual(p.events(),[(174,0,1500)])
   if proj_first:p.packet(0,[1500]+[0]*15);self.assertEqual(p.events(),[])
   p.packet(0 if proj_first else 0x100);self.assertEqual(p.events(),[(173,0,0),(174,0,0)])
   self.assertEqual(p.readword(0x24048ca4)&65535,0)
 def test_full_queue_silences_shifted_press_without_overwrite_and_releases_cleanly(self):
  from test_input import UIQUEUE
  p=test_drum_mute.DrumInput();p.packet(0x100);p.word(UIQUEUE+0x21a0,225);p.word(UIQUEUE+0x2180,1)
  before=bytes(p.u.mem_read(UIQUEUE+0x980,256*24));p.packet(0x100,[1000]+[0]*15)
  self.assertEqual(p.custom(),[]);self.assertEqual(p.events(),[(172,0,1000),(174,0,1000)])
  self.assertEqual(bytes(p.u.mem_read(UIQUEUE+0x980,256*24)),before)
  p.packet();self.assertEqual(p.events(),[(173,0,0),(174,0,0)])
test_drum_mute.Tests=ShiftFreeDrumMute
suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
