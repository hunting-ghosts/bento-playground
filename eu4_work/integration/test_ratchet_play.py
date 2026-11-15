"""R6.13 ratchet playback (M7) through the installed native sequencer renderer.
The renderer runs via the patched only caller (080601E8 -> wrapper -> native
renderer -> rt_block); note records reach the native note-on 0805F8E0 through
the patched accepted-note adapter (08060B9A). Packets are captured at the
native router post (fixture), as in test_melodic. Ratchet tokens are made by
the M4 record code in the same image (locks_ratchet_word)."""
import unittest,struct,gc,hashlib,sys
import native_ids as N
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from test_editable_eu import Edit
from test_euclidean import note
from test_integration import UU,AA,IMAGE
BASE=0x08040000
KEEP=[]
def _wrapper():
 ins=next(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(IMAGE[0x080601e8-BASE:0x080601ec-BASE],0x080601e8))
 assert ins.mnemonic=='bl';return int(ins.op_str.lstrip('#'),16)
WRAP=_wrapper()
FRAMES_PER_TICK=25 # 120 BPM: a 1/16 step is 240 native ticks = 6000 frames
def pnote(at,pitch,ident,vel=90,length=960,lock=0):
 return struct.pack('<BBHIIIHHI',1,0,0,at,length,ident,pitch,vel,lock)
class Play(Edit):
 def __init__(self,notes=None,melodic=False):
  super().__init__(notes=notes or []);KEEP.append(self)
  if melodic:self.u.mem_write(self.clip+0x38,b'\0');self.w(self.clip,0) # absolute-tick clip (piano roll)
 def rt(self,count,shape=0,depth=0,prob=0):
  r=self.call(UU['locks_ratchet_pack'],count,shape,depth,prob);assert r not in (0,0xffffffff) or count<=1;return r
 def token(self,word,r,cond=0):
  t=self.call(UU['locks_condition_word'],word,cond) if cond else word
  return self.call(UU['locks_ratchet_word'],t,r)
 def sync_notes(self,events):
  cursor=self.clip+8;indices=0xc00a0000;arena=0xc00a1000;records=0xc00a2000
  self.w(cursor,indices);self.w(cursor+4,len(events));self.w(cursor+8,0);self.w(cursor+16,arena);self.w(arena,records)
  if events:
   self.u.mem_write(indices,struct.pack('<%dH'%len(events),*range(len(events))));self.u.mem_write(records,b''.join(events))
 def block_ptr(self):return self.r(0x24041fdc)
 def amount(self,owner,value,slot=0):
  b=self.block_ptr();self.w(b+8+slot*4,owner);self.u.mem_write(b+40+slot,bytes([value]))
 def play(self,until,size=1024,start=0):
  for at in range(start,until,size):
   n=min(size,until-at);self.block=at;self.w(self.clock,at);self.w(self.clock+4,0)
   self.call(WRAP,self.audioseq,self.clock,0,n,self.router) # patched only caller of the renderer
   self.release(n)
 def release(self,frames):
  # The native block function's time-based note-off loop (08060490..0806050A,
  # then its table compaction) on a prepared frame of that function: exact-frame
  # releases of every active-note entry ending in this block.
  from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R5,UC_ARM_REG_PC
  f=0x2003c000;self.u.mem_write(f,bytes(0x100))
  self.w(f+0x10,self.clock);self.w(f+0x14,self.router);self.w(f+0x34,frames);self.w(f+0x6c+8*4,self.stop|1)
  self.u.reg_write(UC_ARM_REG_SP,f);self.u.reg_write(UC_ARM_REG_R5,self.audioseq)
  self.u.emu_start(0x08060491,self.stop,count=200000);assert self.u.reg_read(UC_ARM_REG_PC)==self.stop
 def ons(self,kind=0x12):
  return [(self.absolute[i][1],struct.unpack_from('<I',pk,12)[0],struct.unpack_from('<I',pk,16)[0]) for i,pk in enumerate(self.emitted) if pk[0]==kind]
 def diag(self):b=self.block_ptr();return [self.r(b+72+4*i) for i in range(6)]
 def table(self):
  return [(self.u.mem_read(self.audioseq+0x38+16*i,1)[0],self.r(self.audioseq+0x3c+16*i),struct.unpack('<q',self.u.mem_read(self.audioseq+0x40+16*i,8))[0]) for i in range(self.r(self.audioseq+0x238))]
 def active(self):return self.r(self.block_ptr()+68) if self.block_ptr() else 0
