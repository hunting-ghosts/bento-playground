"""Stock A-D storage APIs execute unchanged; model lookup and IPC are fixtures.

These are prerequisites for the RECORD-hold rewrite, not a motion recorder.
No retired motion module or enlarged automation node is loaded.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

from test_integration import Fixture

MODEL = 0x30024b00
HANDLE = 0x20030000
NODE = 0xc0180000
NODE_BYTES = 0x814
SEQUENCE = 0xc0080000
TIME = 0x20030100


class Automation(Fixture):
 def __init__(self):
  super().__init__()
  self.w(HANDLE,55)
  self.undo=0;self.commands=[];self.lookups=[];self.present=True
  self.u.mem_write(NODE-16,b'\xa5'*16)
  self.u.mem_write(NODE+NODE_BYTES,b'\xa5'*16)
  for address in (0x0812ea72,0x081338dc,0x08133d84,0x0813650c,0x08136668,0x08173272):
   self.u.hook_add(UC_HOOK_CODE,self.service,begin=address,end=address)

 def service(self,u,address,size,data):
  r=[u.reg_read(reg) for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  if address==0x0812ea72:
   self.lookups.append((r[1],r[3]))
   if self.present:self.w(r[2],NODE)
   self.ret(int(self.present))
  elif address==0x081338dc:self.undo+=1;self.ret()
  elif address==0x08133d84:self.w(r[2],100);self.w(r[3],0);self.ret(1)
  elif address==0x0813650c:self.commands.append(bytes(u.mem_read(r[1],0x30)));self.ret()
  else:self.ret()

 def write(self,lane,step,value,snapshot=0):
  self.call(0x0813706c,MODEL,HANDLE,lane,step,value&0xffffffff,snapshot)

 def read(self,lane,step):
  value=self.call(0x081322f6,MODEL,HANDLE,lane,step)
  return struct.unpack('<i',struct.pack('<I',value))[0]


class NativeAutomationTests(unittest.TestCase):
 def test_writer_and_reader_preserve_signed_values_in_all_four_lanes(self):
  p=Automation()
  for lane,value in enumerate((-1000,-123,456,1000)):
   for step in (0,127,255):
    p.write(lane,step,value)
    self.assertEqual(p.read(lane,step),value)
    self.assertEqual(struct.unpack('<h',p.u.mem_read(NODE+10+2*(lane*256+step),2))[0],value)
   self.assertEqual(p.u.mem_read(NODE+0x80a+lane,1),b'\1')
  self.assertEqual(p.u.mem_read(NODE-16,16),b'\xa5'*16)
  self.assertEqual(p.u.mem_read(NODE+NODE_BYTES,16),b'\xa5'*16)

 def test_punch_in_write_changes_only_the_requested_step(self):
  p=Automation()
  for step in range(16):p.write(1,step,step*10)
  before=bytearray(p.u.mem_read(NODE,NODE_BYTES))
  p.write(1,7,-500)
  struct.pack_into('<h',before,10+2*(256+7),-500)
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),bytes(before))

 def test_native_writer_can_snapshot_once_then_continue_without_snapshots(self):
  p=Automation()
  p.write(0,0,100,snapshot=1);p.write(0,1,200);p.write(0,2,300)
  self.assertEqual(p.undo,1)
  self.assertEqual(p.lookups,[(55,1)]*3)

 def test_native_write_sends_the_actual_lane_step_and_value_to_audio(self):
  p=Automation();p.write(2,31,-700)
  self.assertEqual(len(p.commands),1)
  packet=p.commands[0]
  self.assertEqual(packet[0x18],7)
  self.assertEqual(struct.unpack_from('<H',packet,2)[0],2)
  self.assertEqual(struct.unpack_from('<I',packet,4)[0],31*960)
  self.assertEqual(struct.unpack_from('<i',packet,20)[0],-700)

 def test_invalid_lane_and_step_do_not_overrun_native_storage(self):
  p=Automation();before=bytes(p.u.mem_read(NODE-16,NODE_BYTES+32))
  for lane,step in ((4,0),(0,256),(0xffffffff,0),(0,0xffffffff)):
   p.write(lane,step,500)
   self.assertEqual(p.read(lane,step),0)
  self.assertEqual(bytes(p.u.mem_read(NODE-16,NODE_BYTES+32)),before)

 def test_missing_node_does_not_publish_a_successful_write(self):
  p=Automation();p.present=False
  p.write(0,0,123)
  self.assertEqual(p.commands,[])
  self.assertEqual(p.read(0,0),0)

 def test_native_clear_leaves_other_lanes_untouched(self):
  p=Automation()
  for lane in range(4):
   p.write(lane,3,100+lane)
   p.u.mem_write(NODE+0x80e+lane,b'\1')
  before=bytearray(p.u.mem_read(NODE,NODE_BYTES))
  p.call(0x081366bc,MODEL,HANDLE,1)
  before[10+512:10+1024]=bytes(512)
  before[0x80b]=0;before[0x80f]=0
  self.assertEqual(bytes(p.u.mem_read(NODE,NODE_BYTES)),bytes(before))
  self.assertEqual(p.undo,1)

 def test_actual_audio_evaluator_reads_native_signed_lane_values(self):
  p=Automation()
  p.call(0x08062a80,SEQUENCE)
  p.w(SEQUENCE+0x14,0);p.u.mem_write(SEQUENCE+0x20,b'\1')
  p.w(SEQUENCE+0x86c0,SEQUENCE+0x240);p.w(SEQUENCE+0x244,16)
  p.u.mem_write(TIME,bytes(8))
  # Native M7 rows interleave each 512-byte lane with its active flag.
  for lane,value in enumerate((-1000,-500,250,1000)):
   p.u.mem_write(SEQUENCE+0x240+0x3a+lane*0x202,struct.pack('<h',value))
   p.u.mem_write(SEQUENCE+0x240+0x23a+lane*0x202,b'\1')
  p.call(0x08061040,SEQUENCE,TIME)
  for lane,value in enumerate((-1.,-.5,.25,1.)):
   actual=struct.unpack('<f',p.u.mem_read(SEQUENCE+0x8720+lane*8,4))[0]
   self.assertAlmostEqual(actual,value,places=6)


if __name__=='__main__':unittest.main(verbosity=2)
