ENTRY(kick_render)
SECTIONS {
 . = 0x080d1600; .sync_process : { *(.sync_process) }
 . = 0x080d5100; .sync_control : { *(.sync_control*) }
 . = 0x080d6000; .text : { KEEP(*(.text.kick_*)) *(.text*) *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
