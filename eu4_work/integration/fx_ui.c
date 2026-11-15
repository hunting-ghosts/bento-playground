#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
#include "fx_shared.h"
#include "live_ui.h"
#include "seq_bank.h"
#include "kit_seq.h"
#include "../../chord_work/device.h"
#include "ui_native.h"
typedef struct {u32 handle;int values[18];} Entry;
typedef struct {u32 magic,active,selected,view,nav,held,serial,pending_count;Entry live[8],pending[8];char titles[3][40];u32 armed,pressed,down_tick,up_tick,last_button; /* R6.2: armed = pending footer tab, up_tick = MIXER/INST press time */Euclid eu;u32 step_view,eu_mode,draw_pattern,draw_head,draw_pad,draw_seq;} Ui;
#define U ((Ui*)UI_ADDR)
_Static_assert(sizeof(Ui)<=0x5c0,"UI state exceeds reservation");
#if BENTO_FW==168
#if !defined(BENTO_NO_CHORD_EDITOR)
#error "Track FX saturator keys 128/129 belong to the chord progression editor: 1.6.8 builds switch it off"
#endif
/* Run 17 (owner, 13 Nov): Clipper -> Saturator (On/Off, Mode, Drive, Level; fx_shared.h). */
static const char *const names[FX_NKEYS]={"EQ","Low Hz","Low dB","Mid Hz","Mid dB","Mid Q","High Hz","High dB","Compressor","Thresh dB","Ratio","Attack ms","Release ms","Auto Makeup","Makeup dB","Mix %","Saturator","Drive","Track","Mode","Level"};
static const char *const mode_names[2]={"Soft","Hard"};
/* Value i of an entry: 16 = On/Off, 19 = Mode, 20 = Level live packed in values[16] (On | Mode<<1 | Level<<8). */
static int fxv(const Entry *e,int i){int p=e->values[16];return i==16?p&1:i==19?p>>1&1:i==20?(int)(signed char)(p>>8):e->values[i];}
static void fxs(Entry *e,int i,int v){
 if(i<16||i==17||i==18){e->values[i]=v;return;}
 int p=e->values[16],on=i==16?v:p&1,mode=i==19?v:p>>1&1,level=i==20?v:(int)(signed char)(p>>8);
 e->values[16]=(on&1)|(mode&1)<<1|(level&255)<<8;
}
#else
static const char *const names[19]={"EQ","Low Hz","Low dB","Mid Hz","Mid dB","Mid Q","High Hz","High dB","Compressor","Thresh dB","Ratio","Attack ms","Release ms","Auto Makeup","Makeup dB","Mix %","Soft Clip","Ceiling dB","Track"};
#define fxv(e,i) ((e)->values[i])
#define fxs(e,i,v) ((e)->values[i]=(v))
#endif
#define zero ui_zero
__attribute__((weak,noinline,section(".text.sls"))) void ui_zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static void defaults(Entry *e,u32 handle){e->handle=handle;for(u32 i=0;i<18;i++)e->values[i]=fx_default[i];}
static void init(){if(U->magic!=0x33555845u){zero(U,sizeof(*U));for(u32 i=0;i<8;i++)defaults(&U->live[i],0);U->magic=0x33555845u;}}
static void publish_request(u32 meter_track){u32 s=(U->serial+2u)&~1u;if(!s)s=2;MAIL->serial=s|1;__asm__ volatile("dmb" ::: "memory");MAIL->magic=MAIL_MAGIC;for(u32 t=0;t<8;t++){MAIL->handles[t]=U->live[t].handle;for(u32 i=0;i<18;i++)MAIL->values[t][i]=U->live[t].values[i];}MAIL->meter_track=meter_track;__asm__ volatile("dmb" ::: "memory");MAIL->serial=s;U->serial=s;}
static void publish(){publish_request(U->selected);}
/* P168 exp3: see ui_key (kick_ui.c). A model track that is a copy takes over the settings kept under the
 * handle it was copied from (project load, Undo), unless that handle is itself still a model track
 * (a duplicated track keeps its own settings and the duplicate starts fresh, as before). */
