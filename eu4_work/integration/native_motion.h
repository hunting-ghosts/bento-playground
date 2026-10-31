#pragma once
#include "live_shared.h"
#define NM_MAGIC 0x314d414eu
#define NM_CLIPS 128u
#define NM_STEPS 256u
#define NM_TICK 240u
#define NM_CONTROL_ADDR 0x24041980u
/* Reuses the retired RECORD latch line. M4 owns it; M7 only reads it. */
typedef struct {u32 magic,pointer,bytes,epoch,enabled,initializing,progress,error;} NmControl;
#define NC ((volatile NmControl*)NM_CONTROL_ADDR)
enum {NM_EMPTY=0,NM_WAITING=1,NM_WRITING=2,NM_HAS_MOTION=3};
/* Only lengths cross cores. Samples and routes remain native A-D objects.
 * Each structure has exactly one writer; no cache line has mixed ownership. */
typedef struct {u32 serial,owner,row,sequence;u16 length[4];u32 spare[2];} NmClip;
typedef struct {
 u32 serial,sequence,owner,row;
 i64 tick,origin;
 u32 valid,epoch,restart,spare;
 u16 length[4];u32 config_serial,config_sequence;
} NmClock;
typedef struct {
 u32 magic,bytes,epoch,spare[5];
 NmClip clips[NM_CLIPS];
 NmClock clock[8];
 u32 spare_tail[16];
} NmShared;
_Static_assert(sizeof(NmClip)==32&&sizeof(NmClock)==64,"motion cache ownership");
_Static_assert(sizeof(NmShared)%32==0,"shared cache ownership");
_Static_assert(sizeof(NmControl)==32,"motion control ownership");
#ifdef BENTO_NATIVE_MOTION
int nm_set_enabled(int);
int nm_enabled(void);
unsigned nm_status(void);
void nm_dispatch(u32,u32);
void nm_increment(void*,int);
int nm_model_event(void*);
int nm_get(void*,void*,u32,void*,u32);
void nm_bar_tick(void*);
void nm_bar_paint(void*,void*);
int nm_tap(void*,void*);
void nm_readout(void*);
void nm_header_before(void*);
void nm_header_after(void*);
int nm_view_event(void*,void*);
void nm_save(void*,void*);
void nm_load(void*,void*);
void nm_finish(void);
void nm_clone(u32,void*,void**,int);
void nm_rebuild(u32,u32);
#else
static inline int nm_set_enabled(int on){return !on;}
static inline int nm_enabled(void){return 0;}
static inline unsigned nm_status(void){return NM_EMPTY;}
static inline void nm_dispatch(u32 a,u32 b){(void)a;(void)b;}
static inline void nm_increment(void *a,int b){(void)a;(void)b;}
static inline int nm_model_event(void *a){(void)a;return 0;}
static inline int nm_get(void *a,void *b,u32 c,void *d,u32 e){(void)a;(void)b;(void)c;(void)d;(void)e;return 0;}
static inline void nm_bar_tick(void *a){(void)a;}
static inline int nm_tap(void *a,void *b){(void)a;(void)b;return 0;}
static inline void nm_readout(void *a){(void)a;}
static inline void nm_header_before(void *a){(void)a;}
static inline void nm_header_after(void *a){(void)a;}
static inline int nm_view_event(void *a,void *b){(void)a;(void)b;return 0;}
static inline void nm_save(void *a,void *b){(void)a;(void)b;}
static inline void nm_load(void *a,void *b){(void)a;(void)b;}
static inline void nm_finish(void){}
#endif
