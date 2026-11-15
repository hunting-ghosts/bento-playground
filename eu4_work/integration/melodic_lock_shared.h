#pragma once
/* Separately allocated on M4. Config is M4-owned; all later lines M7-only. */
#define ML_MARK 0xb8u
#define ML_SIGNATURE 0x4d4cu
#define ML_ENTRIES 128u
#define ML_LOCK_COUNT 0x000000ffu
#define ML_SEND_COUNT 0x0000ff00u
#define ML_ENVELOPE_COUNT 0x00ff0000u
typedef struct {u32 voice,root,word;float gain;u32 filter,resonance,decay,release,delay,reverb;} MelVoice;
typedef struct {
 u32 serial,owners[8],next,config_pad[6];
 u32 queue,word,note_root,note_word,voice,active_word;float gain;u32 pad;
 u32 active_filter,active_resonance,activity,context_pad[5]; /* Three M7-owned 0..128 counts. */
 MelVoice entries[ML_ENTRIES];
 u32 sends;u32 send_pad[7];
} MelAudio;
_Static_assert(sizeof(MelAudio)==5280,"melodic lock allocation/cache ownership");
_Static_assert(ML_ENTRIES<256,"packed melodic counts overflow");
_Static_assert(__builtin_offsetof(MelAudio,activity)==104,"M7-only melodic counters moved");
_Static_assert(__builtin_offsetof(MelAudio,entries)==128,"melodic voice table moved");
