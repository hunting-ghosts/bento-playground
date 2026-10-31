"""P28 arpeggiator. M7: the real native pad module press 08084760 / release
08083FE0 and the patched CH6 post sites reach chord_press/chord_release, which
hand held pads to arp_press/arp_release; arp_block runs once per block. Only
the direct API tests substitute the router post 0809ECA0 and clock read
080A21C0. GraphTests instead run native graph iteration, routing, queue reads,
mixing and reset. M4 covers Performance rows, publication and project save/load
(test_perf fixture)."""
import struct,unittest,re,os
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_chord_audition import Pads,pitches,BANK,TRACK,LAYER,MOD,ROUTER
from test_integration import UU,CANDIDATE
import test_perf
API={m.group(1):int(m.group(2),16) for m in re.finditer(r'#define (\w+) (0x[0-9a-f]+)u',(Path(__file__).resolve().parent/'arp_api.h').read_text())}
ARP=0xc0100000;KEYS=dict(arp=0xa6,mode=0xa7,rate=0xaa,oct=0xb2,gate=0xb3)
class Arp(Pads):
 def __init__(self,layer=False,**cfg):
  super().__init__(layer=layer);self.u.mem_write(ARP,bytes(0x400));self.w(BANK+28,ARP);self.tick=None
  self.u.hook_add(UC_HOOK_CODE,self.clock,begin=0x080a21c0,end=0x080a21c0);self.config(**cfg)
 def config(self,on=1,mode=0,rate=4,octaves=1,gate=50,bpm=120,track=TRACK,serial=None):
  serial=serial or (self.r(ARP)+2)
  self.u.mem_write(ARP,struct.pack('<9I',serial,0x50524141,on,track,mode,rate,octaves,gate,bpm))
 def clock(self,u,a,n,d):
  out=u.reg_read(UC_ARM_REG_R0);self.u.mem_write(out,struct.pack('<q',self.tick));self.ret()
 def run(self,frames,block=64):
  out=[];t=0
  while t<frames:
   self.posts=[];
   self.call(API['ARP_BLOCK'],block,0);out+=[(t,)+p for p in self.posts];t+=block
  return out
def ons(ev):return [p for t,k,h,p,v in ev if k==2]

class GraphArp(Arp):
 """Native graph order: instrument queue reader, mixer, then queue reset.

 The instrument's DSP is a fixture, but its queue read, the graph iterator,
 mixer and final router reset execute native code. Enter at the real block
 call site so a direct ARP_BLOCK call cannot hide a late scheduler.
 """
 QUEUE=0xc0180000
 GRAPH=0xc0160000
 ENGINE=0x20008000
 DESCRIPTOR=0x2001a000
 NOTE=0x20035000
 def __init__(self,layer=False,**cfg):
  self.clock_reads=[]
  super().__init__(layer=layer,**cfg);self.next=0xc0120000;self.mixer();self.consumed=[]
  handles=[TRACK]+([LAYER] if layer else [])+[0xffffff00]
  self.note_queues=[self.QUEUE+i*0x604 for i in range(len(handles)-1)]
  for router in (ROUTER,self.ctx):
   self.w(router+4,self.QUEUE)
   for i,handle in enumerate(handles):
    self.w(router+8+i*8,handle);self.w(router+12+i*8,i)
   self.w(router+0x508,len(handles))
  instrument=0x20034000;vtable=instrument+0x100
  self.w(instrument,vtable);self.w(vtable+8,0x081ff201)
  self.w(self.GRAPH+0x1004,instrument);self.w(self.GRAPH+0x1008,self.root)
  self.w(self.GRAPH+0x2004,2)
  self.w(self.root+0x860,1)
  self.u.mem_write(self.root+0x18+8,struct.pack('<HH',0,15))
  self.u.hook_add(UC_HOOK_CODE,self.instrument,begin=0x081ff200,end=0x081ff200)
  self.u.hook_add(UC_HOOK_CODE,self.read_result,begin=0x081ff204,end=0x081ff204)
 def post(self,u,a,n,d):
  pass # Run the real router and queue append instead of Pads' post substitute.
 def instrument(self,u,a,n,d):
  self.reader_return=u.reg_read(UC_ARM_REG_LR);self.reader_queue=0;self.reader_index=0
  self.read_next()
 def read_next(self):
  self.u.reg_write(UC_ARM_REG_R0,self.note_queues[self.reader_queue])
  self.u.reg_write(UC_ARM_REG_R1,self.reader_index);self.u.reg_write(UC_ARM_REG_R2,self.NOTE)
  self.u.reg_write(UC_ARM_REG_LR,0x081ff205);self.u.reg_write(UC_ARM_REG_PC,0x080655a1)
 def read_result(self,u,a,n,d):
  if u.reg_read(UC_ARM_REG_R0):
   t,_,h,p,v,_=struct.unpack('<6I',u.mem_read(self.NOTE,24))
   self.consumed.append((t&255,h,p,v))
   self.reader_index+=1;self.read_next()
  elif self.reader_queue+1<len(self.note_queues):
   self.reader_queue+=1;self.reader_index=0;self.read_next()
  else:u.reg_write(UC_ARM_REG_PC,self.reader_return)
 def clock(self,u,a,n,d):
  self.clock_reads.append(u.reg_read(UC_ARM_REG_R1));super().clock(u,a,n,d)
 def graph_block(self,frames=64):
  self.consumed=[];self.w(self.buffers[0]+4,frames)
  self.w(self.DESCRIPTOR+0x34,frames)
  self.u.reg_write(UC_ARM_REG_R5,self.DESCRIPTOR)
  self.u.reg_write(UC_ARM_REG_R8,self.ENGINE)
  stop=self.stop;self.stop=0x08057d2a
  try:self.call(0x08057d26,self.GRAPH,self.ctx)
  finally:self.stop=stop
  self.queued_before_reset=self.r(self.QUEUE+0x600)
  self.call(0x0809f220,self.ctx,frames)
  return self.consumed

