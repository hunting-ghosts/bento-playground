#pragma once
/* P28 arpeggiator, shared between the Performance page (M4) and the audio core
 * (M7). One block, allocated by M4 from the native bump heap; its address is
 * EuBank.reserved[3] (reserved[0] MelAudio, [1]/[2] motion). The first cache
 * line is written only by M4 under an odd/even serial; everything after it is
 * written only by M7. */
#include "live_shared.h"
#define ARP_MAGIC 0x50524141u
#define ARP_RATES 8u
#define ARP_MODES 5u /* Up, Down, Up/Down, As played, Random */
typedef struct {u32 serial,magic,on,track,mode,rate,octaves,gate,bpm,spare[7];} ArpMail; /* on: 0 off, 1 on, 2 latch */
typedef struct {u8 root,n,vel,down;u8 tone[6];u8 pad[2];} ArpRoot;
typedef struct {
 u32 diag[8]; /* P29, M7 writes, M4 reads (cleaned to memory): blocks, presses, notes on, notes off, held, running, synced, spare */
 u32 track,router[2],handle[2];
 u32 nroots,wait,running,step,sounding,sound_slots,block,clock_block,rnd,seen_serial,last_track;
 i64 pos,next,off_at,clock_pos,frac;
 ArpMail cfg;
 ArpRoot roots[16];
} ArpState;
typedef struct {ArpMail mail;ArpState state;} ArpBlock;
_Static_assert(sizeof(ArpMail)==64,"arp mail is one cache line pair");
/* Ticks per quarter note are 960 (native clock); rates in ticks. */
static const unsigned short arp_rate_ticks[ARP_RATES]={960,640,480,320,240,160,120,80};
