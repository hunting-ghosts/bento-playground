SECTIONS {
 /* Bank-1 M4 code (needs BENTO_M4_MPU_WIDE=1; build_fx.py refuses otherwise).
    Listed first: .text.bank1* must not fall into .text below. */
 . = 0x080d0510; .bank1c : { *(.text.bank1c*) }
 . = 0x080d1180; .bank1d : { *(.text.bank1d*) }
 . = 0x080d1f20; .bank1g : { *(.text.bank1g*) }
 . = 0x080d2140; .bank1e : { *(.text.bank1e*) }
 . = 0x080d3190; .bank1f : { *(.text.bank1f*) }
 . = 0x080d5960; .bank1a : { *(.text.bank1a*) }
 . = 0x080dbcd0; .bank1b : { *(.text.bank1b*) }
 . = 0x081b3fc0; .pad6 : { *(.pad6) }
 . = 0x081b4a00; .panel : { *(.panel) }
 . = 0x081b4c00; .steptext : { *(.steptext) }
 . = 0x081b5070; .mixstrip : { *(.mixstrip) }
 . = 0x081b5284; .pad8 : { *(.pad8) } /* run 13 */
 . = 0x081b5378; .pad9 : { *(.pad9) } /* run 13 */
 . = 0x081b5400; .stepdraw : { *(.stepdraw) }
 . = 0x081b5800; .pad10 : { *(.pad10) } /* run 13 */
 . = 0x081b5900; .stepnote : { *(.stepnote) }
 . = 0x081b6300; .stepstrings : { *(.stepstrings) }
 . = 0x081b66d0; .pad7 : { *(.pad7) }
 . = 0x081b6a00; .stepui : { *(.stepui) }
 . = 0x081b70d0; .pad4 : { *(.pad4) }
 . = 0x081b7404; .kitinput : { *(.kitinput) }
 . = 0x081b76b0; .cycleundo : { *(.cycleundo) }
 . = 0x081b78bc; .kitevent : { *(.kitevent) }
 . = 0x081b7c60; .kitdraw : { *(.kitdraw) }
 . = 0x081b80c8; .kitlock : { *(.kitlock) }
 . = 0x081b8c04; .banktext : { *(.banktext) }
 . = 0x081b8d04; .bankstate : { *(.bankstate) }
 . = 0x081b8e04; .bankentry : { *(.bankentry) }
 . = 0x081b9004; .bankdraw : { *(.bankdraw) }
 . = 0x081b9420; .pad : { *(.pad) *(.padr*) }
 . = 0x081ba03c; .pad11 : { *(.pad11) } /* run 13 */
 . = 0x081ba0c0; .pad12 : { *(.pad12) } /* run 13 */
 . = 0x081ba140; .pad13 : { *(.pad13) } /* run 13 */
 . = 0x081bac80; .pad5 : { *(.pad5) }
 . = 0x081bb094; .pad14 : { *(.pad14) } /* run 13 */
 . = 0x081bb154; .pad15 : { *(.pad15) } /* run 13 */
 . = 0x081bb23c; .pad16 : { *(.pad16) } /* run 13 */
 . = 0x081bb33c; .pad17 : { *(.pad17) } /* run 13 */
 . = 0x081bbd08; .kitcontext : { *(.kitcontext) }
 . = 0x081bc6a0; .pad2 : { *(.pad2) *(.pad2r*) }
 . = 0x081bd180; .pad3 : { *(.pad3) *(.pad3r*) }
 . = 0x081bdf20; .text : { *(.text*) *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }
}
