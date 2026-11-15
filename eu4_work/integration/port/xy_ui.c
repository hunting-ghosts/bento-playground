/* P168 exp8: XY per-track send, M4 side (owner design, 12 Nov 2026). 1.6.8 only.
 *
 * This directory is not translated by tools/port/make_tree.py (files directly in a directory named "port" are
 * skipped): every native address here is a 1.6.8 address. The 1.6.1 build compiles an empty unit.
 *
 * State: one word in the unused tail of the Track FX mailbox line (FxMail ends at +0x26C):
 *   24016AC  XY_WORD  = 'XY' << 16 | loaded << 15 | returns_off << 8 | deselected-track mask (bits 0..7)
 *   240416B0 XY_BLOCK = bypass block (M7 bus header + 2 x 128 floats), allocated once per boot, 32-byte aligned
 *   240416B4 XY_PROJECT = project settings handle seen last (new project without a load -> stock)
 * M4-written, M7-read (the M7 invalidates the line once per block); the M7 startup zeroes the three words.
 * Absent tag = stock. All tracks on and returns on = stock (the M7 hooks then pass straight through).
 * GPL-3.0-or-later. */
#include "../native_ids.h"
#include "../fx_shared.h"
#include "../ui_native.h"
#if BENTO_FW==168
#define XY_WORD W((void*)0x240416acu,0)
#define XY_BLOCK W((void*)0x240416b0u,0)
#define XY_PROJECT W((void*)0x240416b4u,0)
#define XY_TAG 0x58590000u
#define XY_LOADED 0x8000u   /* set by a project load (file thread), cleared once the project handle changed */
#define XY_TOUCHED 0x4000u  /* set by a user change (UI thread): the current project owns the state */
#define XY_RETURNS_OFF 0x100u
#define XY_BYTES 0x420u      /* header 0x20 + L 0x200 + R 0x200 (the native buses hold 128 frames, 0805B466) */
#define XY_KEY 0x9au         /* registry key, empty after native construction and unused by us (run 13 check) */
#define XY_SLOT 3u           /* encoder 4 of the FX XY page: slots 2..5 are empty natively (0814979C) */
#define REGISTRY 0x30032de4u
u32 ui_settings_handle(void); /* perf_ui.c */
const char xy_returns_name[]="Returns thru XY";
static u32 state_word(void){u32 w=XY_WORD;if((w&0xffff0000u)!=XY_TAG){XY_BLOCK=0;XY_PROJECT=0;w=XY_TAG;XY_WORD=w;}return w;}
u32 xy_state(void){return state_word()&0x1ffu;}
static void store(u32 v,u32 flag){XY_WORD=XY_TAG|(state_word()&XY_LOADED)|flag|(v&0x1ffu);}
void xy_toggle_track(u32 i){if(i<8)store(xy_state()^(1u<<i),XY_TOUCHED);}
/* UI thread, every tick (workflow_periodic). Stock: nothing to do (no native call). Otherwise the state belongs to
   the project it was set in (user change) or loaded with; a new project without a load is stock again (like the
   macros, macro_periodic). Then the bypass block is allocated once per boot. */
void xy_tick(void){
 u32 w=state_word();if(!(w&0x1ffu))return;
 u32 p=ui_settings_handle();
 if(w&XY_TOUCHED){XY_PROJECT=p;w&=~(XY_TOUCHED|XY_LOADED);XY_WORD=w;}
 else if(p!=XY_PROJECT){if(XY_PROJECT&&!(w&XY_LOADED))w=XY_TAG;else w&=~XY_LOADED;XY_WORD=w;XY_PROJECT=p;if(!(w&0x1ffu))return;}
 if(XY_BLOCK)return;
 u32 b=ui_alloc(XY_BYTES+32u,XY_BYTES+64u);
 if(!b){XY_WORD=XY_TAG;NFN(0x08104dac,void(*)(const char*))("XY: no RAM");return;}
 b=(b+31u)&~31u;for(u32 i=0;i<XY_BYTES;i+=4)W((void*)b,i)=0;
 /* bus header as 08052FC0 leaves it (128 frames, silent, mono), then the M7's validation words */
 W((void*)b,0)=128;W((void*)b,8)=b+0x20u;W((void*)b,12)=b+0x220u;W((void*)b,16)=1;W((void*)b,0x14)=0x58585858u;W((void*)b,0x18)=b;
 __asm__ volatile("dsb" ::: "memory");XY_BLOCK=b;
}
/* Saved on the project's Master track object (type 21, like the macros); absent = stock. File thread: no allocation. */
void xy_save(void *object,void *params){
 u32 v=xy_state();if(!object||!params||B(object,4)!=21||!v)return;
 void *a=NFN(0x08109fac,void*(*)(void*,const char*))(params,"bento_xy_v1");if(a)NFN(0x0810985e,void(*)(void*,u32))(a,v);
}
void xy_load(void *node,void *object){
 if(!node||!object||B(object,4)!=21)return;
 void *params=NFN(0x08109538,void*(*)(void*,const char*))(node,"params");u32 v=0;
 void *a=params?NFN(0x08109f34,void*(*)(void*,const char*))(params,"bento_xy_v1"):0;
 if(!a||NFN(0x08109836,int(*)(void*,void*))(a,&v))v=0;
 store(v,XY_LOADED);
}
/* Model getter (fx_get): our key reads the Returns state (On = 1 = stock), should anything poll it. */
int xy_get(u32 key,void *out){if(key!=XY_KEY||!out)return 0;W(out,0)=!(xy_state()&XY_RETURNS_OFF);return 1;}
/* FX XY page (native view 081496A8, page 0C): encoder 4 = "Returns thru XY" On/Off (On = stock). */
static int registry(void){
 u32 r=W((void*)REGISTRY,0);if(!r)return 0;void *d=(void*)(r+XY_KEY*32u);
 if(H(d,0)&&W(d,4)!=(u32)xy_returns_name)return 0;
 for(u32 i=0;i<32;i+=4)W(d,i)=0;
 H(d,0)=XY_KEY;B(d,2)=6;W(d,4)=(u32)xy_returns_name;W(d,20)=1;return 1;
}
/* In place of the native bar update 081724F4 (bar, config) at 08149832: config = handles[8], keys[8], values[8]. */
__attribute__((used)) void xy_bar(void *bar,u32 *config){
 if(registry()){config[XY_SLOT]=0xfffffffeu;((u16*)(config+8))[XY_SLOT]=XY_KEY;config[12+XY_SLOT]=!(xy_state()&XY_RETURNS_OFF);}
 NFN(0x081724f4,void(*)(void*,void*))(bar,config);
}
/* XY view child-event handler (vtable 081A0AA8 slot 12, native 08149508): our encoder's CF stays here. */
__attribute__((used)) int xy_receive(void *view,void *event){
 if(event&&H(event,0)==0xcf&&W(event,8)==XY_KEY){
  u32 v=xy_state();store(W(event,12)?v&~XY_RETURNS_OFF:v|XY_RETURNS_OFF,XY_TOUCHED);
  NFN(0x0814979c,void(*)(void*))(view);return 1;
 }
 return NFN(0x08149508,int(*)(void*,void*))(view,event);
}
#endif
