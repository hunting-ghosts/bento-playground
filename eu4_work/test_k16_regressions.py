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
source=original_test.read_text()
def rewrite(old,new):
 # 1.6.8 port: a rewrite that no longer matches would silently test something else
 global source
 assert old in source,'K16 fixture rewrite no longer matches: '+old
 source=source.replace(old,new)
rewrite("struct.unpack('<2H',p.u.mem_read(0x300000bc+8,4))","struct.unpack('<2H',p.u.mem_read(0x300000bc+12,4))")
rewrite('(1,12,20),(3,20,17),(5,25,17)','(1,12,16),(3,20,13),(5,25,13)');rewrite('p.encoder(NID.NKEY(0x1da),12)','p.encoder(NID.NKEY(0x1da),8)');rewrite('p.encoder(NID.NKEY(0x1e4),13)','p.encoder(NID.NKEY(0x1e4),9)')
# P10: the 909 Snare's Tune readout is 140 Hz x 2^(v/50): the default 10 shows 160 Hz (was 80+12v = 200 Hz).
rewrite("self.assertEqual(p.text(slot+0x2c8),'200 Hz')","self.assertEqual(p.text(slot+0x2c8),'160 Hz')")
exec(compile(source,str(original_test),'exec'),module.__dict__);sys.modules['test_k16']=module
# Translate the historical fixture's modifier calls to actual inline taps.
# The production PROJ path stays a no-op; historical source is left untouched.
def inline_targets(self,down=True):
 self.display()
 for which in range(2):
  key=self.word(0x300000bc+(6+which)*2)&65535;picker=module.NID.NKEY(0x1e4) if which else module.NID.NKEY(0x1da)
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
# P168 exp5 (owner, 12 Nov): the condition lists are in picker order (%, Always, A:B up to 4:4, 1ST..!PRE
# offered; older A:B 1:5..8:8 shown after them, never offered). Stored codes are unchanged. The historical T2
# tests assert the old list order; these overrides check the same paths for every value in the new order.
import test_conditions,struct
from unicorn.arm_const import UC_ARM_REG_R1 as _R1,UC_ARM_REG_R3 as _R3,UC_ARM_REG_R6 as _R6
def _pos(raw):return 99 if raw==0 or raw>138 else raw-1 if raw<100 else raw if raw<109 else raw+4 if raw<135 else raw-26
def _code(q):return 0 if q==99 else q+1 if q<99 else q if q<109 else q+26 if q<113 else q-4
def _edit(raw):return 100 if raw==0 or raw>138 else raw if raw<100 else raw+1 if raw<109 else raw+5 if raw<135 else raw-25
class PickerOrderConditions(test_conditions.Tests):
 def test_on_screen_table_preserves_native_entries_and_appends_labels(self):
  T,IM,ST,L=test_conditions.TABLE,test_conditions.IMAGE,test_conditions.STOCK,test_conditions.LABELS
  self.assertEqual(IM[T-0x08040000:T-0x08040000+400],ST[0x0819f30c-0x08040000:0x0819f30c-0x08040000+400])
  want=L[:9]+['1ST','!1ST','PRE','!PRE']+L[9:]
  for i,label in enumerate(want):
   ptr=struct.unpack_from('<I',IM,T-0x08040000+(100+i)*4)[0]
   self.assertEqual(IM[ptr-0x08040000:].split(b'\0')[0].decode(),label)
 def test_drum_and_piano_display_the_correct_condition_index(self):
  p=test_conditions.ConditionProbe();sp=0x2003c000;dest=0x20027000
  for raw in range(140):
   p.u.mem_write(sp+0x49,bytes([raw]));p.fragment(0x08159b74,0x08159b18,{_R6:dest});self.assertEqual(p.word(dest),_pos(raw),raw)
   p.u.mem_write(sp+1,bytes([raw]));p.fragment(0x0815c3bc,0x0815c352,{_R1:dest});self.assertEqual(p.word(dest),_pos(raw),raw)
 def test_drum_edit_stores_the_visible_condition_without_offset(self):
  p=test_conditions.ConditionProbe()
  for q in range(139):
   p.fragment(0x0815c8b4,0x0815c8be,{_R1:q});self.assertEqual(p.u.reg_read(_R6),_code(q),q)
 def test_piano_edit_and_reference_match_for_existing_and_new_values(self):
  p=test_conditions.ConditionProbe();sp=0x2003c000
  for raw in range(139):
   p.u.mem_write(sp+0x25,bytes([raw]));p.fragment(0x08158f1c,0x08158f26)
   current=p.u.reg_read(_R3);self.assertEqual(current,_edit(raw),raw)
   for q in [0,1,98,99,100,101,108,109,112]:
    delta=q+1-current
    if not delta:continue
    p.u.mem_write(sp+0x19,bytes([raw]));p.w(sp+0x84,delta&0xffffffff)
    p.fragment(0x08158a7c,0x08158aac)
    self.assertEqual(p.u.mem_read(sp+0x31,1)[0],_code(q),(raw,q))
test_conditions.Tests=PickerOrderConditions
suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