extern u32 ui_key(u32);extern int ui_keys_dirty(void);extern void ui_key_adopt(u32,u32,u32);extern void perf_rekey(u32,u32);extern void live_rekey(u32,u32);
static __attribute__((noinline)) void track_adopt(void){
 if(!ui_keys_dirty())return;
 u32 h[8];for(u32 t=0;t<8;t++){h[t]=0;NFN(0x08133960,u32(*)(void*,u32,u32*))(MODEL,t,&h[t]);}
 for(u32 t=0;t<8;t++){
  u32 k=h[t]?ui_key(h[t]):0;if(!k||k==h[t])continue;
  int live=0;for(u32 u=0;u<8;u++)if(h[u]==k)live=1;
  if(!live){
   for(u32 j=0;j<8;j++){if(U->live[j].handle==k)U->live[j].handle=h[t];if(j<U->pending_count&&U->pending[j].handle==k)U->pending[j].handle=h[t];}
   perf_rekey(k,h[t]);live_rekey(k,h[t]);
  }
  ui_key_adopt(h[t],live?0:k,h[t]);
 }
}
static void sync(){
 init();track_adopt();int changed=0;Entry prior[8];for(u32 j=0;j<8;j++)prior[j]=U->live[j];
 for(u32 t=0;t<8;t++){
  u32 h=0;NFN(0x08133960,u32(*)(void*,u32,u32*))(MODEL,t,&h);Entry e;defaults(&e,h);
  for(u32 j=0;j<8;j++)if(h&&prior[j].handle==h){e=prior[j];break;}
  for(u32 j=0;j<U->pending_count;j++)if(h&&U->pending[j].handle==h)e=U->pending[j];
  if(U->live[t].handle!=e.handle)changed=1;
  for(u32 i=0;i<18;i++)if(U->live[t].values[i]!=e.values[i])changed=1;
  U->live[t]=e;
 }
 U->pending_count=0;if(changed||!MAIL->serial)publish();
}
static int registry(){
 u32 r=W((void*)0x30031484u,0);if(!r)return 0;
 for(u32 i=0;i<FX_NKEYS;i++){void *d=(void*)(r+fx_keys[i]*32);if(H(d,0)&&W(d,4)!=(u32)names[i])return 0;}
 for(u32 i=0;i<FX_NKEYS;i++){
  void *d=(void*)(r+fx_keys[i]*32);zero(d,32);H(d,0)=fx_keys[i];B(d,2)=(i==0||i==8||i==13||i==16)?6:2;
#if BENTO_FW==168
  if(i==19){B(d,2)=7;W(d,8)=(u32)mode_names;W(d,12)=2;} /* Mode: Soft / Hard */
#endif
  W(d,4)=(u32)names[i];W(d,16)=(u32)fx_lo[i];W(d,20)=(u32)fx_hi[i];
 }return 1;
}
static void refresh(){if(U->view)NFN(0x08145cf4,void(*)(void*))((void*)U->view);}
#define TICK_NOW W((void*)0x3001fe2cu,0)
static void tab_tick(void) __attribute__((noinline,section(".stepui")));static int tab_button(void*,u32,u32,u32);
#if BENTO_FW==168
int fx_open(void*);
#endif
#define TRACKS_PAGE 2u
#define MIX_VIEW 3u /* R6.2 Mixer > Track: selected track's Level, Pan, Delay, Reverb */
#define MIX_TRACK_TAB 0x1087u
int fx_screen_active(void){init();return U->active&&U->active!=MIX_VIEW&&B(MODEL,0x12c)==0x1a;}
__attribute__((section(".stepui"))) u32 fx_screen_bar(void){return fx_screen_active()&&U->view?U->view+0x38u:0;}
static u32 fx_bank(void){return (U->held>>8)&3u;}
static void rebuild(void){
 if(!U->view)return;u32 handle=W((void*)U->view,0x93bc);
 NFN(0x08145efc,void(*)(void*,void*))((void*)U->view,&handle);
}
int fx_screen_snapshot(u32 *bank,u32 *track,int *values){
 if(!fx_screen_active()||!bank||!track||!values)return 0;sync();
 *bank=fx_bank();*track=U->selected;
 for(u32 i=0;i<18;i++)values[i]=U->live[U->selected].values[i];
 return 1;
}
static __attribute__((noinline,section(".stepdraw"))) void meter_invalidate(void){
 __asm__ volatile("dsb" ::: "memory");
 if(W((void*)0xe000ed14u,0)&(1u<<16))W((void*)0xe000ef5cu,0)=FX_METER_CACHE_LINE;
 __asm__ volatile("dsb" ::: "memory");
}
__attribute__((used,retain,section(".stepdraw"))) int fx_screen_meter_snapshot(float *reduction_db){
 if(!fx_screen_active()||!reduction_db)return 0;
 volatile FxMeterPub *m=FX_METER_PUB;
 for(u32 attempt=0;attempt<2;attempt++){
  meter_invalidate();u32 before=m->serial;
  if(!before||(before&1u))return 0;
  u32 request_tag=m->request_tag;union {float value;u32 bits;} reduction;
  reduction.value=m->reduction_db;
  __asm__ volatile("dmb" ::: "memory");meter_invalidate();
  if(before!=m->serial)continue;
  if(request_tag!=FX_METER_TAG(U->serial,U->selected)||(request_tag&15u)>=TRACKS||
     (reduction.bits>>31)||((reduction.bits>>23)&255u)==255u)return 0;
  *reduction_db=reduction.value;return 1;
 }
 return 0;
}
int fx_screen_hit(void *point,void **out){
 if(!fx_screen_active()||!point||!out)return 0;
 int x=(int)W(point,0),top=480-(int)W(point,4);
 if(top<88||top>=428||x<16||x>=1264||!U->view)return 0;
 *out=(void*)(U->view+0x38u);return 1;
}
int fx_screen_select(void *bar,int x,int top){
 if(!fx_screen_active()||!bar||(u32)bar!=fx_screen_bar()||top<88||top>=428)return 0;
#if BENTO_FW==168
 u32 bank=x>=4&&x<632?0:x>=632&&x<940?1:x>=940&&x<1276?2:3; /* run 17: the v5 section boxes */
#else
 u32 bank=x>=16&&x<626?0:x>=646&&x<1032?1:x>=1052&&x<1264?2:3;
#endif
 if(bank>2)return 0;
 if(fx_bank()!=bank){U->held=(U->held&0xffu)|(bank<<8);rebuild();ui_commit();}
 return 1;
}
int fx_toolbar(void *model,void *out){
 extern int header_fixed_tab(void*,unsigned,unsigned,const char*,int);
 if(!out)return 0;u32 page=B(model,0x12c);
 if(page==0x0bu||page==0x0cu){
#if BENTO_FW==168
  extern int fxv_toolbar(void*,u32);return fxv_toolbar(out,page); /* P168 exp8 FX views (port/fxv_ui.c) */
#endif
  return header_fixed_tab(out,4,0x1067u,"xy",page==0x0cu)|
   header_fixed_tab(out,5,0x1068u,"FX Settings",page==0x0bu);
 }
#if BENTO_FW==168
 int changed=0;
 /* Run 17 (owner, 13 Nov): TRACKS views "Tracks | Track FX" as footer view toggles (the TRACKS button cycles them);
    Track FX has no EQ/Compressor/Saturator toggles any more (Left/Right select the section). */
 if(page==TRACKS_PAGE&&!fx_screen_active()){for(u32 i=0;i<2;i++){changed|=header_fixed_tab(out,4+i,0x1077u+i,i?"Track FX":"Tracks",!i);B((u8*)0x30034d48u+NOFF_ROOT_TABS+0xceu,(4+i)*0xd0u)=0;}return changed;}
 if(!fx_screen_active())return 0;
 for(u32 i=0;i<4;i++){void *r=(u8*)out+NOFF_HDR(0x74)+i*48;zero(r,48);B(r,0x20)=1;}
 for(u32 i=0;i<2;i++)changed|=header_fixed_tab(out,4+i,0x1077u+i,i?"Track FX":"Tracks",i);
 for(u32 i=4;i<6;i++)B((u8*)0x30034d48u+NOFF_ROOT_TABS+0xceu,i*0xd0u)=0; /* no tab dividers (mockup); fx_nav sets them back */
#else
 if(!fx_screen_active())return 0;
 static const char *const labels[3]={"EQ","Compressor","Clipper"};
 int changed=0;
 for(u32 i=0;i<6;i++)if(i<1||i>3){void *r=(u8*)out+NOFF_HDR(0x74)+i*48;zero(r,48);B(r,0x20)=1;}
 for(u32 i=0;i<3;i++)changed|=header_fixed_tab(out,i+1,0x1077u+i,labels[i],fx_bank()==i);
#endif
 char name[256];name[0]=0;u32 h=U->live[U->selected].handle;
 int ok=h&&NFN(0x0813390e,int(*)(void*,void*,u32,void*))(MODEL,&h,0x82u,name);
 if(ok&&name[0]){u32 i=0;while(i<31&&name[i]){B(out,i)=name[i];i++;}B(out,i)=0;}
 else{char fallback[]="Track 1";fallback[6]=(char)('1'+U->selected);for(u32 i=0;i<sizeof(fallback);i++)B(out,i)=fallback[i];}
 B(out,0x60)=0;B(out,NOFF_HDR(0x68))=0xf2;W(out,NOFF_HDR(0x6c))=0;B(out,NOFF_HDR(0x1c3))=2;
 return changed;
}
static const u16 eu_keys[6]={NKEY(0x190),NKEY(0x191),NKEY(0x192),NKEY(0x193),NKEY(0x194),NKEY(0x195)};
static const char *const eu_names[6]={"Pad","Length","Hits","Rotate","Vel Mode","Vel Depth"};
static const char *const vel_names[]={"Flat","Alternate","Hits 3","Hits 4","Grid 4","Rise","Fall","Wave","Humanize","Rnd Accent"};
u32 *eu_shared_scratch(void){return (u32*)&U->eu.scratch;}
const char *eu_drum_title(u32 i){return i<6?eu_names[i]:0;}
const char *const *eu_vel_names(void){return vel_names;}
static int eu_index(u32 key){for(u32 i=0;i<6;i++)if(eu_keys[i]==key)return (int)i;return -1;}
static int eu_registry(){
 u32 r=W((void*)0x30031484u,0);if(!r)return 0;
 for(u32 i=0;i<6;i++){void *d=(void*)(r+eu_keys[i]*32);if(H(d,0)&&W(d,4)!=(u32)eu_names[i])return 0;}
 EuPad p=live_value(&U->eu);u32 len=eu_length(p);int lo[6]={1,1,0,0,0,0},hi[6]={16,256,(int)len,(int)len-1,9,100};
 for(u32 i=0;i<6;i++){void *d=(void*)(r+eu_keys[i]*32);zero(d,32);H(d,0)=eu_keys[i];B(d,2)=i==4?7:2;if(i==4){W(d,8)=(u32)vel_names;W(d,12)=10;}W(d,4)=(u32)eu_names[i];W(d,16)=(u32)lo[i];W(d,20)=(u32)hi[i];}return 1;
}
extern int seq_selection_active(void*);
extern void seq_selection_reset(void*);
static int step_editing(void *v){
 if(seq_selection_active(v))return 1;
 for(u32 i=0;i<32;i++)if(W(v,0x11420+i*4))return 1;
 void *s=(void*)0x24048d80u;return W(s,0)==0x32495042u&&W(s,20)&&W(s,4)==(u32)v&&W(s,8)==W(v,0x113e4)&&W(s,12)==W(v,0x11400);
}
__attribute__((used)) void eu_view_capture(void *v){
 init();U->step_view=(u32)v;eu_capture(&U->eu,v);if(!U->eu.valid)return;
 EuPad p=live_value(&U->eu);u32 n=0;
 if(eu_native(p)&&eu_scheduled(p))n=eu_length(p);
 else ui_get((u8*)v+0x113e4,0x62,&n);
 if(n&&n<=256){W(v,0x113f8)=n;if(W(v,0x113f4)>=n)W(v,0x113f4)=0;}
}
u32 live_record_check(void);
int perf_dispatch(void*,u32,u32);void drum_menu_tick(void);void perf_tick(void);void perf_pad(u32,u32);void perf_nav(u32);int perf_header(void*,u32);int perf_get(void*,void*,u32,void*);int perf_event(void*,void*);void perf_save(void*,void*);void perf_load(void*,void*);
void chord_track_tick(void);
__attribute__((used)) int fx_dispatch(void *m,u32 code,u32 context,u32 index,const u32 *record){
 track_adopt(); /* P168 exp3: copied tracks (load, Undo) take over their settings before the next message is handled */
 if(kit_seq_dispatch(code,index,record))return 1; /* first: its Left+Right combo and lone-arrow release (R6.14 ratchet page there) */
 {extern int rt_ui_arrows(u32,u32);if(rt_ui_arrows(code,index))return 1;} /* R6.14 ratchet page while a step/note is held or selected */
#ifdef BENTO_SYNCUSSION
 {extern int drum_panel_rows(u32,u32);if(drum_panel_rows(code,index))return 1;}
#endif
 if(code==0xfe&&context==0x31544d50u){extern int play_mute_dispatch(void*,u32,const u32*);return play_mute_dispatch(m,index,record);}
 (void)context;init();
 live_record_check(); /* CH7: recorded hits on a Euclid pad switch it to Manual */
 chord_track_tick(); /* CH9: chord pads follow the chord-mode track in every view */
 perf_pad(code,index); /* P7: which pad played the chord (name, Smooth) */
 if((code==0xaf&&index==15)||code==0x8f){extern void melodic_register_tracks(void);melodic_register_tracks();}
 perf_tick(); /* P1: the selected track's fixed velocity for M7 */
 if(perf_dispatch(m,code,index))return 1;
 {extern void seq_nav_menus_tick(void);seq_nav_menus_tick();} {extern void nav_tick(void);nav_tick();} /* R6: remembered sequencer views */ tab_tick();
 {extern void chord_pad_silence(int);extern int piano_eu_pads_select(void);chord_pad_silence(piano_eu_pads_select());} /* R5: Euclid pads choose pitch silently */ /* R5: burger follows the page */
 drum_menu_tick(); /* P6: Drum Synth entry in one-shot pad menus */ /* P1: PROJ+PLAY performance page, PROJ+Left settings */
 if(code==0xb0&&index==(U->held&0xffu)&&(U->held&0xffu)){U->held&=~0xffu;return 1;}
 /* Native HAL_GetTick (081152C0) reads this millisecond counter. A first
    TRACKS press immediately follows K16; only a second short tap is consumed.
    Pad actions, shift, other buttons and a long hold cancel the tap sequence. */
 u32 tick=W((void*)0x3001fe2cu,0);
 /* CH8 (owner): K16's hold MIXER/LAUNCH returns to the previous view on release
    when the hold was used (a pad). An encoder turn (message AB) while holding
    now counts as use too, e.g. changing track volume. P26: a pad press (AC) too
    (LAUNCH hold: the native Launch page plays the pad's clip, then returns). K16 state 24048CC0:
    {magic, button, used, ...}. */
 if((code==0xab||code==0xac)&&W((void*)0x24048cc0u,0)==0x354d5442u){u32 held=W((void*)0x24048cc0u,4);if(held==3||held==5)W((void*)0x24048cc0u,8)=1;}
 /* R6 (owner spec): SEQ cycles the sequencer views (nav_seq_button); TRACKS
    is a single press on the Tracks page: Tracks -> Track FX; pressing TRACKS
    on Track FX returns natively. A held TRACKS (colours, K16 hold) or a press
    used for anything else never switches. */
 if(index!=2&&(code==0xaf||code==0xb0)&&U->pressed)U->pressed=2; /* another button cancels a TRACKS tap */
 #if BENTO_FW==168
 {extern int fxv_go(void*,u32);if(index==6&&code==0xaf&&fxv_go(m,3))return 1;} /* P168 exp8: FX cycles its views */
#endif
 {extern int pg_mixer_arrow(u32,u32);if((index==0||index==1||index==8||index==9)&&(code==0xaf||code==0xb0)&&!W((void*)0x24048d60u,8)&&pg_mixer_arrow(code,index))return 1;} /* run 18: Mixer arrows */
 if((index==5||index==10)&&(code==0xaf||code==0xb0))return tab_button(m,code,index,tick); /* R6.2 MIXER / INST */
#if BENTO_FW==168
 /* Run 17 (owner, 13 Nov): Left/Right select the Track FX section EQ / Compressor / Saturator (no wrap). Checked:
    the native GenericProperties event slot does nothing with arrow messages on this page (run 17 probe). */
 if((index==0||index==9)&&(code==0xaf||code==0xb0)&&fx_screen_active()&&!W((void*)0x24048d60u,8)){
  if(code==0xaf){u32 b=fx_bank();if(index==0?b>0:b<2){U->held=(U->held&0xffu)|((index==0?b-1:b+1)<<8);rebuild();ui_commit();}}
  return 1;
 }
#endif
 if(index==11&&(code==0xaf||code==0xb0)){extern int nav_seq_button(u32);return nav_seq_button(code);}
 if(index!=2||(code!=0xaf&&code!=0xb0)){
  if(code==0xaf||code==0xb0||code==0xfe||code==0xac){if(U->pressed)U->pressed=2;}return 0;
 }
 if(W((void*)0x24048d60u,8)){U->pressed=0;return 0;}
 if(code==0xaf){U->pressed=1;U->down_tick=tick;U->last_button=B(m,0x12c);return 0;}
 {int cycle=U->pressed==1&&U->last_button==2&&B(m,0x12c)==2&&tick-U->down_tick<=400&&!W((void*)0x24048cc0u,8);U->pressed=0;if(!cycle)return 0;}
#if BENTO_FW==168
 fx_open(m);return 0;
}
/* Open Track FX (TRACKS button on the Tracks page; run 17: also the footer toggle "Track FX" there). */
int fx_open(void *m){
 if(!registry())return 0;sync();u32 selected=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)m+4,0x131);U->selected=selected<8?selected:0;U->held=(U->held&0xffu);U->active=1;publish();
 U->nav=1;U->view=0;
 NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(m,0x1a,0,0,0);U->nav=0;
 return 1;
}
#else
 {if(!registry())return 0;sync();u32 selected=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)m+4,0x131);U->selected=selected<8?selected:0;U->held=(U->held&0xffu);U->active=1;publish();}
 U->nav=1;U->view=0;
 NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(m,0x1a,0,0,0);U->nav=0;
 return 0;
}
#endif
extern void piano_eu_nav(u32);
extern void seq_auto_arm(u32);
u32 native_fx_page(u32 page){
 extern u32 *native_fx_view_slot(int);u32 *last=native_fx_view_slot(0);
 if(page==0x0cu)return last&&*last==0x0cu?0x0cu:0x0bu;
 if(page==0x0bu&&last)*last=page;
 return page;
}
int native_fx_event(void *model,void *event){
#if BENTO_FW==168
 /* Run 19 (found by the whole-UI emulation, test_device168): a tap on the footer tab "Track FX" of the Tracks page
    arrives here as a model event; the Tracks view's event slot (pg_tracks_event) never sees it, so the tab was dead. */
 if(H(event,0)==0x1078u&&B(model,0x12c)==TRACKS_PAGE&&!fx_screen_active()){fx_open(model);return 1;}
 {extern int fxv_go(void*,u32);return fxv_go(model,H(event,0)-0x1066u);} /* P168 exp8 FX views (port/fxv_ui.c) */
#endif
 u32 c=H(event,0);if(c!=0x1067u&&c!=0x1068u)return 0;
 u32 page=B(model,0x12c);if(page!=0x0bu&&page!=0x0cu)return 0;
 extern u32 *native_fx_view_slot(int);u32 *last=native_fx_view_slot(1);
 if(!last){NFN(0x08104c00,void(*)(const char*))("FX: view RAM");return 1;}
 *last=c==0x1067u?0x0cu:0x0bu;
 NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(model,*last,0,0,0);return 1;
}
/* R6.2 (owner spec): MIXER and INST cycle the page's footer tabs; the Mixer
   footer gains Track (selected track's Level/Pan/Delay/Reverb). Mixer starts at
   Level; INST remembers its last tab per track. Pending tab: U->armed =
   id | page<<16 (0xff = any INST page), U->up_tick = stamp. */
