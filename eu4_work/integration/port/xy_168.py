"""P168 exp8: XY per-track send, 1.6.8 native addresses (this directory is not translated by make_tree).

Native audio graph (static analysis of stock 1.6.8, RUN11 item 3 and RUN13): per block the mixer process 080A13C0
calls the per-track function 080A10E0 for every strip (r10 = track index, r5 = strip, output bus id strip+0xA,
0xF = master); it adds the track's buffer into its output bus with 08052760(dst, src) at 080A1166. The summer
0808F000 adds the delay return (bus 0x11, 0808F024), the reverb return (bus 0x15, 0808F034) and bus 0x13 into the
master; then the LiveA and LiveB wrappers process the master in place; then the master compressor 08071C60.
Buses: ctx+0x5AC+id*20 (0809FCC0): +0 capacity, +4 frames (0 = capacity), +8 L, +C R, +10 silent, +11 stereo.

Hooks (M7, in the stock-zero bank-1 run 080DB8B0..080DB9F0 that held the .bank1h M4 pad until run 13):
 A 080A1166: a deselected track (mask bit, index < 8, output = master) adds into the private bypass bus instead.
 C 0808F024 / 0808F034: with "Returns thru XY" Off the summer skips the delay / reverb return (flag bit 0 / 1).
 B 08071C60 (compressor entry, after LiveB): add the bypass bus into the master and clear it; add the skipped
   returns; invalidate the XY control line (M4-written) for the next block; then the two replaced instructions.
State word 240416AC (tag 'XY'), bypass block 240416B0 (M4 allocates, 32-byte aligned, zeroed); the M4 writes the
block header before it publishes the block (bus header, magic 'XXXX' at +14, self pointer at +18); the M7 keeps the
skipped returns at +1C. Untagged word, no block or
an uninitialised block = every hook passes straight through (stock). The M7 startup zeroes the three XY words.
"""
XY_CAVE=(0x080db8b0,0x080db9f0)
SITE_TRACK_ADD=0x080a1166;SITE_DELAY=0x0808f024;SITE_REVERB=0x0808f034;SITE_COMP=0x08071c60;COMP_LIT=0x08071ef0
BUS=0x0809fcc0;ADD=0x08052760;CLEAR=0x08052ca0
# test fixtures (native, unhooked): per-track mixer function, summer, its default bus-id getter literal, XY view
PER_TRACK=0x080a10e0;SUMMER=0x0808f000;SUMMER_GETTER_LIT=0x0808f068;STARTUP_SITE=0x080404b6;STARTUP_NEXT=0x080d0800
XY_VIEW_CTOR=0x081496a8;XY_VIEW_UPDATE=0x0814979c;REGISTRY_BUILD=0x08165848;SLOT_TURN=0x08173fa4
XY_VIEW_VT=0x081a0aa8;XY_RECEIVE_NATIVE=0x08149508;XY_BAR_SITE=0x08149832;XY_BAR_NATIVE=0x081724f4
WORD=0x240416ac;LINE=0x240416a0
BOOT=('ldr r0,=0x240416ac; movs r1,#0; str r1,[r0]; str r1,[r0,#4]; str r1,[r0,#8]; dsb; '
      'ldr r2,=0xe000ed14; ldr r2,[r2]; tst.w r2,#0x10000; beq xyboot; ldr r2,=0xe000ef70; ldr r3,=0x240416a0; str r3,[r2]; dsb; isb; xyboot: ')
