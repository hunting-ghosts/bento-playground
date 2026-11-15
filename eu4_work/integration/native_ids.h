/* Native parameter keys and UI/action ids per firmware version (1.6.8 port).
 * NKEY: every native registry key AND every private Playground registry key.
 *   1.6.8 (proven on the complete registries, tools/port/registry_map.py: 350/354
 *   keys aligned, 0 exceptions): keys < 0x139 unchanged; In 1/In 2/In 3
 *   (0x139..0x13B) became one key 0x139; 0x13C..0x1D8 -> k-2; >= 0x1D9 -> k-1.
 *   Private keys sit in empty slots, which shift the same way: every private key
 *   we use lands in a slot that is empty in 1.6.8 (checked, no collisions).
 * NUI: native menu/action ids (tools/port/ui_ids.py, 46 ids by label):
 *   <= 0x1011 unchanged; 0x1013..0x103B +2; 0x103C..0x1047 +3; our own ids
 *   (>= 0x1048) unchanged.
 * NOFF_*: struct offsets that moved. Evidence per offset (native code that
 *   addresses the same field in both versions; tools/port/base_offsets.py for
 *   objects at a fixed address, offsets_check.py composites for the others):
 *   MODEL (30024B00 -> 30025300, address token translated separately):
 *     pad lights +19C4 -> +19D0 (5 sites), changed flag +36C4 -> +3FF4 (8 sites),
 *     pad mode +3C7C -> +45CC, Undo buffer +B26C -> +C3C0.
 *   Header record (0x1C4 -> 0x1DC bytes; the 38 native page templates
 *     08199008 -> 0819BB40 are identical apart from this and the id renumbering):
 *     the 8-byte string at +60 grew to 32 bytes, so every field from +68 on moved
 *     by +0x18 (colour +68 -> +80, +6B -> +83, +6C -> +84, six 48-byte action
 *     records +74 -> +8C, burger +194 -> +1AC, page +1C2 -> +1DA). Native
 *     header_apply 0817FAF8/08181C7C reads exactly these: NOFF_HDR(o).
 *   Root header (30034D48 -> 300366E8) embeds that record at +34, so root
 *     offsets from +9C on moved by +0x18 (title label +23C -> +254, action
 *     widgets +54C -> +564, tab widgets +A2C -> +A44, layout flag +117C -> +1194;
 *     all four seen in header_apply): NOFF_ROOT(o).
 *   Synth view: second knob widget +36C8 -> +3830, knob values +10154 -> +11CA4,
 *     selected tile per track +10238 -> +11D88 (7 native sites; found late: the
 *     inventory did not read constants with a C suffix). Layout compared on the
 *     constructed view of both versions (tools/port/view_layout.py): identical
 *     up to +3618, then +168 (to +3790), +2D0 (to +8840), +F10 (to +D714), +1B50.
 *   Wave pane widget (class 081B3A18, the two panes of the synth view at +3550 and
 *     NOFF_SYNTH_KNOB2; 0x178 -> 0x2E0 bytes): 1.6.8 inserted 0x168 bytes before +90, so
 *     every field from +90 on moved by +0x168. Native paint 08182314/08184550 and the WAV
 *     binding 08182770/08184996 address the same fields in both versions: +90 -> +1F8,
 *     +94 -> +1FC, +A0 -> +208, +C4 -> +22C, label hidden flag +134 -> +29C, +156 -> +2BE,
 *     +168/+169 -> +2D0/+2D1, colours +174..+177 -> +2DC..+2DF: NOFF_WAVE(o).
 *   Offsets not listed here have no evidence of a move (see HANDOVER.md for the
 *   ones still unverified).
 * Compile-time constants; for 1.6.1 all are identities (byte-identical image). */
#ifndef NATIVE_IDS_H
#define NATIVE_IDS_H
#ifndef BENTO_FW
#define BENTO_FW 161
#endif
#if BENTO_FW==168
/* Native multisample/wavetable resource rebuild 0813CCB8 (1.6.8: 0813E4B8) gained a third
 * parameter in 1.6.8 (r2, kept at [sp+24]); five of the seven native callers pass 0. */
#define NATIVE_RELOAD(m,h) NFN(0x0813ccb8,void(*)(void*,u32,u32))(m,h,0)
#define NKEY(k) ((k)<0x139u?(k):(k)<0x13cu?0x139u:(k)<0x1d9u?(k)-2u:(k)-1u)
#define NUI(i) ((i)<0x1013u?(i):(i)<0x103cu?(i)+2u:(i)<0x1048u?(i)+3u:(i))
/* Header tab/action ids 0x108..0x122 (Mixer tabs Level/Pan/.., compared on the 38 native page
 * templates): +1 in 1.6.8. The shift starts at 0x101: 1.6.8 inserted one event code there (model
 * event dispatcher 081403EC/08141EA4, jump tables compared case by case: codes up to 0x100 keep
 * their handlers, 0x101..0x106 -> 0x102..0x107, 0x10C -> 0x10D). No source uses 0x101..0x107 today. */
#define NHID(i) ((i)>=0x101u&&(i)<=0x122u?(i)+1u:(i))
#define NKEY_LIMIT 0x1f2u /* registry 0x3E40 bytes: 498 descriptors */
#define NOFF_MODEL_PADS 0x19d0u
#define NOFF_MODEL_CHANGED 0x3ff4u
#define NOFF_MODEL_PADMODE 0x45ccu
#define NOFF_MODEL_UNDO 0xc3c0u
#define NOFF_ROOT_LAYOUT 0x1194u
#define NOFF_ROOT_SLOTS 0x564u
#define NOFF_ROOT_TABS 0xa44u
#define NOFF_HDR(o) ((o)<0x68u?(o):(o)+0x18u)
#define NOFF_ROOT(o) ((o)<0x9cu?(o):(o)+0x18u)
#define NSIZE_HDR 0x1dcu
#define NOFF_SYNTH_KNOB2 0x3830u
#define NOFF_SYNTH_VALUES 0x11ca4u
#define NOFF_SYNTH_TILE 0x11d88u
#define NOFF_WAVE(o) ((o)<0x90u?(o):(o)+0x168u)
#else
#define NATIVE_RELOAD(m,h) NFN(0x0813ccb8,void(*)(void*,u32))(m,h)
#define NKEY(k) (k)
#define NUI(i) (i)
#define NHID(i) (i)
#define NKEY_LIMIT 0x1f4u /* registry 0x3E60 bytes: 499 descriptors */
#define NOFF_MODEL_PADS 0x19c4u
#define NOFF_MODEL_CHANGED 0x36c4u
#define NOFF_MODEL_PADMODE 0x3c7cu
#define NOFF_MODEL_UNDO 0xb26cu
#define NOFF_ROOT_LAYOUT 0x117cu
#define NOFF_ROOT_SLOTS 0x54cu
#define NOFF_ROOT_TABS 0xa2cu
#define NOFF_HDR(o) (o)
#define NOFF_ROOT(o) (o)
#define NSIZE_HDR 0x1c4u
#define NOFF_SYNTH_KNOB2 0x36c8u
#define NOFF_SYNTH_VALUES 0x10154u
#define NOFF_SYNTH_TILE 0x10238u
#define NOFF_WAVE(o) (o)
#endif
#endif
