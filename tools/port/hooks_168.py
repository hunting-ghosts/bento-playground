"""Per-version ports of hooks whose 1.6.1 site is in code 1010 changed in 1.6.8.

Each entry gives, for both versions: the site, the exact stock bytes there
(hash guard), how our adapter must obtain its arguments, where it continues
when our code consumes the event and when it declines (displaced
instructions + return). Builders read these instead of raw 1.6.1 literals.
`python3 hooks_168.py STOCK161 STOCK168` checks every guard and decodes every
displaced instruction against both images (fails closed).
"""
HOOKS={
 'consumer':dict(
  why='outer button/event consumer: every Playground button, arrow, LAUNCH/MIXER/INST/SEQ shortcut',
  evidence='both versions copy the same 24-byte event record (lr+idx*24+0x980) and switch on code-0x11 over 0xB4 cases; '
           '1.6.8 keeps the copy at r6 (=sp+0x218, set at 08140DEA before the loop head, reused as the copy buffer on every pass) '
           'and loads fields inside the cases instead of into r5..r8',
  v161=dict(site=0x0813f98c,guard='a5f11103',displaced='sub.w r3,r5,#17',resume=0x0813f990,consumed=0x0813f2fc,
            args='r0=r4; r1=r5; r2=r6; r3=r7; [sp]=record (original sp+0x220)'),
  v168=dict(site=0x08141408,guard='3378113b',displaced='ldrb r3,[r6]; subs r3,#0x11',resume=0x0814140c,consumed=0x08140dee,
            args='r0=r4; r1=ldrb [r6]; r2=ldr [r6,#8]; r3=ldr [r6,#12]; [sp]=r6'),
  status='ported (adapter spec); emulator test against 1.6.8 pending'),
 'undo_restore':dict(
  why='restore per-sound cycle metadata after a successful native note Undo (clone-back path)',
  evidence='1.6.8 Undo apply keeps the clone-back path with the same stack slots: [sp+0xC] parent, [sp+0x10] new clone '
           '(out parameter of clone 08124B76 -> 08124EE2), [sp+0x114] track; the site after the clone has identical bytes. '
           'MODEL undo buffer +B26C -> +C3C0 and armed flag +B271 -> +C3C5 are inside native code only. '
           'NEW in 1.6.8: when 081361B4->081376C4 returns non-zero the function takes 081379A4/08138548 (Undo during '
           'recording, owner keeps it native); that path has no clone-back, so the cycle metadata restore does not run there. '
           'The playback install call 08136928->08137EC0 now gets flag 0 instead of 1 (native change, not our hook).',
  v161=dict(site=0x0813b290,guard='45 9b 73 22'.replace(' ',''),displaced='ldr r3,[sp,#0x114]; movs r2,#0x73',resume=0x0813b294,consumed=None,
            args='r0=[sp+0xC] r1=[sp+0x114] r2=[sp+0x10] (original sp; adapter adds its own push)'),
  v168=dict(site=0x0813ca4e,guard='45 9b 73 22'.replace(' ',''),displaced='ldr r3,[sp,#0x114]; movs r2,#0x73',resume=0x0813ca52,consumed=None,
            args='identical stack slots'),
  status='ported (same adapter, new site); Undo-during-recording path not covered (owner test)'),
}
HOOKS['mod_rows']=dict(why='CH11 synth pad rows in the native Mod Matrix (after the native one-shot rows)',
 evidence='same builder frame (0x354) and slot +0x338, identical matrix view fields +8A000+C44/C4D/C50/CCC/DBC/E04 (1.6.8 also reads +DC5); '
          'r4 = view in both; LR never used as scratch in either builder. 1.6.8 dispatches types 0x0E..0x14 after this point '
          '(more track types), the row type is now in fp.',
 v161=dict(site=0x0814ce80,guard='039e0f2e',displaced='ldr r6,[sp,#0xc]; cmp r6,#0xf',resume=None,consumed=None,args='bl site; r0=r4, r1=original sp'),
 v168=dict(site=0x0814eaea,guard='ddf80cb0',displaced='ldr.w fp,[sp,#0xc]',resume=None,consumed=None,args='bl site; r0=r4, r1=original sp; native cmp.w fp,#0xf follows'),
 status='ported (adapter displaces only the load); owner test: Mod Matrix with drum synth pads')