class GraphTests(unittest.TestCase):
 def test_piano_tracks_physical_chord_keys_not_arp_steps_or_released_latch(self):
  for mode in (1,2):
   a=Arp(on=mode);a.mail([0,4,7]);a.press(8)
   self.assertEqual(a.keys(),(1,1,[48,52,55]))
   a.run(7000);self.assertEqual(a.keys(),(1,1,[48,52,55]))
   a.release(8);self.assertEqual(a.keys(),(1,0,[]))
   events=a.run(7000)
   if mode==2:self.assertTrue(ons(events))

 def test_off_keeps_real_native_pad_queue_delivery(self):
  a=GraphArp(on=0);a.press(8)
  self.assertEqual(pitches(a.graph_block(),2),[48])
  a.release(8);self.assertEqual(pitches(a.graph_block(),3),[48])
 def test_arp_reaches_instrument_before_native_mixer_and_queue_reset(self):
  a=GraphArp();a.press(8)
  self.assertEqual(pitches(a.graph_block(),2),[48])
  self.assertEqual(a.r(a.QUEUE+0x600),0)
 def test_arp_clock_runs_without_tracks_in_the_mixer(self):
  a=GraphArp();a.w(a.root+0x860,0);a.press(8)
  self.assertEqual(pitches(a.graph_block(),2),[48])
 def test_gate_off_and_no_double_scheduling_from_mixer(self):
  a=GraphArp();a.press(8)
  events=[]
  for _ in range(100):events+=a.graph_block()
  self.assertEqual(pitches(events,2),[48,48])
  self.assertEqual(pitches(events,3),[48])
  self.assertEqual(a.r(ARP+64),100)
  a.release(8);self.assertEqual(pitches(a.graph_block(),3),[48])
 def test_layer_receives_the_same_native_arp_events(self):
  a=GraphArp(layer=True);a.press(8);events=a.graph_block()
  self.assertEqual(pitches(events,2),[48])
  self.assertEqual(pitches(events,2,LAYER),[48])
  a.config(on=0);events=a.graph_block()
  self.assertEqual(pitches(events,3),[48])
  self.assertEqual(pitches(events,3,LAYER),[48])
 def test_transport_clock_is_read_once_per_block_before_graph(self):
  a=GraphArp();a.tick=1000;a.press(8);a.u.mem_write(a.ENGINE+8+0x38,b'\1')
  starts=[]
  for frames in range(0,20000,64):
   a.tick=1000+frames*120//3000
   if pitches(a.graph_block(),2):starts.append(a.tick)
  self.assertTrue(len(starts)>=3 and all(min(s%240,240-s%240)<=3 for s in starts),starts)
  self.assertEqual(round(starts[0]/240),5)
  self.assertEqual(a.clock_reads,[a.ENGINE+8]*313)
  a.u.mem_write(a.ENGINE+8+0x38,b'\0');a.graph_block()
  self.assertEqual(len(a.clock_reads),313)
 def test_pre_graph_adapter_preserves_native_registers_flags_and_fp(self):
  a=GraphArp();a.tick=0;a.u.mem_write(a.ENGINE+8+0x38,b'\1')
  regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
        UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
        UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12]
  expected=[0x11220000+i for i in range(len(regs))]
  for reg,value in zip(regs,expected):a.u.reg_write(reg,value)
  expected[0:2]=[a.GRAPH,a.ctx];expected[5]=a.DESCRIPTOR;expected[8]=a.ENGINE
  for i in range(16):a.u.reg_write(UC_ARM_REG_S0+i,0x3f800000+i)
  a.u.reg_write(UC_ARM_REG_APSR,0xa0000000)
  regs += [UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_APSR]+[UC_ARM_REG_S0+i for i in range(16)]
  expected += [0x2003e000,0x08057d2b,a.u.reg_read(UC_ARM_REG_APSR)]+[0x3f800000+i for i in range(16)]
  entry=[]
  def capture(u,address,size,data):entry.extend(u.reg_read(reg) for reg in regs)
  a.u.hook_add(UC_HOOK_CODE,capture,begin=0x080654a0,end=0x080654a0)
  a.graph_block();self.assertEqual(entry,expected)
 def test_latch_replacement_and_track_switch_cleanup_reach_native_queue(self):
  a=GraphArp(on=2);a.press(8);a.release(8)
  self.assertEqual(pitches(a.graph_block(),2),[48])
  a.press(10);a.release(10)
  events=a.graph_block()
  self.assertEqual(pitches(events,3),[48])
  self.assertEqual(pitches(events,2),[50])
  a.config(on=2,track=TRACK+1)
  events=a.graph_block()
  self.assertEqual(pitches(events,3),[50])
  self.assertEqual(pitches(events,2),[])

