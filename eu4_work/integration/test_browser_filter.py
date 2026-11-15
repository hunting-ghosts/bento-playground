"""Browser carrier filter: the real native PrepareFileList 081041F8 and the
real browser view request 0816C9B0 run in the emulator with the compiled
browser_filter_ui.c patched in at the exact native BL sites.

Only FatFS directory enumeration (f_findfirst 08120E2C, f_findnext 08120DF2,
f_closedir 08120D8C) and, for the UI request, the current-track getters 08133CFC/08133F7C and the
file-manager post 08132DB4 are fixtures. The native list push 081020AC, the
.WAV rename, the folder pass and the browser mode switch are stock code."""
import fnmatch,hashlib,json,os,struct,subprocess,sys,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
R=Path(__file__).resolve().parent
ROOT=R.parents[1]
CANDIDATE=Path(os.environ.get('BENTO_FX_CANDIDATE',ROOT/'build/seq-fix-04'))
IMAGES=[Path(p) for p in os.environ.get('BENTO_BROWSER_IMAGES',
 f"{CANDIDATE/'bento1.bin'}{os.pathsep}{ROOT/'build/retrigger-stock.bin'}").split(os.pathsep)]
OUT=ROOT/'build'/'browser-filter-test'
BASE=0x08040000;CODE=0x08300000;STOP=0x081ff000
HOOK_SITE=0x08104296;REQUEST_SITE=0x0816ca0e
CONTEXT=0x24043510;ONE_SHOT=0x4f534842
MODEL=0x30024b00;FS=0x300010f4;LIST=0x20010000;PTRS=0x20011000;STORE=0xc0100000;VIEW=0xc0200000
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
EXPORTS=['browser_list_hook','browser_list_add','browser_request']
SHIPPED={}
for path in IMAGES:
 manifest=path.parent/'manifest.json'
 if path.is_file() and manifest.is_file():
  symbols=json.loads(manifest.read_text()).get('ui_symbols',{})
  if all(name in symbols for name in EXPORTS):
   SHIPPED[hashlib.sha256(path.read_bytes()).digest()]={name:symbols[name] for name in EXPORTS}
RETIRED=288102;MELODIC=288114
def bl(src,dst):
 o=dst-(src+4);assert -(1<<24)<=o<(1<<24) and not o&1
 s=(o>>24)&1;i1=(o>>23)&1;i2=(o>>22)&1;j1=(~i1^s)&1;j2=(~i2^s)&1
 return struct.pack('<HH',0xf000|(s<<10)|((o>>12)&0x3ff),0xd000|(j1<<13)|(j2<<11)|((o>>1)&0x7ff))
def elf(path):
 b=path.read_bytes();off=struct.unpack_from('<I',b,32)[0];step,n=struct.unpack_from('<HH',b,46)
 ss=[struct.unpack_from('<10I',b,off+i*step) for i in range(n)];chunks=[];syms={}
 for s in ss:
  if s[2]&2 and s[1]!=8:chunks.append((s[3],b[s[4]:s[4]+s[5]]))
  if s[1]!=2:continue
  st=ss[s[6]];tab=b[st[4]:st[4]+st[5]]
  for i in range(0,s[5],s[9]):
   name,value,size,info,_,idx=struct.unpack_from('<IIIBBH',b,s[4]+i)
   if idx and info&15==2:syms[tab[name:].split(b'\0')[0].decode()]=value&~1
 return chunks,syms
def compile_filter():
 """Compiled with the shipped UI flags (LTO, exports kept), linked alone."""
 OUT.mkdir(parents=True,exist_ok=True);ld=OUT/'browser.ld';out=OUT/'browser.elf'
 ld.write_text(f"SECTIONS {{ . = {CODE:#x}; .text : {{ *(.text*) *(.rodata*) *(.pad) *(.stepui) *(.kitdraw) }} "
  "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n")
 subprocess.run([os.environ.get('BENTO_ZIG_PYTHON',sys.executable),'-m','ziglang','cc',
  '-DBENTO_SYNCUSSION=1','-flto','-fno-inline-functions',*['-Wl,-u,'+n for n in EXPORTS],
  '-DBENTO_STOCK_INST=1','-target','thumb-freestanding-eabi','-mcpu=cortex_m4','-mfloat-abi=soft','-Oz',
  '-mllvm','-enable-machine-outliner=always','-g','-ffreestanding','-fno-builtin',
  '-fno-stack-protector','-nostdlib','-Wl,--entry=browser_list_hook','-Wl,--script='+str(ld),
  str(R/'browser_filter_ui.c'),'-o',str(out)],check=True)
 chunks,syms=elf(out);assert all(n in syms for n in EXPORTS),syms
 return chunks,syms