#define ROOT_HDR ((u8*)0x30034d48u)
static int inst_page(u32 p){return p<32&&(0x22380u>>p&1u);} /* pages 07 08 09 0D 11 */
static u32 tabs(u16 *ids,u32 *lit){
 u32 n=0;*lit=~0u;if(W(ROOT_HDR,0)!=0x081b3680u)return 0;
 for(u32 i=0;i<6;i++){u8 *r=ROOT_HDR+0x34+NOFF_HDR(0x74)+i*48;if(!B(r,0x22)||B(r,0x20)||!H(r,44)||B(ROOT_HDR+NOFF_ROOT_TABS+i*0xd0,0x30))continue; /* R6.3: also hidden on screen (Wavetable Grain 2) */if(B(r,0x21))*lit=n;ids[n++]=H(r,44);}
 return n;
}
static void tap(u32 id){u32 e[5]={0x7a,0,id,0,0};NFN(0x0817fe70,void(*)(void*,void*))(ROOT_HDR,e);}
unsigned short *nav_inst_tabs(void);
u32 nav_track_index(void);
#define track_index nav_track_index
static __attribute__((noinline,section(".stepui"))) void tab_tick(void){
 u32 page=B(MODEL,0x12c),lit;u16 ids[6];
 if(!inst_page(page)&&!U->armed)return;
 u32 n=tabs(ids,&lit),ready=W(ROOT_HDR,0)==0x081b3680u&&B(ROOT_HDR+0x34,NOFF_HDR(0x1c2))==page;
 if(inst_page(page)&&ready&&lit<n&&!U->armed){unsigned short *t=nav_inst_tabs();if(t){t[track_index()]=ids[lit];if(!t[9])t[9]=(unsigned short)page;}}
 if(!U->armed)return;if(TICK_NOW-U->up_tick>1500u){U->armed=0;return;}
 u32 want=U->armed>>16;if(!ready||(want==0xff?!inst_page(page):want!=page))return;
 u32 id=U->armed&0xffffu;U->armed=0;if(id==0xfffeu){if(n&&lit)tap(ids[0]);return;} /* R6.3: home page, first tab */
 for(u32 i=0;i<n;i++)if(ids[i]==id&&i!=lit)tap(id);
}
/* Run 18 (owner FINAL 13 Nov; design/native/native_kit.png, native_pad.png, design/oneshot_inst_v4.png): one-shot INST
 * has two main views, Kit (the native bank, page 07, in Mix mode: track property 1BB = 0) and Pad (the opened pad's
 * Dashboard, page 08; drum synth pads: our synth panel). Fixed right-aligned footer slots in every one-shot INST view:
 *   2 Kit | 3 Pad | 4 Recording (Kit) / WAV (Pad; page 11) / Mix (drum synth pads, see below) | 5 Mute (Kit) / Motion
 * built from the native ids, checked in both firmwares (bank view slot 12 = 081512A4: 40 Edit opens the pad, 43/44 set
 * 1BB to 1/0 = Recording/Mix, 45 Mute, 3F Load; model events 01 -> page 07, 03 -> page 08, 08 -> page 11). "Edit"
 * and "Load" leave the footer: Load is the tap on the footer label (oneshot_label_tap) and the bank burger F4 (its
 * empty cell; the pad burger F1 has the native Load WAV). Pad -> Kit is our 1088: 1BB = 0, then model event 01.
 * Drum synth pads: the owner's slot 3 is empty there, but our drum Mix view (Level/Pitch/Pan/Overdrive/sends/filter)
 * would then be unreachable ("no feature removed"), so Mix stays in that slot (deviation, reported).
 * INST: Kit -> Pad, Recording -> Kit, Pad -> Kit, WAV -> Pad (tab_button). */