def ticks_to_frames(t):return t*FRAMES_PER_TICK
def release_block(frame,size):
 # 1.6.1: the native release frame is block end - end position (08060490.., 080605C2 subs r2,r2,r1),
 # so a note ending at a block start is released at that block's end boundary.
 # 1.6.8: 1010 changed the native loop to end position - block start, clamped at 0 (08060960 subs r2,r2,r0;
 # 0806096A bic r2,r2,r2,asr#31): the release is posted on the exact frame, a note ending at a block start
 # at offset 0 of that block. Decided on the two stock images (ratchet_stock_evidence.py, HANDOVER section 8).
 if N.FW168:return frame//size
 return frame//size if frame%size else frame//size-1
class Tests(unittest.TestCase):
 def drum(self,r_args,steps=(1,),vel=90,size=1024,until=None,lock=0x5101030c):
  p=Play();r=p.rt(*r_args);tok=p.token(lock,r)
  p.notes=[note(s,vel=vel,lock=tok,ident=10+s) for s in steps];self.load(p);p.play(until or 6000*(max(steps)+2),size)
  return p
 def load(self,p):p.sync_notes(p.notes) # the native cursor reads exactly these note records
 def test_drum_hits_on_exact_frames_for_two_to_eight(self):
  for n in range(2,9):
   for size in (1024,1000,64):
    with self.subTest(count=n,block=size):
     p=self.drum((n,),size=size,until=6000*3)
     t0=240;want=[ticks_to_frames(t0+240*k//n) for k in range(n)]
     self.assertEqual([f for f,_,_ in p.ons()],want)
     self.assertEqual({v for _,_,v in p.ons()},{90})
     self.assertEqual(p.active(),0)
 def test_hit_on_a_block_boundary_and_lengths_follow_count(self):
  p=self.drum((2,),size=1000,until=6000*3) # second hit at frame 9000 = a block start
  self.assertEqual([f for f,_,_ in p.ons()],[6000,9000])
  # Each hit lasts note length / count (here 120 ticks = 3000 frames), the
  # native first hit too (the native alone would round it down to whole steps).
  # The drum key retriggers like native consecutive steps (no release between),
  # so one release, in the block where the last hit ends (12000).
  self.assertEqual(release_block(p.ons(0x13)[0][0],1000),12000//1000);self.assertEqual(len(p.ons(0x13)),1)
  if N.FW168:self.assertEqual(p.ons(0x13)[0][0],12000) # 1.6.8 posts the exact frame
  self.assertEqual(p.r(p.audioseq+0x238),0);self.assertEqual(p.diag(),[1,0,1,0,0,1])
 def test_plain_notes_play_as_on_the_stock_image(self):
  # Port 1.6.8: the packets of plain notes (no lock, no ratchet word) through the installed wrapper are the
  # packets of the stock image of this firmware version without any Playground code, block sizes 1024/1000/64,
  # with a note-off on a block start. Nothing outside the stock image may run in the stock pass.
  import ratchet_stock_evidence as E
  for name,(size,until,make) in E.SCENARIOS.items():
   with self.subTest(scenario=name):
    s=E.run(sys.modules[__name__],True,size,until,make());q=E.run(sys.modules[__name__],False,size,until,make())
    self.assertEqual(s['outside'],[]);self.assertEqual(s['left'],0);self.assertEqual(q['left'],0)
    self.assertGreaterEqual(len([r for r in s['rows'] if r[0]==0x13]),1)
    self.assertEqual(q['rows'],s['rows']);self.assertEqual(q['digest'],s['digest'])
    if name=='sixteen_steps_block_1024':self.assertEqual(s['digest'],GOLDEN_STOCK_PLAIN)
    if name=='one_step_block_1000': # the note ends on frame 12000 = a block start
     off=[r for r in s['rows'] if r[0]==0x13];self.assertEqual(len(off),1)
     self.assertEqual((off[0][1],off[0][2]),(0,12000) if N.FW168 else (1000,13000))
 def test_shapes_scale_velocity_by_depth(self):
  for shape,depth,want in [(0,100,[100,100,100,100]),(1,100,[100,67,33,1]),(2,100,[1,33,67,100]),(1,50,[100,83,67,50]),(2,50,[50,67,83,100])]:
   with self.subTest(shape=shape,depth=depth):
    p=self.drum((4,shape,depth),vel=100,until=6000*3)
    self.assertEqual([v for _,_,v in p.ons()],want)
 def test_probability_and_amount_roll_once_per_note(self):
  steps=tuple(range(16))
  p=self.drum((3,0,0,50),steps=steps,until=6000*18)
  per=[sum(1 for f,_,_ in p.ons() if 6000*s<=f<6000*(s+1)) for s in steps]
  self.assertTrue(set(per)<={1,3},per);self.assertIn(1,per);self.assertIn(3,per) # all hits or none
  for s,count in zip(steps,per): # a failed roll plays once, normally (full velocity)
   if count==1:self.assertEqual([v for f,_,v in p.ons() if 6000*s<=f<6000*(s+1)],[90])
  p=Play();r=p.rt(3);tok=p.token(0x5101030c,r);p.amount(p.owner,0)
  p.notes=[note(s,lock=tok,ident=10+s) for s in steps];self.load(p);p.play(6000*18)
  self.assertEqual(len(p.ons()),16) # amount 0 = no ratchets
  p=Play();r=p.rt(3);tok=p.token(0x5101030c,r);p.amount(p.owner,50)
  p.notes=[note(s,lock=tok,ident=10+s) for s in steps];self.load(p);p.play(6000*18)
  per=[sum(1 for f,_,_ in p.ons() if 6000*s<=f<6000*(s+1)) for s in steps]
  self.assertIn(1,per);self.assertIn(3,per)
 def raw(self,step,length,lock,ident=11,vel=90,pad=2):
  return struct.pack('<BBHIIIHHI',1,0,pad,step*960,length,ident,0,vel,lock)
 def test_span_is_the_note_length_but_never_less_than_one_step(self):
  # R6.14 owner: span = max(note length, one step), hits = span / count.
  for length,n,want in [(3840,4,[6000,12000,18000,24000]),(1920,4,[6000,9000,12000,15000]),(480,2,[6000,9000]),(960,2,[6000,9000])]:
   with self.subTest(length=length,count=n):
    p=Play();r=p.rt(n);tok=p.token(0x5101030c,r);p.notes=[self.raw(1,length,tok)];self.load(p);p.play(6000*7)
    self.assertEqual([f for f,_,_ in p.ons()],want);self.assertEqual(p.table(),[])
 def test_melodic_span_uses_the_published_step_len_and_never_overlaps(self):
  for step,length,n,want_ticks in [(0,60,2,[0,120]),(480,60,2,[0,240]),(0,3840,4,[0,960,1920,2880]),(480,960,4,[0,240,480,720])]:
   with self.subTest(step=step,length=length,count=n):
    p=Play(melodic=True);r=p.rt(n);tok=p.call(UU['locks_ratchet_word'],0,r)
    if step:b=p.block_ptr();p.w(b+8,p.owner);p.u.mem_write(b+48,struct.pack('<H',step))
    p.notes=[pnote(960,60,11,length=length,lock=tok)];self.load(p);p.play(ticks_to_frames(960+max(length,step or 240))+12000)
    self.assertEqual([f for f,_,_ in p.ons()],[ticks_to_frames(960+t) for t in want_ticks])
    offs=[f for f,_,_ in p.ons(0x13)];self.assertEqual(len(offs),n);self.assertEqual(p.table(),[])
    hit=want_ticks[1]-want_ticks[0]
    for k,t in enumerate(want_ticks):self.assertEqual(release_block(offs[k],1024),ticks_to_frames(960+t+hit)//1024) # hits never overlap
 def test_amount_scales_percent_only_and_a_b_always_plays_on_its_loop(self):
  for c,amount,loop,want in [(100,0,0,3),(100,0,1,1),(0,0,0,1),(99,100,0,3)]:
   with self.subTest(prob=c,amount=amount,loop=loop):
    p=Play();r=p.rt(3,0,0,c);tok=p.token(0x5101030c,r);p.amount(p.owner,amount)
    cc=0x24048a60
    for off,v in [(0,p.audioseq),(4,p.r(p.audioseq+12)),(8,p.clip),(12,loop)]:p.w(cc+off,v)
    p.notes=[note(1,lock=tok,ident=11)];self.load(p);p.play(6000*3)
    self.assertEqual(len(p.ons()),want)
 def test_a_b_probability_uses_the_condition_loop_count(self):
  for loop,want in [(0,3),(1,1),(2,3),(3,1)]:
   with self.subTest(loop=loop):
    p=Play();r=p.rt(3,0,0,100);tok=p.token(0x5101030c,r) # 100 = 1:2
    c=0x24048a60
    for off,v in [(0,p.audioseq),(4,p.r(p.audioseq+12)),(8,p.clip),(12,loop)]:p.w(c+off,v)
    p.notes=[note(1,lock=tok,ident=11)];self.load(p);p.play(6000*3)
    self.assertEqual(len(p.ons()),want)
 def test_locks_and_condition_of_the_note_apply_to_every_hit(self):
  p=self.drum((4,),until=6000*3,lock=0x51010348)
  self.assertEqual(len(p.ons()),4);self.assertEqual({lt for lt,pk in zip(p.locktrace,p.emitted) if pk[0]==0x12},{0x51010348})
 def test_ratchet_only_record_plays_hits_without_locks(self):
  p=Play();r=p.rt(2);tok=p.call(UU['locks_ratchet_word'],0,r);self.assertEqual(p.call(UU['locks_condition_get'],tok),0)
  p.notes=[note(1,lock=tok,ident=11)];self.load(p);p.play(6000*3)
  self.assertEqual([f for f,_,_ in p.ons()],[6000,9000]);self.assertEqual(set(p.locktrace[:2]),{0})
 def test_last_step_and_the_next_pass_across_a_clip_loop(self):
  p=Play();r=p.rt(4);tok=p.token(0x5101030c,r)
  p.notes=[note(0,lock=tok,ident=10),note(15,lock=tok,ident=25)];self.load(p)
  p.play(6000*16,1024)
  first=[f for f,_,_ in p.ons()]
  p.w(p.clip+0x20,16*240);p.sync_notes(p.notes) # loop: next pass, native cursor from the start
  p.play(6000*18,1024,start=6000*16)
  self.assertEqual(first,[1500*k for k in range(4)]+[90000+1500*k for k in range(4)])
  self.assertEqual([f for f,_,_ in p.ons()],first+[96000+1500*k for k in range(4)])
 def test_stop_and_rewind_leave_nothing_pending(self):
  p=Play();r=p.rt(8);tok=p.token(0x5101030c,r);p.notes=[note(1,lock=tok,ident=11)];self.load(p)
  p.play(6000+1024,1024);self.assertGreater(p.active(),0)
  before=len(p.ons());p.u.mem_write(p.audioseq+0x20,b'\0');p.play(6000+2048,1024,start=6000+1024)
  self.assertEqual(p.active(),0);self.assertEqual(len(p.ons()),before)
  p=Play();r=p.rt(8);tok=p.token(0x5101030c,r);p.notes=[note(1,lock=tok,ident=11)];self.load(p)
  p.play(6000+1024,1024);before=len(p.ons());p.sync_notes([]);p.play(1024,1024,start=0) # rewind to 0
  self.assertEqual(p.active(),0);self.assertEqual(len(p.ons()),before)
 def melodic(self,n,transpose=0,length=960,at=960):
  p=Play(melodic=True);r=p.rt(n);tok=p.call(UU['locks_ratchet_word'],0,r)
  if transpose:
   p.call(UU['tr_set'],p.owner,0,1);t=p.call(UU['tr_block'],0);slot=next(i for i in range(8) if p.r(t+8+4*i)==p.owner)
   p.u.mem_write(t+96+slot,bytes([transpose&255]))
  p.notes=[pnote(at,60,11,length=length,lock=tok)];self.load(p);p.play(ticks_to_frames(at+length)+12000)
  return p
 def test_melodic_hits_lengths_and_note_offs(self):
  for n in (2,3,4,8):
   with self.subTest(count=n):
    p=self.melodic(n)
    ons=[f for f,_,_ in p.ons()];offs=[f for f,_,_ in p.ons(0x13)]
    self.assertEqual(ons,[ticks_to_frames(960+960*k//n) for k in range(n)])
    self.assertEqual(len(offs),n) # every hit is released once, none hangs
    # The native releases a note in the block where its end falls; each hit
    # ends 960/n ticks after it starts (the first hit too: shortened natively).
    for k in range(n):
     end=ticks_to_frames(960+960*k//n+960//n)
     self.assertEqual(release_block(offs[k],1024),end//1024,(k,offs,end))
    self.assertEqual({x for _,x,_ in p.ons()}|{x for _,x,_ in p.ons(0x13)},{60})
    self.assertEqual(p.table(),[])
 def test_melodic_note_offs_follow_transpose(self):
  p=self.melodic(4,transpose=3)
  self.assertEqual({x for _,x,_ in p.ons()},{63});self.assertEqual({x for _,x,_ in p.ons(0x13)},{63})
  self.assertEqual(len(p.ons(0x13)),4)
 def test_chord_notes_starting_together_share_one_roll(self):
  p=Play(melodic=True);r=p.rt(2,0,0,50);tok=p.call(UU['locks_ratchet_word'],0,r)
  p.notes=[pnote(960*k,60+i,10+4*k+i,length=960,lock=tok) for k in range(8) for i in range(3)];self.load(p);p.play(ticks_to_frames(960*9))
  per={}
  for f,pitch,_ in p.ons():per.setdefault(f//24000,{}).setdefault(pitch,0);per[f//24000][pitch]+=1
  for k,counts in per.items():self.assertEqual(len(set(counts.values())),1,(k,counts))
  self.assertEqual({c for counts in per.values() for c in counts.values()},{1,2})
 def test_no_ratchet_word_plays_byte_identically_to_r6_12(self):
  # Golden: packet stream of this scenario on R6.12 (1e889f34...): conditions,
  # locks and plain notes, no ratchet word anywhere.
  p=Play();cond=p.call(UU['locks_condition_word'],0x51010348,101)
  p.notes=[note(s,vel=60+s,lock=(cond if s%3==0 else 0x5101030c if s%3==1 else 0),ident=10+s) for s in range(16)];self.load(p)
  p.play(6000*17,1024)
  self.assertEqual(len(p.ons()),16)
  digest=hashlib.sha256(b''.join(p.emitted)+struct.pack('<%dI'%len(p.absolute),*[a for _,a in p.absolute])).hexdigest()
  self.assertEqual(digest,GOLDEN_NO_RATCHET)
  self.assertEqual(p.block_ptr() and p.active(),0)
# 1.6.1: recorded on R6.12 1e889f34 (rt_c5); stock 1.6.1 (14475e9d...) plays the plain-note scenario with the same digest.
# 1.6.8: the same scenario on STOCK 1.6.8 (cb8f830e...) gives 31325fd4...: only the last of the 32 packets differs
# (the note-off ending on frame 96000: offset field 0x300 = end - block start, where 1.6.1 posts 0x100 = block end - end).
# A native change of the release loop, not a port effect; the lock/condition words of the golden scenario change nothing
# in it (plain notes on stock give the same digest in both versions). See test_plain_notes_play_as_on_the_stock_image.
GOLDEN_NO_RATCHET=N._v('8b4099f2998583afaab433059e4c3eb15b7a2898a87fe80053d6e534955d1ee2','31325fd43f9162f33035a0ba35dd3a0285478ad96da5e37575aec205dd20c04e')
GOLDEN_STOCK_PLAIN=GOLDEN_NO_RATCHET
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
