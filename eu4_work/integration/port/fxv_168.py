"""P168 exp8 FX button views (FX views worker), 1.6.8 native addresses (this directory is not translated by make_tree).

The native FX Settings page view (model page 0B, ctor 08149014, vtable 081A0A20) gets five vtable slots of ours; the
code is port/fxv_ui.c. Every slot is hash-guarded against its stock word and restored by the build's reversal check.
 slot 0  tick   08149427 -> fxv_tick   (native tick first; pending section, row layout, repaint request)
 slot 1  paint  08171C4D -> fxv_paint  (native children first; our part of the Mod FX view)
 slot 6  up     081456A1 -> fxv_up     (default no-op; effect list and track toggles)
 slot 7  accept 081456A3 -> fxv_accept (default 'no touches'; the view takes touches outside its children)
 slot 13 event  08149391 -> fxv_arrows (Left/Right in the Mod FX view; everything else native)
"""
FX_VT=0x081a0a20
SLOTS=((0,0x08149427,'fxv_tick'),(1,0x08171c4d,'fxv_paint'),(6,0x081456a1,'fxv_up'),(7,0x081456a3,'fxv_accept'),(13,0x08149391,'fxv_arrows'))
EXPORTS=['fxv_tick','fxv_paint','fxv_up','fxv_accept','fxv_arrows','fxv_toolbar','fxv_go']
def m4(base,BASE,asm,put,uu):
 import struct
 for slot,old,fn in SLOTS:
  a=FX_VT+4*slot
  assert struct.unpack_from('<I',base,a-BASE)[0]==old,hex(a)
  put(a,struct.pack('<I',uu[fn]|1),'P168 exp8 FX views: FX Settings view slot %d -> %s'%(slot,fn))

# Native 1.6.8 addresses the test (test_fxviews.py) drives. This directory is not translated by make_tree, so these
# stay exact 1.6.8 addresses (the test file in integration/ would otherwise be address-translated like the sources).
VIEW_CTOR=0x08149014;VIEW_SETUP=0x081490f4;SET_SECTION=0x08172de6
UI_GET=0x08134a70;TRACK_HANDLE=0x08134dbc;MODEL_POST=0x08141ea4;TRACK_COLOUR=0x08142a04;REGISTRY_BUILD=0x08165848
FX_PAGE_NAV=0x08143d44;SLOT_COMMIT=0x08171d94
# run 16: track name getter (key 82), native cell encoder turn (cell, delta; 160 per value step), native fill, native children paint, root tab widgets (+CE divider flag)
NAME_GET=0x08134d6a;CELL_TURN=0x08173fa4;FILL=0x08168d62;CHILD_PAINT=0x08171c4c;ROOT_TAB_FLAGS=0x300366e8+0xa44+0xce