#define KIT_ACTION 0x1088u
static int one_shot(void){u32 t=0;return ui_owner(&t)&&t&&ui_type(&t)==14;}
int oneshot_kit(void){u32 t=0;if(!ui_owner(&t)||!t)return 0;ui_post(0xd3,t,NKEY(0x1bb),0);ui_post(1,0,0,0);return 1;}
int oneshot_event(void *event){return H(event,0)==KIT_ACTION&&one_shot()?oneshot_kit():0;}
int header_fixed_tab(void*,unsigned,unsigned,const char*,int);int header_fixed_action(void*,unsigned,unsigned,const char*,int);
u32 kit_seq_inst_cell(void);void *inst_bank_view(void);
static void put(char **d,const char *t,char *end){while(*t&&*d<end)*(*d)++=*t++;}
/* Footer label "<Kit>: Pad <n>: <sample>" (sample only when one is loaded), one line, at most 31 characters. */
static void oneshot_title(void *out,u32 page){
 char kit[32],sample[32];kit[0]=sample[0]=0;u32 t=0,n=0;
 if(!ui_owner(&t)||!t)return;ui_name(&t,kit); /* run 19: ui_name (the raw getter writes 256 bytes) */
 if(page==7){u8 *v=inst_bank_view();if(!v)return;n=W(v,0x6b34)+1u;u8 *tile=v+0x50+(n-1u)*0x400u;
  if(n<=16&&B(tile,0x3f9))for(u32 i=0;i<31;i++)sample[i]=(char)B(tile,0xa1+i);sample[31]=0;}
 else{const char *p=(const char*)out;u32 i=0;while(i<31&&p[i])i++;while(i&&p[i-1]>='0'&&p[i-1]<='9')i--;while(i<31&&p[i]>='0'&&p[i]<='9')n=n*10+(u32)(p[i++]-'0');
  u32 cell=kit_seq_inst_cell(); /* page 11 (WAV): the pad last opened in the Dashboard */
  if(cell)ui_name(&cell,sample);}
 if(!n||n>16)return;
 char text[32],*d=text,*end=text+31,num[3]={(char)('0'+n/10),(char)('0'+n%10),0};
 put(&d,kit,end);put(&d,": Pad ",end);put(&d,n<10?num+1:num,end);if(sample[0]){put(&d,": ",end);put(&d,sample,end);}*d=0;
 for(u32 i=0;i<32;i++){B(out,i)=(u8)text[i];if(!text[i])break;}B(out,0x60)=0;
}
int oneshot_footer(void *out){
 u32 page=B(out,NOFF_HDR(0x1c2));if((page!=7&&page!=8&&page!=0x11)||!one_shot())return 0;
 u32 lit=0,ids=0;u8 motion[48];int has_motion=0;
 for(u32 i=0;i<6;i++){u8 *r=(u8*)out+NOFF_HDR(0x74)+i*48;u32 id=H(r,44);if(B(r,0x20))continue;
  u32 bit=id==0x44?1u:id==0x43?2u:id==0x45?4u:id==0x1067u?8u:id==0x1068u?16u:id==0x3?32u:id==0x8?64u:0;ids|=bit;if(B(r,0x21))lit|=bit;
  if(id==0x1076u){for(u32 j=0;j<48;j++)motion[j]=r[j];has_motion=1;}}
 if(page==7&&!(ids&1u))return 0; /* not the bank footer */
 int c=0;
 for(u32 i=0;i<2;i++){u8 *r=(u8*)out+NOFF_HDR(0x74)+i*48;if(!B(r,0x20)||H(r,44)){for(u32 j=0;j<48;j++)r[j]=j==0x20;c=1;}}
 if(page==7){c|=header_fixed_tab(out,2,0x44,"Kit",lit&1u);c|=header_fixed_tab(out,3,0x40,"Pad",0);
  c|=header_fixed_tab(out,4,0x43,"Recording",(lit&2u)!=0);c|=header_fixed_action(out,5,0x45,"Mute",(lit&4u)!=0);}
 else{c|=header_fixed_tab(out,2,KIT_ACTION,"Kit",0);
  if(ids&24u){c|=header_fixed_tab(out,3,0x1067u,"Pad",!(lit&16u));c|=header_fixed_tab(out,4,0x1068u,"Mix",(lit&16u)!=0);}
  else{c|=header_fixed_tab(out,3,0x3,"Pad",page==8);c|=header_fixed_tab(out,4,0x8,"WAV",page==0x11);}
  u8 *r=(u8*)out+NOFF_HDR(0x74)+5*48;
  if(has_motion){for(u32 j=0;j<48;j++)r[j]=motion[j];}else if(H(r,44)||!B(r,0x20)){for(u32 j=0;j<48;j++)r[j]=j==0x20;c=1;}}
 for(u32 i=2;i<6;i++)B((u8*)0x30034d48u+NOFF_ROOT_TABS+0xceu,i*0xd0u)=0; /* no tab dividers (mockup); fx_nav sets them back */
 oneshot_title(out,page);
 return c;
}
/* A tap on the footer label: Load (bank: the native Load 3F; pad: the model's Load event 3F with the pad, as the bank
   posts it; the browser for that pad). Same label rectangle as the macro readout tap (macro_ui.c readout_tap). */
