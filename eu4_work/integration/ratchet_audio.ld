SECTIONS { .text 0x080cf4c0 : { *(.text*) *(.rodata*) } .rt2 0x080da640 : { *(.rt2code*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }
