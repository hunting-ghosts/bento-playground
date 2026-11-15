"""Fixture twin of native_ids.h (1.6.8 port): native keys, ids and struct offsets
per firmware version, for emulator fixtures that build native RAM state or read
native fields. Evidence for every value is in native_ids.h; keep the two in step.

The translated 1.6.8 tree rewrites the BENTO_FW line below (overrides `strings`);
in the repository it is 161, so the 1.6.1 suites see the values they always used.
"""
BENTO_FW=161 # fixtures: firmware version of this tree
FW168=BENTO_FW==168
# Owner decision 13 Nov 2026 (exp8): the chord progression editor (piano-roll chord mode / melodic SEQ "Chord" view)
# is switched off in 1.6.8 builds by a build switch (build_fx.py passes -DBENTO_NO_CHORD_EDITOR=1; source kept).
# BENTO_CHORD_EDITOR=1 in the environment builds it back in. Fixtures read this to assert the switched-off state.
import os as _os
CHORD_EDITOR=not FW168 or _os.environ.get('BENTO_CHORD_EDITOR')=='1'
def NKEY(k):
 """Native registry key (and private Playground key) in this firmware's numbering."""
 if not FW168:return k
 return k if k<0x139 else 0x139 if k<0x13c else k-2 if k<0x1d9 else k-1
def NUI(i):
 """Native menu/action id. Event/header ids 0x101..0x122 moved by one in 1.6.8 (38 page templates, model event dispatcher)."""
 if not FW168:return i
 if 0x101<=i<=0x122:return i+1   # from 0x101: model event dispatcher jump tables (native_ids.h NHID)
 return i if i<0x1013 else i+2 if i<0x103c else i+3 if i<0x1048 else i
def _v(v161,v168):return v168 if FW168 else v161
MODEL_PADS=_v(0x19c4,0x19d0)       # MODEL pad lights
MODEL_CHANGED=_v(0x36c4,0x3ff4)    # MODEL changed flag
MODEL_PADMODE=_v(0x3c7c,0x45cc)
MODEL_UNDO=_v(0xb26c,0xc3c0)
MODEL_PATCH_STASH=_v(0xb2e0,0xc434) # fixtures only: the track the patch browser moves aside (native 081363F0 / 1.6.8 08137900, read back by 0813DB94 / 0813F440); no firmware use
_MODEL_SEGMENTS=((0,0x160,0),(0x19c4,0x19c8,0xc),(0x36c4,0x36c8,0x930),(0x3a00,0x3bc4,0x938),(0x3bc4,0x3c84,0x950),(0x9ca0,0x9cc4,0x950),(0xaf64,0xb280,0x1154))
def MODEL(o):
 """MODEL field offset. Only ranges with native evidence are known (header builder 08134800/08135D74, Undo
 entry, base_offsets.py): +0..15F same, pad lights +C, changed flag +930, the header record copy +3A00.. +938,
 message slots/pad mode +3BC4.. +950, +9CA0.. +950, +AF64..B27F +1154. Anything else raises: find the evidence first."""
 if not FW168:return o
 for lo,hi,d in _MODEL_SEGMENTS:
  if lo<=o<hi:return o+d
 raise KeyError('MODEL+%#x has no 1.6.8 evidence'%o)
MODEL_REC_STATE=_v(0x9ca0,0xa5f0)   # MODEL recording state byte (1 = a take is being recorded): native check 081361B4 / 081376C4
MODEL_REC_OWNER=MODEL_REC_STATE+4  # owner (track handle) of the running take, same check
MODEL_REC_NOTES=_v(None,0xa5f8)    # 1.6.8 only: pointer to the note list saved when the take started (native take discard 08138548)
MODEL_REC_SEQ=_v(None,0xa5fc)      # 1.6.8 only: sequence the take records into (081379A4, 08138548)
ROOT_LAYOUT=_v(0x117c,0x1194)      # root header layout flag
ROOT_SLOTS=_v(0x54c,0x564)         # six action widgets (0xD0 each)
ROOT_TABS=_v(0xa2c,0xa44)          # six tab widgets
HDR_SIZE=_v(0x1c4,0x1dc)           # header record / page template size
def HDR(o):return o+0x18 if FW168 and o>=0x68 else o     # header record field
def ROOT(o):return o+0x18 if FW168 and o>=0x9c else o    # root header field
SYNTH_KNOB2=_v(0x36c8,0x3830)
SYNTH_VALUES=_v(0x10154,0x11ca4)
SYNTH_TILE=_v(0x10238,0x11d88)     # synth view: selected tile per track
def SYNTH(o):
 """Synth view field (constructed view of both versions compared, tools/port/view_layout.py)."""
 if not FW168:return o
 return o if o<0x3618 else o+0x168 if o<0x3790 else o+0x2d0 if o<0x8840 else o+0xf10 if o<0xd714 else o+0x1b50
def WAVE(o):
 """Wave pane widget field (the two panes of the synth view): 1.6.8 inserted 0x168 bytes before +90
 (native paint 08182314/08184550, WAV binding 08182770/08184996: +134 -> +29C, +174 -> +2DC)."""
 return o+0x168 if FW168 and o>=0x90 else o
def PADMOD(o):
 """M7 pad module field (native press 08084760 / release 08083FE0): 1.6.8 inserted a per-pad pitch table at +34
 (16 words; the release posts the pitch stored at the press), so the fields the fixtures set moved by +0x40
 (+84 -> +C4, +C4 -> +104, +2C8 -> +308, +2CC -> +30C, +2EC -> +32C, +424 -> +464, +474 -> +4B4, +490 -> +4D0)."""
 return o+0x40 if FW168 and o>=0x34 else o
AUDIO_RECORD_FLAG=_v(0x8ea5,0x8ea4) # M7 engine object: byte the native record entry sets (080584E0 in 1.6.8)
SDRAM_TOP=0xc0000000+_v(0x200000,0x400000) # first address above the fixture SDRAM map (objects a fixture maps itself go above it)
SDRAM_MAP=_v(0x200000,0x400000)    # fixture SDRAM map at C0000000 (bump heap from C0100000): the 1.6.8 synth view constructor allocates 0x1A8000+ (1.6.1: 0xB7240)
def MACRO_VER(v):
 """First byte (hex) of the saved Performance macro string where 1.6.1 writes version v (2 or 3): 1.6.8 always writes format 4."""
 return '04' if FW168 else '%02X'%v
def macro_saved(s):
 """The macro string this firmware saves for the state that 1.6.1 saves as s (format 2 or 3):
 1.6.8 writes format 4 = format 3 layout (a sensitivity byte per macro, 02 = Normal) with keys in 1.6.8 numbering."""
 if not FW168 or s is None:return s
 ver=int(s[:2],16);assert ver in (2,3),ver
 out=['04'];i=2
 for m in range(8):
  count=int(s[i+2:i+4],16);out.append(s[i:i+4]);i+=4
  if ver==3:out.append(s[i:i+2]);i+=2
  else:out.append('02')
  out.append(s[i:i+24]);i+=24
  for t in range(count):
   key=NKEY(int(s[i+6:i+8],16)|int(s[i+8:i+10],16)<<8)
   out.append(s[i:i+6]+'%02X%02X'%(key&255,key>>8)+s[i+10:i+42+24]);i+=42+24
 assert i==len(s),(i,len(s))
 return ''.join(out)
def consumer_context(sp,record,before,model):
 """Native UI event loop state at the consumer hook, for fixtures that enter there. 1.6.1 keeps the
 event in r5..r7 (code, word 2, word 3) with the 24-byte record at sp+0x220; 1.6.8 keeps a pointer
 to the record (sp+0x218) in r6 and reads the fields from it (hooks_168.py 'consumer'). Fills the
 expected-register list `before` in place and returns the address to write the record to."""
 before[4]=model
 if FW168:before[6]=sp+0x218;return sp+0x218
 before[5:8]=[record[0],record[2],record[3]];return sp+0x220

def native_string(text):
 """What the native string getter (1.6.1 0813390E / 1.6.8 08134D6A -> body 0812ED98) writes for `text`: ALWAYS 256
 bytes (strncpy(out,text,0xFF) pads with zeros, then out[0xFF]=0). Run 19: every fixture stand-in for the getter
 writes this, so a caller with a shorter buffer destroys its own stack in the fixture as on the device (exp8
 crashes A/B: three 64-byte buffers that the short stand-ins never touched)."""
 b=bytes(text).split(b'\0')[0][:255];return b+bytes(256-len(b))
