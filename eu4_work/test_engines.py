"""CH12 drum engines on M7: Clap and Tom / FM perc, and the bit-identical
optimisation of Kick/Snare/HiHat, on the built image."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
from pathlib import Path
import os,sys,unittest,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'k16_work'));sys.path.insert(0,str(ROOT/'k16_work/bento_controls'))
import release
stock=Path(os.environ['BENTO_STOCK_IMAGE']).read_bytes()
# Compile K16 symbol maps needed by the inherited compiled-code fixtures.
base,_=release.candidate(stock)
out=Path(os.environ['BENTO_FX_CANDIDATE']);image=(out/'bento1.bin').read_bytes()
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
import struct,unittest
from unicorn.arm_const import *
from test_kick import Kick
SYMS=kick_build.SYMS
KNOBS=0x24043500;HANDLE=101
TUNE,DECAY,TONE,CLICK=N.NKEY(0x1a0),N.NKEY(0x1a1),N.NKEY(0x1a2),N.NKEY(0x1b0)
def knobs(p,values=(55,65,45,65,55,25,25),reserved=1,click=40):
 p.u.mem_write(KNOBS,bytes(0x900));p.w(KNOBS,0x35424e4b);p.w(KNOBS+4,2)
 e=KNOBS+32;p.w(e,2);p.w(e+4,HANDLE);p.u.mem_write(e+8,bytes(values)+bytes([reserved]));p.u.mem_write(0x24043d80,bytes([click]))
def command(p,key,src,amount,slot=0,at=0x2002a000):
 p.u.mem_write(at,struct.pack('<BBHIIIIHh',0x3f,0,0,0,HANDLE,key,slot,src,amount));return at
def routes(p):
 n=p.r(p.root+0x5fc);return [(round(p.f(p.root+0x590+12*i),4),)+struct.unpack('<HHB',p.u.mem_read(p.root+0x594+12*i,5)) for i in range(n)]
def tail(x):return sum(v*v for v in x[1600:2560])
class Synth(Kick):
 def __init__(self,**k):
  super().__init__();knobs(self,**k);self.w(self.root+0x5fc,0)
 def r(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def route(self,key,src,amount,slot=0):
  self.call(SYMS['kick_route'],self.root,command(self,key,src,amount,slot));return self.u.reg_read(UC_ARM_REG_R0)
 def audio(self,blocks=6):
  self.start();out=[]
  for _ in range(blocks):ok,s=self.render();assert ok==1;out.extend(s)
  return out
import hashlib
from unicorn import UC_HOOK_CODE
# CH11 output (30 blocks x 64 samples) of the unoptimised engines.
# P10: Kick knob 7 is Punch (was Dirt), so the CH11 Kick references use 0 there
# (the P9 engine at Dirt 0 = this engine at Punch 0, bit for bit).
# R6.3: re-recorded after the per-engine output level match (kick.cpp engine_gain);
# the DSP is unchanged, only the final output multiplier replaced the fixed 0.6.
GOLDEN=[(1,(55,65,45,65,55,25,0),'1d246130726aef31819d9b355e1bcbe72da01baa9fb04a995c4053ce514e068f'),
 (1,(120,90,80,100,90,60,0),'4da06483edee13a85e0f0f9f6f892fe288299e54f9d32a6639d13b38165bc4bb'),
 (5,(10,70,65,65,30,0,0),'7e4b5fcb8210b8efdaf4f98cc621aac53de200bb9b4d266b6f15bacb362d2998'),
 (5,(80,95,20,100,90,0,0),'e3aa98f6dc753257ae172bc98317eaf7f77d12d10c36901edd6889361d4e2ebf')]
# Run 14 (item 5b): Metal (engine 15) output of the run 13 build (1.6.8 80b9e93b..., 1.6.1 46b45cf2..., same digests),
# recorded BEFORE the Syncussion engine was specialised to Metal; the specialised engine must reproduce them bit for bit.
GOLDEN_METAL=[((78, 55, 50, 65, 0, 30, 0),'e22bb2f8ad06c75078148b22a761e8f97c26cbb2cf50abb455944fc0802df335'),
 ((78, 55, 50, 65, 35, 30, 0),'305994c13e1b0b7b67e8bff4a6786f569d805406d7ed5300c052db9d35e19bb4'),
 ((25, 0, 0, 0, 0, 0, 0),'5a5c1f82f34a258608eec2c6690e73843d2a5ec508c34e41f8c423aaa5615ca9'),
 ((180, 100, 100, 100, 100, 100, 100),'09bc19372c4087063be1d2a1e17f8a4ed5bf3e1b25d031aefd1804aa9596dbd8'),
 ((104, 70, 30, 40, 80, 60, 90),'5b0c9ef1a53fe6844682928ad5e97f1a252d80159ad65e9665b540c2aa32162a'),
 ((60, 90, 20, 10, 50, 95, 70),'35dabf2f6838d5593e734057fd3a25d32513c3f470ea7f8ee80c5ebf31146058')]
GOLDEN_METAL_ATTACK=[(0x30,'c0be4b71ded90f4733b2bf758c9b865a472355c728105cae433dbf17344e8970'),(0x64,'59939b37944a28faf710cc61f1e6f93f778cdac59da2a57a5808a86cfe809a6a')];GOLDEN_METAL_RATIO=(1.7,'58e586789f46252591052da48124b4dce3152284693fcb60615f22df1e4eb86d')
CLAP=(40,40,50,65,40,0,0);TOM=(86,50,40,65,40,30,10)
def engine(eng,values,lock=None):
 p=Synth(reserved=eng,values=values);p.w(p.desc+0x24,144019+eng-1)
 if lock:p.w(0x24046000,0x374c5042);p.w(0x24046008,p.root);p.w(0x2404600c,0x51000000|lock[0]<<16|lock[1])
 return p
def run(p,blocks=30,cost=None):
 p.start();out=[]
 for i in range(blocks):
  if cost is not None and i==10:
   n=[0];h=p.u.hook_add(UC_HOOK_CODE,lambda u,a,s,d:n.__setitem__(0,n[0]+1))
  out+=p.render()[1]
  if cost is not None and i==10:p.u.hook_del(h);cost.append(n[0]/64)
 return out
def digest(o):return hashlib.sha256(struct.pack('<%df'%len(o),*o)).hexdigest()
def energy(o,a=0,b=None):return sum(x*x for x in o[a:b])
# The K16 lock-UI harness, adapted to this image exactly as test_k16_regressions does.
import types
_src=(ROOT/'k16_work/bento_controls/test_k16.py').read_text().replace("struct.unpack('<2H',p.u.mem_read(0x300000bc+8,4))","struct.unpack('<2H',p.u.mem_read(0x300000bc+12,4))")
_k16=types.ModuleType('k16_for_engines');_k16.__file__=str(ROOT/'k16_work/bento_controls/test_k16.py');exec(compile(_src,_k16.__file__,'exec'),_k16.__dict__)
class LockUI(_k16.SynthUI):
 def __init__(self,model):
  self.engine=model;self.path={7:'BENTO_Synth_Clap.wav',9:'BENTO_Synth_Tom.wav'}[model];_k16.UIProbe.__init__(self)
 def choice(self,i):return self.text(self.word(0x24048480+4*i))
 def pick_lock(self,value):
  self.display();slot=self.view+0xebf0+0x38+6*0x468
  key=self.word(0x300000c8)&65535
  self.u.mem_write(slot+0x9c,struct.pack('<H',key))
  target=json.loads((out/'manifest.json').read_text())['ui_symbols']['locks_touch']
  self.call(target,slot,0);assert self.u.reg_read(UC_ARM_REG_R0)==1
  self.prepare();self.encoder(N.NKEY(0x1da),value);self.display()
  self.u.mem_write(slot+0x9c,struct.pack('<H',N.NKEY(0x1da)))
  self.call(target,slot,0);assert self.u.reg_read(UC_ARM_REG_R0)==1
class Tests(unittest.TestCase):
 def test_optimised_engines_are_bit_identical_to_ch11(self):
  for eng,values,want in GOLDEN:self.assertEqual(digest(run(engine(eng,values))),want,(eng,values))
 def test_metal_is_bit_identical_to_the_six_mode_syncussion_engine(self):
  # Run 14: the M7 engine keeps only Metal's fixed switches; these digests come from the build before that change.
  for values,want in GOLDEN_METAL:self.assertEqual(digest(run(engine(15,values))),want,values)
  for amount,want in GOLDEN_METAL_ATTACK:
   p=engine(15,GOLDEN_METAL[1][0]);p.u.mem_map(0xc6000000,0x1000);p.w(0x24043508,0xc6000000);p.w(0xc6000000,0x41594e53);p.u.mem_write(0xc6000020,bytes([amount]))
   self.assertEqual(digest(run(p)),want,amount)
  p=engine(15,GOLDEN_METAL[4][0]);p.f(p.voice+0x48,GOLDEN_METAL_RATIO[0]);self.assertEqual(digest(run(p)),GOLDEN_METAL_RATIO[1])
 def test_optimised_engines_cost_less(self):
  # Emulated instructions per sample in one block; CH11 was 331 / 352-362 / 388-391.
  # R6.3: Kick +~1.5 from the per-engine gain lookup. P10: Kick +~1 from the Punch branch (same samples at Punch 0); the 909 Snare is far cheaper.
  # R6.15: Kick +~0.8 from the per-block native release-ramp check (the retrigger de-click; nothing per sample unless releasing).
  for eng,values,budget in [(1,(55,65,45,65,55,25,0),320),(1,(55,65,45,65,55,25,25),330),(3,(10,45,50,65,70,0,0),200),(5,(10,70,65,65,30,0,0),240),(7,CLAP,200),(9,TOM,335)]:
   c=[];run(engine(eng,values),12,c);self.assertLess(c[0],budget,(eng,c))
 def test_kick_punch_is_a_sharper_start_and_a_denser_body(self):
  # P10 (owner: missing punch). Punch adds a fast pitch dive and warm drive.
  def zc(o):return sum(1 for a,b in zip(o,o[1:]) if a<0<=b)
  plain=run(engine(1,(55,65,45,65,55,25,0)),40);punch=run(engine(1,(55,65,45,65,55,25,100)),40)
  self.assertGreater(zc(punch[:960]),zc(plain[:960])) # extra cycles from the dive in the first 20 ms
  self.assertGreater(energy(punch,480,4800),energy(plain,480,4800)*1.3) # fuller body
  self.assertLessEqual(max(abs(x) for x in punch),.93) # saturates, never clips (R6.3 level: .61*.906/.6)
 def test_snare_is_a_909_two_shells_and_snappy_noise(self):
  # P10 (owner: "a 909 type snare"): shells at f and 1.62 f, noise set by Snappy and Tone.
  import math
  def power(o,f,a=0,b=4800):
   c=s_=0
   for i,x in enumerate(o[a:b]):c+=x*math.cos(2*math.pi*f*i/48000);s_+=x*math.sin(2*math.pi*f*i/48000)
   return c*c+s_*s_
  def hf(o):return sum((b-a)**2 for a,b in zip(o[:4800],o[1:4800])) # rough high-frequency energy
  f=140*2**(10/50);o=run(engine(3,(10,45,50,65,70,0,0)),80)
  self.assertGreater(power(o,f,960),power(o,f*1.3,960)*4);self.assertGreater(power(o,f*1.62,960),power(o,f*1.3,960)*2)
  self.assertGreater(hf(o),hf(run(engine(3,(10,45,50,65,0,0,0)),80))*5) # Snappy brings the noise
  self.assertGreater(hf(run(engine(3,(10,45,100,65,70,0,0)),80)),hf(run(engine(3,(10,45,0,65,70,0,0)),80))*1.5) # Tone brightens
  hi=run(engine(3,(60,45,50,65,0,0,0)),80);self.assertGreater(power(hi,140*2**(60/50),960),power(hi,f,960)) # Tune moves the shells
  long=run(engine(3,(10,95,50,65,70,0,0)),200);short=run(engine(3,(10,5,50,65,70,0,0)),200)
  self.assertGreater(energy(long,9600,14400),energy(short,9600,14400)*4) # Decay
  self.assertTrue(all(abs(x)<=1 for x in o))
 def test_new_carriers_are_recognised(self):
  for eng in (7,9):
   p=engine(eng,CLAP if eng==7 else TOM);p.call(SYMS['kick_marker'],p.desc);self.assertEqual(p.u.reg_read(UC_ARM_REG_R0),eng)
 def test_clap_is_three_bursts_and_a_tail(self):
  o=run(engine(7,CLAP),40);self.assertTrue(all(abs(x)<1 for x in o));self.assertGreater(max(abs(x) for x in o),.05)
  spacing=int(48000*(.004+.4*.018));quiet=[energy(o,k*spacing-40,k*spacing) for k in (1,2,3)]
  peaks=[energy(o,k*spacing,k*spacing+40) for k in (1,2,3)]
  for q,pk in zip(quiet,peaks):self.assertGreater(pk,q*3) # each burst restarts loud
  self.assertGreater(energy(o,3*spacing+400,3*spacing+800),0) # tail rings on
 def test_clap_controls_change_the_sound(self):
  base=run(engine(7,CLAP),40)
  for i,v in [(0,90),(1,90),(2,0),(3,100),(4,90)]:
   vals=list(CLAP);vals[i]=v;self.assertNotEqual(run(engine(7,tuple(vals)),40),base,i)
  self.assertGreater(energy(run(engine(7,(40,95,50,65,40,0,0)),60),3000),energy(run(engine(7,CLAP),60),3000)*4) # longer Decay: the tail rings on
 def test_tom_is_pitched_by_tune(self):
  def zero_crossings(o):return sum(1 for a,b in zip(o,o[1:]) if a<0<=b)
  low=run(engine(9,(60,)+TOM[1:]),40);high=run(engine(9,(150,)+TOM[1:]),40)
  self.assertGreater(max(abs(x) for x in low),.05);self.assertGreater(zero_crossings(high),zero_crossings(low)*3)
 def test_tom_takes_kick_locks_and_clap_takes_snare_locks(self):
  base=run(engine(9,TOM),20);self.assertNotEqual(run(engine(9,TOM,(12,150-25)),20),base) # Kick Tune kind
  self.assertEqual(run(engine(9,TOM,(19,90)),20),base) # Kick Click kind: not a Tom control
  self.assertEqual(run(engine(9,TOM,(20,90)),20),base) # Snare kind: other family
  base=run(engine(7,CLAP),40);self.assertNotEqual(run(engine(7,CLAP,(21,95)),40),base) # Snare Decay kind = Clap Decay (tail after the bursts)
  self.assertEqual(run(engine(7,CLAP,(12,90-25)),40),base)
 def test_mod_matrix_reaches_the_new_engines(self):
  for eng,values,key in [(7,CLAP,DECAY),(9,TOM,TUNE)]:
   base=run(engine(eng,values),40);p=engine(eng,values);p.route(key,13,700);self.assertNotEqual(run(p,40),base,eng)
   p=engine(eng,values);p.route(N.NKEY(0x1a6),13,700) # sixth parameter (Sweep Dec) exists on Tom only
   (self.assertNotEqual if eng==9 else self.assertEqual)(run(p,40),base)
 def test_lock_picker_lists_tom_and_clap_controls_on_their_family_kinds(self):
  for model,first,total,names in [(9,12,15,['Tom Tune','Tom Decay','Tom Tone','Tom Impact','Tom Sweep','Tom Sweep Dec','Tom Dirt']),(7,20,13,['Clap Tune','Clap Decay','Clap Tone','Clap Impact','Clap Spread'])]:
   p=LockUI(model);p.press(0);p.prepare();self.assertEqual(p.word(0x20029000+N.NKEY(0x1da)*32+12),total)
   self.assertEqual([p.choice(8+i) for i in range(len(names))],names)
   p.pick_lock(8);p.encoder(_k16.KEYS[0],80)
   self.assertEqual(p.stored(),_k16.word(first,80))
 def test_instrument_page_shows_the_new_engines(self):
  K=[N.NKEY(0x1a0),N.NKEY(0x1a1),N.NKEY(0x1a2),N.NKEY(0x1a4),N.NKEY(0x1a5),N.NKEY(0x1a6),N.NKEY(0x1a9)]
  for name,title,keys,labels,hz in [('BENTO_Synth_Clap.wav','Clap / Pad 1',K[:5]+[0,0],['Tune','Decay','Tone','Impact','Spread'],'914 Hz'),
                                    ('BENTO_Synth_Tom.wav','Tom / Pad 1',K,['Tune','Decay','Tone','Impact','Sweep','Sweep Dec','Dirt'],'180 Hz')]:
   p=_k16.UI();p.path='\\Projects\\'+name;p.prepare()
   self.assertEqual(list(struct.unpack('<8H',p.u.mem_read(p.v+0x703c,16))),keys+[0])
   # Modern Synth panels reuse row 2 for Engine; neither instrument gains Click.
   row2_key=N.NKEY(0x1ad) if json.loads((out/'FULL_MANIFEST.json').read_text()).get('syncussion') else 0
   self.assertEqual(struct.unpack('<H',p.u.mem_read(p.v+0x703c+2*0x50,2))[0],row2_key)
   titles=[c[2] for c in p.calls if c[0]=='title'];self.assertIn(title,titles)
   for l in labels:self.assertIn(l,titles)
   self.assertIn(hz,[c[3] for c in p.calls if c[0]=='value'])
if __name__=='__main__':unittest.main(verbosity=2)
