/* R6.13 ratchet playback: block shared by M4 (config) and M7 (scheduler).
 * Allocated by M4 on the native bump heap together with the EU7 lock-record
 * pool (step_lock_ui.c conditional(): ratchet records cannot exist without that
 * pool). Its address is EuControl.reserved[3] (24041FDC; zeroed at UI startup,
 * unused before R6.13). First cache lines: M4 only. Everything after: M7 only.
 *
 * Owner spec (8 Nov): count 2..8 hits split the step evenly; each hit lasts
 * note length / count; shape flat/fade/swell scaled by depth; the ratchet's own
 * probability uses the lock-condition coding and is rolled once per note (a
 * failed roll plays the note once, normally); a per-track amount 0..100 %
 * scales % probabilities (0 = no ratchets); an A:B ratchet always plays on its
 * loop. % rolls pass when roll <= p, like the lock filter. Owner (8 Nov, R6.14):
 * span = max(note length, one step), hits = span / count, never overlapping.
 * One step: the clip's grid (step clips) or the track's Seq view Step Len
 * published by M4 (absolute clips; 1/16 = 240 ticks until known). Chord notes
 * starting together share one roll. */
#pragma once
#define RT_BLOCK_MAGIC 0x31425452u /* "RTB1" */
#define RT_TRACKS 8u
#define RT_ENTRIES 32u
#define RT_ROLLS 16u
#define RT_M7_MAGIC 0x37425452u /* "RTB7": M7 zeroed its own area */
typedef struct {
 u32 magic,serial;
 u32 owner[RT_TRACKS];     /* M4: native track handle per amount slot (0 = unused) */
 u8 amount[RT_TRACKS];     /* M4: 0..100 %, default 100 */
 unsigned short step[RT_TRACKS]; /* M4: the track's Seq view Step Len in ticks (absolute piano-roll clips), 0 = unknown */
} RtConfig;                 /* 64 bytes = two cache lines */
typedef struct {
 u32 seq,owner,clip;
 u32 word;                  /* accepted (condition-filtered) lock word, replayed on every hit */
 long long t0,now0,last;    /* note time, time at its first frame, last segment start */
 u32 span,hit,len;          /* ticks: whole ratchet span, one hit (0 = learn from the native table), event length */
 unsigned short pad;u8 pitch,vel,count,next,shape,depth,melodic,spare[3];
} RtEntry;                  /* 64 bytes */
typedef struct {u32 seq,word;long long t0;u32 pass,spare[2];} RtRoll;
/* R6.16 mono roll (owner): hit k of a note cuts that note's previous hit. Each
 * hit posts a request for its voice start (FIFO per track handle, consumed by
 * rt_voice at the native sampler voice start); rt_voice releases the entry's
 * previous voice (native 5 ms ramp release, as a mono retrigger) and records
 * the new one. All M7-owned. */
#define RT_CUTS 16u
typedef struct {u32 voice,root,age,gen;} RtVoice; /* R6.16c: root of the voice; age = native voice+8 plus 1 once known (0 = unknown) */
typedef struct {u32 handle,entry,gen,tick,cut,order,check,spare;} RtCut; /* check = rt_cut_check(...) */
static inline u32 rt_cut_check(u32 epoch,u32 handle,u32 entry,u32 gen,u32 tick,u32 cut,u32 order){
 u32 h=epoch^0x5bd1e995u;h=(h^handle)*0x9e3779b1u;h=(h^entry^(cut<<8))*0x85ebca6bu;h=(h^gen)*0xc2b2ae35u;h=(h^tick)*0x27d4eb2fu;return h^order^(h>>15);
}
typedef struct {
 RtConfig cfg;
 u32 m7_magic,active,diag[6]; /* M7: own-area init mark, live entries; diag: armed, rolled off, hits, dropped, no slot, learned */
 RtEntry entries[RT_ENTRIES];
 RtRoll rolls[RT_ROLLS];
 u32 tick,order,pending,epoch,cut_count,cut_diag[3]; /* R6.16c: armed-call counter, request order, outstanding requests, per-init epoch, cuts; diag: posted, consumed, rejected */
 RtVoice voices[RT_ENTRIES];
 RtCut cuts[RT_CUTS];
} RtBlock;
_Static_assert(sizeof(RtConfig)==64,"ratchet config is two cache lines");
_Static_assert(sizeof(RtEntry)==64,"ratchet entry size");
#define RT_EC_POINTER ((volatile u32*)0x24041fdcu) /* EuControl.reserved[3] */
/* Ratchet word fields (step_lock_shared.h rt_ok has validated them on M4). */
static inline u32 rt_count(u32 r){return (r&7u)+1u;}
static inline u32 rt_shape(u32 r){return (r>>3)&3u;}
static inline u32 rt_depth(u32 r){u32 d=(r>>8)&127u;return d>100?100:d;}
#ifndef RT_CONDITIONS
#define RT_CONDITIONS 139u /* step_lock_shared.h */
#endif
static inline u32 rt_prob(u32 r){u32 p=(r>>16)&255u;return p<RT_CONDITIONS?p:0;}
/* Velocity of hit k of n: flat = v; fade falls by depth % to the last hit;
 * swell rises by depth % to the last hit (the first hit is the quietest). */
static inline u32 rt_velocity(u32 v,u32 k,u32 n,u32 shape,u32 depth){
 if(!shape||n<2||!depth||k>=n)return v;
 u32 steps=n-1,pos=shape==1?k:steps-k;
 u32 out=(v*(100u*steps-depth*pos)+50u*steps)/(100u*steps);
 return out<1?1:out>127?127:out;
}