class Tests(unittest.TestCase):
 def test_held_pads_are_kept_and_played_one_note_per_step_up(self):
  a=Arp();on=a.press(8);self.assertEqual(on,[]) # nothing posted by the press itself
  a.press(12);ev=a.run(6000*4+64) # 1/16 at 120 BPM = 6000 frames
  self.assertEqual(ons(ev),[48,52,48,52,48]);starts=[t for t,k,h,p,v in ev if k==2]
  self.assertTrue(all(5900<=starts[i+1]-starts[i]<=6100 for i in range(4)))
  self.assertTrue(all(h==TRACK for t,k,h,p,v in ev))
 def test_gate_half_step_and_every_on_has_an_off(self):
  a=Arp(gate=50);a.press(8);ev=a.run(6000*3)
  on=[t for t,k,h,p,v in ev if k==2];off=[t for t,k,h,p,v in ev if k==3]
  self.assertTrue(len(on)>=3 and len(off)>=len(on)-1);self.assertTrue(all(2900<=off[i]-on[i]<=3100 for i in range(min(len(on),len(off)))))
 def test_release_stops_and_latch_keeps_playing_until_new_press(self):
  a=Arp();a.press(8);a.run(6000);self.assertEqual(pitches(a.release(8),3),[]);ev=a.run(13000);self.assertEqual(ons(ev),[])
  b=Arp(on=2);b.press(8);b.release(8);self.assertEqual(ons(b.run(12500)),[48,48,48])
  b.press(10);b.release(10);ev=b.run(12500);self.assertEqual(set(ons(ev)),{50}) # new press replaces the latched notes
 def test_modes_and_octaves(self):
  for mode,want in [(0,[48,52,60,64,48]),(1,[64,60,52,48,64]),(2,[48,52,60,64,60,52,48]),(3,[52,48,64,60,52])]:
   a=Arp(mode=mode,octaves=2);a.press(12);a.press(8) # As played: E first
   self.assertEqual(ons(a.run(6000*(len(want)-1)+64)),want,mode)
  a=Arp(mode=4,octaves=2);a.press(8);a.press(12);self.assertTrue(set(ons(a.run(6000*12)))<= {48,52,60,64})
 def test_chord_mode_feeds_the_arp_with_the_chord_tones(self):
  a=Arp();a.mail([0,4,7]);a.press(8);self.assertEqual(ons(a.run(6000*2+64)),[48,52,55])
 def test_off_or_other_track_settings_leave_pads_native(self):
  a=Arp(on=0);self.assertEqual(pitches(a.press(8),2),[48]);self.assertEqual(pitches(a.release(8),3),[48])
  b=Arp();b.press(8);b.run(64);b.config(on=0);ev=b.run(64);self.assertEqual([k for t,k,h,p,v in ev],[3]) # switching off ends the note
  b.release(8);self.assertEqual(pitches(b.press(8),2),[48]) # native again
 def test_rate_and_tempo(self):
  a=Arp(rate=2,bpm=60);a.press(8);starts=[t for t,k,h,p,v in a.run(48000*2) if k==2] # 1/8 at 60 BPM = 24000 frames
  self.assertTrue(all(23900<=starts[i+1]-starts[i]<=24100 for i in range(len(starts)-1)),starts)
 def test_song_position_puts_steps_on_the_grid(self):
  a=Arp();a.tick=1000;a.press(8) # tick 1000: next 1/16 grid line is 1200 (240 ticks per 1/16)
  ev=[];t=0
  while t<20000: # a playing sequence reports the song position each block (0.04 ticks per frame at 120 BPM)
   a.posts=[];a.call(API['ARP_CLOCK'],0x20034000);a.call(API['ARP_BLOCK'],64,0);ev+=[(a.tick,)+p for p in a.posts];t+=64;a.tick=1000+int(t*0.04)
  starts=[tk for tk,k,h,p,v in ev if k==2] # block granularity: within 64 frames (2.6 ticks) after a grid line
  self.assertTrue(len(starts)>=3 and all(min(s_%240,240-s_%240)<=3 for s_ in starts),starts);self.assertEqual(round(starts[0]/240),5)