int oneshot_label_tap(void *point){
 u32 page=B(MODEL,0x12c);if((page!=7&&page!=8&&page!=0x11)||!point||W(ROOT_HDR,0)!=0x081b3680u||!one_shot())return 0;
 int x=(int)W(point,0),y=(int)W(point,4),x0=(int)W(ROOT_HDR,NOFF_ROOT(0x240)),w=(int)W(ROOT_HDR,NOFF_ROOT(0x248));
 if(y<0||y>=(int)W(ROOT_HDR,0x10)||x<x0||x>=x0+w)return 0;
 if(page==7){void *v=inst_bank_view();if(!v)return 0;u32 e[5]={0x3f,0,0,0,0};NFN(0x081512a4,int(*)(void*,void*))(v,e);return 1;}
 u32 cell=kit_seq_inst_cell();if(!cell)return 0;ui_post(0x3f,cell,0,0);return 1;
}
static int tab_button(void *m,u32 code,u32 index,u32 tick){
 u32 page=B(m,0x12c);unsigned short *mem=nav_inst_tabs();if(!mem)return 0; /* mem[8] = press page */
 /* P168 exp3 (owner on exp2: MIXER on Track flashed Level and returned to Track). The native
    press of MIXER navigates to page 1F even from page 1F (08142E58: movs r1,#0x1f; bl 081420EC,
    no test of the current page), and every navigation ends our overlays (fx_nav -> workflow_nav
    -> pg_tracks_nav), Track included. So "Track was shown" is noted at the press, before the
    native handler runs (mem[8] bit 8); the release then goes on to Pan whatever the header
    shows by then. */
 if(code==0xaf){extern int pg_mixer_compressor(void);extern u32 pg_mixer_mode(void);mem[8]=(unsigned short)(page|(index==5&&pg_mixer_compressor()?0x100u:0u)|(index==5?pg_mixer_mode()<<9:0u));U->up_tick=tick;return 0;}
 u32 from=mem[8]&0xffu,track=mem[8]>>8&1u,mode=mem[8]>>9&7u;mem[8]=0;
 if(tick-U->up_tick>400u||W((void*)0x24048cc0u,8))return 0; /* held / used: K16 behaviour */
 u32 lit;u16 ids[6];
 if(index==5){
  /* R6.6 (owner: from Track, MIXER showed Level then Track again): Track is our
     overlay; the press is ours and goes on to Pan (native would relight Level). */
  if(from==0x1fu){extern int pg_mixer_compressor(void);if(pg_mixer_compressor()){tap(NHID(0x109));return 1;}
   if(track){tap(NHID(0x109));return 0;} /* exp3: Track at the press; the release stays with the hold controls */
   /* exp5: the native view's mode at the press decides (Level -> Track -> Pan -> Delay -> Reverb -> Level) */
   if(mode){static const u16 next[4]={0x1087,NHID(0x10a),NHID(0x10b),NHID(0x108)};tap(next[mode-1]);return 0;}
   u32 n=tabs(ids,&lit);if(n>1)tap(ids[lit<n?(lit+1)%n:0]);return 0;}
  U->armed=NHID(0x108u)|(0x1fu<<16);U->up_tick=tick;return 0; /* elsewhere -> Level */
 }
 if(inst_page(from)&&from==page&&(page==7||page==8||page==0x11)&&one_shot()){ /* run 18: Kit <-> Pad, Recording -> Kit, WAV -> Pad */
  if(page==7){u32 n=tabs(ids,&lit),rec=0;for(u32 i=0;i<n;i++)if(ids[i]==0x43&&i==lit)rec=1;tap(rec?0x44:0x40);}
  else if(page==0x11)ui_post(3,0,0,0);else oneshot_kit();
  return 0;}
 if(inst_page(from)&&from==page){u32 n=tabs(ids,&lit);u32 home=mem[9];
  /* R6.3 (owner: stuck on Mix): a side page (e.g. Mix on its own native page)
   * whose last tab is lit goes back to the home page's first tab. */
  if(home&&home!=page&&inst_page(home)&&(n<2||lit+1>=n)){U->armed=0xfffeu|(home<<16);U->up_tick=tick;NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(m,home,0,0,0);return 1;}
  if(n>1)tap(ids[lit<n?(lit+1)%n:0]);return 0;}
 if(!inst_page(from)){mem[9]=0;u32 t=mem[track_index()];if(t){U->armed=t|(0xffu<<16);U->up_tick=tick;}}
 return 0;
}
__attribute__((used)) u32 fx_nav(void *m,u32 page){extern void workflow_nav(void);workflow_nav();
 for(u32 i=2;i<6;i++)B((u8*)0x30034d48u+NOFF_ROOT_TABS+0xceu,i*0xd0u)=1; /* Run 16/18: tab dividers back (fxv_toolbar, oneshot_footer clear them) */
 extern u32 perf_hold_view(u32,u32);extern void perf_hold_reopen(u32);u32 back=perf_hold_view(page,(u32)fx_screen_active()); /* run 19: a K16 hold returns to OUR view, not to the bare page */
 page=native_fx_page(page);perf_nav(page);chord_nav(m,page);piano_eu_nav(page);seq_auto_arm(page);(void)m;init();u32 meter_active=U->active==1;if(!U->nav){U->active=0;U->view=0;if(page!=0x27){U->eu_mode=0;U->step_view=0;}}
 if(back>1)perf_hold_reopen(back-2u);
 else if(back==1&&registry()){sync();u32 selected=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)m+4,0x131);U->selected=selected<8?selected:0;U->active=1;publish();U->view=0;meter_active=1;} /* Track FX as fx_open, bank kept; this navigation (page 1A) builds it */
