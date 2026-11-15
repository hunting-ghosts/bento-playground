SECTIONS { . = 0x080d08b0; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.data*) *(.bss*) } }
