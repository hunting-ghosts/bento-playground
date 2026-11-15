"""The compact UI 64-bit division (ui_rt.c) against exact integer arithmetic."""
import os,random,subprocess,sys,tempfile,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB
from unicorn.arm_const import *
R=Path(__file__).resolve().parent;M=(1<<64)-1;BASE=0x08100000;STOP=0x080ff000
def sg(x):return x-(1<<64) if x>>63 else x
class UiRuntime(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  d=tempfile.mkdtemp();elf=os.path.join(d,'rt.elf');ld=os.path.join(d,'rt.ld')
  open(ld,'w').write('SECTIONS { . = 0x%x; .text : { *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n'%BASE)
  subprocess.run([os.environ.get('BENTO_ZIG_PYTHON',sys.executable),'-m','ziglang','cc','-target','thumb-freestanding-eabi','-mcpu=cortex_m4','-mfloat-abi=soft','-Oz','-g','-ffreestanding','-nostdlib','-Wl,--entry=__aeabi_ldivmod','-Wl,--script='+ld,str(R/'ui_rt.c'),'-o',elf],check=True)
  import struct
  e=open(elf,'rb').read();off=struct.unpack_from('<I',e,32)[0];step,n=struct.unpack_from('<HH',e,46);ss=[struct.unpack_from('<10I',e,off+i*step) for i in range(n)];c.sym={};c.code=b''
  for s in ss:
   if s[2]&2 and s[3]==BASE:c.code=e[s[4]:s[4]+s[5]]
   if s[1]!=2:continue
   st=ss[s[6]];tab=e[st[4]:st[4]+st[5]]
   for i in range(0,s[5],s[9]):
    name,value,size,info,_,idx=struct.unpack_from('<IIIBBH',e,s[4]+i)
    if info&15==2:c.sym[tab[name:].split(b'\0')[0].decode()]=value&~1
  c.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);c.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
  c.u.mem_map(0x080ff000,0x4000);c.u.mem_write(BASE,c.code);c.u.mem_write(STOP,b'\x00\xbe');c.u.mem_map(0x20000000,0x4000)
 def call(self,name,n,d):
  u=self.u;keep=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
  u.reg_write(UC_ARM_REG_SP,0x20002000);u.reg_write(UC_ARM_REG_LR,STOP|1)
  for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(n&0xffffffff,n>>32,d&0xffffffff,d>>32)):u.reg_write(r,v)
  for i,r in enumerate(keep):u.reg_write(r,0x1111*(i+4))
  u.emu_start(self.sym[name]|1,STOP,count=4000)
  self.assertEqual((u.reg_read(UC_ARM_REG_PC),u.reg_read(UC_ARM_REG_SP)),(STOP,0x20002000))
  for i,r in enumerate(keep):self.assertEqual(u.reg_read(r),0x1111*(i+4))
  g=u.reg_read;return g(UC_ARM_REG_R0)|g(UC_ARM_REG_R1)<<32,g(UC_ARM_REG_R2)|g(UC_ARM_REG_R3)<<32
 def vectors(self):
  random.seed(168);edge=[0,1,2,3,100,127,360,2000,160000,0x7fffffff,0x80000000,0xffffffff,1<<32,(1<<63)-1,1<<63,(1<<63)+1,M-159999,M-1,M]
  v=[(a,b) for a in edge for b in edge]
  for _ in range(6000):
   a=random.getrandbits(random.choice((8,16,31,32,33,48,63,64)));b=random.getrandbits(random.choice((1,8,16,18,31,32,33,48,63,64)))
   v.append(((-a)&M if random.random()<.5 else a,(-b)&M if random.random()<.3 else b))
  return v
 def test_unsigned_division_is_exact(self):
  for a,b in self.vectors():
   if b:self.assertEqual(self.call('__aeabi_uldivmod',a,b),(a//b,a%b),(hex(a),hex(b)))
 def test_signed_division_truncates_toward_zero(self):
  for a,b in self.vectors():
   if not b:continue
   x,y=sg(a),sg(b);q=abs(x)//abs(y);q=-q if (x<0)!=(y<0) else q
   self.assertEqual(self.call('__aeabi_ldivmod',a,b),(q&M,(x-q*y)&M),(hex(a),hex(b)))
 def test_zero_divisor_returns_zero_and_the_dividend(self):
  for a,_ in self.vectors():
   self.assertEqual(self.call('__aeabi_ldivmod',a,0),(0,a));self.assertEqual(self.call('__aeabi_uldivmod',a,0),(0,a))
 def test_the_pair_stays_small(self):
  self.assertLessEqual(len(self.code),120)
if __name__=='__main__':unittest.main(verbosity=2)