def page():
 p=test_perf.Page();p.open();p.header();p.w(0x3000004c,p.next)
 p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.w(0x3000004c,p.next),begin=0x08104c08,end=0x08104c08) # the bump cursor follows the fixture allocator
 return p
class PageTests(unittest.TestCase):
 def test_combined_row_has_the_arp_and_values_are_per_track(self):
  p=page();self.assertEqual(p.keys(2)[1],[0x132,0x14a,0x144,0xa7,0xaa,0xb2,0xb3,0xa6])
  r=p.r(0x30031484);self.assertEqual([p.text(p.r(r+k*32+4)) for k in KEYS.values()],['Arp','Arp Mode','Rate','Octaves','Gate'])
  self.assertEqual([p.get(k) for k in KEYS.values()],[0,0,4,1,50])
  p.edit(0xa6,2);p.edit(0xa7,3);p.edit(0xaa,6);p.edit(0xb2,9);p.edit(0xb3,5)
  self.assertEqual([p.get(k) for k in KEYS.values()],[2,3,6,4,10])
  p.track=0x92;self.assertEqual(p.get(0xa6),0)
 def test_settings_reach_the_audio_core_for_pitched_tracks(self):
  p=page();p.edit(0xa6,1);p.edit(0xaa,2)
  b=p.r(0x24041fc0+4);blk=p.r(b+28);self.assertTrue(blk)
  serial,magic,on,track,mode,rate,octs,gate,bpm=struct.unpack('<9I',p.u.mem_read(blk,36))
  self.assertEqual((serial%2,magic,on,track,rate,octs,gate,bpm),(0,0x50524141,1,p.track,2,1,50,120))
  p.ttype=14;p.call(UU['fx_dispatch'],0x30024b00,0xfe,0,0) # a one-shot track: no arp
  self.assertEqual(struct.unpack('<I',p.u.mem_read(blk+8,4))[0],0)
 def test_saved_with_the_track(self):
  p=page();p.edit(0xa6,2);p.edit(0xa7,1);p.edit(0xb3,80)
  obj=0x20010000;p.w(obj+16,p.track);p.call(UU['fx_save'],obj,0x20017000);self.assertIn('bento_perf_arp',p.attrs)
  saved=p.attrs['bento_perf_arp'];q=page();q.attrs['bento_perf_arp']=saved
  q.w(0x20010010,q.track);q.call(UU['fx_load'],0x20011000,0x20010000);q.call(UU['fx_finish'],0,0x20012000)
  self.assertEqual([q.get(k) for k in KEYS.values()],[2,1,4,1,80])
if __name__=='__main__':unittest.main(verbosity=2)
