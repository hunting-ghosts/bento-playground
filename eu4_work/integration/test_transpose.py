"""R6.6 Berlin-school transpose (owner, 7 Nov). M7: real native pad module
press 08084760 / release 08083FE0 through the patched CH6 sites reach
tr_press/tr_release first; the native note entries 0805F8E0 / 0805FE00 are
patched to adapters that call tr_note_pitch / tr_off_pitch."""
import struct,unittest,re
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_chord_audition import Pads,pitches,BANK,TRACK,PUB
from test_integration import UU,IMAGE
API={m.group(1):int(m.group(2),16) for m in re.finditer(r'#define (\w+) (0x[0-9a-f]+)u',(Path(__file__).resolve().parent/'seqfx_api.h').read_text())}
ARP=0xc0100000;TR=0xc0101000;OWNER=0x77;SEQ=0xc0110000
MAJOR=bytes([0,2,4,5,7,9,11])
class Tr(Pads):
 def __init__(self,armed=1,on=1,mode=0,base=60,root=0,rel=MAJOR):
  super().__init__();self.u.mem_write(ARP,bytes(0x400));self.u.mem_write(TR,bytes(0x200));self.w(BANK+28,ARP)
  self.w(ARP+60,TR) # ArpMail.spare[6]
  self.w(TR,0x31505254);self.w(TR+4,armed);self.w(TR+8,OWNER)
  self.u.mem_write(TR+40,bytes([on])+bytes(7)+bytes([mode])+bytes(7)+bytes([base,root])+rel)
  self.u.mem_write(SEQ,bytes(0x1000));self.w(SEQ+12,OWNER)
 def off(self):return struct.unpack('<b',self.u.mem_read(TR+96,1))[0]
 def note(self,pitch):return self.call(API['TR_NOTE_PITCH'],SEQ,pitch)
 def note_off(self,pitch):return self.call(API['TR_OFF_PITCH'],SEQ,pitch)
def native_pitch(pad):
 p=Pads();return pitches(p.press(pad),2)[0]
class Tests(unittest.TestCase):
 def test_native_note_entries_branch_to_the_transpose_adapters(self):
  for entry in (0x0805f8e0,0x0805fe00):
   h1,h2=struct.unpack_from('<HH',IMAGE,entry-0x08040000)
   self.assertEqual(h1&0xf800,0xf000,hex(entry));self.assertEqual(h2&0xd000,0x9000,hex(entry)) # b.w
 def test_patched_entries_reach_native_code_with_the_shifted_pitch(self):
  for entry,back in ((0x0805f8e0,0x0805f8e8),(0x0805fe00,0x0805fe08)):
   p=Tr();p.u.mem_write(TR+96,struct.pack('<b',5));seen=[]
   if entry==0x0805fe00:p.note(60) # the note-off follows the note-on's pitch
   def hit(u,a,n,d):seen.append((u.reg_read(UC_ARM_REG_R0),u.reg_read(UC_ARM_REG_R1),u.reg_read(UC_ARM_REG_R5)));u.emu_stop()
   p.u.hook_add(UC_HOOK_CODE,hit,begin=back,end=back)
   try:p.call(entry,SEQ,60,100,0)
   except Exception:pass
   self.assertEqual(seen,[(SEQ,65,SEQ+0x8000)],hex(entry))
 def test_armed_pad_sets_the_offset_silently_and_its_release_is_swallowed(self):
  pitch=native_pitch(4);p=Tr(base=pitch-5)
  self.assertEqual(p.press(4),[]);self.assertEqual(p.off(),5)
  self.assertEqual(p.u.mem_read(PUB+4+4,1)[0],0x80|pitch) # R6.10: the swallowed pad still publishes its pitch (pad lights)
  self.assertEqual(p.release(4),[])
 def test_not_armed_pads_play_normally(self):
  pitch=native_pitch(4);p=Tr(armed=0)
  self.assertEqual(pitches(p.press(4),2),[pitch]);self.assertEqual(pitches(p.release(4),3),[pitch])
 def test_chromatic_shift_and_note_off_follows_the_sounding_pitch(self):
  p=Tr();p.u.mem_write(TR+96,struct.pack('<b',3))
  self.assertEqual(p.note(60),63);self.assertEqual(p.note(67),70)
  p.u.mem_write(TR+96,struct.pack('<b',7)) # changed while the notes sound
  self.assertEqual(p.note_off(60),63);self.assertEqual(p.note_off(67),70)
  self.assertEqual(p.note_off(60),60) # map entry used up
 def test_diatonic_shift_stays_in_key(self):
  p=Tr(mode=1);p.u.mem_write(TR+96,struct.pack('<b',2)) # two scale degrees up
  self.assertEqual([p.note(n) for n in (60,62,64,65,71,72)],[64,65,67,69,74,76])
  self.assertEqual(p.note(61),65) # C# = C + 1 -> E + 1
  p.u.mem_write(TR+96,struct.pack('<b',-1))
  self.assertEqual([p.note(n) for n in (60,64)],[59,62])
 def test_diatonic_offset_from_pad_counts_scale_degrees(self):
  pitch=native_pitch(4);p=Tr(mode=1,base=pitch-4,root=(pitch-4)%12) # pad = major third above root
  p.press(4);self.assertEqual(p.off(),2)
 def test_other_tracks_and_off_tracks_are_untouched(self):
  p=Tr(on=0);p.u.mem_write(TR+96,struct.pack('<b',3));self.assertEqual(p.note(60),60)
  p=Tr();p.u.mem_write(TR+96,struct.pack('<b',3));p.w(SEQ+12,OWNER+1);self.assertEqual(p.note(60),60)
if __name__=='__main__':unittest.main()