CHUNKS=SYMS=None
def compiled():
 global CHUNKS,SYMS
 if CHUNKS is None:
  pre=os.environ.get('BENTO_BROWSER_ELF')
  CHUNKS,SYMS=elf(Path(pre)) if pre else compile_filter()
 return CHUNKS,SYMS
class Card:
 """FatFS enumeration fixture: (dir, name, size, attr) entries."""
 def __init__(self,entries):self.entries=entries;self.iters={}
class Emu:
 def __init__(self,image,card=None,patch=True):
  self.syms=SHIPPED.get(hashlib.sha256(image).digest())
  self.shipped=self.syms is not None
  chunks=[] if self.shipped else compiled()[0]
  if not self.shipped:self.syms=compiled()[1]
  self.image=image;self.card=card or Card([])
  u=self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
  for a,n in [(BASE,0x1c0000),(CODE,0x10000),(0x20000000,0x40000),(0x24000000,0x80000),(0x30000000,0x40000),(0xc0000000,0x400000)]:u.mem_map(a,n)
  u.mem_write(BASE,image)
  for a,d in chunks:u.mem_write(a,d)
  self.posts=[];self.types={};self.index=3;self.track=0x77;self.calls=[]
  for site,old,new in [(HOOK_SITE,0x081020ac,self.syms['browser_list_hook']),(REQUEST_SITE,0x08132db4,self.syms['browser_request'])]:
   assert image[site-BASE:site-BASE+4]==bl(site,new if self.shipped else old),hex(site)
   if not patch or not self.shipped:u.mem_write(site,bl(site,new if patch else old))
  for a in [0x08120e2c,0x08120df2,0x08120d8c,0x08133cfc,0x08133f7c,0x08132db4,0x08132e6c]:
   u.hook_add(UC_HOOK_CODE,self.native,begin=a,end=a)
 def w(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
 def r(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def text(self,a,n=256):return bytes(self.u.mem_read(a,n)).split(b'\0')[0].decode('latin-1')
 def ret(self,v=0):self.u.reg_write(UC_ARM_REG_R0,v&0xffffffff);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def fill(self,fno,e):
  self.u.mem_write(fno,bytes(0x120))
  if e is None:return
  _,name,size,attr=e
  self.u.mem_write(fno,struct.pack('<Q',size));self.u.mem_write(fno+0xc,bytes([attr]))
  self.u.mem_write(fno+0x1a,name.encode()+b'\0')
 def native(self,u,a,n,d):
  r=[u.reg_read(x) for x in REGS]
  if a==0x08120e2c:
   path,pat=self.text(r[2]),self.text(r[3]);self.calls.append(('find',path,pat))
   it=iter([e for e in self.card.entries if e[0]==path and fnmatch.fnmatch(e[1].lower(),pat.lower())])
   self.card.iters[r[0]]=it;self.fill(r[1],next(it,None));self.ret(0)
  elif a==0x08120df2:self.fill(r[1],next(self.card.iters[r[0]],None));self.ret(0)
  elif a==0x08120d8c:self.card.iters.pop(r[0],None);self.ret(0)
  elif a==0x08133cfc:
   assert r[0]==MODEL;self.w(r[1],self.track);self.ret(int(self.track!=0))
  elif a==0x08133f7c:
   assert r[0]==MODEL and self.r(r[1])==self.track;self.ret(self.types.get(self.track,0))
  elif a==0x08132e6c:self.posts.append(('mode3',self.text(r[1])));self.ret(0)
  elif a==0x08132db4:
   self.posts.append((r[0],self.text(r[1]),r[2],self.r(CONTEXT)));self.ret(0)
 def call(self,a,*args):
  for reg,v in zip(REGS,args):self.u.reg_write(reg,v)
  sp=0x2003e000
  for i,v in enumerate(args[4:]):self.w(sp+i*4,v)
  self.u.reg_write(UC_ARM_REG_SP,sp);self.u.reg_write(UC_ARM_REG_LR,STOP|1)
  for reg in (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11):self.u.reg_write(reg,0x5a5a0000|reg)
  self.u.emu_start(a|1,STOP,count=5000000)
  assert self.u.reg_read(UC_ARM_REG_PC)==STOP,hex(self.u.reg_read(UC_ARM_REG_PC))
  for reg in (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11):
   assert self.u.reg_read(reg)==0x5a5a0000|reg,'callee-saved register clobbered'
  return self.u.reg_read(UC_ARM_REG_R0)
 def listing(self,path,pattern='*.wav',dirs=1,context=0,capacity=64,mounted=1):
  self.w(CONTEXT,context);self.u.mem_write(FS+0x15,bytes([mounted]))
  self.w(LIST,0x1234);self.w(LIST+4,capacity);self.w(LIST+8,STORE);self.w(LIST+0xc,PTRS);self.u.mem_write(LIST+0x10,bytes(4))
  self.u.mem_write(0x20012000,path.encode()+b'\0');self.u.mem_write(0x20012200,pattern.encode()+b'\0')
  self.call(0x081041f8,FS,0x20012000,0x20012200,dirs,LIST)
  count=self.r(LIST);assert count<capacity
  out=[]
  for i in range(count):
   p=self.r(PTRS+i*4);assert p==STORE+i*256;out.append(self.text(p))
  return out
 def request(self,pattern,folders=0,mode=0,path='\\Drum Synths'):
  self.u.mem_write(MODEL+0x18b8,pattern.encode()+b'\0')
  self.u.mem_write(VIEW+0xb67c8,b'\0');self.u.mem_write(VIEW+0xb6a01,bytes([mode]))
  self.u.mem_write(VIEW+0xb6a02,path.encode()+b'\0');self.u.mem_write(VIEW+0xb6c02,bytes([folders]))
  self.call(0x0816c9b0,VIEW)
SYN='\\Drum Synths'
CARD=[(SYN,'Kick.wav',288082,0x20),(SYN,'Snare.wav',288086,0x20),(SYN,'HiHat.wav',288090,0x20),
 (SYN,'Clap.wav',288094,0x20),(SYN,'Tom.wav',288098,0x20),(SYN,'Syncussion.wav',288110,0x20),
 (SYN,'Syncussion Melodic.wav',MELODIC,0x20),(SYN,'Subtractive.wav',RETIRED,0x20),
 (SYN,'My Loop.wav',4000,0x20),(SYN,'SHOUT.WAV',RETIRED,0x20),(SYN,'Old',0,0x10),
 ('\\Projects','BENTO_Synth_Subtractive.wav',RETIRED,0x20),('\\Projects','Subtractive.wav',RETIRED,0x20),
 ('\\Projects','Syncussion Melodic.wav',MELODIC,0x20),('\\Projects','Song',0,0x10),
 ('\\Samples','Subtractive.wav',RETIRED,0x20)]
ALL_SYN=['Kick.wav','Snare.wav','HiHat.wav','Clap.wav','Tom.wav','Syncussion.wav','Syncussion Melodic.wav','Subtractive.wav','My Loop.wav','SHOUT.wav','\\Old']
def present():return [p for p in IMAGES if p.is_file()]
@unittest.skipUnless(present(),'private firmware images are not present (kept outside Git)')
class BrowserFilter(unittest.TestCase):
 def images(self):
  for p in present():
   with self.subTest(image=p.name):yield p.read_bytes()
 def test_patch_sites_are_stock_and_reach(self):
  for image in self.images():
   e=Emu(image,patch=False)
   self.assertEqual(image[HOOK_SITE-BASE:HOOK_SITE-BASE+4],bl(HOOK_SITE,e.syms['browser_list_hook'] if e.shipped else 0x081020ac))
   self.assertEqual(image[0x0810435a-BASE:0x0810435a-BASE+4],bl(0x0810435a,0x081020ac))
   self.assertEqual(image[REQUEST_SITE-BASE:REQUEST_SITE-BASE+4],bl(REQUEST_SITE,e.syms['browser_request'] if e.shipped else 0x08132db4))
   for s in EXPORTS:self.assertIn(s,e.syms)
 def test_unpatched_native_listing_shows_every_file(self):
  for image in self.images():
   e=Emu(image,Card(CARD),patch=False)
   self.assertEqual(e.listing(SYN,context=ONE_SHOT),ALL_SYN)
 def test_retired_subtractive_hidden_everywhere_in_drum_synths(self):
  for image in self.images():
   e=Emu(image,Card(CARD))
   got=e.listing(SYN)
   self.assertEqual(got,[n for n in ALL_SYN if n not in('Subtractive.wav','Syncussion.wav','Syncussion Melodic.wav')]) # run 14: melodic hidden everywhere
   self.assertNotIn('Subtractive.wav',e.listing(SYN,pattern='*'))
 def test_old_syncussion_carrier_hidden_metal_listed(self):
  # R6.6 (owner: the browser still said Syncussion): Metal.wav is the carrier;
  # the old same-size Syncussion.wav stays readable but is not listed.
  card=CARD+[(SYN,'Metal.wav',288110,0x20)]
  for image in self.images():
   e=Emu(image,Card(card))
   got=e.listing(SYN)
   self.assertNotIn('Syncussion.wav',got);self.assertIn('Metal.wav',got)
 def test_melodic_hidden_in_every_context(self):
  # Run 14 (owner, 13 Nov): melodic Syncussion is retired, so its carrier is not offered in any browser
  # (until then it was listed for Multisample tracks).
  for image in self.images():
   e=Emu(image,Card(CARD))
   self.assertNotIn('Syncussion Melodic.wav',e.listing(SYN,context=0))
   self.assertNotIn('Syncussion Melodic.wav',e.listing(SYN,context=0x12345678))
   got=e.listing(SYN,context=ONE_SHOT)
   self.assertEqual(got,[n for n in ALL_SYN if n not in ('Subtractive.wav','Syncussion.wav','Syncussion Melodic.wav')])
 def test_path_forms_for_root_drum_synths(self):
  for image in self.images():
   for path in ['Drum Synths','\\Drum Synths','\\Drum Synths\\','0:\\Drum Synths','0:/Drum Synths/']:
    card=Card([(path,n,s,a) for _,n,s,a in CARD if _==SYN])
    e=Emu(image,card)
    self.assertEqual(e.listing(path,context=ONE_SHOT),[n for n in ALL_SYN if n not in ('Subtractive.wav','Syncussion.wav','Syncussion Melodic.wav')],path)
 def test_older_packaged_melodic_name_is_also_hidden_everywhere(self):
  for image in self.images():
   files=[(SYN,'Syncussion_Melodic.wav',MELODIC,0x20),
    (SYN,'Syncussion_Melodic.wav',MELODIC+2,0x20),
    (SYN,'SyncussionXMelodic.wav',MELODIC,0x20),
    ('\\Samples','Syncussion_Melodic.wav',MELODIC,0x20)]
   e=Emu(image,Card(files))
   self.assertEqual(e.listing(SYN,context=ONE_SHOT,dirs=0),
    ['Syncussion_Melodic.wav','SyncussionXMelodic.wav'])
   self.assertEqual(e.listing(SYN,context=0,dirs=0),
    ['Syncussion_Melodic.wav','SyncussionXMelodic.wav'])
   self.assertEqual(e.listing('\\Samples',context=ONE_SHOT,dirs=0),
    ['Syncussion_Melodic.wav'])
 def test_user_files_and_other_folders_untouched(self):
  for image in self.images():
   e=Emu(image,Card(CARD+[('\\Samples\\Drum Synths','Subtractive.wav',RETIRED,0x20),
    ('\\Drum Synths Old','Subtractive.wav',RETIRED,0x20),(SYN+'2','Syncussion Melodic.wav',MELODIC,0x20)]))
   self.assertEqual(e.listing('\\Projects',context=ONE_SHOT),['BENTO_Synth_Subtractive.wav','Subtractive.wav','Syncussion Melodic.wav','\\Song'])
   self.assertEqual(e.listing('\\Samples',context=ONE_SHOT,dirs=0),['Subtractive.wav'])
   self.assertEqual(e.listing('\\Samples\\Drum Synths',context=ONE_SHOT,dirs=0),['Subtractive.wav'])
   self.assertEqual(e.listing('\\Drum Synths Old',context=ONE_SHOT,dirs=0),['Subtractive.wav'])
   self.assertEqual(e.listing(SYN+'2',context=ONE_SHOT,dirs=0),['Syncussion Melodic.wav'])
 def test_exact_size_and_name_required(self):
  for image in self.images():
   card=Card([(SYN,'Subtractive.wav',RETIRED+2,0x20),(SYN,'Syncussion Melodic.wav',MELODIC-2,0x20),
    (SYN,'Subtractive.wav.wav',RETIRED,0x20),(SYN,'xSubtractive.wav',RETIRED,0x20),
    (SYN,'Syncussion Melodic.wav',MELODIC|(1<<32),0x20)])
   e=Emu(image,card)
   self.assertEqual(e.listing(SYN,context=ONE_SHOT,dirs=0),['Subtractive.wav','Syncussion Melodic.wav','Subtractive.wav.wav','xSubtractive.wav','Syncussion Melodic.wav'])
   # Carriers are written by the firmware in exact case; other case is a user file.
   e=Emu(image,Card([(SYN,'SUBTRACTIVE.WAV',RETIRED,0x20),(SYN,'syncussion melodic.wav',MELODIC,0x20),(SYN,'Subtractive.WAV',RETIRED,0x20),(SYN,'Kick.wav',288082,0x20)]))
   self.assertEqual(e.listing(SYN,context=ONE_SHOT,dirs=0),['SUBTRACTIVE.wav','syncussion melodic.wav','Kick.wav'])
 def test_capacity_bound_and_unmounted(self):
  for image in self.images():
   e=Emu(image,Card(CARD))
   self.assertEqual(e.listing(SYN,context=ONE_SHOT,capacity=4),['Kick.wav','Snare.wav','HiHat.wav'])
   self.assertEqual(e.listing(SYN,mounted=0),[])
 def test_request_context_from_real_browser_view(self):
  for image in self.images():
   e=Emu(image);e.types[e.track]=14
   e.w(CONTEXT,0xdeadbeef);e.request('*.wav')
   self.assertEqual(e.posts[-1],(MODEL,SYN,0,ONE_SHOT))
   for t in (15,18,19,22,0):
    e.types[e.track]=t;e.w(CONTEXT,ONE_SHOT);e.request('*.wav')
    self.assertEqual(e.posts[-1],(MODEL,SYN,0,0),t)
   e.types[e.track]=14
   for pattern in ('*.xml','*','*.wav2','*.WAV'):
    e.w(CONTEXT,ONE_SHOT);e.request(pattern)
    self.assertEqual(e.posts[-1],(MODEL,SYN,0,0),pattern)
   # Folder-only requests (message 1A) never run the PrepareFileList file pass.
   e.request('*.wav',folders=1)
   self.assertEqual(e.posts[-1][:3],(MODEL,SYN,1))
   e.track=0;e.w(CONTEXT,ONE_SHOT);e.request('*.wav')
   self.assertEqual(e.posts[-1],(MODEL,SYN,0,0))
   n=len(e.posts);e.w(CONTEXT,0x55);e.request('*.wav',mode=3)
   self.assertEqual((e.posts[n:],e.r(CONTEXT)),([('mode3',SYN)],0x55))
 def test_end_to_end_one_shot_then_multisample(self):
  for image in self.images():
   e=Emu(image,Card(CARD));e.types[e.track]=14;e.request('*.wav')
   self.assertNotIn('Syncussion Melodic.wav',e.listing(SYN,context=e.r(CONTEXT)))
   e.types[e.track]=15;e.request('*.wav')
   got=e.listing(SYN,context=e.r(CONTEXT))
   self.assertNotIn('Syncussion Melodic.wav',got);self.assertNotIn('Subtractive.wav',got) # run 14: hidden for Multisample too
if __name__=='__main__':unittest.main()