def m7(base,BASE,asm,put,image):
 import struct
 lo,hi=XY_CAVE
 assert base[lo-16-BASE:hi-BASE]==bytes(hi-lo+16) and bytes(image[lo-16-BASE:hi-BASE])==bytes(hi-lo+16),'XY M7 cave must be stock zero and unwritten'
 for a in (SITE_TRACK_ADD,SITE_DELAY,SITE_REVERB):assert base[a-BASE:a-BASE+4]==asm('bl %#x'%ADD,a),hex(a)
 assert base[SITE_COMP-BASE:SITE_COMP-BASE+4]==asm('ldr r3,[r0]; ldr r2,[pc,#0x28c]',SITE_COMP)
 lit=struct.unpack_from('<I',base,COMP_LIT-BASE)[0]
 code=bytearray();at={}
 def piece(name,s):
  while len(code)%4:code.append(0)
  at[name]=lo+len(code);code.extend(asm(s,at[name]))
 # xyv: r3 = block (tag 'XY', range C0000000..C7FFFFFF, 32-byte alignment, header written by the M4: self pointer
 # at +18, magic 'XXXX' at +14) or 0; r2 = state word. Uses r2, r3, r12 only.
 piece('xyv','ldr r12,=0x240416ac; ldr r2,[r12]; ldr r3,[r12,#4]; movw r12,#0x5859; cmp.w r12,r2,lsr #16; bne bad; '
  'lsrs r12,r3,#27; cmp.w r12,#0x18; bne bad; ands r12,r3,#0x1f; bne bad; ldr r12,[r3,#0x18]; cmp r12,r3; bne bad; '
  'ldr r12,[r3,#0x14]; cmp.w r12,#0x58585858; bne bad; bx lr; bad: movs r3,#0; bx lr')
 v=at['xyv']
 piece('A','push {r0,lr}; bl %#x; cbz r3,nat; cmp r10,#8; bhs nat; lsr.w r2,r2,r10; tst.w r2,#1; beq nat; '
  'ldrh r2,[r5,#0xa]; cmp r2,#0xf; bne nat; str r3,[sp]; nat: pop {r0,lr}; b.w %#x'%(v,ADD))
 head='push {r0,r1,r4,lr}; movs r4,#1; b go; '
 piece('C1',head+'push {r0,r1,r4,lr}; movs r4,#2; go: bl %#x; cbz r3,cnat; tst.w r2,#0x100; beq cnat; ldr r2,[r3,#0x1c]; orrs r2,r4; '
  'str r2,[r3,#0x1c]; pop {r0,r1,r4,pc}; cnat: pop {r0,r1,r4,lr}; b.w %#x'%(v,ADD))
 at['C2']=at['C1']+6 # push (2) + movs (2) + b go (2)
 assert code[at['C2']-lo:at['C2']-lo+2]==asm('push {r0,r1,r4,lr}',at['C2']) and code[at['C1']-lo+4:at['C1']-lo+6]!=b'\0\0'
 piece('B','push {r0,r1,r4,r5,r6,r7,r8,lr}; mov r5,r1; bl %#x; movs r6,r3; beq done; '
  'mov r0,r5; movs r1,#0xf; bl %#x; mov r4,r0; ldrb r3,[r6,#0x10]; cbnz r3,rets; mov r1,r6; mov r0,r4; bl %#x; mov r0,r6; bl %#x; '
  'rets: ldr r7,[r6,#0x1c]; cbz r7,done; movs r2,#0; str r2,[r6,#0x1c]; lsls r3,r7,#31; bpl rev; mov r0,r5; movs r1,#0x11; bl %#x; mov r1,r0; mov r0,r4; bl %#x; '
  'rev: lsls r3,r7,#30; bpl done; mov r0,r5; movs r1,#0x15; bl %#x; mov r1,r0; mov r0,r4; bl %#x; '
  'done: ldr r0,=0xe000ed14; ldr r0,[r0]; tst.w r0,#0x10000; beq out; dsb; ldr r0,=0xe000ef5c; ldr r1,=0x240416a0; str r1,[r0]; dsb; isb; '
  'out: pop {r0,r1,r4,r5,r6,r7,r8,lr}; ldr r3,[r0]; ldr r2,=%#x; b.w %#x'%(v,BUS,ADD,CLEAR,BUS,ADD,BUS,ADD,lit,SITE_COMP+4))
 assert lo+len(code)<=hi,('XY M7 code overflows its cave',len(code))
 put(lo,bytes(code),'P168 exp8 XY per-track send (M7) in checked zero run %08X..%08X'%(lo,hi))
 put(SITE_TRACK_ADD,asm('bl %#x'%at['A'],SITE_TRACK_ADD),'P168 exp8 XY: a deselected track adds into the bypass bus (per-track add 080A1166)')
 put(SITE_DELAY,asm('bl %#x'%at['C1'],SITE_DELAY),'P168 exp8 XY: Returns thru XY Off skips the delay return in the summer')
 put(SITE_REVERB,asm('bl %#x'%at['C2'],SITE_REVERB),'P168 exp8 XY: Returns thru XY Off skips the reverb return in the summer')
 put(SITE_COMP,asm('b.w %#x'%at['B'],SITE_COMP),'P168 exp8 XY: bypass bus and skipped returns into the master after LiveB, before the compressor')
 return at,len(code)
def m4(base,BASE,asm,put,uu):
 import struct
 slot=XY_VIEW_VT+12*4
 assert struct.unpack_from('<I',base,slot-BASE)[0]==XY_RECEIVE_NATIVE|1
 put(slot,struct.pack('<I',uu['xy_receive']|1),'P168 exp8 XY page: Returns thru XY encoder events (view receive)')
 assert base[XY_BAR_SITE-BASE:XY_BAR_SITE-BASE+4]==asm('bl %#x'%XY_BAR_NATIVE,XY_BAR_SITE)
 put(XY_BAR_SITE,asm('bl %#x'%uu['xy_bar'],XY_BAR_SITE),'P168 exp8 XY page: encoder 4 = Returns thru XY (bar update)')
