/* Space (1.6.8 port): compact 64-bit division for the UI link.
 * The compiler runtime's __udivmoddi4/__divmoddi4/__divdi3 took 444 B of the
 * main UI text; this restoring shift-subtract pair takes under 100 B. Results
 * are identical for every non-zero divisor (quotient truncated toward zero,
 * remainder with the sign of the dividend, INT64_MIN wraps as before). A zero
 * divisor yields quotient 0 and the dividend as remainder: identical to the old
 * signed entry (all eleven signed callers). The old unsigned entry returned
 * only the low word of the dividend as remainder for a zero divisor; its one
 * caller (encoder_frequency_delta) divides by the constant 160000.
 * UI-rate code only (encoder turns, readouts): 64 loop passes per division. */
__attribute__((naked,used,noinline)) void __aeabi_uldivmod(void){
 __asm__(
  "push {r4,r5,r6,lr}\n"
  "movs r4,#0\n"
  "movs r5,#0\n"
  "movs r6,#64\n"
  "orrs.w r12,r2,r3\n"
  "bne 1f\n"
  "mov r4,r0\n" /* zero divisor: quotient 0, remainder = dividend (as before) */
  "mov r5,r1\n"
  "movs r0,#0\n"
  "movs r1,#0\n"
  "b 4f\n"
  "1: adds r0,r0,r0\n"
  "adcs r1,r1\n"
  "adcs r4,r4\n"
  "adcs r5,r5\n"
  "bcs 2f\n"
  "cmp r4,r2\n"
  "sbcs.w r12,r5,r3\n"
  "bcc 3f\n"
  "2: subs r4,r4,r2\n"
  "sbcs r5,r3\n"
  "adds r0,#1\n"
  "3: subs r6,#1\n"
  "bne 1b\n"
  "4: mov r2,r4\n"
  "mov r3,r5\n"
  "pop {r4,r5,r6,pc}\n");
}
__attribute__((naked,used,noinline)) void __aeabi_ldivmod(void){
 __asm__(
  "push {r4,r5,r6,lr}\n"
  "eor.w r4,r1,r3\n"
  "movs r5,r1\n"
  "bpl 1f\n"
  "negs r0,r0\n"
  "sbc.w r1,r1,r1,lsl #1\n"
  "1: cmp r3,#0\n"
  "bge 2f\n"
  "negs r2,r2\n"
  "sbc.w r3,r3,r3,lsl #1\n"
  "2: bl __aeabi_uldivmod\n"
  "cmp r4,#0\n"
  "bge 3f\n"
  "negs r0,r0\n"
  "sbc.w r1,r1,r1,lsl #1\n"
  "3: cmp r5,#0\n"
  "bge 4f\n"
  "negs r2,r2\n"
  "sbc.w r3,r3,r3,lsl #1\n"
  "4: pop {r4,r5,r6,pc}\n");
}