if(meter_active)publish_request(page==0x1a?U->selected:FX_METER_TRACKS);return page;}
__attribute__((used)) int fx_header(void *m,void *handle,void *out,u32 mode,u32 caller){
 if(perf_header(out,caller))return 1;
 if(chord_header(m,handle,out,mode,caller))return 1;
 (void)m;(void)handle;(void)mode;init();
 if(!U->active||(caller&~1u)!=0x08145f22u)return 0;

 if(!registry())return 0;sync();U->view=(u32)out-0x93c4;zero(out,0x54);B(out,0)=1;
 u32 bank=fx_bank();
 static const char *const suffix[3]={" / EQ"," / Compressor",BENTO_FW==168?" / Saturator":" / Soft Clip"};
 char *s=U->titles[0];s[0]='T';s[1]='r';s[2]='a';s[3]='c';s[4]='k';s[5]=' ';s[6]='1'+U->selected;u32 n=7;
 const char *p=suffix[bank<3?bank:0];while(*p)s[n++]=*p++;s[n]=0;W(out,4)=(u32)s;
 for(u32 i=0;i<8;i++){
#if BENTO_FW==168
  static const u8 sat[8]={16,19,17,20,FX_NKEYS,FX_NKEYS,FX_NKEYS,18}; /* Saturator | Mode | Drive | Level | ... | Track */
  u32 at=bank==0?i:bank==1?i+8:sat[i];
  H(out,0x14+i*2)=at<FX_NKEYS?fx_keys[at]:0;
#else
  u32 at=bank==0?i:bank==1?i+8:i<3?(u32[]){16,17,18}[i]:19;
  H(out,0x14+i*2)=at<19?fx_keys[at]:0;
#endif
 }
 return 1;
}
int analog_get(u32,void*);
__attribute__((used)) int fx_get(void *m,void *handle,u32 key,void *out){
 if(perf_get(m,handle,key,out))return 1;
 if(chord_get(m,handle,key,out))return 1;
 if(analog_get(key,out))return 1;
#if BENTO_FW==168
 {extern int xy_get(u32,void*) __attribute__((weak));if(xy_get&&xy_get(key,out))return 1;} /* P168 exp8: Returns thru XY */
#endif
 (void)m;(void)handle;init();if(U->active&&out&&key==0){W(out,0)=0;return 1;}

 int i=key_index(key);if(i<0||!U->active||!out)return 0;
 W(out,0)=i==18?U->selected+1:(u32)fxv(&U->live[U->selected],i);return 1;
}
__attribute__((used)) int fx_event(void *v,void *event){
#if BENTO_FW==168
 if(fx_screen_active()&&U->view==(u32)v&&H(event,0)==0x1077u){NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(MODEL,TRACKS_PAGE,0,0,0);return 1;} /* footer "Tracks" */
 if(fx_screen_active()&&U->view==(u32)v&&H(event,0)==0x1078u)return 1; /* footer "Track FX": already shown */
#else
 if(fx_screen_active()&&U->view==(u32)v&&H(event,0)>=0x1077u&&H(event,0)<=0x1079u){
  U->held=(U->held&0xffu)|((H(event,0)-0x1077u)<<8);rebuild();ui_commit();return 1;
 }
#endif
 if(perf_event(v,event))return 1;
 if(chord_event(v,event))return 1;
 init();
 if(!U->active||U->view!=(u32)v||H(event,0)!=0xcf)return 0;

 int i=key_index(W(event,8));if(i<0)return 0;int value=(int)W(event,12);if(value<fx_lo[i])value=fx_lo[i];if(value>fx_hi[i])value=fx_hi[i];
 if(i==18){U->selected=(u32)value-1;publish();NFN(0x0813bc3c,void(*)(void*,u32))(MODEL,U->selected);u32 h=W(v,0x93bc);NFN(0x08145efc,void(*)(void*,void*))(v,&h);}
 else {fxs(&U->live[U->selected],i,value);publish();ui_commit();refresh();}
 return 1;
}
/* exp6: the native value text of an integer descriptor (formatter type 1/2/18 path) asks here first:
   Track FX EQ gains show tenths of a dB with sign ("+1.5 dB"), Mid Q hundredths ("1.25"). */
__attribute__((used)) int fx_value_text(u32 key,int v,char *p){
 int i=key_index(key);
#if BENTO_FW==168
 if(i==17||i==20){NFN(0x08186ee6,int(*)(char*,u32,const char*,...))(p,32,v>0?"+%d dB":"%d dB",v);return 1;} /* run 17: Drive, Level */
#endif
 u32 q=i<0?1:(u32)FX_FINE(i);if(q==1)return 0;u32 a=(u32)(v<0?-v:v),g=q==10;
 NFN(0x08186ee6,int(*)(char*,u32,const char*,...))(p,32,"%s%u.%0*u%s",g?v<0?"-":"+":"",a/q,2-g,a%q,g?" dB":"");return 1;
}
/* Called in place of the native formatter's "movs r1,#0x20; add r0,sp,#8" before its snprintf(buf,32,"%ld",v):
   r8 = key, r3 = value. Handled text is written into buf and the size becomes 0 (snprintf writes nothing). */
__attribute__((naked,used)) void fx_value_fmt(void){__asm__ volatile(
 "add r0, sp, #8\n movs r1, #0x20\n push {r0, r1, r2, r3, r12, lr}\n mov r2, r0\n mov r1, r3\n mov r0, r8\n"
 "bl fx_value_text\n cmp r0, #0\n pop {r0, r1, r2, r3, r12, lr}\n it ne\n movne r1, #0\n bx lr\n");}
static void attr(void *params,const char *name,u32 value){void *a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,name);if(a)NFN(0x0810958e,void(*)(void*,u32))(a,value);}
static int read(void *params,const char *name,u32 *value){void *a=params?NFN(0x08109c64,void*(*)(void*,const char*))(params,name):0;return a&&!NFN(0x08109566,int(*)(void*,void*))(a,value);}
static void attrname(char name[16],u32 i){const char *s="bento_fx_v1_00";u32 j=0;do{name[j]=s[j];}while(s[j++]);name[12]='0'+i/10;name[13]='0'+i%10;}
__attribute__((used)) void fx_save(void *object,void *params){
 track_adopt();live_save(object,params);perf_save(object,params);init();u32 h=ui_key(W(object,0x10));if(!h||!params)return;sync();
#if BENTO_FW==168
 /* Run 17: version 3 = version 2 + bento_fx_v1_19 Mode, _20 Level; _16 stays On/Off and _17 the ceiling (-Drive), so a
    version-2 reader (older Playground) still loads the On/Off switch and the clip level of a Soft saturator. */
 for(u32 t=0;t<8;t++)if(U->live[t].handle==h){attr(params,"bento_fx_version",3);for(u32 i=0;i<21;i++){if(i==18)continue;char name[16];attrname(name,i);int v=fxv(&U->live[t],(int)i);attr(params,name,(u32)(i==17?-v:v));}return;}
#else
 for(u32 t=0;t<8;t++)if(U->live[t].handle==h){attr(params,"bento_fx_version",2);for(u32 i=0;i<18;i++){char name[16];attrname(name,i);attr(params,name,(u32)U->live[t].values[i]);}return;}
#endif
}
__attribute__((used)) void fx_load(void *node,void *object){
 if(node&&object&&B(object,4)>=15&&B(object,4)<=20){
  extern int mel_audio_prepare(u32);
  if(!mel_audio_prepare(0))NFN(0x08104c00,void(*)(const char*))("Send: no RAM");
 }
 live_load(node,object);perf_load(node,object);if(!node||!object||B(object,4)<14||B(object,4)>22||!W(object,0x10))return;init();
 void *params=NFN(0x08109268,void*(*)(void*,const char*))(node,"params");u32 ver=0;int valid=read(params,"bento_fx_version",&ver)&&(ver==1||ver==2||(BENTO_FW==168&&ver==3));
 if(U->pending_count>=8){for(u32 i=1;i<8;i++)U->pending[i-1]=U->pending[i];U->pending_count=7;}
 Entry *e=&U->pending[U->pending_count++];defaults(e,W(object,0x10));
#if BENTO_FW==168
 /* Run 17: _17 is the ceiling in every version (-Drive); an old project's ceiling c dB becomes Drive -c dB, the
    identical sound (track_fx.h); versions 1/2 have no Mode/Level (Soft, 0 dB). */
 if(valid)for(u32 i=0;i<21;i++){if(i==18||(ver<3&&i>18))continue;char name[16];attrname(name,i);u32 raw;int n=read(params,name,&raw)?(int)raw*(ver==1?FX_FINE(i):1):i>=16&&i!=17?0:fx_default[i];
  if(i==17&&read(params,name,&raw))n=-n;if(n<fx_lo[i])n=fx_lo[i];if(n>fx_hi[i])n=fx_hi[i];fxs(e,(int)i,n);}
#else
 if(valid)for(u32 i=0;i<18;i++){char name[16];attrname(name,i);u32 raw;int n=read(params,name,&raw)?(int)raw*(ver==1?FX_FINE(i):1):fx_default[i]; /* exp6: version 1 = whole dB / whole Q */if(n<fx_lo[i])n=fx_lo[i];if(n>fx_hi[i])n=fx_hi[i];e->values[i]=n;}
#endif
}
/* P168 exp4 (owner, exp3 hardware: Multisample silent and Wavetable without its wave after save, power cycle,
 * load): the former "reload Multisample/Wavetable after project load" workaround is gone. Native load
 * completion (0813EF04) copies the load store into the model and then runs SessionMgr::FinalizeBankLoading
 * (0813E618), which already starts the native resource rebuild 0813CCB8 of every track (call at 0813E706).
 * Our workaround started a SECOND rebuild of every type 15/18 track from the completion event while the
 * native one was loading their files. Until run 5 it never ran (it looked the tracks up under the handles
 * of the load copy); since run 5's track_adopt moves those handles to the model copy it ran on every load.
 * Stock 1.6.1 and 1.6.8 rebuild nothing after FinalizeBankLoading (test_project_roundtrip). */
