"""Native evidence for struct offsets our code uses on native objects (1.6.8 port audit).

  python3 tools/port/offset_evidence.py            (exit 1 on any mismatch)

Every row names a field, where our sources use it, and one native instruction of stock 1.6.1 and its
counterpart in stock 1.6.8 that address the same field. The tool disassembles both stock images and
checks that both instructions are exactly as written, so a number shared only by a fixture and our
firmware (how SEND_MOTION and ANALOG_UI were green) cannot pass here. A row with a different text for
1.6.8 documents a field that moved (the source must use the NOFF_*/N.* name given).
Read-only; needs the stock images (BENTO_STOCK_OLD / BENTO_STOCK_NEW). Proves where a field is, not behaviour.
"""
import os,sys,capstone
BASE=0x08040000
# (field, used by, 1.6.1 address, 1.6.1 instruction, 1.6.8 address, 1.6.8 instruction or None = same text)
ROWS=[
 # --- UI model, 1.6.8 only: the two clip rows the pads launch (playground_ui.c launch_pad_row; 1.6.1 address None)
 ('MODEL+2540 top pad row (base +2000)','playground_ui.c launch_pad_row',None,None,0x08136afe,'add.w r3, r6, #0x2000'),
 ('MODEL+2540 top pad row','playground_ui.c launch_pad_row',None,None,0x08136b02,'ldr.w r1, [r3, #0x540]'),
 ('MODEL+2540: the row below goes to pads 9-16','playground_ui.c launch_pad_row',None,None,0x08136b0e,'adds r4, #8'),
 # --- M7: generic instrument root / mixer (motion_send_audio.h, melodic_send_audio.cpp)
 ('root+284 bus index','motion_send_audio.h motion_send_route/begin',0x0807a4ac,'ldr.w r1, [r4, #0x284]',0x0807ac6c,None),
 ('root+C handle','motion_send_audio.h',0x0807a4ea,'ldr r1, [r4, #0xc]',0x0807acaa,None),
 ('router+5AC+bus*20 input (index*5)','motion_send_begin',0x0809f0c0,'add.w r1, r1, r1, lsl #2',0x0809fcc0,None),
 ('router+5AC+bus*20 input (*4)','motion_send_begin',0x0809f0c4,'add.w r0, r0, r1, lsl #2',0x0809fcc4,None),
 ('router+5AC+bus*20 input (base)','motion_send_begin',0x0809f0c8,'addw r0, r0, #0x5ac',0x0809fcc8,None),
 ('strip+50 first send control','motion_send_mix',0x080a052e,'add.w r0, r5, #0x50',0x080a114e,None),
 ('strip+80 second send control','motion_send_mix (j=1)',0x080a053a,'add.w r0, r5, #0x80',0x080a115a,None),
 ('strip+98 duck state','melodic_send_audio.cpp mel_send_duck',0x080a0522,'add.w r0, r5, #0x98',0x080a1142,None),
 ('route record +16 amount','motion_send_route',0x0807c128,'ldrsh.w r3, [r1, #0x16]',0x0807c8a8,None),
 ('route record +14 source','motion_send_route',0x0807c12e,'ldrh r7, [r1, #0x14]',0x0807c8ae,None),
 ('route record +2','motion_send_route',0x0807c136,'ldrh.w ip, [r1, #2]',0x0807c8b6,None),
 ('route record +C key','motion_send_route',0x0807c152,'ldrh r6, [r1, #0xc]',0x0807c8d2,None),
 ('route record +10 slot','motion_send_route',0x0807c158,'ldrh.w sl, [r1, #0x10]',0x0807c8d8,None),
 ('root+F8+8*source source values (source 9 = +140)','motion_source(root,source,0x140)',0x0807c47e,'add.w r1, r4, r3, lsl #3',0x0807cbfe,None),
 ('root+F8+8*source source values (base)','motion_source',0x0807c484,'adds r1, #0xf8',0x0807cc04,None),
 # --- M7: sampler root (motion_pad_begin/end, drums/kick.cpp)
 ('sampler root+650+8n Auto A-D values','motion_pad_begin, kick.cpp',0x08092920,'add.w r1, r3, r6, lsl #3',0x08093420,None),
 ('sampler root+650+8n (base)','motion_pad_begin',0x08092924,'add.w r1, r1, #0x650',0x08093424,None),
 ('sampler root+5FC route count','motion_pad_begin',0x0808f25e,'ldr.w r2, [r4, #0x5fc]',0x0808fd5e,None),
 ('sampler root+590 route list','motion_pad_begin, kick_route',0x0808f26a,'add.w r3, r4, #0x590',0x0808fd6a,None),
 ('sampler root+608 send gain A','motion_pad_begin/end',0x0808f11a,'add.w sl, r4, #0x608',0x0808fc1a,None),
 ('sampler root+60C send gain B','motion_pad_begin/end',0x0808f116,'addw r2, r4, #0x60c',0x0808fc16,None),
 ('sampler root+624 sends active','motion_pad_begin/end',0x0808fc60,'ldrb.w r3, [r4, #0x624]',0x08090760,None),
 # --- M7: sequence player (live_audio.cpp, ratchet_audio.cpp, drums/conditions.c)
 ('sequence+8000+6C4 (same object as +86C0 current clip)','live_audio.cpp rowof, ratchet_audio.cpp',0x08060208,'ldr.w r3, [sl, #0x6c4]',0x080605a8,None),
 # --- M7: pad module (moved; fixtures use N.PADMOD, firmware reads only the posted record)
 ('pad module +2C8 selected slot (moved +40)','fixtures N.PADMOD',0x0808491c,'ldr.w r3, [r5, #0x2c8]',0x08085382,'ldr.w r3, [r5, #0x308]'),
 ('pad post record: pitch = rec[3], velocity = rec[4]','live_audio.cpp chord_press, seqfx tr_press',0x08084914,'strd r2, r3, [sp, #0x1c]',0x08085368,'str r2, [sp, #0x1c]'),
 # --- UI: wave pane widget (moved +168 from +90; kick_ui.c NOFF_WAVE)
 ('wave pane +134 label hidden flag','kick_ui.c analog_wave_tick NOFF_WAVE(0x104)+0x30',0x08182784,'ldrb.w r3, [r4, #0x134]',0x081849aa,'ldrb.w r3, [r4, #0x29c]'),
 ('wave pane +175 background colour','kick_ui.c wave_draw NOFF_WAVE(0x175)',0x081823ac,'ldrb.w r1, [r5, #0x175]',0x081845d6,'ldrb.w r1, [r8, #0x2dd]'),
 ('wave pane +174 line colour','kick_ui.c analog_wave_tick NOFF_WAVE(0x174)',0x081823e4,'ldrb.w r2, [r5, #0x174]',0x08184608,'ldrb.w r2, [r8, #0x2dc]'),
 ('wave pane +34 bound handle (not moved)','kick_ui.c',0x08182778,'ldr r3, [r0, #0x34]',0x0818499e,None),
 # --- UI: piano view high fields (not moved; lanes_ui.c, melodic_*.c, bars_ui.c, seq_nav_ui.c)
 ('piano view +124000+1000+DAC mode byte (= +125DAC)','melodic_lock_ui.c, seq_nav_ui.c, workflow_ui.c',0x08159a9e,'ldrb.w r3, [r3, #0xdac]',0x0815b812,None),
 ('piano view +125DAC base','same',0x08159a96,'add.w r3, r4, #0x124000',0x0815b80a,None),
 # --- UI: MODEL recording state (moved; fixtures N.MODEL_REC_*)
 ('MODEL+9CA0 recording state (moved)','test_manual_cycle.py N.MODEL_REC_STATE',0x081361bc,'ldrb.w r3, [r3, #0xca0]',0x081376cc,'ldrb.w r3, [r3, #0x5f0]'),
 ('MODEL+9CA4 recording owner (moved)','N.MODEL_REC_OWNER',0x081361dc,'ldr.w r0, [r0, #0xca4]',0x081376ec,'ldr.w r0, [r0, #0x5f4]'),
]
def main():
 imgs=[open(os.environ.get(k,d),'rb').read() for k,d in (('BENTO_STOCK_OLD','/home/claude/stock/bento1.bin'),('BENTO_STOCK_NEW','/home/claude/fw168/bento1.bin'))]
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB)
 def at(img,a):
  i=next(cs.disasm(img[a-BASE:a-BASE+4],a),None);return (i.mnemonic+' '+i.op_str).strip() if i else '?'
 bad=0
 for field,used,a,ta,b,tb in ROWS:
  ga,gb=(at(imgs[0],a) if a else '(1.6.8 only)'),at(imgs[1],b);tb=tb or ta;ok=(not a or ga==ta) and gb==tb;bad+=not ok
  print('%-4s %-52s %08x %-26s| %08x %-26s| %s'%('ok' if ok else 'FAIL',field,a or 0,ga,b,gb,used))
 print('%d rows, %d failed'%(len(ROWS),bad));sys.exit(1 if bad else 0)
if __name__=='__main__':main()
