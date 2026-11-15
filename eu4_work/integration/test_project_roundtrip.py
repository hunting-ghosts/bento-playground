"""Project save/load of the drum synth and Analog settings through the real native path.

Everything between the XML text that goes in and the XML text that comes out is
native firmware code of the image under test, started the way the device starts
it: the native reset (data copy, static constructors), the native registry
builder, the native node stores (0812D66C), the native project loader
(081304F8, tinyxml reader 0812FAAC), the native store copy (0812D68E: every
node is cloned through 0812E270 and gets a NEW handle) and the native project
writer (0813032C). Only FatFs open/read/write/close are a Python file table.

The device moves a project through three stores: the worker loads the file
into its load store, the load store is copied into the model store (what
plays), and Save copies the model store into the worker's save store, which
the writer prints. Our settings are keyed by node handle, so they have to
follow every one of those copies. P168 exp2 (owner, hardware): after save,
power cycle and load, the Analog track and drum synth pads were silent; the
project file had no `bento_analog` and no `bento_kick_*` on the pad that had a
Mod Matrix route. The oracle here is the native writer's output.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import os,struct,unittest
import xml.etree.ElementTree as ET
from unicorn import Uc,UcError,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
from test_integration import IMAGE,UU
KEEP=[]
MODEL=0x30024b00
DRUM0=dict(bento_kick_version='1',bento_drum_model='15',bento_drum_v2_click='7',bento_syncussion_attack='9',bento_kick_v1_tune='70',bento_kick_v1_decay='41',bento_kick_v1_tone='42',bento_kick_v1_impact='43',bento_kick_v1_sweep='44',bento_kick_v1_sweep_decay='45',bento_kick_v1_dirt='46')
DRUM1=dict(bento_kick_version='1',bento_drum_model='1',bento_drum_v2_click='33',bento_kick_v1_tune='60',bento_kick_v1_decay='61',bento_kick_v1_tone='62',bento_kick_v1_impact='63',bento_kick_v1_sweep='64',bento_kick_v1_sweep_decay='65',bento_kick_v1_dirt='66')
ANALOG=dict(bento_analog='1',bento_analog_sync='1',bento_analog_glide='37')
# per-track settings kept by track handle: Track FX (one value off its default), Perform fixed velocity, one Euclid pad
# (row 0, pad 3: 16 steps, 5 pulses, rotation 2, enabled; velocity 100)
KIT=dict(bento_fx_v1_01='77',bento_perf_velocity='356',bento_eu2_00_03_0='33817871',bento_eu2_00_03_1='100',bento_eu2_00_03_2='0',bento_eu2_00_03_3='0')
KIT_IN=dict(KIT,bento_fx_version='1',bento_eu2_version='1')
KEPT=('bento_kick','bento_drum','bento_syncussion','bento_analog','bento_mod_engine','bento_perf','bento_eu2_00_03','bento_fx_v1_01')
def attrs(d):return ' '.join('%s="%s"'%kv for kv in d.items())
def project(drum0=DRUM0,drum1=DRUM1,analog=ANALOG,kit=KIT_IN):
 return ('''<?xml version="1.0" encoding="UTF-8"?>
<document>
    <session version="2">
        <track type="samtrack">
            <params cellname="Kit" celldisppos="0" %s/>
            <cell type="saminst">
                <params celldisppos="0" %s/>
            </cell>
            <cell type="samasst">
                <params filename="\\Drum Synths\\Metal.wav" samlen="144033"/>
            </cell>
            <cell type="saminst">
                <params celldisppos="1" %s/>
                <modsource dest="gaindb" src="velocity" slot="0" amount="1000"/>
            </cell>
            <cell type="samasst">
                <params filename="\\Drum Synths\\Kick.wav" samlen="144019"/>
            </cell>
            <cell type="saminst">
                <params celldisppos="2"/>
            </cell>
            <cell type="samasst">
                <params filename="Patches\\OneShots\\Plain.wav" samlen="1000"/>
            </cell>
        </track>
        <track type="wttrack">
            <params cellname="Analog" celldisppos="1" %s/>
            <cell type="wavetable">
                <params level="0" samlen="0" filename=""/>
            </cell>
        </track>
        <track type="wttrack">
            <params cellname="Plain WT" celldisppos="2"/>
        </track>
        <track type="mastrack">
            <params/>
        </track>
    </session>
</document>
'''%(attrs(kit),attrs(drum0),attrs(drum1),attrs(analog))).encode()
def ours(text):
 """{(track index, 'track' | pad number): our drum/Analog attributes} of a project file"""
 root=ET.fromstring(text.decode('utf-8-sig'));out={}
 for t,track in enumerate(root.find('session').findall('track')):
  def own(e):
   p=e.find('params');a=p.attrib if p is not None else {}
   return {k:v for k,v in a.items() if k.startswith(KEPT) and not (k=='bento_fx_v1_01' and v=='120')},a # 120: Track FX default, written for every track
  o,_=own(track)
  if o:out[(t,'track')]=o
  for cell in track.findall('cell'):
   if cell.attrib.get('type')!='saminst':continue
   o,a=own(cell)
   if o:out[(t,int(a.get('celldisppos','-1')))]=o
 return out
class Device:
 """The image after its own reset code, with three native node stores and a file table."""
 LOAD,MODELS,SAVE,UNDO=0x20020000,0x20021000,0x20022000,0x20023000
 def __init__(self,image=None):
  KEEP.append(self) # Unicorn callback lifetime (see AGENTS.md, EU10)
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
  for a,n in [(0x08040000,0x1c0000),(0x20000000,0x40000),(0x24000000,0x80000),(0x30000000,0x40000),(0x38000000,0x10000),(0xc0000000,0x8000000),(0xe000e000,0x2000),(0x58004000,0x1000)]:u.mem_map(a,n) # 58004000: RTC backup registers (the black box reads them after the native reader)
  u.mem_write(0x08040000,image or IMAGE);u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
  self.stop=0x081ff000;self.files={};self.open={};self.messages=[];self.hooks=[]
  for a,f in ((0x08120148,self.f_open),(0x08120464,self.f_read),(0x08120604,self.f_write),(0x08120974,self.f_close),(0x08104c00,self.message),(0x08123f7c,self.ret)):
   self.hooks.append(u.hook_add(UC_HOOK_CODE,lambda u_,a_,n_,d_,f=f:f(),begin=a,end=a))
  # native reset up to the call of main: stack, data copy, zeroed RAM, static constructors, our boot hook
  u.reg_write(UC_ARM_REG_SP,0x30040000);u.emu_start(0x081003cc|1,0x081004ca,count=200000000)
  assert u.reg_read(UC_ARM_REG_PC)==0x081004ca,hex(u.reg_read(UC_ARM_REG_PC))
  self.w(0x30024ae8,0x20038000) # the project file object the native reader/writer use
  for store in (self.LOAD,self.MODELS,self.SAVE,self.UNDO):self.call(0x0812d66c,store,0x180000) # as the native worker does (08125E92)
  self.call(0x081639a8,0) # native parameter registry
  self.w(MODEL,self.MODELS)
 def w(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
 def r(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def text(self,a):return bytes(self.u.mem_read(a,300)).split(b'\0')[0].decode('latin1')
 def args(self):return [self.u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
 def ret(self,v=0):self.u.reg_write(UC_ARM_REG_R0,v&0xffffffff);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def call(self,a,*args):
  for reg,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):self.u.reg_write(reg,v)
  self.u.reg_write(UC_ARM_REG_SP,0x2003e000);self.u.reg_write(UC_ARM_REG_LR,self.stop|1)
  try:self.u.emu_start(a|1,self.stop,count=400000000)
  except UcError as e:raise RuntimeError('%s at pc=%08x lr=%08x'%(e,self.u.reg_read(UC_ARM_REG_PC),self.u.reg_read(UC_ARM_REG_LR))) from e
  assert self.u.reg_read(UC_ARM_REG_PC)==self.stop,hex(self.u.reg_read(UC_ARM_REG_PC))
  return self.u.reg_read(UC_ARM_REG_R0)
 # FatFs: FIL +0x10 is the size the native reader allocates for
 def f_open(self):
  f,p,mode=self.args()[:3];name=self.text(p)
  if mode&8:self.files[name]=bytearray()
  if name not in self.files:return self.ret(4)
  self.open[f]=[name,0];self.w(f+0x10,len(self.files[name]));self.ret(0)
 def f_read(self):
  f,b,n,got=self.args();name,pos=self.open[f];d=bytes(self.files[name][pos:pos+n]);self.u.mem_write(b,d);self.open[f][1]+=len(d);self.w(got,len(d));self.ret(0)
 def f_write(self):
  f,b,n,got=self.args();self.files[self.open[f][0]]+=bytes(self.u.mem_read(b,n));self.w(got,n);self.ret(0)
 def f_close(self):self.ret(0)
 def message(self):self.messages.append(self.text(self.args()[0]));self.ret(0)
 def path(self,name):
  self.u.mem_write(0x20010000,name.encode()+b'\0');return 0x20010000
 # the three steps of the device
 def load_file(self,text):
  """worker: file -> load store; UI: load store -> model store (native completion 081263FC)"""
  self.files['in.xml']=bytearray(text)
  assert self.call(0x081304f8,self.path('in.xml'),0x20030000,0x1000,self.LOAD)==1
  self.call(0x0812d68e,self.MODELS,self.LOAD)
  self.u.mem_write(0x20010800,struct.pack('<HH4I',0x3f,0,0,0,0,0));self.call(UU['fx_finish'],0,0x20010800) # native "project loaded" notification (our hook at 081512A4)
  self.call(0x0812d686,self.LOAD) # the next worker job empties its load store
 def save_file(self):
  """UI: model store -> save store (native request 081260E4); worker: save store -> file"""
  self.call(0x0812d68e,self.SAVE,self.MODELS)
  assert self.call(0x0813032c,self.path('out.xml'),0x20030000,0x1000,self.SAVE)==1
  return bytes(self.files['out.xml'])
 def tracks(self,store):
  out=[];i=0
  while self.call(0x0812d78a,store,i,0x20010400):out.append(self.r(0x20010400));i+=1
  return out
 def handle(self,node):return self.r(node+0x10)
# P168 exp3 (owner, hardware): a native Multisample track was silent and Wavetable tracks had no wave after
# save, power cycle and load; the saved file was complete (evidence/exp3). One track of every native asset type,
# with files referenced as on the device.
ASSETS=b'''<?xml version="1.0" encoding="UTF-8"?>
<document>
    <session version="2">
        <track type="samtrack">
            <params cellname="Kit" celldisppos="0"/>
            <cell type="saminst"><params celldisppos="0"/></cell>
            <cell type="samasst"><params filename="Patches\\OneShots\\Plain.wav" rootnote="0" keyrangebottom="0" keyrangetop="0" velroot="0" velrangebottom="0" velrangetop="0" samstart="0" samlen="1000" loopstart="0" loopend="1000"/></cell>
        </track>
        <track type="multisamtrack">
            <params cellname="Keys" celldisppos="1"/>
            <cell type="saminst"><params celldisppos="0" multisammode="1"/></cell>
            <cell type="samasst"><params filename="Patches\\Multisamples\\Keys\\Keys C3.wav" rootnote="48" keyrangebottom="0" keyrangetop="53" velroot="0" velrangebottom="0" velrangetop="127" samstart="0" samlen="50000" loopstart="0" loopend="50000"/></cell>
            <cell type="samasst"><params filename="Patches\\Multisamples\\Keys\\Keys C4.wav" rootnote="60" keyrangebottom="54" keyrangetop="127" velroot="0" velrangebottom="0" velrangetop="127" samstart="0" samlen="40000" loopstart="0" loopend="40000"/></cell>
        </track>
        <track type="wttrack">
            <params cellname="Wave" celldisppos="2"/>
            <cell type="wavetable"><params pitch="0" level="1000" wavesel="5" wavepos="0" samlen="1040384" filename="Patches\\Wavetable\\DreamTar\\Rippin.wav"/></cell>
            <cell type="wavetable"><params pitch="0" level="1000" wavesel="5" wavepos="0" samlen="1040384" filename="\\AKWF\\AKWF_0003\\AKWF_0201.wav"/></cell>
        </track>
        <track type="slicertrack">
            <params cellname="Slice" celldisppos="3"/>
            <cell type="saminst"><params celldisppos="0"/></cell>
            <cell type="samasst"><params filename="Patches\\Loops\\Beat.wav" rootnote="60" samstart="0" samlen="96000" loopstart="0" loopend="96000"/></cell>
        </track>
        <track type="looptrack">
            <params cellname="Loop" celldisppos="4"/>
            <cell type="loopinst"><params celldisppos="0"/></cell>
            <cell type="samasst"><params filename="Patches\\Loops\\Loop.wav" rootnote="60" samstart="0" samlen="96000" loopstart="0" loopend="96000"/></cell>
        </track>
        <track type="grtrack">
            <params cellname="Grain" celldisppos="5"/>
            <cell type="saminst"><params celldisppos="0"/></cell>
            <cell type="samasst"><params filename="Patches\\Granular\\Pad.wav" rootnote="60" samstart="0" samlen="96000" loopstart="0" loopend="96000"/></cell>
        </track>
        <track type="mastrack"><params/></track>
    </session>
</document>
'''
def assets(text):
 """[(track type, [(cell type, params of every asset cell)])] of a project file"""
 root=ET.fromstring(text.decode('utf-8-sig'))
 return [(t.attrib['type'],[(c.attrib['type'],dict(c.find('params').attrib)) for c in t.findall('cell') if c.attrib.get('type') in ('samasst','wavetable')]) for t in root.find('session').findall('track')]
class Rebuilds:
 """Native resource rebuild 0813CCB8 (1.6.8: 0813E4B8): records the track handle and returns. The real
 rebuild queues file loads for the file thread, which the emulator does not run."""
 def __init__(self,d):
  self.calls=[];d.hooks.append(d.u.hook_add(UC_HOOK_CODE,lambda u,a,n,_:(self.calls.append(u.reg_read(UC_ARM_REG_R1)),d.ret(0)),begin=0x0813ccb8,end=0x0813ccb8))
class ProjectRoundTrip(unittest.TestCase):
 def test_native_assets_of_every_track_type_load_and_save_like_stock(self):
  # Oracle: the stock image of the same version, through the same native loader, store copy and writer.
  # The device order after the worker's load: the UI copies the load store into the model (081263FC), runs
  # SessionMgr::FinalizeBankLoading 0813E618 (the native rebuild of every track, call at 0813E706), then
  # handles messages (our fx_dispatch first), then the "project loaded" event 3F reaches the pane (fx_finish).
  # exp3 started a second rebuild of the Multisample and the Wavetable track there (both lost on the device).
  stock=os.environ.get('BENTO_STOCK_IMAGE')
  if not stock:self.skipTest('BENTO_STOCK_IMAGE (the stock image of this firmware version) is not set')
  s=Device(open(stock,'rb').read());s.files['in.xml']=bytearray(ASSETS)
  assert s.call(0x081304f8,s.path('in.xml'),0x20030000,0x1000,s.LOAD)==1
  sr=Rebuilds(s);s.call(0x0812d68e,s.MODELS,s.LOAD);s.call(0x0812d686,s.LOAD);oracle=s.save_file()
  d=Device();rebuilt=Rebuilds(d);d.files['in.xml']=bytearray(ASSETS)
  assert d.call(0x081304f8,d.path('in.xml'),0x20030000,0x1000,d.LOAD)==1
  d.call(0x0812d68e,d.MODELS,d.LOAD)
  d.call(UU['fx_dispatch'],MODEL,1,0,0,0) # any message: our handles follow the copy here (run 5, track_adopt)
  d.u.mem_write(0x20010800,struct.pack('<HH4I',0x3f,0,0,0,0,0));d.call(UU['fx_finish'],0,0x20010800)
  d.call(0x0812d686,d.LOAD)
  self.assertEqual(rebuilt.calls,sr.calls,'resource rebuilds after the native FinalizeBankLoading (stock: none)')
  self.assertEqual(assets(d.save_file()),assets(oracle))
  self.assertEqual([len(c) for _,c in assets(oracle)],[1,2,2,1,1,1,0]) # the oracle keeps every asset cell

 def test_drum_and_analog_settings_survive_load_and_save_on_their_own_pads(self):
  d=Device();d.load_file(project());saved=ours(d.save_file())
  self.assertEqual(saved.get((0,0)),DRUM0) # no route on this pad: this one survived on exp2 too
  self.assertEqual(saved.get((0,1)),DRUM1) # the pad with a modulation route (exp2: no bento_kick_* at all)
  self.assertEqual(saved.get((1,'track')),ANALOG) # exp2: no bento_analog
  self.assertEqual(saved.get((0,'track')),KIT) # Track FX, Perform and Euclid settings of the track (exp2: no bento_fx_* at all)
  self.assertEqual(set(saved),{(0,'track'),(0,0),(0,1),(1,'track')}) # nothing on the plain sample pad or the plain Wavetable
 def test_second_save_and_reload_of_the_saved_file_are_stable(self):
  d=Device();d.load_file(project());first=d.save_file();second=d.save_file()
  self.assertEqual(ours(second),ours(first))
  e=Device();e.load_file(first);self.assertEqual(ours(e.save_file()),ours(first))
  self.assertEqual(ours(first),{(0,'track'):KIT,(0,0):DRUM0,(0,1):DRUM1,(1,'track'):ANALOG})
 def test_playing_track_keeps_its_analog_marker_and_copies_do_not_leak(self):
  d=Device();d.load_file(project())
  model=d.tracks(d.MODELS);self.assertEqual(len(model),3)
  analog=lambda node:d.call(UU['analog_track'],d.handle(node))
  self.assertEqual([analog(t) for t in model],[0,1,0]) # what M7 looks up: the handle of the playing track
  d.save_file();save=d.tracks(d.SAVE);self.assertEqual(analog(save[1]),1)
  d.call(0x0812d686,d.SAVE) # the save store is emptied by the next job: its copies are forgotten
  self.assertEqual(analog(save[1]),0)
  self.assertEqual([analog(t) for t in model],[0,1,0])
  self.assertEqual(ours(d.save_file()),{(0,'track'):KIT,(0,0):DRUM0,(0,1):DRUM1,(1,'track'):ANALOG})
 def test_settings_follow_a_copy_out_and_back_like_native_undo(self):
  d=Device();d.load_file(project())
  d.call(0x0812d68e,d.UNDO,d.MODELS);d.call(0x0812d68e,d.MODELS,d.UNDO);d.call(0x0812d686,d.UNDO)
  self.assertEqual(ours(d.save_file()),{(0,'track'):KIT,(0,0):DRUM0,(0,1):DRUM1,(1,'track'):ANALOG})
 def test_track_fx_eq_gain_and_q_load_from_version_1_and_save_finer_as_version_2(self):
  # exp6 (owner: 0.5 dB / finer Q, old projects must keep their values): version 1 stored whole dB and whole Q;
  # it now loads scaled (tenths of a dB, hundredths of Q) and saves as bento_fx_version 2; a version 2 file
  # loads unchanged. The other Track FX values keep their units.
  def track0(text):
   root=ET.fromstring(text.decode('utf-8-sig'));return root.find('session').findall('track')[0].find('params').attrib
  old=dict(KIT_IN,bento_fx_v1_02='-3',bento_fx_v1_04='5',bento_fx_v1_05='2',bento_fx_v1_07='12',bento_fx_v1_09='-24')
  d=Device();d.load_file(project(kit=old));a=track0(d.save_file())
  self.assertEqual(a.get('bento_fx_version'),'3' if N.FW168 else '2') # run 17 (1.6.8): 3 = + saturator Mode/Level
  if N.FW168:self.assertEqual((a.get('bento_fx_v1_19'),a.get('bento_fx_v1_20')),('0','0')) # an old project: Soft, Level 0 dB
  self.assertEqual({k:a.get(k) for k in ('bento_fx_v1_01','bento_fx_v1_02','bento_fx_v1_04','bento_fx_v1_05','bento_fx_v1_07','bento_fx_v1_09')},
                   dict(bento_fx_v1_01='77',bento_fx_v1_02=str(-30&0xffffffff) if a.get('bento_fx_v1_02','').isdigit() else '-30',bento_fx_v1_04='50',bento_fx_v1_05='200',bento_fx_v1_07='120',bento_fx_v1_09=a.get('bento_fx_v1_09')))
  self.assertIn(a.get('bento_fx_v1_09'),('-24',str(-24&0xffffffff)))  # threshold: unchanged units
  new=dict(KIT_IN,bento_fx_version='2',bento_fx_v1_02='-35',bento_fx_v1_05='125')
  e=Device();e.load_file(project(kit=new));b=track0(e.save_file())
  self.assertIn(b.get('bento_fx_v1_02'),('-35',str(-35&0xffffffff)));self.assertEqual(b.get('bento_fx_v1_05'),'125')
 def test_project_saved_without_the_settings_loads_and_saves_cleanly(self):
  # what exp2 wrote: the route pad and the Analog track without our attributes
  d=Device();d.load_file(project(drum1={},analog={},kit={}))
  self.assertEqual(ours(d.save_file()),{(0,0):DRUM0})
  self.assertEqual([d.call(UU['analog_track'],d.handle(t)) for t in d.tracks(d.MODELS)],[0,0,0])
# I4 (owner, exp3 hardware): loading a patch from the INST page browser onto an existing Wavetable or Multisample
# track emptied its clip. The native path, run here end to end on the image under test and on the stock image:
# the browser (0814F098) calls 081363F0, which moves the track aside into the patch stash (08124C12, MODEL+stash),
# removes it from the model and posts worker job 0x33; the job reads the patch file with the project loader 081304F8
# into the load store; its completion (worker event 0x35) runs 0813DB94, which adds the patch track and, when the
# stashed track has the same type, clones the stashed noteseq cells into it (0812EA2A), then 081346C8.
# Not emulated (posted work for other threads): the job queue post 0812684C, the audio messages, osDelay, the native
# resource rebuild 0813CCB8 and the sample jobs 081346C8 starts. Both tests pass on the exp4 image as well: the cause
# of the device loss is not in this path (RUN8_PROGRESS.md, I4); they guard it.
PATCH_SONG=b'''<?xml version="1.0" encoding="UTF-8"?>
<document>
    <session version="2">
        <track type="wttrack">
            <params bento_eu2_version="1" bento_fx_version="1" bento_fx_v1_01="120" cellname="DreamTar" celldisppos="0" selseqpos="0"/>
            <cell type="wavetable"><params pitch="0" level="1000" wavesel="5" wavepos="0" samlen="1040384" filename="Patches\\Wavetable\\DreamTar\\Rippin.wav"/></cell>
            <cell type="noteseq">
                <params cellname="Seq 1" notesteplen="10" notestepcount="16" seqstepmode="1" celldisppos="0"/>
                <sequence>
                    <seqevent step="0" bento_lock_condition_v1="0" bento_lock1_v1="0" bento_lock2_v1="0" type="note" strtks="0" pitch="60" lencount="1" lentks="960" velocity="7"/>
                    <seqevent step="6" bento_lock_condition_v1="0" bento_lock1_v1="0" bento_lock2_v1="0" type="note" strtks="5760" pitch="65" lencount="1" lentks="960" velocity="31"/>
                </sequence>
            </cell>
            <cell type="noteseq">
                <params cellname="Seq 2" notesteplen="10" notestepcount="32" seqstepmode="1" celldisppos="1"/>
                <sequence>
                    <seqevent step="4" type="note" strtks="3840" pitch="50" lencount="4" lentks="3840" velocity="90"/>
                </sequence>
            </cell>
        </track>
        <track type="multisamtrack">
            <params bento_eu2_version="1" bento_fx_version="1" bento_fx_v1_01="120" cellname="Housey" celldisppos="1" selseqpos="0"/>
            <cell type="saminst"><params celldisppos="0" multisammode="1"/></cell>
            <cell type="samasst"><params filename="Patches\\SampInst\\Housey\\Housey_Junos_60_0_127.wav" rootnote="60" keyrangebottom="0" keyrangetop="127" velroot="64" velrangebottom="0" velrangetop="127" samstart="0" samlen="224240" loopstart="0" loopend="224240"/></cell>
            <cell type="noteseq">
                <params cellname="Seq 1" notesteplen="10" notestepcount="64" seqstepmode="1" celldisppos="0"/>
                <sequence>
                    <seqevent step="0" bento_lock_condition_v1="0" bento_lock1_v1="0" bento_lock2_v1="0" type="note" strtks="0" pitch="41" lencount="16" lentks="15360" velocity="30"/>
                    <seqevent step="32" bento_lock_condition_v1="0" bento_lock1_v1="0" bento_lock2_v1="0" type="note" strtks="30720" pitch="39" lencount="32" lentks="30720" velocity="11"/>
                </sequence>
            </cell>
        </track>
        <track type="mastrack"><params/></track>
    </session>
</document>
'''
def patch_file(kind,name,cells):
 return ('<?xml version="1.0" encoding="UTF-8"?>\n<document>\n    <session version="2">\n        <track type="%s">\n'
  '            <params bento_eu2_version="1" bento_fx_version="1" bento_fx_v1_01="120" cellname="%s"/>\n%s\n'
  '        </track>\n    </session>\n</document>\n'%(kind,name,cells)).encode()
WT_PATCH=patch_file('wttrack','Other WT','            <cell type="wavetable"><params pitch="0" level="900" wavesel="3" wavepos="0" samlen="1040384" filename="Patches\\Wavetable\\Other\\Other.wav"/></cell>')
MS_PATCH=patch_file('multisamtrack','Classic Sub','            <cell type="saminst"><params celldisppos="0" multisammode="1"/></cell>\n            <cell type="samasst"><params filename="Patches\\SampInst\\Classic Sub\\ClassicSub_OB_93_0_127.wav" rootnote="93" keyrangebottom="0" keyrangetop="127" velroot="63" velrangebottom="0" velrangetop="127" samstart="0" samlen="87053" loopstart="0" loopend="87053"/></cell>')
def clips(text):
 """{track cellname: [(clip params, [event attributes])]} of a project file"""
 root=ET.fromstring(text.decode('utf-8-sig'));out={}
 for t in root.find('session').findall('track'):
  p=t.find('params');name=p.attrib.get('cellname','') if p is not None else ''
  native=lambda a:{k:v for k,v in a.items() if not k.startswith('bento_')} # our own note attributes: other suites
  out[name]=[(native(c.find('params').attrib),[native(e.attrib) for e in c.iter('seqevent')]) for c in t.findall('cell') if c.attrib.get('type')=='noteseq']
 return out
def apply_patch(image,slot,patch,ours):
 """song -> patch onto the track in model slot `slot` through the native browser path; returns the saved file"""
 d=Device(image);d.files['in.xml']=bytearray(PATCH_SONG)
 assert d.call(0x081304f8,d.path('in.xml'),0x20030000,0x1000,d.LOAD)==1
 d.call(0x0812d68e,d.MODELS,d.LOAD);d.call(0x0812d686,d.LOAD)
 if ours:
  d.call(UU['fx_dispatch'],MODEL,1,0,0,0)
  d.u.mem_write(0x20010800,struct.pack('<HH4I',0x3f,0,0,0,0,0));d.call(UU['fx_finish'],0,0x20010800)
 Rebuilds(d);d.u.mem_map(0x1000,0xf000) # the select path (0813BC3C) reads a string through a track name table this fixture leaves empty
 for a in (0x0812684c,0x081152cc,0x0810bca6,0x0810e0b8,0x0810b650,0x0810bcec,0x08126fcc,0x081270c4,0x0810b5c8,0x0810b920,0x0810b6fc,0x0810b782,0x0810b7aa,0x0810b7d4,0x081082d8):
  d.hooks.append(d.u.hook_add(UC_HOOK_CODE,lambda u,x,n,_:d.ret(0),begin=a,end=a))
 d.call(0x08124a52,MODEL+N.MODEL_PATCH_STASH) # the stash's store, as the session constructor makes it
 d.w(0x20010900,d.handle(d.tracks(d.MODELS)[slot]));d.u.mem_write(0x20010a00,b'Patches\\Patch.xml\0')
 d.call(0x081363f0,MODEL,0x20010900,slot,0x20010a00) # browser: stash the track, remove it, post job 0x33
 assert len(d.tracks(d.MODELS))==1
 d.files['Patches\\Patch.xml']=bytearray(patch)
 assert d.call(0x081304f8,d.path('Patches\\Patch.xml'),0x20030000,0x1000,d.LOAD)==1 # worker job 0x33
 d.w(0x30020760+0x330,d.LOAD) # the worker's load store pointer (the job's store)
 if ours:d.call(UU['fx_dispatch'],MODEL,1,0,0,0)
 d.call(0x0813db94,MODEL);d.call(0x081346c8,MODEL) # worker event 0x35
 if ours:d.call(UU['fx_dispatch'],MODEL,1,0,0,0)
 return d.save_file()
class PatchOntoTrack(unittest.TestCase):
 def stock(self):
  s=os.environ.get('BENTO_STOCK_IMAGE')
  if not s:self.skipTest('BENTO_STOCK_IMAGE (the stock image of this firmware version) is not set')
  return open(s,'rb').read()
 def test_patch_onto_an_existing_track_keeps_its_clips_like_stock(self):
  stock=self.stock();s=Device(stock);s.files['in.xml']=bytearray(PATCH_SONG)
  assert s.call(0x081304f8,s.path('in.xml'),0x20030000,0x1000,s.LOAD)==1
  s.call(0x0812d68e,s.MODELS,s.LOAD);before=clips(s.save_file()) # the song as stock writes it
  for slot,patch,old,new in ((0,WT_PATCH,'DreamTar','Patch.xml'),(1,MS_PATCH,'Housey','Patch.xml')):
   with self.subTest(track=old):
    oracle=clips(apply_patch(stock,slot,patch,False));got=clips(apply_patch(None,slot,patch,True))
    self.assertEqual(set(oracle),set(before)-{old}|{new},'the browser names the track after the patch file')
    self.assertEqual(oracle[new],before[old]) # stock: the same clips (notes and clip settings) on the new instrument
    self.assertNotIn(old,oracle)
    self.assertEqual(got,oracle)
 def test_patch_of_another_track_type_replaces_the_clips_like_stock(self):
  # native 0813DB94 clones the stashed clips only into a track of the same type; otherwise one empty clip
  stock=self.stock();oracle=clips(apply_patch(stock,0,MS_PATCH,False))
  self.assertEqual([len(e) for _,e in oracle['Patch.xml']],[0])
  self.assertEqual(clips(apply_patch(None,0,MS_PATCH,True)),oracle)
if __name__=='__main__':unittest.main(verbosity=2)