__attribute__((used)) void fx_finish(void *pane,void *event){(void)pane;if(H(event,0)==0x3f){live_finish();init();U->eu.valid=0;if(U->active==2){U->active=0;U->view=0;}sync();}}

/* EU3 edits the native SEQ encoder bar, never navigates to GenericProperties. */
extern void locks_header_before(void*);
int seq_eu_active(void *v){init();return U->eu_mode&&U->step_view==(u32)v&&B(MODEL,0x12c)==0x27;}
static int drum_view(void *v){return v&&B(MODEL,0x12c)==0x27&&W(v,0x113e4)&&W(v,0x11400)<16&&ui_type((u8*)v+0x113e8)==14;}
int seq_follow(int);
static const char follow_title[]="Follow";
static __attribute__((noinline,section(".pad3"))) void seq_follow_header(void *v){
 if(!drum_view(v)||!B(v,0x113e0)||seq_eu_active(v))return;
 u32 r=W((void*)0x30031484u,0);if(!r)return;void *d=(void*)(r+0x88u*32);
 if(H(d,0)&&W(d,4)!=(u32)follow_title)return;
 if(!H(d,0)){zero(d,32);H(d,0)=0x88;B(d,2)=6;W(d,4)=(u32)follow_title;W(d,20)=1;}
 int on=seq_follow(-1);void *bar=(u8*)v+0xebf0,*slot=(u8*)bar+0x38+6*0x468;
 H(v,0x113ac+12)=0x88;W(v,0x113bc+24)=(u32)on;W(v,0x1138c+24)=W(v,0x113e4);
 NFN(0x08170656,void(*)(void*,u32,const char*))(bar,6,0);ui_slot_set(slot,0x88,on);
}
static __attribute__((noinline,section(".pad2"))) void seq_page(void *v,u32 id){
 u32 length=W(v,0x113f8),base=W(v,0x113f4)/32*32,max=length?(length-1)/32*32:0;
 base=id==1?(base>=32?base-32:0):(base<max?base+32:max);if(base>max)base=max;
 seq_follow(0);W(v,0x113f4)=base;W(v,0x11404)=base;W((void*)0x24048d80u,20)=0;
 NFN(0x0815c4b8,void(*)(void*))(v);
}
/* W14 HW3 (owner: unclear what the arrows do): Left/Right move the step cursor
   (the held-step inspection frame, whose lock encoders follow) to the
   previous/next hit of the shown pad on the visible page, wrapping; Up/Down
   pick the previous/next pad like the Pad encoder. Held LOCK keeps native. */
__attribute__((used,retain,section(".pad2"))) int seq_eu_arrows(void *v,void *event){
 init();if(!drum_view(v)||W((void*)0x24048d60u,8))return 0;
 u32 id=W(event,8);volatile u32 *S=(volatile u32*)0x24048d80u;
 if(id==1||id==8){seq_page(v,id);return 1;}
 if(id!=0&&id!=9)return 0;
 u32 base=W(v,0x113f4),steps=W(v,0x113f8),n=steps>base?steps-base:0;if(n>32)n=32;if(!n||!W(v,0x113dc))return 1;
 int cur=S[0]==0x32495042u&&S[5]&&S[1]==(u32)v&&S[2]==W(v,0x113e4)&&S[3]==W(v,0x11400)&&S[4]>=base&&S[4]-base<n?(int)(S[4]-base):id==9?-1:(int)n;
 for(u32 k=1;k<=n+1;k++){int i=cur+(id==9?(int)k:-(int)k);i=((i%(int)n)+(int)n)%(int)n;
  if(NFN(0x0815bcb4,int(*)(void*,u32))(v,(u32)i)){seq_selection_reset(v);S[0]=0x32495042u;S[1]=(u32)v;S[2]=W(v,0x113e4);S[3]=W(v,0x11400);S[4]=base+(u32)i;S[5]=1;break;}}
 NFN(0x0815c27c,void(*)(void*))(v);return 1;
}
static int eu_enter(void *v){
 U->step_view=(u32)v;eu_capture(&U->eu,v);if(!live_begin(&U->eu)||!eu_registry())return 0;
 W((void*)0x24048d80u,20)=0;seq_selection_reset(v);U->eu_mode=1;live_generate(&U->eu,5,1);return 1;
}
/* Euclidean tab pressed (from the native SEQ action dispatcher). */
/* Like the former Right: also clears a held-step inspection so the generator
   controls come back when the tab is tapped again. */
int seq_eu_tab(void *v){init();if(!drum_view(v))return 0;if(!U->eu_mode)eu_enter(v);else{W((void*)0x24048d80u,20)=0;seq_selection_reset(v);}NFN(0x0815c27c,void(*)(void*))(v);return 1;}
/* Native Step/Sequence tab pressed: leave the Euclid bank, then native handles it. */
void seq_eu_leave(void *v){init();if(U->eu_mode&&U->step_view==(u32)v){U->eu_mode=0;NFN(0x0815c4b8,void(*)(void*))(v);}}
int seq_eu_mode(void *v){init();return U->eu_mode&&U->step_view==(u32)v;}
/* P21: the one-shot Euclidean view is shown (native Step/Sequence lights must stay off). */
int drum_eu_view(void){init();return B(MODEL,0x12c)==0x27&&U->eu_mode&&U->step_view;}
extern int seq_auto_take(void*);
__attribute__((noinline,section(".pad2"))) static int seq_open_euclid(void *v){
 eu_capture(&U->eu,v);if(U->eu.valid&&eu_enabled(live_value(&U->eu)))return 1;
 u32 e[6];for(u32 j=0;j<511;j++){if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))((void*)W(v,0x113dc),j,e))break;if(B(e,0)==1&&H(e,2)==W(v,0x11400))return 0;}
 return 1;
}
__attribute__((noinline,section(".pad2"))) static void open_step(void *v){
 if(!U->eu_mode&&!B(v,0x113e0))return;U->eu_mode=0;W((void*)0x24048d80u,20)=0;B(v,0x113e0)=0;NFN(0x0815c4b8,void(*)(void*))(v);
}
void seq_eu_header(void *v){
 seq_follow_header(v);
 /* W14 HW3 (owner, replaces CH5 "always Euclidean"): SEQ opens in the
    Euclidean view when the pad has no hits or its hits come from the Euclid
    encoders; recorded or step-entered hits (Manual pad) open Step. */
 if(seq_auto_take(v)&&drum_view(v)){if(seq_open_euclid(v)){if(!U->eu_mode)eu_enter(v);}else open_step(v);}
 if(!seq_eu_active(v)||!eu_registry()||step_editing(v))return;eu_capture(&U->eu,v);EuPad p=live_value(&U->eu);
 u32 values[6]={U->eu.pad+1,eu_length(p),eu_pulses(p),eu_rotation(p),eu_mode(p),eu_depth(p)};
 for(u32 i=0;i<6;i++){
  u32 key=eu_keys[i],value=values[i];H(v,0x113ac+i*2)=(u16)key;W(v,0x113bc+i*4)=value;
  void *slot=(u8*)v+0xebf0+0x38+i*0x468;NFN(0x08170656,void(*)(void*,u32,const char*))((u8*)v+0xebf0,i,0);
  ui_slot_set(slot,key,(int)value);
  if(i==4)NFN(0x08170656,void(*)(void*,u32,const char*))((u8*)v+0xebf0,4," ");
  if(i==5){ui_slot_title(slot,eu_names[i]);
   if(U->eu.status==EU_FULL||U->eu.status==EU_MEMORY)NFN(0x08170656,void(*)(void*,u32,const char*))((u8*)v+0xebf0,5,U->eu.status==EU_FULL?"Clip note limit":"No edit memory");}
 }
}
int seq_eu_encoder(void *v,u32 key,int value){
 if(!seq_eu_mode(v)&&drum_view(v)&&key==0x62){
  eu_capture(&U->eu,v);
  if(!live_cycle(&U->eu,(u32)value))NFN(0x08141902,void(*)(const char*,u32,u32,u32))("Step Count: no edit memory",0,0,1);
  NFN(0x0815c4b8,void(*)(void*))(v);NFN(0x0815c27c,void(*)(void*))(v);return 1;
 }
 if(!seq_eu_active(v))return 0;int i=eu_index(key);if(i<0||i>5)return 0;
 if(i==0){u32 pad=value<1?0:value>16?15:(u32)value-1;W(v,0x11400)=pad;U->eu.pad=pad;U->eu.hits=0;NFN(0x0815c4b8,void(*)(void*))(v);}
 else if(i==4||i==5){live_dynamic(&U->eu,i==4?4:6,value);}
 else if(live_generate(&U->eu,(u32)i,value)){
  NFN(0x0815c4b8,void(*)(void*))(v);
 }
 NFN(0x0815c27c,void(*)(void*))(v);return 1;
}

