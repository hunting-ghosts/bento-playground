SECTIONS { . = 0x080d2500; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.data*) *(.bss*) } }
