"""Native MPU enforcement and early startup with the FPU disabled.
This checks the known F1/K8 failure classes; it is not a full device emulator.
"""
from pathlib import Path
import json,os,struct,unittest
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_MEM_WRITE,UC_HOOK_MEM_READ,UC_HOOK_CODE
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ['BENTO_FX_CANDIDATE']);IMAGE=(OUT/'bento1.bin').read_bytes()
BASELINE=Path(os.environ['BENTO_K16_IMAGE']).read_bytes();MAN=json.loads((OUT/'manifest.json').read_text())
BASE=0x08040000
UI_CODE_START=0x081bd8c0
class Machine:
 def __init__(self,core,image=IMAGE,mclass=True):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|(UC_MODE_MCLASS if mclass else 0));self.core=core
  self.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4 if core==4 else UC_CPU_ARM_CORTEX_M7)
  for a,n in [(BASE,0x1c0000),(0x20000000,0x40000),(0x24000000,0x80000),(0x30000000,0x40000),(0xe000e000,0x2000)]:self.u.mem_map(a,n)
  self.u.mem_write(BASE,image);self.regions={};self.control=0;self.enforce=False;self.accesses=[]
  self.u.hook_add(UC_HOOK_MEM_WRITE,self.mpu,begin=0xe000ed94,end=0xe000eda3)
  self.u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,self.access,begin=0x24000000,end=0x2407ffff)
 def r(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def mpu(self,u,kind,a,size,value,data):
  if a==0xe000ed94:self.control=value
  if a==0xe000eda0:self.regions[self.r(0xe000ed98)]=(self.r(0xe000ed9c),value)
 def allowed(self,a,execute=False):
  if not self.control&1:return True
  for _,(base,r) in sorted(self.regions.items(),reverse=True):
   size=1<<(((r>>1)&31)+1);base&=~(size-1)
   if not r&1 or not base<=a<base+size:continue
   if size>=256 and r&(1<<(8+(a-base)*8//size)):continue
   return (r>>24)&7==3 and (not execute or not r&(1<<28))
  return bool(self.control&4)
 def access(self,u,kind,a,size,value,data):
  if self.enforce:
   assert self.allowed(a) and self.allowed(a+size-1),f'MPU denied {a:08x}'
   self.accesses.append((a,size))
 def call(self,a,end=0x3003f000,count=100000):
  self.u.reg_write(UC_ARM_REG_SP,0x3003e000);self.u.reg_write(UC_ARM_REG_LR,0x3003f001)
  self.u.emu_start(a|1,end,count=count)
  assert self.u.reg_read(UC_ARM_REG_PC)==end,hex(self.u.reg_read(UC_ARM_REG_PC))
 def configure(self):self.call(0x08114d74 if self.core==4 else 0x0804fa00)
def prepare_motion(p):
 p.u.mem_map(0xc6000000,0x200000)
 p.u.mem_write(0xc6000000,b'\xa5'*0x200000)
 p.u.mem_write(0x30000048,struct.pack('<2I',0xc6200000,0xc6000000))
 p.u.reg_write(UC_ARM_REG_R0,1);p.call(MAN['ui_symbols']['nm_set_enabled'])
 assert p.r(0x3000004c)==0xc6000000 and p.r(0x24041984)==0
 def no_selection(u,a,n,d):
  u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 h=p.u.hook_add(UC_HOOK_CODE,no_selection,begin=0x08133cfc,end=0x08133cfc)
 try:
  for _ in range(64):
   before=p.r(0x24041998)
   p.call(MAN['ui_symbols']['nm_status'])
   if p.r(0x24041984):break
   assert p.r(0x24041998)-before==1024
  else:raise AssertionError('Initialization never published')
 finally:p.u.hook_del(h)
 return p.r(0x24041984)
class Tests(unittest.TestCase):
 def historical_patched_record_entry(self):
  # Used only by the pinned D14 diagnostic's explicit suite, not this core.
  for mode in (0,1):
   p=Machine(7);p.configure();p.enforce=True
   p.u.mem_map(0xc6000000,0x10000)
   p.u.mem_write(0xc6000040,bytes([mode]))
   p.u.reg_write(UC_ARM_REG_R0,0xc6000000);p.u.reg_write(UC_ARM_REG_R1,1)
   p.call(0x08058500,0x08058520)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_R0),0xc6000000)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_R1),1)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_R2),0xc6008000)
   self.assertEqual(p.u.mem_read(0xc6008ea5,1),b'\1')
   self.assertTrue(p.allowed(MAN['audio_symbols']['nm_audio_record'],True))
   self.assertTrue(p.allowed(0x080d15f0,True))

 def test_full_native_record_dispatch_and_queue_match_baseline(self):
  for mode in (0,1):
   for before in (0,1):
    results=[]
    for image in (BASELINE,IMAGE):
     p=Machine(7,image);p.configure();p.enforce=True
     p.u.mem_map(0xc6000000,0x20000)
     p.u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);p.u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
     p.u.mem_write(0xc6000040,bytes([mode]))
     p.u.mem_write(0xc6000000+(0x14b if mode else 0x8be9),bytes([before]))
     saved=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
     for r in saved:p.u.reg_write(r,0x12340000+r)
     # The native M7 button dispatcher receives type 90, track -2 and a
     # boolean at +10. Execute its real tail branch and K16 queue producer.
     for pressed in (1,0):
      p.u.mem_write(0x30030000,struct.pack('<6I',0x90,0,0xfffffffe,0,pressed,0))
      p.u.reg_write(UC_ARM_REG_R0,0xc6000000);p.u.reg_write(UC_ARM_REG_R1,0x30030000)
      p.call(0x08059980,count=1000000)
      for r in saved:self.assertEqual(p.u.reg_read(r),0x12340000+r)
     results.append(bytes(p.u.mem_read(0xc6000000,0x10000)))
    self.assertEqual(*results)

 @unittest.skipUnless('nm_dispatch' in MAN['ui_symbols'],'Native motion is not enabled')
 def test_first_record_publication_runs_native_audio_frames_without_capture(self):
  ui=Machine(4);ui.configure();ui.enforce=True
  prepare_motion(ui)
  for cache_enabled in (0,1):
   # Stock evaluator uses double-precision instructions which this Unicorn
   # MCLASS model rejects; the existing audio suites use its Thumb engine.
   p=Machine(7,mclass=False);p.configure();p.enforce=True
   p.u.mem_map(0xc6000000,0x200000)
   p.u.mem_write(0xc6000000,bytes(ui.u.mem_read(0xc6000000,0x200000)))
   p.u.mem_write(0x24041980,bytes(ui.u.mem_read(0x24041980,32)))
   p.u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);p.u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
   p.u.mem_write(0xe000ed14,struct.pack('<I',cache_enabled<<16))
   sequence=0xc6040000
   p.u.reg_write(UC_ARM_REG_R0,sequence);p.call(0x08062a80,count=1000000)
   p.u.mem_write(sequence+12,struct.pack('<I',100))
   p.u.mem_write(sequence+0x14,bytes(4));p.u.mem_write(sequence+0x20,b'\1')
   p.u.mem_write(sequence+0x86c0,struct.pack('<I',sequence+0x240))
   p.u.mem_write(sequence+0x260,bytes(8))
   cache_writes=[]
   h=p.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,k,a,n,v,d:cache_writes.append(v),
                  begin=0xe000ef5c,end=0xe000ef6b)
   for tick in (0,240,3840,7680):
    p.u.mem_write(0x30030000,struct.pack('<q',tick))
    p.u.reg_write(UC_ARM_REG_R0,sequence);p.u.reg_write(UC_ARM_REG_R1,0x30030000)
    try:p.call(MAN['audio_symbols']['nm_audio_automation'],count=1000000)
    except Exception as error:raise RuntimeError(f'cache={cache_enabled} tick={tick} pc={p.u.reg_read(UC_ARM_REG_PC):08x}') from error
   p.u.hook_del(h)
   self.assertLessEqual(len(cache_writes),40,'Empty publication must not invalidate 128 clip lines per frame')
   shared=p.r(0x24041984)
   self.assertEqual(p.r(shared+0x1020+4),sequence)
   self.assertEqual(p.r(shared+0x1020+0x10),7680)
   self.assertEqual(bytes(p.u.mem_read(shared+32,128*32)),bytes(128*32))

 @unittest.skipUnless('nm_dispatch' in MAN['ui_symbols'],'Native motion is not enabled')
 def test_cold_toggle_slices_real_allocation_without_fpu_or_euclid_publication(self):
  p=Machine(4);p.configure();p.enforce=True
  ec=bytes(p.u.mem_read(0x24041fc0,32))
  shared=prepare_motion(p)
  self.assertEqual(bytes(p.u.mem_read(0x24041fc0,32)),ec)
  self.assertEqual(p.r(shared),0x314d414e)
  self.assertEqual(bytes(p.u.mem_read(shared+32,128*32+8*64+64)),bytes(128*32+8*64+64))
  cursor=p.r(0x3000004c);self.assertLess(cursor,0xc6008000)
  state=bytes(p.u.mem_read(0x24041980,32))
  p.u.reg_write(UC_ARM_REG_R0,0xaf);p.u.reg_write(UC_ARM_REG_R1,14)
  p.call(MAN['ui_symbols']['nm_dispatch'])
  p.u.reg_write(UC_ARM_REG_R0,0xb0);p.u.reg_write(UC_ARM_REG_R1,14)
  p.call(MAN['ui_symbols']['nm_dispatch'])
  self.assertEqual(p.r(0x3000004c),cursor)
  self.assertEqual(bytes(p.u.mem_read(0x24041980,32)),state)

 @unittest.skipUnless('nm_dispatch' in MAN['ui_symbols'],'Native motion is not enabled')
 def test_exhausted_heap_refuses_motion_and_surfaces_the_error(self):
  p=Machine(4);p.configure();p.enforce=True
  p.u.mem_map(0xc6000000,0x200000)
  p.u.mem_write(0x30000048,struct.pack('<2I',0xc6000000,0xc6000000))
  p.u.reg_write(UC_ARM_REG_R0,1);p.call(MAN['ui_symbols']['nm_set_enabled'])
  def no_selection(u,a,n,d):
   u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  h=p.u.hook_add(UC_HOOK_CODE,no_selection,begin=0x08133cfc,end=0x08133cfc)
  try:p.call(MAN['ui_symbols']['nm_status'])
  finally:p.u.hook_del(h)
  self.assertEqual(p.r(0x24041984),0);self.assertEqual(p.r(0x24041990),0)
  # A failed Mod allocation is also a failed recorder allocation.
  p.u.reg_write(UC_ARM_REG_R0,0x30030000);p.call(MAN['ui_symbols']['nm_readout'])
  self.assertEqual(bytes(p.u.mem_read(0x30030000,16)),b'! MOTION MEMORY\0')

 def test_original_record_entry_is_unpatched_and_keeps_native_registers(self):
  self.assertEqual(IMAGE[0x08058500-BASE:0x08058520-BASE],BASELINE[0x08058500-BASE:0x08058520-BASE])
  self.assertEqual(IMAGE[0x080d15f0-BASE:0x080d1600-BASE],BASELINE[0x080d15f0-BASE:0x080d1600-BASE])
  self.assertNotIn('nm_audio_record',MAN['audio_symbols']);self.assertNotIn('nm_audio_poll',MAN['audio_symbols'])
  for mode in (0,1):
   p=Machine(7);p.configure();p.enforce=True
   p.u.mem_map(0xc6000000,0x10000)
   p.u.mem_write(0xc6000040,bytes([mode]))
   p.u.reg_write(UC_ARM_REG_R0,0xc6000000);p.u.reg_write(UC_ARM_REG_R1,1)
   p.call(0x08058500,0x08058520)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_R0),0xc6000000)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_R1),1)
   self.assertEqual(p.u.reg_read(UC_ARM_REG_R2),0xc6008000)
   self.assertEqual(p.u.mem_read(0xc6008ea5,1),b'\1')

 def test_native_c6_ui_heap_is_privileged_accessible_without_mpu_change(self):
  # Initial data copied by native reset sets allocator end/start at offsets48/4c.
  import struct
  stock=Path(os.environ['BENTO_STOCK_IMAGE']).read_bytes()
  self.assertEqual(struct.unpack_from('<2I',stock,0x081b3e38-BASE+0x48),(0xc8000000,0xc6000000))
  for core in [4,7]:
   p=Machine(core);p.configure()
   self.assertTrue(p.allowed(0xc6000000));self.assertTrue(p.allowed(0xc7ffffff))

 def test_native_mpu_unchanged_and_all_new_state_permitted_on_both_cores(self):
  for core in [4,7]:
   old=Machine(core,BASELINE);old.configure();p=Machine(core);p.configure()
   self.assertEqual((p.regions,p.control),(old.regions,old.control))
   for a in range(0x24040000,0x24042000,32):self.assertTrue(p.allowed(a),hex(a))
   code=(UI_CODE_START,BASE+len(IMAGE)) if core==4 else (0x080dc000,0x080e0000)
   for a in range(*code,32):self.assertTrue(p.allowed(a,True),hex(a))
   if core==4:self.assertFalse(p.allowed(0x2403a400))
 def test_ui_startup_no_fpu_and_permissions_enforced_and_owner_boundaries(self):
  p=Machine(4);p.configure();p.enforce=True
  p.u.mem_write(0x24040000,b'\xa5'*0x2000);p.u.mem_write(0x24042000,b'\x6b'*32)
  p.u.reg_write(UC_ARM_REG_R4,0x12345678);p.call(0x081004b6,0x081004ba)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_R4),0x12345678)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_R0),0x081891fc)
  self.assertEqual(bytes(p.u.mem_read(0x24041440,0x280)),bytes(0x280))
  self.assertEqual(bytes(p.u.mem_read(0x24041a00,0x600)),bytes(0x600))
  self.assertEqual(bytes(p.u.mem_read(0x24040000,0x1440)),b'\xa5'*0x1440)
  self.assertEqual(bytes(p.u.mem_read(0x240416c0,0x340)),b'\xa5'*0x340)
  self.assertEqual(bytes(p.u.mem_read(0x24042000,32)),b'\x6b'*32)
 def test_audio_startup_no_fpu_preserves_mailbox_and_k16_startup(self):
  p=Machine(7);p.configure();p.enforce=True
  p.u.mem_write(0x24040000,b'\xa5'*0x2000);p.call(0x080404b6,0x080404ba)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_R0),0x080a5f9c)
  self.assertEqual(bytes(p.u.mem_read(0x24040000,0x1440)),bytes(0x1440))
  self.assertEqual(bytes(p.u.mem_read(0x240416c0,0x340)),bytes(0x340))
  self.assertEqual(bytes(p.u.mem_read(0x24041440,0x280)),b'\xa5'*0x280)
  self.assertEqual(bytes(p.u.mem_read(0x24041a00,0x600)),b'\xa5'*0x600)
 def test_new_ui_code_contains_no_floating_point_instructions(self):
  # Limit disassembly to executable ELF symbol sizes (exclude string literals).
  # P1: only FUNC symbols are code (data such as label tables can decode as
  # anything); the next symbol of any kind still bounds each function.
  source=OUT/'workspace/eu4_work/integration' if (OUT/'workspace').exists() else Path(__file__).resolve().parent
  b=(source/'ui.elf').read_bytes();off=struct.unpack_from('<I',b,32)[0];step,n=struct.unpack_from('<HH',b,46)
  ss=[struct.unpack_from('<10I',b,off+i*step) for i in range(n)];funcs=set();starts=set()
  for sh in ss:
   if sh[1]==1 and sh[2]&4:
    self.assertEqual(b[sh[4]:sh[4]+sh[5]],IMAGE[sh[3]-BASE:sh[3]-BASE+sh[5]],'UI ELF must match the candidate image')
    starts.add(sh[3]+sh[5]) # W14 HW3: a section end bounds its last function (pad caves end before K16 code)
   if sh[1]!=2:continue
   for i in range(0,sh[5],sh[9]):
    _,value,size,info,_,_=struct.unpack_from('<IIIBBH',b,sh[4]+i)
    if info&15==2:funcs.add(value&~1);starts.add(value&~1)
    elif info&15==1:starts.add(value)
  starts=sorted(starts);c=Cs(CS_ARCH_ARM,CS_MODE_THUMB);self.assertGreater(len(funcs),100)
  for start in sorted(funcs):
   end=next((a for a in starts if a>start),start+20)
   for i in c.disasm(IMAGE[start-BASE:end-BASE],start):self.assertFalse(i.mnemonic.startswith('v'),str(i))
 def test_native_millisecond_counter_used_by_gesture(self):
  p=Machine(4);p.u.mem_write(0x3001fe2c,struct.pack('<I',0xfffffff0));p.call(0x081152c0)
  self.assertEqual(p.u.reg_read(UC_ARM_REG_R0),0xfffffff0)
 def test_patch_reversal_alignment_vectors_recovery_and_heap_guards(self):
  layer=bytearray(IMAGE)
  # The palette is last even when the retired motion layer is absent.
  if (OUT/'PALETTE_MANIFEST.json').exists():
   for w in reversed(json.loads((OUT/'PALETTE_MANIFEST.json').read_text())['writes']):
    a=w['address']-BASE;self.assertEqual(IMAGE[a:a+w['size']].hex(),w['replacement_hex'])
    layer[a:a+w['size']]=bytes.fromhex(w['original_hex'])
  pre=bytes(layer)
  if (OUT/'MOTION_MANIFEST.json').exists():
   # P22: the motion layer is applied to the complete Playground image (fx/).
   pre=(OUT/'fx/bento1.bin').read_bytes()
   for w in reversed(json.loads((OUT/'MOTION_MANIFEST.json').read_text())['writes']):
    a=w['address']-BASE;self.assertEqual(bytes(layer[a:a+w['size']]).hex(),w['replacement_hex'])
    layer[a:a+w['size']]=bytes.fromhex(w['original_hex'])
   self.assertEqual(bytes(layer[:len(pre)]),pre);self.assertFalse(any(layer[len(pre):]))
  restored=bytearray(pre)
  for w in reversed(MAN['writes']):
   a=w['address']-BASE;self.assertEqual(pre[a:a+w['size']].hex(),w['replacement_hex'])
   restored[a:a+w['size']]=bytes.fromhex(w['original_hex'])
  self.assertEqual(bytes(restored[:len(BASELINE)]),BASELINE);self.assertEqual(len(IMAGE)%4,0)
  motion_manifest=OUT/'MOTION_MANIFEST.json'
  if motion_manifest.exists():
   motion=json.loads(motion_manifest.read_text())
   for w in motion['writes']:
    self.assertFalse(0x080e0000<=w['address']<0x08100000) # P22b: never the 080E0000 program sector
  for a,n in [(BASE,0x400),(0x080e0000,0x20000),(0x08100000,0x400),(0x08114d74,0x180),(0x0804fa00,0x200)]:
   self.assertEqual(IMAGE[a-BASE:a-BASE+n],BASELINE[a-BASE:a-BASE+n])
  for a in [0x08040588,0x080a3bdc,0x080a3e94]:self.assertEqual(struct.unpack_from('<I',IMAGE,a-BASE)[0],0x24040000)
if __name__=='__main__':unittest.main(verbosity=2)