/* Native cell setters: visibility, number, track colour, trigger and playhead.
   The generator is a view over native notes: no note/clip-length mutation. */
int seq_eu_grid(void *v,int force){
 if(U->magic!=0x33555845u||U->step_view!=(u32)v||B(MODEL,0x12c)!=0x27)return 0;eu_capture(&U->eu,v);EuPad p=live_value(&U->eu);
 if(!U->eu_mode&&!(eu_native(p)&&eu_scheduled(p)))return 0;
 u32 length=eu_length(p),head=0,playing=eu_scheduled(p)&&live_position(&U->eu,&head);
 if(playing)head%=length;else head=0xffffffffu;
 u32 base=playing&&seq_follow(-1)&&!step_editing(v)?(head/32)*32:W(v,0x113f4);if(base>=length)base=0;
 if(eu_native(p)&&eu_scheduled(p)){W(v,0x113f8)=length;W(v,0x113f4)=base;}
 u32 signature=(base<<9)|(playing?head:256);
 if(!force&&U->draw_pattern==p.pattern&&U->draw_head==signature&&U->draw_pad==U->eu.pad&&U->draw_seq==U->eu.seq)return 1;
 U->draw_pattern=p.pattern;U->draw_head=signature;U->draw_pad=U->eu.pad;U->draw_seq=U->eu.seq;
 u32 active=0,marked=0,event[6];
 if(eu_native(p))for(u32 i=0;i<511;i++){
  if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))((void*)W(v,0x113dc),i,event))break;
  if(B(event,0)!=1||H(event,2)!=W(v,0x11400))continue;
  int t=(int)event[1],q=t%960;if(q>480)q-=960;int at=(t-q)/960;
  if(at<(int)base||at>=(int)(base+32)||(u32)at>=length)continue;
  active|=1u<<((u32)at-base);if(event[5])marked|=1u<<((u32)at-base);
 }
 for(u32 i=0;i<32;i++){
  u32 n=base+i,visible=n<length;void *cell=(u8*)v+0x34+i*0x704;
  NFN(0x08143ada,void(*)(void*,u32))(cell,!visible);
  NFN(0x0817e174,void(*)(void*,u32))(cell,n+1);
  NFN(0x0817e1d8,void(*)(void*,u32))(cell,B(v,0x1140c));
  NFN(0x0817e1fe,void(*)(void*,u32))(cell,visible&&(eu_native(p)?(active>>i)&1u:eu_hit(n,length,eu_pulses(p),eu_rotation(p))));
  NFN(0x0817e19c,void(*)(void*,u32))(cell,visible&&playing&&n==head);
  if(eu_native(p)&&visible){
   char text[12];u32 at=0;int selected=NFN(0x0815b9c0,int(*)(void*,u32))(v,n);if(selected)text[at++]='[';
   extern u32 ui_dec3(char*,u32);at+=ui_dec3(text+at,n+1);
   if(marked&(1u<<i))text[at++]='*';if(selected)text[at++]=']';text[at]=0;
   NFN(0x0817e85e,void(*)(void*,const char*))((u8*)cell+0x13c,text);
  }
  B(cell,0xf9)=1;
 }

 return 1;
}
void seq_eu_tick(void *model){(void)model;if(U->magic==0x33555845u&&U->step_view)seq_eu_grid((void*)U->step_view,0);}
/* W14 HW3: Vel Mode of the shown pad for the Step cell fill (mode | depth<<8 | length<<16, 0 = off). */
__attribute__((used,retain,section(".pad2"))) u32 seq_eu_dynamics(void *v){
 init();eu_capture(&U->eu,v);if(!U->eu.valid)return 0;EuPad p=live_value(&U->eu);
 if(!(eu_enabled(p)||eu_native(p))||!eu_mode(p)||!eu_depth(p))return 0;
 return eu_mode(p)|eu_depth(p)<<8|eu_length(p)<<16;
}
__attribute__((used,retain)) int seq_eu_native_head(void *v,int position){
 extern void seq_location(void*,void*);
 u32 old=W(v,0x11408);
 if(seq_eu_grid(v,1)){W(v,0x11408)=(u32)position;if(old!=(u32)position)seq_location(v,0);return 1;}
 if(drum_view(v)&&position>=0&&(u32)position<W(v,0x113f8)&&seq_follow(-1)&&!step_editing(v)){
  u32 base=(u32)position/32*32;if(base!=W(v,0x113f4)){W(v,0x113f4)=base;W(v,0x11404)=base;W(v,0x11408)=(u32)position;NFN(0x0815c4b8,void(*)(void*))(v);}
 }
 if(drum_view(v)&&old!=(u32)position){u32 prior=W(v,0x11408);W(v,0x11408)=(u32)position;seq_location(v,0);W(v,0x11408)=prior;}
 return 0;
}

/* EU9: replace the value text with a white glyph at its native text size. */
__attribute__((used,retain)) void eu_velocity_glyph(void *slot,void *paint,u32 mode){
 if(!paint||(!B(paint,0)&&!B(paint,1))||!W(paint,4)||mode>=10)return;
 u32 width=W(slot,12),height=W(slot,16);
 if(B(slot,0x30)||width<140||width>320||height<64||height>160)return;
 static const u8 bars[10][5]={{6,6,6,6,6},{12,3,12,3,12},{12,3,3,12,3},{12,3,3,3,12},{12,1,1,1,12},{2,4,7,9,12},{12,9,7,4,2},{2,7,12,7,2},{6,7,5,8,6},{3,12,3,4,9}};
 void *label=(u8*)slot+0xa8;
 u32 lx=W(label,4),ly=W(label,8),lw=W(label,12),lh=W(label,16);
 if(lw<45||lw>320||lh<12||lh>48)return;
 u32 x=lx+(lw-45)/2,y=ly+(lh-12)/2;
 u32 rect[4]={lx,ly,lw,lh};NFN(0x08166ef6,void(*)(void*,u32,void*))(rect,0xf1,(void*)W(paint,4));
 for(u32 i=0;i<5;i++){rect[0]=x+i*9;rect[1]=y+12-bars[mode][i];rect[2]=6;rect[3]=bars[mode][i];NFN(0x08166e9e,void(*)(void*,u32,void*))(rect,0xf2,(void*)W(paint,4));}
}
__attribute__((used,retain)) void eu_glyph_paint(void *v,void *paint){
 if(!seq_eu_active(v)||step_editing(v)||H(v,0x113ac+8)!=NKEY(0x194))return;
 EuPad p=live_value(&U->eu);eu_velocity_glyph((u8*)v+0xebf0+0x38+4*0x468,paint,eu_mode(p));
}
