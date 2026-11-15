"""Evidence tool (port 1.6.8, RATCHET_PLAY): the note path of plain notes on the
STOCK image of the firmware version, without any Playground code.

The fixture objects of test_ratchet_play are built as usual; then the complete
stock application is written over the patched one (hooks, adapters and caves
are gone), the translation cache is dropped and the native renderer is called
directly (the target of the stock BL at 080601E8). A code hook proves that no
instruction outside the stock image runs. The same scenarios are then played on
the patched image through the installed wrapper. Output: JSON on stdout.

Run with the environment of tools/validate_p30.py (PYTHONPATH, BENTO_FX_CANDIDATE,
BENTO_STOCK_IMAGE); in the 1.6.8 tree the addresses below are the translated ones.
Nothing here is a test and nothing here is hardware evidence."""
import os,sys,struct,json,hashlib,gc
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from unicorn import UC_HOOK_CODE
from test_euclidean import note
BASE=0x08040000
STOCK=Path(os.environ['BENTO_STOCK_IMAGE']).read_bytes()
def bl_target(image,site):
 ins=next(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(image[site-BASE:site-BASE+4],site));assert ins.mnemonic=='bl',ins.mnemonic
 return int(ins.op_str.lstrip('#'),16)
NATIVE_RENDER=bl_target(STOCK,0x080601e8)
def run(T,stock,size,until,notes):
 # T: the test_ratchet_play module (passed in, so the suite can call this without a second import of itself)
 p=T.Play();outside=[]
 if stock:
  p.u.mem_write(BASE,STOCK);p.u.ctl_remove_cache(BASE,BASE+len(T.IMAGE)+0x1000)
  # Everything behind the stock image, and every stock-zero cave, is not stock code.
  end=BASE+len(STOCK)
  def watch(u,a,n,d):
   if a>=end and a<0x08200000 and a!=p.stop:outside.append(a)
  p.u.hook_add(UC_HOOK_CODE,watch,begin=end,end=0x08200000)
 p.notes=notes;p.sync_notes(notes)
 for at in range(0,until,size):
  n=min(size,until-at);p.block=at;p.w(p.clock,at);p.w(p.clock+4,0)
  p.call(NATIVE_RENDER if stock else T.WRAP,p.audioseq,p.clock,0,n,p.router)
  p.release(n)
 rows=[(pk[0],struct.unpack_from('<I',pk,4)[0],p.absolute[i][1],p.absolute[i][0],struct.unpack_from('<I',pk,16)[0]) for i,pk in enumerate(p.emitted)]
 digest=hashlib.sha256(b''.join(p.emitted)+struct.pack('<%dI'%len(p.absolute),*[a for _,a in p.absolute])).hexdigest()
 return dict(rows=rows,digest=digest,outside=outside,left=p.r(p.audioseq+0x238))
SCENARIOS={
 # the golden scenario of test_no_ratchet_word_plays_byte_identically_to_r6_12 without lock words
 'sixteen_steps_block_1024':(1024,6000*17,lambda:[note(s,vel=60+s,lock=0,ident=10+s) for s in range(16)]),
 # one note on step 1: its end (12000) is a block start with 1000-frame blocks
 'one_step_block_1000':(1000,6000*4,lambda:[note(1,vel=90,lock=0,ident=11)]),
 # the same note with 1024-frame blocks: its end falls inside a block
 'one_step_block_1024':(1024,6000*4,lambda:[note(1,vel=90,lock=0,ident=11)]),
 'one_step_block_64':(64,6000*4,lambda:[note(1,vel=90,lock=0,ident=11)]),
}
if __name__=='__main__':
 import test_ratchet_play as T
 gc.disable();out={'stock_sha256':hashlib.sha256(STOCK).hexdigest(),'image_sha256':hashlib.sha256(T.IMAGE).hexdigest(),'native_renderer':'%08X'%NATIVE_RENDER,'scenarios':{}}
 for name,(size,until,make) in SCENARIOS.items():
  s=run(T,True,size,until,make());q=run(T,False,size,until,make())
  offs=[r for r in s['rows'] if r[0]==0x13]
  out['scenarios'][name]=dict(block=size,stock_digest=s['digest'],patched_digest=q['digest'],patched_equals_stock=s['rows']==q['rows'],
   stock_ran_outside_stock=len(s['outside']),stock_notes_left=s['left'],packets=len(s['rows']),
   note_offs=[dict(offset_field=r[1],absolute_frame=r[2],key=r[3]) for r in offs],
   differing=[dict(index=i,stock=a,patched=b) for i,(a,b) in enumerate(zip(s['rows'],q['rows'])) if a!=b])
 json.dump(out,sys.stdout,indent=1)