HOOKS['header_actions']=dict(why='persistent header custom actions (Select/Chord) with visibility sync: entry wrapper with prologue replay',
 evidence='same arguments (r0 obj, r1, r2, r3) and r0 result fed to seq_toolbar; 1.6.8 pushes one register fewer (r4-r9,lr) and its '
          'frame is 0xC; the replay stub must use the 1.6.8 prologue. Inside, MODEL+B19C -> +C2F0 (native only).',
 v161=dict(site=0x08134800,guard='2de9f047',displaced='push.w {r4-r10,lr}',resume=0x08134804,consumed=None,args='entry; replay = displaced + b.w resume'),
 v168=dict(site=0x08135d74,guard='2de9f043',displaced='push.w {r4-r9,lr}',resume=0x08135d78,consumed=None,args='entry; replay = displaced + b.w resume'),
 status='ported (replay stub per version)')
HOOKS['header_apply']=dict(why='P12 custom controls at final native header application (device_header_prepare(record) then native)',
 evidence='entry and prologue bytes identical; the function changed inside: frame 0x44 -> 0xD4 and the header record field it reads '
          'moved +0x6B -> +0x83 (+0x18). device_header_prepare/header_actions.c read header record fields: DATA-LAYOUT REVIEW required.',
 v161=dict(site=0x0817faf8,guard='2de9f04f',displaced='push.w {r4-r11,lr}',resume=0x0817fafc,consumed=None,args='r0 = original r1 (record)'),
 v168=dict(site=0x08181c7c,guard='2de9f04f',displaced='push.w {r4-r11,lr}',resume=0x08181c80,consumed=None,args='same'),
 status='site ported; header record layout (+0x18 shift seen) must be audited before use')
# Release identity (tools/preview_identity.py): the two literal words that point at the
# native version record are repointed to our label. Same structure in 1.6.8.
for key,a161,a168 in [('identity_ptr_a',0x08131054,0x08132014),('identity_ptr_b',0x08162ad8,0x08164958)]:
 HOOKS[key]=dict(why='version label pointer (Settings/About)',
  v161=dict(site=a161,guard='d4ba1808',displaced=None,resume=None,consumed=None,args='literal word -> version record 0818BAD4'),
  v168=dict(site=a168,guard='94dd1808',displaced=None,resume=None,consumed=None,args='literal word -> version record 0818DD94'),
  status='ported (data pointer)')
# CH6 chord pad audition / R6.6 transpose: the keyboard-pad note posts. The note
# post 0809ECA0 maps (high) to 0809F8A0; r0 = router, r1 = 24-byte record with the
# same layout; the press functions are structurally identical (r4 set at +0x04 and
# +0xE6 in both). 1.6.8 rebuilt the release record (velocity from [r5+0x34], the
# pad object fields moved +0x40: 2C8->308, 2CC->30C, 2EC->32C), so the old release
# site was in "changed" code; the new call sites are the same posts.
for key,a161,a168,why in [('chord_press_track',0x08084918,0x0808537e,'track press'),('chord_press_layer',0x0808494e,0x080853b4,'layer press'),
                          ('chord_release_track',0x0808414a,0x08084bc6,'track release'),('chord_release_layer',0x08084180,0x08084bfc,'layer release')]:
 HOOKS[key]=dict(why='chord pad audition / transpose: '+why,
  v161=dict(site=a161,guard_asm='bl 0x0809eca0',displaced='bl 0x0809eca0',resume=None,consumed=None,args='r0 router, r1 record'+(', r2=r4 pad' if 'press' in key else '')),
  v168=dict(site=a168,guard_asm='bl 0x0809f8a0',displaced='bl 0x0809f8a0',resume=None,consumed=None,args='same registers'),
  status='ported (same adapter, new site); owner test: chord pads, transpose, arp')
if __name__=='__main__':
 import sys,capstone
 B=0x08040000;imgs={'v161':open(sys.argv[1],'rb').read(),'v168':open(sys.argv[2],'rb').read()}
 cs=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);ok=True
 for name,h in HOOKS.items():
  for v,img in imgs.items():
   d=h[v];o=d['site']-B
   if 'guard_asm' in d:
    from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
    d['guard']=bytes(Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(d['guard_asm'],d['site'])[0]).hex()
   g=bytes.fromhex(d['guard'])
   got=img[o:o+len(g)]
   dis='; '.join('%s %s'%(i.mnemonic,i.op_str) for i in cs.disasm(got,d['site']))
   good=got==g
   ok&=good
   print('%-9s %s %08x guard %s %s  [%s]'%(name,v,d['site'],d['guard'],'OK' if good else 'MISMATCH '+got.hex(),dis))
 raise SystemExit(0 if ok else 1)
