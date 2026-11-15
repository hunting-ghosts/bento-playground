"""Exercise the hardware finger dispatcher, not direct macro touch callbacks."""
import struct
import unittest
from unicorn import UC_HOOK_CODE

from test_macro import Macros, BAR, APP, V, UU, slot
from test_mod import FILT1

MANAGER = 0x20035000
REPORT = 0x20036000


class NativeTouchTests(unittest.TestCase):
 def fixture(self):
  p=Macros()
  p.u.mem_write(MANAGER,bytes(0x500))
  p.u.mem_write(MANAGER+0x470,bytes(p.u.mem_read(APP,0x60)))
  p.call(0x0816fb64,MANAGER+0x470,V)
  p.w(0x3000004c,p.next)
  p.tick()
  return p

 def finger(self,p,x,y,down):
  report=bytearray(16)
  if down:
   struct.pack_into('<h',report,0,1)
   struct.pack_into('<hhB',report,4,x,y,1)
  p.u.mem_write(REPORT,bytes(report))
  p.call(0x0816332c,MANAGER,REPORT)

 def double(self,p,x,y=440):
  self.finger(p,x,y,True);self.finger(p,x,y,False);p.later(150)
  self.finger(p,x,y,True);self.finger(p,x,y,False);p.settle_tap()

 # W14 HW4 (owner, 29 Oct): one tap selects and toggles map mode; a double tap
 # clears that macro's mappings and disarms.
 def test_native_dispatcher_single_tap_arms_and_disarms_double_tap_clears(self):
  p=self.fixture();p.perform()
  x=p.r(slot(2)+4)+20
  self.finger(p,x,440,True);self.finger(p,x,440,False);p.settle_tap()
  self.assertEqual((p.focus,p.armed()),(2,3))
  self.finger(p,x,440,True);self.finger(p,x,440,False);p.settle_tap()
  self.assertEqual((p.focus,p.armed()),(2,0))
  self.finger(p,30,440,True);self.finger(p,30,440,False);p.settle_tap()
  self.assertEqual((p.focus,p.armed()),(0,1))
  self.double(p,30);self.assertEqual(p.armed(),0)

 def test_macro_detail_navigation_and_proj_disarm_through_native_dispatch(self):
  p=self.fixture();p.view=None # the real Perform state decides the page
  p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(),begin=0x081420ec,end=0x081420ec)
  p.call(UU['perf_dispatch'],0x30024b00,0xaf,7)
  p.u.mem_write(REPORT,struct.pack('<5I',0x1072,0,0,0,0))
  self.assertEqual(p.call(UU['perf_event'],V,REPORT),1)
  p.call(UU['macro_periodic'],0)
  self.assertEqual((p.call(UU['perf_macro_view']),p.call(UU['perf_macro_targets'])),(1,0))
  self.assertEqual(p.name(0),'MACRO 1')
  p.call(UU['perf_dispatch'],0x30024b00,0xaf,8) # Down selects Controls
  p.call(UU['macro_periodic'],0)
  self.assertEqual((p.call(UU['perf_macro_view']),p.call(UU['perf_macro_targets'])),(1,1))
  p.call(UU['macro_select'],1)
  self.assertEqual((p.call(UU['perf_macro_focus'],0xffffffff),p.armed()),(1,0))
  p.call(UU['perf_dispatch'],0x30024b00,0xaf,7) # PROJ: back to Perform, mapping ends
  self.assertEqual(p.armed(),0)

 def test_redirected_touch_has_a_native_identity_for_move_and_release(self):
  p=self.fixture();p.perform()
  hidden=0x20031c80
  p.u.mem_write(hidden,bytes(0x40));p.u.mem_write(hidden+0x30,b'\x01')
  p.w(MANAGER+0x470+0x3c,hidden)
  self.finger(p,600,440,True)
  self.assertEqual(p.r(MANAGER+0x420),p.r(BAR+0x28))
  self.finger(p,400,440,True)
  self.finger(p,400,440,False)
  self.assertTrue(p.overlay()) # a drag is neither a tap nor (any more) a swipe
  self.assertEqual((p.focus,p.armed()),(0,0))

 def test_redirected_tap_arms_and_disarms(self):
  p=self.fixture();p.perform()
  hidden=0x20031c80
  p.u.mem_write(hidden,bytes(0x40));p.u.mem_write(hidden+0x30,b'\x01')
  p.w(MANAGER+0x470+0x3c,hidden)
  self.finger(p,30,440,True);self.finger(p,30,440,False);p.settle_tap()
  self.assertEqual(p.armed(),1)
  self.assertTrue(p.overlay())
  self.finger(p,30,440,True);self.finger(p,30,440,False);p.settle_tap()
  self.assertEqual(p.armed(),0)

 def test_redirect_does_not_claim_unrelated_page_area(self):
  p=self.fixture()
  hidden=0x20031c80
  p.u.mem_write(hidden,bytes(0x40));p.u.mem_write(hidden+0x30,b'\x01')
  p.w(MANAGER+0x470+0x3c,hidden)
  self.finger(p,600,200,True);self.finger(p,600,200,False)
  self.assertFalse(p.overlay())
  self.assertEqual(p.armed(),0)

 def test_native_tap_maps_later_single_tap_keeps_and_double_tap_removes(self):
  p=self.fixture();p.perform();p.arm(0);p.leave()
  p.w(slot(1)+0x34,FILT1)
  x=p.r(slot(1)+4)+20
  self.finger(p,x,440,True);self.finger(p,x,440,False)
  self.assertEqual(p.readout(),'+ Resonance')
  p.later(3000)
  self.assertEqual(p.readout(),'MAP M1 1/3')
  self.finger(p,x,440,True);self.finger(p,x,440,False)
  self.assertEqual(p.readout(),'= Resonance')
  p.later(150)
  self.finger(p,x,440,True);self.finger(p,x,440,False)
  self.assertEqual(p.readout(),'- Resonance')


if __name__=='__main__':unittest.main(verbosity=2)
