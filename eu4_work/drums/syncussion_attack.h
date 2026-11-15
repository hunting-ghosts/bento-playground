#pragma once

/* UI-owned extension, published under the existing knob-entry transaction.
 * KNOBS reserved[0] owns its pointer; existing mailbox/voice layouts stay fixed. */
#define SYNC_ATTACK_MAGIC 0x41594e53u
typedef struct {
 unsigned magic,reserved[7];
 unsigned char values[128];
} SyncAttack;
static inline int sync_attack_memory(unsigned p) {
 return p>=0xc0000000u && p<=0xc8000000u-sizeof(SyncAttack) && !(p&31u);
}
