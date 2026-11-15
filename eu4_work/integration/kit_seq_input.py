"""Silent Kit/Seq pad ownership before native audition and recording.

Only the existing K16 input branch and its declared zero application tail
change. Register/flag state, held-before-Seq notes and other modifiers chain.
"""
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB

BASE = 0x08040000
START, END, SITE = 0x080D0400, 0x080D0800, 0x0808D1FE


def writes_for(base):
    asm = Ks(KS_ARCH_ARM, KS_MODE_THUMB)

    def code(text, address):
        return bytes(asm.asm(text, address)[0])

    old = code("b.w 0x080d0000", SITE)
    assert base[SITE-BASE:SITE-BASE+4] == old, "Exact inherited input gate"
    payload = code("""
        push.w {r0-r12,lr}
        mrs r0,APSR
        push {r0,r1}
        sub sp,#24
        ldr r8,=0x24048ca0
        ldr r0,[r8]
        ldr r1,=0x31534d42
        cmp r0,r1
        bne native
        cmp r7,#15
        bhi native
        movs r0,#1
        lsl.w r10,r0,r7
        ldrh r9,[r8,#6]
        tst r9,r10
        beq fresh
        cmp r4,#0
        bne consumed
        bic.w r9,r9,r10
        strh r9,[r8,#6]
        movs r5,#13
        b request
      fresh:
        cmp r3,#0
        bne native
        cmp r4,#0
        beq native
        ldrb r0,[r8,#12]
        cmp r0,#1
        bne native
        ldrb r0,[r8,#14]
        cmp r0,#1
        bne native
        ldrh r0,[r8,#4]
        tst r0,r10
        bne native
        add.w r0,r11,#0x1000
        ldrh r0,[r0,#0x338]
        cmp r0,#0
        bne native
        orr.w r9,r9,r10
        strh r9,[r8,#6]
        movs r5,#12
      request:
        add.w r0,r8,#16
        ldrb r6,[r0,r7]
        cmp r6,#15
        bhi consumed
        ldr r0,=0x2401bd3c
        ldr r0,[r0]
        add.w r1,r0,#0x2000
        ldr r2,[r1,#0x1a0]
        ldr r3,[r1,#0x180]
        subs r2,r2,r3
        cmp r2,#224
        bhs full
        movs r1,#254
        str r1,[sp]
        ldr r1,=0x314d5442
        str r1,[sp,#4]
        ldr r1,=0x3151534b
        str r1,[sp,#8]
        str r6,[sp,#12]
        str r5,[sp,#16]
        ldr r1,=0x31525400
        ldrb r2,[r8,#15]
        orrs r1,r2
        str r1,[sp,#20]
        mov r1,sp
        bl 0x08082220
        b consumed
      full:
        ldr r0,[r8,#8]
        adds r0,#1
        str r0,[r8,#8]
      consumed:
        add sp,#24
        pop {r0,r1}
        msr APSR_nzcvq,r0
        pop.w {r0-r12,lr}
        b.w 0x0808d1f0
      native:
        add sp,#24
        pop {r0,r1}
        msr APSR_nzcvq,r0
        pop.w {r0-r12,lr}
        b.w 0x080d0000
    """, START)
    payload += bytes(-len(payload) % 4)
    assert START+len(payload) <= END
    assert base[START-BASE:START-BASE+len(payload)] == bytes(len(payload)), \
        "Kit/Seq input tail must be exact zero, not a resource"
    return [
        (START, payload, bytes(len(payload)),
         "Kit/Seq silent pad press/release ownership in K16 input-code tail"),
        (SITE, code("b.w "+hex(START), SITE), old,
         "Kit/Seq gate before unchanged native pad audition/record path"),
    ]
