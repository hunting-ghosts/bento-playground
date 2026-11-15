/* R6.6 Berlin-school transpose: block shared by M4 (config) and M7 (offsets).
 * Allocated by M4 on the native heap; its address lives in the arp mail's
 * spare[6] (ArpBlock.mail.spare[6], unused before R6.6). No EuBank change.
 *
 * M4 writes: magic, owner/on/mode per track, armed (selected track index + 1
 * while its Transpose is On), base (pitch of the lowest pad playing the
 * project root), root (pitch class of the project root, 0 = C) and rel (scale
 * as 7 semitone offsets from the root). M7 writes off[] (semitones in
 * chromatic mode, scale degrees in diatonic mode), offserial, held[] (pads it
 * swallowed) and the note map. Only playback pitches change; stored notes do
 * not. Offsets apply to every note that starts after the press (next step). */
#pragma once
#define TR_MAGIC 0x31505254u /* "TRP1" */
#define TR_TRACKS 8u
#define TR_MAP 32u
typedef struct {u32 seq;u8 from,to,used,spare;} TrMap;
typedef struct {
 u32 magic,armed;                    /* M4 */
 u32 owner[TR_TRACKS];               /* M4: native track handles (08133CFC) */
 u8 on[TR_TRACKS],mode[TR_TRACKS];   /* M4: mode 0 chromatic, 1 diatonic */
 u8 base,root,rel[7];u8 spare0[3];   /* M4 */
 u8 m4_pad[28];                       /* M4 part ends on a cache-line boundary (96) */
 signed char off[TR_TRACKS];         /* M7 */
 u32 offserial;                      /* M7: +1 on every change */
 u32 held[4];                        /* M7: pads swallowed while armed */
 TrMap map[TR_MAP];                  /* M7: note-on pitch -> played pitch, for the note-off */
} TrBlock;
_Static_assert(__builtin_offsetof(TrBlock,off)==96,"M7-written part must start on its own cache line");
/* Pitch of scale degree d (0 = root of octave 0, may be negative). */
static inline int tr_degree_pitch(const volatile TrBlock *t,int d){
 int o=d>=0?d/7:-((6-d)/7);int i=d-o*7;return (int)t->root+12*o+(int)t->rel[i];
}
/* Scale degree at or below pitch p, and p's distance above it (semitones). */
static inline int tr_degree(const volatile TrBlock *t,int p,int *extra){
 int k=p-(int)t->root;int o=k>=0?k/12:-((11-k)/12);int pc=k-o*12;int i=6;while(i>0&&(int)t->rel[i]>pc)i--;
 if(extra)*extra=pc-(int)t->rel[i];return o*7+i;
}
/* Played pitch for note p of a track with offset off in mode m. */
static inline int tr_apply(const volatile TrBlock *t,int p,int off,int m){
 if(!m)return p+off;
 int extra=0,d=tr_degree(t,p,&extra);return tr_degree_pitch(t,d+off)+extra;
}
