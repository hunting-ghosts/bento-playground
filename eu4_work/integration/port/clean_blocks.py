"""Run 15 item C step 1 (owner, 13 Nov 2026): the shared native SectionGroup and footer tab in the Clean look.

Constant-only patches found by the shared-blocks study (docs/port-1.6.8/SHARED_BLOCKS_STUDY.md,
research/display_emulator/shared_blocks/clean_patch.py), plus the bottom separator (owner: no dividing lines).
Same offsets and stock halfwords on 1.6.1 and 1.6.8; this directory is not translated by make_tree, so both
versions' function addresses are listed here. Every site is checked against its stock halfword (hash guard of the
build: exact stock and K16 reversal), one Thumb-16 halfword each, reversible.
Pages: every SectionGroup page (Settings and the other GenericProperties pages 23/24, 03, 12, 1C, 1D, 1E, 26, 2C);
the footer tab change reaches every footer."""
FN={161:dict(tick=0x0816FABC,sg_ctor=0x08170964,sg_setrect=0x081706C4,tab_paint=0x08180790,sg_vt=0x081B2884,walk=0x0816F9E8),
    168:dict(tick=0x08171C1C,sg_ctor=0x08172AC4,sg_setrect=0x08172824,tab_paint=0x081829CC,sg_vt=0x081B5764,walk=0x08171B48)}
SITES=[ # (function, offset, stock halfword, new halfword, what)
 ('sg_ctor',0xD0,0x23F2,0x23A6,'section selection frame colour F2 (white) -> A6 (frame A; run 18: the owner\'s lighter ~(110,118,120) instead of F3 (59,65,66))'),
 ('sg_ctor',0xDE,0x2302,0x2301,'section selection frame width 2 -> 1 (path A)'),
 ('sg_ctor',0x17E,0x2302,0x2301,'section selection frame width 2 -> 1 (path B)'),
 ('sg_ctor',0x106,0x25F3,0x25F1,'section title box fill/border and title label ground F3 -> F1 (no grey title bar)'),
 ('sg_setrect',0xFC,0x2300,0x2301,'bottom separator Box (+358) stays hidden (+388 = 1; owner: no dividing lines)'),
 ('tab_paint',0xDC,0x3B04,0x3B01,'selected footer tab: upper bar offset 4 -> 1'),
 ('tab_paint',0xE8,0x2304,0x2301,'selected footer tab: bar height 4 -> 1'),
]
def m4(fw,base,BASE,put,uu):
    import struct
    a=FN[fw]
    for fn,off,old,new,what in SITES:
        at=a[fn]+off
        assert struct.unpack_from('<H',base,at-BASE)[0]==old,'%s+%X: stock %04X expected'%(fn,off,old)
        put(at,struct.pack('<H',new),'Run 15 Clean SectionGroup/footer: '+what)
    # Step 2: the SectionGroup tick (slot 0) and walk (slot 2, default = the shared tree walker) go through
    # pg_sg_tick / pg_sg_walk (playground_ui.c), which chain to the native functions.
    for n,native,fn,what in ((0,a['tick'],'pg_sg_tick','small upper-case titles, small dim labels'),(2,a['walk'],'pg_sg_walk','switch pills')):
        slot=a['sg_vt']+n*4
        assert struct.unpack_from('<I',base,slot-BASE)[0]==native|1,'SectionGroup slot %d'%n
        put(slot,struct.pack('<I',uu[fn]|1),'Run 15 Clean SectionGroup: '+fn+' ('+what+')')
