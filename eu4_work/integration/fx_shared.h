#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
#pragma once
typedef unsigned int u32;typedef unsigned char u8;typedef unsigned short u16;
#define W(p,o) (*(volatile u32*)((u8*)(p)+(o)))
#define H(p,o) (*(volatile u16*)((u8*)(p)+(o)))
#define B(p,o) (*(volatile u8*)((u8*)(p)+(o)))
#define FN(a,t) ((t)((a)|1u))
#ifdef BENTO_NATIVE_SYMBOLS /* 1.6.8 port/space: direct BL via linker symbol NAT_<address> */
#define NFN(a,t) ((t)({extern char NAT_##a[];(void*)NAT_##a;}))
#else
#define NFN(a,t) FN(a,t)
#endif
#define MAIL_MAGIC 0x324d5846u
/* All UI-owned state is inside the native M4 MPU's RW region, >=24040000.
   Reserve exactly 8 KiB below K16's heap ceiling; never change the MPU. */
#define DSP_ADDR 0x24040000u
#define DSP_BYTES 0x1440u
#define MAIL_ADDR 0x24041440u
#define META_ADDR 0x240416c0u
#define UI_ADDR 0x24041a00u
#define FX_METER_REQUEST_OFFSET 0x2b0u
#define FX_METER_PUB_OFFSET 0x2b4u
#define FX_METER_CACHE_LINE (META_ADDR+0x2a0u)
#define MODEL ((void*)0x30024b00u)
enum {PARAMS=18,TRACKS=8};
#define FX_METER_TRACKS TRACKS
#define FX_METER_TAG(serial,track) ((((serial)&0x0fffffffu)<<4)|((track)&0x0fu))
typedef struct {u32 magic,serial,handles[8];int values[8][18];u32 meter_track;} FxMail;
typedef char MailFits[(sizeof(FxMail)<=0x280)?1:-1];
typedef char MailMeterTrackOffset[(__builtin_offsetof(FxMail,meter_track)==0x268)?1:-1];
typedef struct {u32 serial,request_tag;float reduction_db;} FxMeterPub;
typedef char MeterPubFits[(sizeof(FxMeterPub)==12)?1:-1];
#define MAIL ((volatile FxMail*)MAIL_ADDR)
#define FX_METER_PUB ((volatile FxMeterPub*)(META_ADDR+FX_METER_PUB_OFFSET))
#if BENTO_FW==168
/* Run 17 (owner, 13 Nov, saturator FINAL): Saturator On/Off (16) | Mode (19: Soft/Hard) | Drive (17: 0..24 dB, the
   former Ceiling slot as -Ceiling: an old ceiling c dB loads as Drive -c, the identical sound) | Level (20: -12..+12 dB).
   Mode and Level travel packed in value 16 (On | Mode<<1 | Level<<8, track_fx.h TF_CLIP_*): the mailbox and the M7
   metadata keep their layout. Keys 128/129 (Mode/Level): empty after native registry construction on 1.6.1 and 1.6.8
   and owned by the chord progression editor only, which 1.6.8 builds switch off (fx_ui.c refuses the combination). */
#define FX_NKEYS 21
#define FX_LEVEL_LO (-12)
#define FX_LEVEL_HI 12
#define FX_CLIP_ON(v) ((u32)(v)&1u)
static const u16 fx_keys[FX_NKEYS]={NKEY(0x1b1),NKEY(0x1b2),NKEY(0x1b3),NKEY(0x1b4),NKEY(0x1b5),NKEY(0x1b6),NKEY(0x1b7),NKEY(0x1b9),NKEY(0x1bc),NKEY(0x1bf),NKEY(0x1c0),NKEY(0x1c1),NKEY(0x1c2),NKEY(0x1c3),NKEY(0x1c4),NKEY(0x1c5),NKEY(0x1c6),NKEY(0x1ca),NKEY(0x1d0),0x128,0x129};
#define FX_FINE(i) ((i)==5?100:((i)==2||(i)==4||(i)==7)?10:1)
static const int fx_lo[FX_NKEYS]={0,20,-120,20,-120,100,20,-120,0,-60,1,1,10,0,0,0,0,0,1,0,FX_LEVEL_LO};
static const int fx_hi[FX_NKEYS]={1,20000,120,20000,120,600,20000,120,1,0,20,100,2000,1,12,100,1,24,8,1,FX_LEVEL_HI};
static const int fx_default[18]={0,120,0,1000,0,100,6000,0,0,-18,3,10,120,1,0,100,0,1};
#else
#define FX_NKEYS 19
#define FX_CLIP_ON(v) (v)
static const u16 fx_keys[19]={NKEY(0x1b1),NKEY(0x1b2),NKEY(0x1b3),NKEY(0x1b4),NKEY(0x1b5),NKEY(0x1b6),NKEY(0x1b7),NKEY(0x1b9),NKEY(0x1bc),NKEY(0x1bf),NKEY(0x1c0),NKEY(0x1c1),NKEY(0x1c2),NKEY(0x1c3),NKEY(0x1c4),NKEY(0x1c5),NKEY(0x1c6),NKEY(0x1ca),NKEY(0x1d0)};
/* exp6 (owner: finer EQ steps): EQ gains (2 Low, 4 Mid, 7 High) in tenths of a dB, Mid Q (5) in hundredths;
   saved as bento_fx_version 2 (version 1 projects are scaled on load, fx_load). Encoder: 0.5 dB / 0.05 Q per
   native whole-number step (perf_ui encoder_fx_delta); shown with decimals (fx_value_text). */
#define FX_FINE(i) ((i)==5?100:((i)==2||(i)==4||(i)==7)?10:1)
static const int fx_lo[19]={0,20,-120,20,-120,100,20,-120,0,-60,1,1,10,0,0,0,0,-12,1};
static const int fx_hi[19]={1,20000,120,20000,120,600,20000,120,1,0,20,100,2000,1,12,100,1,0,8};
static const int fx_default[18]={0,120,0,1000,0,100,6000,0,0,-18,3,10,120,1,0,100,0,-1};
#endif
static inline int key_index(u32 key){for(int i=0;i<FX_NKEYS;i++)if(fx_keys[i]==key)return i;return -1;}
