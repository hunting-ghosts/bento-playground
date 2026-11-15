#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
/* BENTO_MOD K7: reuse the exact native sample-editor rows. */
#include "step_lock_shared.h"
#include "kick_knobs.h"
#include "drum_models.h"
#include "encoder_speed.h"
#include "kit_seq.h"
#ifdef BENTO_SYNCUSSION
#include "../drums/syncussion_attack.h"
static const char attack_name[]="Attack";
#endif
#include "../drums/mod_matrix.h"
#include "ui_native.h"
#define MODEL ((void*)0x30024b00u)
#define PAD_KEY NKEY(0x1aau)
#define LOAD_KEY NKEY(0x1adu)
#define U ((volatile ViewState*)0x24043d20u)
typedef struct {u32 magic,view,active,third,wave;} ViewState;
static const char *const model_names[]={"Kick","Snare","HiHat","Clap","Tom"
#ifdef BENTO_SYNCUSSION
 ,"Metal"
#endif
};
static u32 model_slot(u32 m){return m==15?5:m==3?1:m==5?2:m==7?3:m==9?4:0;}
static const char load_name[]="Engine",click_name[]="Click";
static const char *const names[7]={"Tune","Decay","Tone","Impact","Sweep","Sweep Dec","Punch"}; /* P10: Kick Dirt -> Punch */
static const char *label(u32 m,u32 i){
#ifdef BENTO_SYNCUSSION
 if(m==15)return sync_labels[i];
#endif
 return m==3?snare_labels[i]:m==5?hat_labels[i]:m==7?clap_labels[i]:m==9?tom_labels[i]:names[i];}
static const unsigned short top[8]={2,NKEY(0x1a0),NKEY(0x1a1),NKEY(0x1a2),NKEY(0x1a4),NKEY(0x1a5),NKEY(0x1a6),NKEY(0x1a9)};
/* Mix: Level, Pitch, Pan, Overdrive, Delay, Reverb, Filter, Resonance (owner). */
static const unsigned short bottom[8]={2,3,4,0xe5,0x36,0x37,0x32,0x33};
#ifdef BENTO_SYNCUSSION
int kick_ui_supported(void*);
void kick_ui_after(void*);
static int panel_model(u32 m){return (m>=1&&m<=9&&(m&1u))||m==15;}
static u32 panel_mix(void){return (U->active>>8)&1u;}
/* Held steps have their own transient row focus, never a selector focus. */
static u32 panel_engine_row(void){return !panel_mix()&&(kit_seq_holding()?kit_seq_step_focus(-1):(U->active&0x200u)!=0);}
void drum_panel_hold_reset(void){U->active&=~0x200u;}
static __attribute__((noinline,section(".panel"))) void panel_layout(void*);
static int panel_visible(void){
 void *v=(void*)U->view;
 return U->magic==0x3756494bu&&panel_model(U->active>>16)&&v&&
  B(MODEL,0x12c)==8&&W(v,0)==0x0819e624u&&!B(v,0x30)&&kick_ui_supported(v)==(int)(U->active>>16);
}
static __attribute__((noinline)) void panel_header_refresh(void){
 void *root=(void*)0x30034d48u;
 if(W(root,0)!=0x081b3680u||!panel_visible())return;
 u8 snapshot[NSIZE_HDR];u8 *current=(u8*)root+0x34;
 /* The native header may be applied before this editor has bound its pad. */
 if(current[NOFF_HDR(0x1c2)]!=8)return;
 for(u32 i=0;i<sizeof(snapshot);i++)snapshot[i]=current[i];
 extern int drum_panel_toolbar(void*,void*);
 drum_panel_toolbar(MODEL,snapshot);kit_seq_toolbar(snapshot);
 int changed=0;for(u32 i=0;i<sizeof(snapshot);i++)if(snapshot[i]!=current[i]){changed=1;break;}
 if(!changed)return;
 B(root,NOFF_ROOT_LAYOUT)=1;
 NFN(0x0817faf8,void(*)(void*,void*))(root,snapshot);
}
__attribute__((section(".pad2"))) int drum_panel_toolbar(void *model,void *out){
 (void)model;if(!out||!panel_visible())return 0;
 kit_seq_header_reset(out);
 int changed=B(out,0)!=0;B(out,0)=0;
 /* These existing FX tab actions are reused only on the sample editor. */
 for(u32 i=0;i<4;i++)if(B(out,NOFF_HDR(0x74)+i*48+0x21)){B(out,NOFF_HDR(0x74)+i*48+0x21)=0;changed=1;}
 /* R6.3: the native WAV tab in slot 5 gives way to Motion (Synth · Mix · Motion). */
 if(!B(out,NOFF_HDR(0x74)+5*48+0x20)){B(out,NOFF_HDR(0x74)+5*48+0x20)=1;changed=1;}
 extern int header_fixed_tab(void*,unsigned,unsigned,const char*,int);
 return changed|header_fixed_tab(out,3,0x1067u,"Synth",!panel_mix())|
  header_fixed_tab(out,4,0x1068u,"Mix",panel_mix()!=0);
}
int drum_panel_navigation(void *model,void *event){
 (void)model;u32 code=H(event,0);
 if((code!=0x1067u&&code!=0x1068u)||!panel_visible())return 0;
 u32 mix=code==0x1068u;if(mix==panel_mix())return 1;
 kit_seq_step_focus(0);
 U->active=(U->active&~256u)|(mix<<8);
 extern void drum_panel_cancel_touch(void);drum_panel_cancel_touch();
 void *v=(void*)U->view,*group=(void*)W((u8*)v+0x38,0x2c);
 NFN(0x08152144,void(*)(void*))(v);
 if(group)NFN(0x08170c86,void(*)(void*,u32))(group,mix);
 kick_ui_after(v);
 B(v,0x31)=1;B((void*)0x30034d48u,NOFF_ROOT_LAYOUT)=1;
 return 1;
}
#endif
#define zero ui_zero
__attribute__((weak,noinline,section(".text.sls"))) void ui_zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
int drum_assign(u32 pad,u32 *cell,u32 engine);
#ifdef BENTO_DRUM_DIAG
typedef struct {u32 magic,n,last_o,spare;u32 rec[64][6];} DiagLog;
#define DIAG_MAGIC 0x47414944u
static void diag(u32,u32,u32,u32,u32);static u32 diag_slot(u32);static DiagLog *diag_log(int);static char *hx(char*,u32);
#define DIAG(t,a,b,c,e) diag(t,a,b,c,e)
#else
#define DIAG(t,a,b,c,e) ((void)0)
#endif
int drum_menu_event(void *event);
/* P11 (owner: drum synths loaded from the card show the sample page; the
 * synth page only via the burger menu). The file name/folder test (drum_path)
 * misses the path form the device stores, so a pad's file is also recognised
 * by its content: our carrier (48 kHz mono 16-bit, 144019 + id - 1 frames,
 * signature in the first 32 samples), exactly what the audio core checks.
 * Results are cached per file node handle (UI heap block). */
void **drum_cache_slot(void);
typedef struct {u32 magic,next,handle[8],model[8],key[8];char path[256];} DrumCache;
/* P168 exp7 (crash cycle, docs/port-1.6.8/RUN12_PROGRESS.md item 1): the native card library (FatFS built without
 * FF_FS_REENTRANT) and SD driver (one DMA completion queue) serve ONE thread at a time; the native firmware does every
 * load, save and stream on its file thread (pcmStreamer, loop 08112B54). These checks and writes ran on the UI thread
 * and collided with the project's sample loading (5 s driver waits -> native watchdog restart). They now run on the
 * file thread: card_poll() is called there each time it goes idle (before its 10-tick queue wait 08112BF0); the UI
 * only posts. Box in the free words 24048A40..24048A5F (between the black-box line and the T2 counters), cleared by
 * bb_boot at every startup. install: 0 none, 1 posted, 2 running, 3 all carriers verified, 4 failed; state: 0 idle,
 * 1 check posted (handle/key/path), 2 result ready; on_file: the file thread is inside card_poll. */
typedef struct {volatile u32 install,state,handle,key,result;const char *volatile path;volatile u32 on_file;} CardBox;
#define CARD ((CardBox*)0x24048a40u)
static DrumCache *drum_cache(void){
 void **slot=drum_cache_slot();if(!slot)return 0;DrumCache *c=*slot;if(c)return c->magic==0x48434d45u?c:0;
 u32 bytes=(sizeof(DrumCache)+31u)&~31u;c=(void*)ui_alloc(bytes,bytes+32);if(!c)return 0;for(u32 i=0;i<sizeof(*c)/4;i++)((u32*)c)[i]=0;c->magic=0x48434d45u;*slot=c;return c;
}
static u32 carrier_open(const char *path,int *opened){
 u32 file[22];for(u32 i=0;i<22;i++)file[i]=0;u8 b[108];char alt[260];if(opened)*opened=0;
 if(NFN(0x08120148,u32(*)(void*,const char*,u32))(file,path,1)){
  u32 n=0;alt[n++]='\\';for(u32 i=0;path[i]&&n<259;i++)alt[n++]=path[i];alt[n]=0;
  for(u32 i=0;i<22;i++)file[i]=0;if(NFN(0x08120148,u32(*)(void*,const char*,u32))(file,alt,1))return 0;
 }
 if(opened)*opened=1;
 u32 size=file[4],high=file[5],got=0;u32 r=NFN(0x08120464,u32(*)(void*,void*,u32,u32*))(file,b,108,&got);NFN(0x08120974,u32(*)(void*))(file);
 if(r||got!=108||high||size<44u||(size-44u)&1u)return 0;u32 frames=(size-44u)/2u;
 if(frames<144019u||frames>
#ifdef BENTO_SYNCUSSION
 SYNCUSSION_FRAMES /* run 14: the melodic Syncussion carrier (144035) is no drum synth any more */
#else
 144029u
#endif
 )return 0;u32 id=frames-144018u;if(!(id&1u)||id==11||id==13)return 0;
 if(W(b,0)!=0x46464952u||W(b,8)!=0x45564157u||W(b,24)!=48000u||H(b,22)!=1||H(b,34)!=16||W(b,40)!=frames*2u)return 0;
 for(u32 i=0;i<32;i++){u32 v=H(b,44+2*i),want=(0xb1e70a5cu>>i)&1u?1u:0xffffu;if(v!=want)return 0;}
 return id;
}
/* HiHat silence (owner, 4 November): a carrier NAME alone made the UI show the
 * engine page, while M7 plays only a byte-verified carrier and otherwise the
 * near-silent file. A named file that opens but fails verification is marked
 * STALE (cached per file node): the reserved Drum Synths copy is rewritten, a
 * message is shown once, and choosing the same engine again reloads the pad.
 * Files that cannot be opened keep the name result (P11 path forms). */
#define DRUM_STALE 0x100u
int drum_ensure(const char *path,u32 frames);
static u32 drum_frames(u32 engine);
static u32 file_index(u32 m){return m==15?5:m==3?1:m==5?2:m==7?3:m==9?4:0;}
static u32 drum_file_state(u32 file,const char *path){
 u32 named=drum_path(path);if(named&&!file)return named;if(!file)return 0;
 DrumCache *c=drum_cache();u32 key=2166136261u;for(const char *q=path;*q;q++)key=(key^(u8)*q)*16777619u;
 if(!c)return named; /* exp7: never the card from the UI thread */
 CardBox *b=CARD;
 if(b->state==2){u32 i=c->next++&7u;c->handle[i]=b->handle;c->model[i]=b->result;c->key[i]=b->key;b->state=0;}
 for(u32 i=0;i<8;i++)if(c->handle[i]==file&&c->key[i]==key)return c->model[i];
 if(!b->state){u32 n=0;while(path[n]&&n<255){c->path[n]=path[n];n++;}c->path[n]=0;b->handle=file;b->key=key;b->path=c->path;b->state=1;}
 return named; /* until the file thread has checked the file (card_poll) */
}
/* File thread: the check that used to run in drum_file_state (an altered reserved carrier is rewritten). */
static void card_check(CardBox *b){
 const char *path=b->path;u32 named=drum_path(path);int opened=0;u32 m=carrier_open(path,&opened);if(m==13)m=0;
 if(named){
  if(opened&&m!=named){
   extern const char *const drum_files[];char fs[48];u32 n=0;const char *a="\\Drum Synths\\";
   while(*a)fs[n++]=*a++;for(const char *q=drum_files[file_index(named)];*q&&n<47;)fs[n++]=*q++;fs[n]=0;
   drum_ensure(fs,drum_frames(file_index(named)));
   NFN(0x08104c00,void(*)(const char*))("Drum synth file outdated: choose its engine again");
   m=named|DRUM_STALE;
  }else m=named;
 }
 b->result=m;b->state=2;
}
static u32 drum_file_model(u32 file,const char *path){return drum_file_state(file,path)&0xffu;}
static int drum_stale(void *v){
 if(!v||!W(v,0x87c4))return 0;char path[256];path[0]=0;NFN(0x0813390e,int(*)(void*,void*,u32,char*))(MODEL,(u8*)v+0x87c4,0x81,path);
 return (drum_file_state(W(v,0x87c4),path)&DRUM_STALE)!=0;
}
__attribute__((used,retain)) int kick_ui_supported(void *v){
 if(!v || !W(v,0x87bc) || !W(v,0x87c4) || B(v,0x87cc)!=14)return 0; /* run 14: no melodic (Multisample) editor */
 u32 type=ui_type((u8*)v+0x87bc);
 if(type!=1 && type!=2)return 0;
 char path[256];path[0]=0;NFN(0x0813390e,int(*)(void*,void*,u32,char*))(MODEL,(u8*)v+0x87c4,0x81,path);
 return (int)drum_file_model(W(v,0x87c4),path);
}
static int registry(u32 model){
 u32 r=*(volatile u32*)0x30031484u;if(!r)return 0;
 for(u32 i=0;i<10;i++){
  u32 key=i<7?kick_keys[i]:i==7?PAD_KEY:i==8?LOAD_KEY:CLICK_KEY;void *d=(void*)(r+key*32);
  const char *name=i<7?label(model,i):i==7?model_names[model_slot(model)]:i==8?load_name:click_name;
#ifdef BENTO_SYNCUSSION
  if(i==9&&model==15)name=attack_name;
#endif
  if(H(d,0)){
   u32 old=W(d,4);int owned=old==(u32)name || old==(u32)load_name || old==(u32)click_name;for(u32 j=0;j<sizeof(model_names)/sizeof(*model_names);j++)if(old==(u32)model_names[j])owned=1;
   for(u32 j=0;j<7;j++)if(old==(u32)names[j] || old==(u32)snare_labels[j] || old==(u32)hat_labels[j] || old==(u32)clap_labels[j] || old==(u32)tom_labels[j])owned=1;
#ifdef BENTO_SYNCUSSION
   for(u32 j=0;j<7;j++)if(old==(u32)sync_labels[j])owned=1;
   if(old==(u32)attack_name)owned=1;
#endif
   if(!owned)return 0;
  }
 }
 for(u32 i=0;i<10;i++){
  u32 key=i<7?kick_keys[i]:i==7?PAD_KEY:i==8?LOAD_KEY:CLICK_KEY;void *d=(void*)(r+key*32);
  zero(d,32);H(d,0)=key;B(d,2)=i==8?7:2;if(i==8){W(d,8)=(u32)model_names;W(d,12)=sizeof(model_names)/sizeof(*model_names);}W(d,4)=(u32)(i<7?label(model,i):i==7?model_names[model_slot(model)]:i==8?load_name:click_name);
  W(d,16)=i==0&&drum_family(model)==1?25:i==7?1:0;W(d,20)=i==0&&drum_family(model)==1?180:i==7?16:i==8?4:100;
#ifdef BENTO_SYNCUSSION
  if(i==8)W(d,20)=6;
  if(model==15&&i==9)W(d,4)=(u32)attack_name;
#endif
 }return 1;
}
/* R4 (owner: Syncussion crash/init after reload): KNOBS lives in RAM that a
 * reset can preserve, but native handles (counter 30000088, only increasing)
 * and the native heap restart at boot. An entry whose handle was not yet
 * issued in this boot is from an earlier one and would alias a new pad, as
 * its pointers would alias reused heap blocks: all of it is dropped then (as
 * a magic mismatch; nothing is freed, that heap is gone). Stateless: nothing
 * is written while the table is current. */
static void init(void){
 /* R6.3 (owner 7 Nov, engine switch silent/crash): the R4 rule "an entry whose
  * handle was not yet issued is stale -> wipe the whole table" is gone. The
  * device log showed the table wiped mid-session, and this RAM is cleared at
  * every boot anyway (verified 7 Nov), so only a missing magic means stale. */
 int stale=KNOBS->magic!=KNOBS_MAGIC;
 if(stale){DIAG(1,0,KNOBS->magic,0,0);
  for(u32 i=0;i<128;i++)KNOBS->entries[i].sequence=1;__asm__ volatile("dsb" ::: "memory");
  zero(KNOBS,sizeof(*KNOBS));zero((void*)CLICKS,128);KNOBS->magic=KNOBS_MAGIC;U->magic=0;
 }
 if(U->magic!=0x3756494bu){zero((void*)U,sizeof(*U));U->magic=0x3756494bu;}
}
#ifdef BENTO_SYNCUSSION
static SyncAttack *sync_attack(int create){
 u32 p=KNOBS->reserved[0];
 if(sync_attack_memory(p)&&((SyncAttack*)p)->magic==SYNC_ATTACK_MAGIC)return (SyncAttack*)p;
 if(!create)return 0;
 u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0);
 if(!sync_attack_memory(cursor)||end>0xc8000000u||cursor>end||end-cursor<sizeof(SyncAttack)+32u){
  NFN(0x08104c00,void(*)(const char*))("Sync: no attack RAM");return 0;
 }
 SyncAttack *s=NFN(0x08104c08,void*(*)(u32))(sizeof(SyncAttack));
 if((u32)s!=cursor){NFN(0x08104c00,void(*)(const char*))("Sync: attack alloc");return 0;}
 zero(s,sizeof(*s));s->magic=SYNC_ATTACK_MAGIC;
 __asm__ volatile("dsb" ::: "memory");KNOBS->reserved[0]=(u32)s;return s;
}
static u32 attack_value(KickKnob *e){SyncAttack *s=sync_attack(0);return s?s->values[e-KNOBS->entries]:0;}
#endif
/* Native Save/Undo copies have new handles. Keep their frozen sound settings
 * outside the live 128-slot audio mailbox, until the native cell is destroyed. */
typedef struct DrumCopy {struct DrumCopy *next;void *object;KickKnob knob;u32 click,attack,magic;} DrumCopy;
#define DRUM_COPIES (*(DrumCopy**)&KNOBS->reserved[1])
#define DRUM_COPY_MAGIC 0x59504f43u
/* A node must be a live block of the native top-down allocator (08104c58:
 * [p-4]==p) carrying our magic; a list is cut at the first node that is not. */
static __attribute__((noinline)) int copy_valid(DrumCopy *s){
 u32 p=(u32)s;return p>=0xc0000010u&&p<0xc1000000u&&!(p&3u)&&((u32*)p)[-1]==p&&s->magic==DRUM_COPY_MAGIC;
}
static __attribute__((noinline,section(".kitinput"))) DrumCopy *drum_copy(u32 handle){
 if(KNOBS->magic==KNOBS_MAGIC)for(DrumCopy *s=DRUM_COPIES;s&&copy_valid(s);s=s->next)if(s->knob.handle==handle)return s;
 return 0;
}
static __attribute__((noinline,section(".pad3"))) KickKnob *existing(u32 handle){
 if(KNOBS->magic==KNOBS_MAGIC)for(u32 i=0;i<128;i++){KickKnob *e=&KNOBS->entries[i];if(e->sequence&&e->handle==handle)return e;}
 return 0;
}
static __attribute__((noinline,section(".kitlock"))) KickKnob *drum_saved(u32 handle,u32 *click,u32 *attack){
 KickKnob *e=existing(handle);
 if(e){*click=CLICKS[e-KNOBS->entries];*attack=0;
#ifdef BENTO_SYNCUSSION
  if(MOD_ENGINE(e->reserved)==15)*attack=attack_value(e);
#endif
  return e;
 }
 DrumCopy *s=drum_copy(handle);if(!s)return 0;*click=s->click;*attack=s->attack;return &s->knob;
}
static KickKnob *entry(u32 handle,u32 model);
static void knob_clear(KickKnob *e);
/* R4 (owner: sounds return to init as soon as a project is saved): a native
 * copy that becomes the playing cell has a new handle, and M7 plays defaults
 * for a handle without a KNOBS entry. The copy also gets a live entry (filled
 * from its snapshot by entry/drum_copy_restore), but only in a free slot,
 * never evicting a live sound; it is removed when the copy is destroyed. */
static __attribute__((noinline,section(".bankentry"))) void copy_mirror(DrumCopy *s){
 if(existing(s->knob.handle))return;
 for(u32 i=0;i<128;i++)if(!KNOBS->entries[i].sequence){entry(s->knob.handle,MOD_ENGINE(s->knob.reserved));return;}
}
/* P168 exp3 (owner: settings gone after save / power cycle / load). The device
 * never writes or plays the nodes a project file was read into: the worker
 * reads the file into its load store, the model gets a COPY of that store
 * (native 0812D68E, completion 0813EF04), and Save writes another copy
 * (081314C4 -> 081260E4). Every copied node has a new handle (0812D8AC), and
 * all our per-track settings (Track FX, Perform, Euclid) are keyed by track
 * handle: they were stored under the load handle and never found again, and a
 * Save looked them up under the handle of the save copy. A copied track now
 * remembers the handle its settings are kept under; ui_key() resolves it for
 * the save hooks, and track_adopt() (fx_ui.c) moves the settings to the copy
 * once it is a track of the playing model. Block: native bump heap, pointer in
 * KNOBS->reserved[2] (cleared with KNOBS at boot; M7 does not read it). */
#define HANDLE_KEYS 62u
typedef struct {u32 magic,dirty;struct {u32 clone,key;} a[HANDLE_KEYS];} HandleKeys;
#define HANDLE_KEYS_MAGIC 0x59454b48u
static int handle_keys_memory(u32 p){return p>=0xc0000000u&&p<=0xc8000000u-sizeof(HandleKeys)&&!(p&31u);}
static __attribute__((noinline)) HandleKeys *handle_keys(int create){
 u32 p=KNOBS->magic==KNOBS_MAGIC?KNOBS->reserved[2]:0;
 if(handle_keys_memory(p)&&((HandleKeys*)p)->magic==HANDLE_KEYS_MAGIC)return (HandleKeys*)p;
 if(!create)return 0;
 u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0);
 if(!handle_keys_memory(cursor)||end>0xc8000000u||cursor>end||end-cursor<sizeof(HandleKeys)+32u)return 0;
 HandleKeys *k=NFN(0x08104c08,void*(*)(u32))(sizeof(HandleKeys));if((u32)k!=cursor)return 0;
 zero(k,sizeof(*k));k->magic=HANDLE_KEYS_MAGIC;__asm__ volatile("dsb" ::: "memory");KNOBS->reserved[2]=(u32)k;return k;
}
/* The handle a track's settings are kept under (the handle itself for a track that is no copy). */
__attribute__((used,retain,noinline)) u32 ui_key(u32 handle){
 HandleKeys *k=handle_keys(0);if(k&&handle)for(u32 i=0;i<HANDLE_KEYS;i++)if(k->a[i].clone==handle)return k->a[i].key;
 return handle;
}
/* 1 once after tracks were copied (track_adopt then looks at the model's tracks). */
__attribute__((used,retain)) int ui_keys_dirty(void){HandleKeys *k=handle_keys(0);if(!k||!k->dirty)return 0;k->dirty=0;return 1;}
/* `live` is a model track now: it is its own key; other copies kept under `from` follow it to `to`. */
__attribute__((used,retain)) void ui_key_adopt(u32 live,u32 from,u32 to){
 HandleKeys *k=handle_keys(0);if(!k)return;
 for(u32 i=0;i<HANDLE_KEYS;i++){if(k->a[i].clone==live)k->a[i].clone=0;else if(from&&k->a[i].clone&&k->a[i].key==from)k->a[i].key=to;}
}
static void key_note(u32 clone,u32 key){
 HandleKeys *k=handle_keys(1);if(!k||!clone)return;u32 slot=HANDLE_KEYS;
 for(u32 i=0;i<HANDLE_KEYS;i++){if(k->a[i].clone==clone){slot=i;break;}if(!k->a[i].clone&&slot==HANDLE_KEYS)slot=i;}
 if(slot==HANDLE_KEYS)slot=clone%HANDLE_KEYS; /* full: the oldest copies are long gone */
 k->a[slot].key=key;k->a[slot].clone=clone;k->dirty=1;
}
static __attribute__((noinline)) int capture_body(void *source,void *target,int ok){ /* exp3: grown, no longer pinned to the .stepui cave */
 if(!ok||!source||!target)return ok;
 u32 type=B(source,4);
 if(type>=14&&type<=22){init();key_note(W(target,0x10),ui_key(W(source,0x10)));}
 /* P168 exp3: a Wavetable track (18) carries the Analog marker (engine 13) the same way as a pad its drum synth. */
 if(type!=1&&type!=2&&type!=18)return 1;
 init();u32 click,attack;KickKnob *e=drum_saved(W(source,0x10),&click,&attack);if(!e||(type==18)!=(MOD_ENGINE(e->reserved)==13u))return 1;
 DIAG(2,W(source,0x10),W(target,0x10),MOD_ENGINE(e->reserved),0);
 KickKnob saved=*e;
 DrumCopy *s=NFN(0x08104c58,void*(*)(u32))(sizeof(DrumCopy));
 if(!s){NFN(0x08104c00,void(*)(const char*))("Drum: copy alloc");return 0;}
 s->object=target;s->knob=saved;s->knob.handle=W(target,0x10);s->click=click;s->attack=attack;s->magic=DRUM_COPY_MAGIC;
 s->next=DRUM_COPIES;DRUM_COPIES=s;copy_mirror(s);return 1;
}
#ifdef BENTO_DRUM_DIAG
#define FORGET_SECTION ".text.diag"
#else
#define FORGET_SECTION ".cycleundo"
#endif
static __attribute__((noinline,section(FORGET_SECTION))) void forget_body(void *object){
 if(KNOBS->magic!=KNOBS_MAGIC)return;
 if(B(object,4)>=14&&B(object,4)<=22)ui_key_adopt(W(object,0x10),0,0);
 init();DrumCopy **slot=&DRUM_COPIES;
 while(*slot){DrumCopy *s=*slot;if(!copy_valid(s)){*slot=0;return;}
  if(s->object==object){DIAG(3,s->knob.handle,W(object,0x10),0,0);*slot=s->next;{KickKnob *e=existing(s->knob.handle);if(e)knob_clear(e);}s->magic=0;NFN(0x08104cc4,void(*)(void*))(s);return;}slot=&s->next;}
}
__attribute__((used,retain,noinline,section(".stepui"))) int drum_copy_capture(void *source,void *target,int ok){return capture_body(source,target,ok);}
__attribute__((used,retain,noinline,section(".stepnote"))) void drum_copy_forget(void *object){forget_body(object);}
static __attribute__((noinline,section(".stepstrings"))) void drum_copy_restore(KickKnob *e,u32 model){
 DrumCopy *s=drum_copy(e->handle);if(!s||MOD_ENGINE(s->knob.reserved)!=model)return;
 for(u32 j=0;j<7;j++)e->values[j]=s->knob.values[j];e->reserved=s->knob.reserved;
 CLICKS[e-KNOBS->entries]=(u8)s->click;
#ifdef BENTO_SYNCUSSION
 if(s->attack){SyncAttack *a=sync_attack(1);if(a)a->values[e-KNOBS->entries]=(u8)s->attack;}
#endif
}
static KickKnob *entry(u32 handle,u32 model){
 KickKnob *chosen=0;u32 age=0;
 for(u32 i=0;i<128;i++){KickKnob *e=&KNOBS->entries[i];if(e->sequence && e->handle==handle){if(MOD_ENGINE(e->reserved)==model)return e;chosen=e;break;}if(!e->sequence && !chosen)chosen=e;}
 if(!chosen)for(u32 i=0;i<128;i++){KickKnob *e=&KNOBS->entries[i];u32 a=KNOBS->serial-e->sequence;if(!chosen || a>age){age=a;chosen=e;}}
 /* CH11: a pad whose sound changed engine keeps its routes for the old engine
  * (tag), silent until a synth route is edited on the new engine. */
 u32 keep=0;if(chosen->sequence && chosen->handle==handle){u32 r=chosen->reserved;keep=MOD_TAG(r)?MOD_TAG(r):MOD_ENGINE(r);}
 u32 serial=(KNOBS->serial+2u)&~1u;if(!serial)serial=2;
 chosen->sequence=serial|1u;__asm__ volatile("dsb" ::: "memory");chosen->handle=handle;chosen->reserved=(u8)(model|keep<<4);
 for(u32 j=0;j<7;j++)chosen->values[j]=drum_defaults(model)[j];
 CLICKS[chosen-KNOBS->entries]=model==15?0:kick_defaults[2];
#ifdef BENTO_SYNCUSSION
 SyncAttack *s=sync_attack(0);if(s)s->values[chosen-KNOBS->entries]=0;
#endif
 drum_copy_restore(chosen,model);
 __asm__ volatile("dsb" ::: "memory");chosen->sequence=serial;KNOBS->serial=serial;return chosen;
}
static void update(KickKnob *e,u32 index,u32 value){
#ifdef BENTO_SYNCUSSION
 SyncAttack *s=index==8?sync_attack(1):0;if(index==8&&!s)return;
#endif
 u32 serial=(KNOBS->serial+2u)&~1u;if(!serial)serial=2;
 e->sequence=serial|1u;__asm__ volatile("dsb" ::: "memory");
#ifdef BENTO_SYNCUSSION
 if(index==8)s->values[e-KNOBS->entries]=(u8)value;else
#endif
 if(index==7)CLICKS[e-KNOBS->entries]=(u8)value;else e->values[index]=(u8)value;
 __asm__ volatile("dsb" ::: "memory");e->sequence=serial;KNOBS->serial=serial;__asm__ volatile("dsb" ::: "memory");
}
static void set_tag(KickKnob *e,u32 tag){
 if(MOD_TAG(e->reserved)==tag)return;u32 serial=(KNOBS->serial+2u)&~1u;if(!serial)serial=2;
 e->sequence=serial|1u;__asm__ volatile("dsb" ::: "memory");e->reserved=(u8)((e->reserved&15u)|tag<<4);
 __asm__ volatile("dsb" ::: "memory");e->sequence=serial;KNOBS->serial=serial;__asm__ volatile("dsb" ::: "memory");
}
__attribute__((noinline,section(".stepstrings"))) int drum_motion_range(u32 handle,u32 key,int *low){
 void *v=(void*)U->view;int j=mod_index(key);
 if(j<0||U->magic!=0x3756494bu||!U->active||!v||B(v,0x30)||B(MODEL,0x12c)!=8||W(v,0x87bc)!=handle)return 0;
 u32 model=kick_ui_supported(v);if(!model||(u32)j>=mod_count(model))return 0;
 KickKnob *e=entry(handle,model);u32 tag=MOD_TAG(e->reserved);
 if(tag&&tag!=model)return 0;
 *low=mod_low(model,(u32)j);return mod_span(model,(u32)j);
}
static __attribute__((noinline,section(".stepstrings"))) u32 motion_value(KickKnob *e,u32 key,u32 base){
 extern int motion_capture_get(void*,u32,void*);u32 value,handle=e->handle;
 return motion_capture_get(&handle,key,&value)?value:base;
}
static u32 pad(void *v){u32 n=0;ui_get((u8*)v+0x87bc,0x73,&n);return n<16?n:0;}
static void rows(void *v,int custom){
 u32 handle=W(v,0x87bc);u32 model=custom?kick_ui_supported(v):0;
 for(u32 row=0;row<3;row++)for(u32 i=0;i<8;i++){
  W(v,0x701c+row*0x50+i*4)=handle;
  H(v,0x703c+row*0x50+i*2)=custom?(row==0?(drum_count(model)<7&&i>=6?0:top[i]):row==1?bottom[i]:model==1&&i==0?CLICK_KEY:0):H(v,0x6fdc+row*16+i*2);
#ifdef BENTO_SYNCUSSION
  if(custom&&model==15&&row==0&&i<2)H(v,0x703c+i*2)=i==0?kick_keys[0]:CLICK_KEY;
  if(custom&&model<=9&&row==0)H(v,0x703c+i*2)=i<drum_count(model)?kick_keys[i]:model==1&&i==7?CLICK_KEY:0;
  if(custom&&model<=9&&row==2)H(v,0x703c+row*0x50+i*2)=i==0?LOAD_KEY:0;
#endif
 }
}
#ifdef BENTO_SYNCUSSION
static const unsigned short panel_hidden[]={0x7f30,0x7e60,0x8000,0x803c,0x8078,0x715c,0x710c,0x8284,0x8244,0x8204,0x8194,0x8124};
#endif
__attribute__((used,retain)) void kick_ui_before(void *v){
#ifdef BENTO_DRUM_DIAG
 init(); /* a stale reset clears the log pointer: run it first */
 {DiagLog *d=diag_log(1);u32 h=W(v,0x87bc),m=kick_ui_supported(v),o=h^(m<<24)^((u32)v<<4);if(d&&d->last_o!=o){d->last_o=o;KickKnob *x=existing(h);diag(4,(u32)v,h,m|(B(MODEL,0x12c)<<8)|(B(v,0x87cc)<<16),(x?MOD_ENGINE(x->reserved):0xffu)|(diag_slot(h)<<8));}}
#endif
 kit_seq_bind(v);
 init();u32 model=kick_ui_supported(v);
#ifdef BENTO_SYNCUSSION
 if(U->view==(u32)v&&panel_model(U->active>>16)&&model!=(U->active>>16)){
  void *group=(void*)W((u8*)v+0x38,0x2c);
  if(group)NFN(0x08170b7c,void(*)(void*))(group);
  B((u8*)v+0x38,0x30)=0;B((u8*)v+0x2430,0x30)=0;
  B(v,0x4828+0x30)=(u8)U->third;B(v,0x71c0+0x30)=(u8)U->wave;
  for(u32 i=0;i<12;i++)B(v,panel_hidden[i]+0x30)=(U->wave>>(8+i))&1u;
  extern void drum_panel_cancel_touch(void);drum_panel_cancel_touch();
 }
 u32 keep=U->active&0x200u;if(!panel_model(model)||model==15)keep=0;
 if(model&&(U->active>>16)!=model)U->active=0;
#else
 u32 keep=0;
#endif
 int active=model && registry(model);
 if(active){
  if(!U->active || U->view!=(u32)v){
   U->view=(u32)v;U->active=1u|(model<<16)|keep;U->third=B(v,0x4828+0x30);U->wave=B(v,0x71c0+0x30);
#ifdef BENTO_SYNCUSSION
   for(u32 i=0;i<12;i++)U->wave|=(u32)(B(v,panel_hidden[i]+0x30)!=0)<<(8+i);
#endif
  }
  entry(W(v,0x87bc),model);rows(v,1);
  /* Key zero does not clear native text overrides left by the previous model. */
  for(u32 row=0;row<3;row++)for(u32 i=0;i<8;i++)if(!H(v,0x703c+row*0x50+i*2)){
   void *bar=(u8*)v+0x38+row*0x23f8,*slot=(u8*)bar+0x38+i*0x468;
   NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,0);
   ui_slot(slot,0,0,"");
  }
  B(v,0x4828+0x30)=model==1||model==15?0:1;B(v,0x71c0+0x30)=1;
#ifdef BENTO_SYNCUSSION
  if(panel_model(model))B(v,0x4828+0x30)=0;
#endif
 }else if(U->active && U->view==(u32)v){rows(v,0);
 for(u32 row=0;row<3;row++)for(u32 i=0;i<8;i++){
  void *bar=(u8*)v+0x38+row*0x23f8;u32 key=H(v,0x703c+row*0x50+i*2),value=0;
  NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,0);
  ui_get((u8*)v+0x87bc,key,&value);
  ui_slot_set((u8*)bar+0x38+i*0x468,key,(int)value);
 }
 B(v,0x4828+0x30)=(u8)U->third;B(v,0x71c0+0x30)=(u8)U->wave;U->active=0;
 /* Only the native constructor (08153560) places this label; restore its
  * rect and text so the drum title is not left in the sample footer. */
 void *title=(u8*)v+0x80b4;if(!W(title,0))return; /* not constructed yet */
 if(W(title,8)!=50||W(title,16)!=216){int r[4]={6,50,318,216};FN(W((void*)W(title,0),0x20),void(*)(void*,void*))(title,r);}
 NFN(0x0817e85e,void(*)(void*,const char*))(title,"Filename");}
}
static __attribute__((section(".pad2"))) void text_value(void *bar,u32 index,u32 value,int percent){
 char text[16];u32 at=0;if(value>=1000)text[at++]='0'+value/1000%10;if(value>=100)text[at++]='0'+value/100%10;if(value>=10)text[at++]='0'+value/10%10;text[at++]='0'+value%10;
 if(percent)text[at++]='%';else{text[at++]=' ';text[at++]='H';text[at++]='z';}text[at]=0;
 NFN(0x08170656,void(*)(void*,u32,const char*))(bar,index,text);
}
#ifdef BENTO_SYNCUSSION
__attribute__((used,retain)) int drum_panel(void *bar,u32 *values){
 if(!U->active||!U->view)return 0;void *v=(void*)U->view;
 if(W(v,0)!=0x0819e624u||B(v,0x30))return 0;
 u32 model=kick_ui_supported(v);if(!panel_model(model))return 0;
 if(bar==(u8*)v+0x2430)return panel_mix()?3:0;
 int row=bar==(u8*)v+0x38?1:bar==(u8*)v+0x4828?2:0;if(!row)return 0;
 KickKnob *e=entry(W(v,0x87bc),model);
 if(values){for(u32 i=0;i<7;i++)values[i]=motion_value(e,kick_keys[i],e->values[i]);values[7]=model==15?CLICKS[e-KNOBS->entries]:motion_value(e,CLICK_KEY,CLICKS[e-KNOBS->entries]);values[8]=model==15?motion_value(e,CLICK_KEY,attack_value(e)):0;values[9]=W(v,0x87bc);values[10]=model;}
 if(values&&kit_seq_holding())for(u32 i=0;i<8;i++){int status=0;values[i]=kit_seq_value(i==7?CLICK_KEY:kick_keys[i],(int)values[i],&status);}
 return row;
}
/* R6.4: the engine row, if the drum screen is up (direct touch routing). */
void *drum_panel_row(void){void *b=U->view?(u8*)U->view+0x4828:0;return b&&drum_panel(b,0)==2?b:0;}
const char *drum_panel_label(u32 model,u32 index){return index==7?click_name:index==8?attack_name:label(model,index);} /* run 15: 8 = Metal's Attack column */
int kick_ui_event(void*,const void*);
static __attribute__((noinline,section(".panel"))) void panel_layout(void *v){
 for(u32 row=0;row<3;row++)if(W((u8*)v+0x38+row*0x23f8,0)!=0x081b2838u)return;
 for(u32 row=0;row<3;row++){
  void *bar=(u8*)v+0x38+row*0x23f8;
  /* Mix takes the switch row's place at its full height (owner). */
  int r[4]={6,row==0?49:row==1?407:382,1268,row==0?333:row==1?73:90}; /* R6.5: Mix strip at the native header strip position (top, 73 px) */
  B(bar,0x30)=row==0?0:row==1?!panel_mix():panel_mix();
  if(W(bar,8)!=(u32)r[1]||W(bar,16)!=(u32)r[3])
   FN(W((void*)W(bar,0),0x20),void(*)(void*,void*))(bar,r);
 }
 void *title=(u8*)v+0x80b4;
 if(W(title,8)!=8||W(title,16)!=39){
  int r[4]={6,8,780,39};
  FN(W((void*)W(title,0),0x20),void(*)(void*,void*))(title,r);
 }
 void *group=(void*)W((u8*)v+0x38,0x2c);
 if(group&&W(group,0x204)==3){
  u32 selected=panel_mix()?1u:panel_engine_row()?2u:0u;
  if(W(group,0x39c)!=selected)NFN(0x08170c86,void(*)(void*,u32))(group,selected);
  void *bar=(u8*)v+0x38+selected*0x23f8,*box=(u8*)group+0x208;
  if(W(box,8)!=W(bar,8)||W(box,16)!=W(bar,16)){
   int r[4]={(int)W(bar,4),(int)W(bar,8),(int)W(bar,12),(int)W(bar,16)};
   FN(W((void*)W(box,0),0x20),void(*)(void*,void*))(box,r);
  }
 }
}
/* R6.3: the native control group moves its white box to the row a finger
 * touches; the engine row is not a focus area, so it goes straight back. */
__attribute__((noinline)) void drum_panel_focus_fix(void){
 void *v=(void*)U->view;if(!v||U->magic!=0x3756494bu||B(MODEL,0x12c)!=8)return;
 void *group=(void*)W((u8*)v+0x38,0x2c);if(!group||W(group,0x204)!=3)return;
 u32 want=panel_mix()?1u:panel_engine_row()?2u:0u;
 if(W(group,0x39c)!=want){NFN(0x08170c86,void(*)(void*,u32))(group,want);B(v,0x31)=1;}
 /* R6.5 (owner: a full-width rectangle above the footer after touching the
  * lower third): a native release shrinks the focus box (+208) to a 70 px strip
  * at the bottom; keep it on the whole selected row. */
 void *box=(u8*)group+0x208,*bar=(u8*)v+0x38+want*0x23f8;
 if(W(box,8)!=W(bar,8)||W(box,16)!=W(bar,16)||W(box,4)!=W(bar,4)||W(box,12)!=W(bar,12)){
  int r[4]={(int)W(bar,4),(int)W(bar,8),(int)W(bar,12),(int)W(bar,16)};
  FN(W((void*)W(box,0),0x20),void(*)(void*,void*))(box,r);B(v,0x31)=1;}
}
__attribute__((section(".pad2"))) int drum_panel_rows(u32 code,u32 index){
 if((code!=0xaf&&code!=0xb0)||(index!=1&&index!=8)||!panel_visible())return 0;
 if(code==0xb0)return 1;
 if(!panel_mix()&&kit_seq_holding()){kit_seq_step_focus(index==1);return 1;}
 /* R6.3 (owner): only the fader rectangle exists; Up/Down no longer focus the engine row. */
 U->active&=~0x200u;
 void *v=(void*)U->view;panel_layout(v);
 B(v,0x31)=1;B(v,0x38+0x31)=1;B(v,0x4828+0x31)=1;B((void*)0x30034d48u,NOFF_ROOT_LAYOUT)=1;
 return 1;
}
#endif
__attribute__((used,retain)) void kick_ui_after(void *v){
 if(!U->active || U->view!=(u32)v){kit_seq_after(v);return;}
 u32 model=kick_ui_supported(v);if(!model)return;
 KickKnob *e=entry(W(v,0x87bc),model);void *bar=(u8*)v+0x38;
#ifdef BENTO_SYNCUSSION
 if(panel_model(model)){
  panel_layout(v);
  /* Native sample-info/range widgets otherwise erase cached fader pixels. */
  for(u32 i=0;i<12;i++)B(v,panel_hidden[i]+0x30)=1;
 }
#endif
 for(u32 i=0;i<drum_count(model);i++){
  void *slot=(u8*)bar+0x38+(i+1)*0x468;
#ifdef BENTO_SYNCUSSION
  if(model<=9)slot=(u8*)bar+0x38+i*0x468;
  if(model==15&&i==0)slot=(u8*)bar+0x38;
  if(model==15&&i==0){
   void *mode=(u8*)bar+0x38+0x468;
   u32 attack=motion_value(e,CLICK_KEY,attack_value(e));
   ui_slot(mode,CLICK_KEY,attack,attack_name);
   text_value(bar,1,attack,1);
  }
#endif
  u32 value=motion_value(e,kick_keys[i],e->values[i]);
  ui_slot(slot,kick_keys[i],value,label(model,i));
  u32 column=i+1;
#ifdef BENTO_SYNCUSSION
  if(model<=9||(model==15&&i==0))column=i;
#endif
  text_value(bar,column,i==0?drum_tune_hz(model,value):value,i!=0);
 }
 if(model==1){
  void *third=(u8*)v+0x4828;
  u32 column=0;
#ifdef BENTO_SYNCUSSION
  if(model==1){third=bar;column=7;}
#endif
  void *slot=(u8*)third+0x38+column*0x468;
  u32 value=motion_value(e,CLICK_KEY,CLICKS[e-KNOBS->entries]);
  ui_slot(slot,CLICK_KEY,value,click_name);
  text_value(third,column,value,1);
 }
#ifdef BENTO_SYNCUSSION
 if(panel_model(model)&&model!=15)ui_slot_set((u8*)v+0x4828+0x38,LOAD_KEY,(int)model_slot(model));
#endif
 char title[56];const char *prefix=model_names[model_slot(model)];u32 at=0;while(prefix[at]){title[at]=prefix[at];at++;}const char *pad_text=" / Pad ";for(u32 c=0;pad_text[c];c++)title[at++]=pad_text[c];u32 n=pad(v)+1;if(n>=10)title[at++]='1';title[at++]='0'+n%10;
 title[at]=0;
 NFN(0x0817e85e,void(*)(void*,const char*))((u8*)v+0x80b4,title);
#ifdef BENTO_SYNCUSSION
 if(panel_model(model))panel_header_refresh();
#endif
 /* Illustrative envelope in the existing native envelope widget. Audio's own
  * amplitude envelope is untouched; pitch-sweep drawing is deferred. */
 NFN(0x081689f8,void(*)(void*,u32,u32,u32,u32))((u8*)v+0x710c,0,e->values[1]*10,0,0);
 kit_seq_after(v);
}
__attribute__((used,retain)) int kick_ui_event(void *v,const void *event){
 if(kit_seq_event(v,(void*)event))return 1;
#ifdef BENTO_SYNCUSSION
 if(drum_panel_navigation(MODEL,(void*)event))return 1;
#endif
 if(H(event,0)!=0xcf)return 0;
 u32 model=kick_ui_supported(v);if(!model)return 0;
 u32 key=W(event,8);int value=(int)W(event,12);init();
 for(u32 i=0;i<8;i++)if(key==(i==7?CLICK_KEY:kick_keys[i])){
#ifdef BENTO_SYNCUSSION
  if(panel_model(model)){
   if(i>=drum_count(model)&&!(i==7&&(model==1||model==15)))return 1;
   extern int motion_capture_event(void*);if(motion_capture_event((void*)event)){B(v,0x31)=1;return 1;}
   KickKnob *e=entry(W(v,0x87bc),model);
   int lo=i==0&&drum_family(model)==1?25:0,hi=i==0&&drum_family(model)==1?180:100;
   if(value<lo)value=lo;if(value>hi)value=hi;update(e,i==7&&model==15?8:i,(u32)value);
   ui_commit();
   /* Native turn handling retains its accumulator and updates the slot itself. */
   void *bar=(u8*)v+0x38;
   B(bar,0x31)=1;if(model!=15)B(v,0x4828+0x31)=1;B(v,0x31)=1;return 1;
  }
#endif
  if(i==7&&model!=1)return 1;
  int lo=i==0&&drum_family(model)==1?25:0,hi=i==0&&drum_family(model)==1?180:100;if(value<lo)value=lo;if(value>hi)value=hi;
  update(entry(W(v,0x87bc),model),i,(u32)value);ui_commit();NFN(0x08152144,void(*)(void*))(v);return 1;
 }
 if(key==PAD_KEY){if(value<1)value=1;if(value>16)value=16;NFN(0x08152acc,void(*)(void*,u32))(v,(u32)value-1);return 1;}
 /* D1: Engine (was Browse) swaps the pad's synth; the pad keeps its place. */
 if(key==LOAD_KEY){if(value<0)value=0;
#ifdef BENTO_SYNCUSSION
 if(value>5)value=5;
 if(panel_model(model)&&panel_engine_row()&&value>4)value=4;
#else
 if(value>4)value=4;
#endif
 if((u32)value!=model_slot(model)||drum_stale(v)){u32 cell=W(v,0x87bc);DIAG(5,cell,model,(u32)value,pad(v));if(!drum_assign(pad(v),&cell,(u32)value))NFN(0x08104c00,void(*)(const char*))("Drum: assign failed");NFN(0x08152144,void(*)(void*))(v);}return 1;}
 return 0;
}
int kick_base_value(void *v,u32 key,int *value){
 u32 model=kick_ui_supported(v);
 if(model){
  KickKnob *e=entry(W(v,0x87bc),model);
  for(u32 i=0;i<7;i++)if(key==kick_keys[i]){*value=e->values[i];return 1;}
  if(key==CLICK_KEY){
#ifdef BENTO_SYNCUSSION
   *value=model==15?(int)attack_value(e):(int)CLICKS[e-KNOBS->entries];
#else
   *value=CLICKS[e-KNOBS->entries];
#endif
   return 1;
  }
 }
 return ui_get((u8*)v+0x87bc,key,value);
}
/* Versioned attributes on the pad's existing params element. They do not
 * consume native automation lanes or change any original property value. */
static const char *const attrs[7]={"bento_kick_v1_tune","bento_kick_v1_decay","bento_kick_v1_tone","bento_kick_v1_impact","bento_kick_v1_sweep","bento_kick_v1_sweep_decay","bento_kick_v1_dirt"};
static void analog_save(void *object,void *params);
static void analog_load(void *node,void *object);
extern void macro_save(void*,void*);extern void macro_load(void*,void*);extern int macro_increment(void*,int);
__attribute__((used,retain)) void kick_ui_save(void *object,void *params){
 macro_save(object,params); /* P27 */
#if BENTO_FW==168
 {extern void xy_save(void*,void*) __attribute__((weak));if(xy_save)xy_save(object,params);} /* P168 exp8: XY send state on the Master track */
#endif
 if(object && params && B(object,4)==18){analog_save(object,params);return;}
 if(!object || !params || (B(object,4)!=1 && B(object,4)!=2))return;
 init();u32 click,attack;KickKnob *e=drum_saved(W(object,0x10),&click,&attack);if(!e)return;
 void *a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_kick_version");if(!a)return;
 NFN(0x0810958e,void(*)(void*,u32))(a,1);
 a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_drum_model");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,MOD_ENGINE(e->reserved));
 if(MOD_TAG(e->reserved)){a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_mod_engine");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,MOD_TAG(e->reserved));}
 a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_drum_v2_click");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,click);
#ifdef BENTO_SYNCUSSION
 if(MOD_ENGINE(e->reserved)==15){a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_syncussion_attack");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,attack);}
#endif
 for(u32 i=0;i<7;i++){a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,attrs[i]);if(a)NFN(0x0810958e,void(*)(void*,u32))(a,e->values[i]);}
}
__attribute__((used,retain)) void kick_ui_load(void *node,void *object){
 macro_load(node,object); /* P27 */
#if BENTO_FW==168
 {extern void xy_load(void*,void*) __attribute__((weak));if(xy_load)xy_load(node,object);} /* P168 exp8 */
#endif
 if(node && object && B(object,4)==18){analog_load(node,object);return;}
 if(!node || !object || (B(object,4)!=1 && B(object,4)!=2) || !W(object,0x10))return;
 init();void *params=NFN(0x08109268,void*(*)(void*,const char*))(node,"params");
 u32 version=0;void *a=params?NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_kick_version"):0;
 int valid=a && !NFN(0x08109566,int(*)(void*,void*))(a,&version) && version==1;
 u32 model=1;void *m=valid?NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_drum_model"):0;if(m)NFN(0x08109566,int(*)(void*,void*))(m,&model);
#ifdef BENTO_SYNCUSSION
 if(model!=15)
#endif
 if(model!=1&&model!=3&&model!=5&&model!=7&&model!=9)model=1;
 KickKnob *e=valid?entry(W(object,0x10),model):existing(W(object,0x10));if(!e)return;
 for(u32 i=0;i<7;i++){
  int value=drum_defaults(model)[i];u32 raw=0;
  a=valid?NFN(0x08109c64,void*(*)(void*,const char*))(params,attrs[i]):0;
  if(a && !NFN(0x08109566,int(*)(void*,void*))(a,&raw))value=(int)raw;
  int lo=i==0&&drum_family(model)==1?25:0,hi=i==0&&drum_family(model)==1?180:100;if(value<lo)value=lo;if(value>hi)value=hi;update(e,i,(u32)value);
 }
 // Migrate old kicks with no Click attribute to their saved Tone amount.
 u32 cv=model==15?0:e->values[2];a=valid?NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_drum_v2_click"):0;
 if(a)NFN(0x08109566,int(*)(void*,void*))(a,&cv);if(cv>(model==15?107u:100u))cv=model==15?0:100;update(e,7,cv);
#ifdef BENTO_SYNCUSSION
 if(model==15){
  u32 av=0;a=valid?NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_syncussion_attack"):0;
  if(a&&NFN(0x08109566,int(*)(void*,void*))(a,&av)){NFN(0x08104c00,void(*)(const char*))("Sync: bad attack");av=0;}
  if(av>100){NFN(0x08104c00,void(*)(const char*))("Sync: attack range");av=100;}
  if(av||sync_attack(0))update(e,8,av);
 }
#endif
 u32 tag=0;a=valid?NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_mod_engine"):0;
 if(a && NFN(0x08109566,int(*)(void*,void*))(a,&tag))tag=0;
#ifdef BENTO_SYNCUSSION
 if(tag!=15)
#endif
 if(tag!=1&&tag!=3&&tag!=5&&tag!=7&&tag!=9)tag=0;set_tag(e,tag);
}

/* Normalize the range, not whole value steps. The native quantizer retains
 * fine movement and its timestamp history supplies the native acceleration. */
static __attribute__((section(".panel"))) int drum_turn(void *slot,int delta){
 int lo=(int)W(slot,0x450),hi=(int)W(slot,0x454);u32 quantum=W(slot,0x88);
 if(quantum&&quantum<=160000u&&hi>lo){
  long long out=(long long)delta*(hi-lo)*quantum/160000;
  if(out>0x15555555)return 0x15555555;if(out<-0x15555555)return -0x15555555;
  return (int)out;
 }
 if(delta>0x10000000)delta=0x10000000;if(delta<-0x10000000)delta=-0x10000000;return delta*5;
}
/* One global raw-delta adjustment, before either macro or native ownership.
 * Range normalization remains distinct from the user setting. */
__attribute__((used,retain)) int kick_ui_increment(void *slot,int delta){
 int direct=kit_seq_increment(slot);if(direct==2)return 0;
 if(direct==1){
  delta=encoder_speed_delta(slot,delta);u32 key=H(slot,0x9c);int synth=key==CLICK_KEY;
  for(u32 i=0;i<7;i++)if(key==kick_keys[i])synth=1;
  return synth?drum_turn(slot,delta):delta;
 }
 extern void motion_capture_begin(void*,int);motion_capture_begin(slot,0);
 delta=encoder_speed_delta(slot,delta);
 if(macro_increment(slot,delta))return 0; /* P27: macro strip owns the encoders */
 u32 key=H(slot,0x9c);int ours=key==CLICK_KEY || key==NKEY(0x195);for(u32 i=0;i<7;i++)if(key==kick_keys[i])ours=1;
 if(!ours)delta=encoder_fx_delta(slot,delta); /* Track FX and wide number fields; the drum knobs have drum_turn */
 motion_capture_begin(slot,delta);
 if(!ours)return delta;
 return drum_turn(slot,delta);
}

__attribute__((used,retain)) u32 drum_ui_step(u32 parent,u32 row,u32 *values){
 u32 cell=0,index=0,file=0;char path[256];
 for(u32 i=0;i<128;i++){
  if(!ui_child(&parent,i,&cell))break;
  u32 type=ui_type(&cell);if(type!=1 && type!=2)continue;
  ui_get(&cell,0x73,&index);if(index!=row)continue;
  if(!ui_child(&parent,i+1,&file))return 0;
  if(ui_type(&file)!=5)return 0;
  path[0]=0;NFN(0x0813390e,int(*)(void*,void*,u32,char*))(MODEL,&file,0x81,path);u32 model=drum_file_model(file,path);if(!model || !registry(model))return 0;
  init();KickKnob *e=entry(cell,model);if(values){for(u32 j=0;j<7;j++)values[j]=e->values[j];values[7]=CLICKS[e-KNOBS->entries];}return model;
 }return 0;
}

/* CH11: drum-synth destinations in the native Mod Matrix (see mod_matrix.h).
 * Engine of a one-shot cell: same walk as drum_ui_step (cell, then its file). */
static u32 cell_model(u32 parent,u32 handle){
 u32 cell=0,file=0;char path[256];
 for(u32 i=0;i<128;i++){
  if(!ui_child(&parent,i,&cell))return 0;
  if(cell!=handle)continue;
  u32 type=ui_type(&cell);if(type!=1 && type!=2)return 0;
  if(!ui_child(&parent,i+1,&file))return 0;
  if(ui_type(&file)!=5)return 0;
  path[0]=0;NFN(0x0813390e,int(*)(void*,void*,u32,char*))(MODEL,&file,0x81,path);return drum_file_model(file,path);
 }return 0;
}
static const char *mod_label(u32 model,u32 j){return j==7?
#ifdef BENTO_SYNCUSSION
 model==15?attack_name:
#endif
 click_name:label(model,j);}
static void row_name(char *out,u32 model,u32 j){
 const char *a=model_names[model_slot(model)],*b=mod_label(model,j);u32 n=0;
 while(*a&&n<15)out[n++]=*a++;if(n<15)out[n++]=' ';while(*b&&n<15)out[n++]=*b++;while(n<16)out[n++]=0;
}
/* Called at 0814CE80, after the native one-shot rows (types 1/2) are built.
 * Matrix view +8AC44 cell, +8AC4D rows, +8AC50 keys (u16), +8ACCC row handles,
 * +8ADBC row byte, +8AE04 names (16 bytes). frame = the builder's stack, whose
 * +338 holds the current track. A synth pad lists its engine's parameters
 * first, then the native rows minus the sample envelope (Attack/Decay/Release),
 * which the synth instrument page does not offer. */
__attribute__((used,retain)) void mod_rows(void *view,void *frame){
 u8 *m=(u8*)view+0x8a000;u32 cell=W(m,0xc44),n=B(m,0xc4d);
 u32 model=cell&&n<=16?cell_model(W(frame,0x338),cell):0;if(!model)return;
 init();KickKnob *e=entry(cell,model);registry(model);
 u32 tag=MOD_TAG(e->reserved),shown=tag?tag:model,count=mod_count(shown);
 /* In place, no large stack buffers: drop the envelope rows, move the rest
  * down by count, then write the synth rows on top. */
 u32 k=0;
 for(u32 i=0;i<n;i++){
  u32 key=H(m,0xc50+2*i);if(key==0x1e||key==0x1f||key==0x21)continue;
  if(k!=i){H(m,0xc50+2*k)=(unsigned short)key;W(m,0xccc+4*k)=W(m,0xccc+4*i);B(m,0xdbc+k)=B(m,0xdbc+i);for(u32 c=0;c<16;c++)B(m,0xe04+16*k+c)=B(m,0xe04+16*i+c);}
  k++;
 }
 for(u32 i=k;i-->0;){u32 r=count+i;H(m,0xc50+2*r)=H(m,0xc50+2*i);W(m,0xccc+4*r)=W(m,0xccc+4*i);B(m,0xdbc+r)=B(m,0xdbc+i);for(u32 c=0;c<16;c++)B(m,0xe04+16*r+c)=B(m,0xe04+16*i+c);}
 for(u32 j=0;j<count;j++){H(m,0xc50+2*j)=mod_keys[j];W(m,0xccc+4*j)=cell;B(m,0xdbc+j)=0;row_name((char*)m+0xe04+16*j,shown,j);}
 B(m,0xc4d)=(u8)(count+k);
}
/* Saved destination names: 0812F6A2 (write) and 0812FE52 (read) call these
 * instead of the registry token lookups. Synth descriptors exist only lazily. */
__attribute__((used,retain)) const char *mod_token(u32 key){
 int j=mod_index(key);return j>=0?mod_tokens[j]:NFN(0x081666f8,const char*(*)(u32))(key);
}
__attribute__((used,retain)) u32 mod_key(const char *s){
 for(u32 j=0;s&&j<MOD_PARAMS;j++){const char *t=mod_tokens[j];u32 i=0;while(t[i]&&s[i]==t[i])i++;if(!t[i]&&!s[i])return mod_keys[j];}
 return NFN(0x08166720,u32(*)(const char*))(s);
}
/* 08140924: a matrix edit (event: +4 cell, +8 key). Editing a synth route
 * adopts the pad's routes for its current engine. */
__attribute__((used,retain)) u32 mod_edit(void *model,void *event){
 if(mod_index(H(event,8))>=0){KickKnob *e=existing(W(event,4));if(e)set_tag(e,MOD_ENGINE(e->reserved));}
 return NFN(0x08133388,u32(*)(void*,void*))(model,event);
}

/* A1 "Analog": a native Wavetable track (type 18) whose WT1/WT2 play analog
 * oscillators on M7. The track's handle gets a KickKnob entry with engine 13;
 * values[0] is Sync (0 off). It is created from the native instrument menu
 * (action 1052 in the free ninth cell) and saved on the track's params as
 * bento_analog / bento_analog_sync / bento_analog_glide (values[1], 0..100).
 * Stock firmware sees a Wavetable track. */
#define ANALOG 13u
#define ANALOG_ACTION 0x1052u
void analog_registry(void);
const char analog_label[] __attribute__((used,retain))="Analog";
static KickKnob *analog_entry(u32 handle){KickKnob *e=existing(handle);return e && MOD_ENGINE(e->reserved)==ANALOG?e:0;}
static __attribute__((noinline,section(".stepdraw"))) void knob_clear(KickKnob *e){
 u32 serial=(KNOBS->serial+2u)&~1u;if(!serial)serial=2;
 e->sequence=serial|1u;__asm__ volatile("dsb" ::: "memory");e->handle=0;e->reserved=0;
 __asm__ volatile("dsb" ::: "memory");e->sequence=0;KNOBS->serial=serial;__asm__ volatile("dsb" ::: "memory");
}
static void analog_clear(u32 handle){KickKnob *e=analog_entry(handle);if(e)knob_clear(e);}
static void analog_mark(u32 handle,u32 sync){if(!handle)return;init();KickKnob *e=entry(handle,ANALOG);if(e->values[0]!=(sync?1:0))update(e,0,sync?1:0);}
__attribute__((used,retain)) int analog_track(u32 handle){return analog_entry(handle)!=0;}
static void analog_save(void *object,void *params){
 u32 click,attack;KickKnob *e=drum_saved(W(object,0x10),&click,&attack);if(!e||MOD_ENGINE(e->reserved)!=ANALOG)return;
 void *a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_analog");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,1);
 a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_analog_sync");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,e->values[0]);
 a=NFN(0x08109cdc,void*(*)(void*,const char*))(params,"bento_analog_glide");if(a)NFN(0x0810958e,void(*)(void*,u32))(a,e->values[1]);
}
static void analog_load(void *node,void *object){
 u32 handle=W(object,0x10);if(!handle)return;init();
 void *params=NFN(0x08109268,void*(*)(void*,const char*))(node,"params");u32 on=0,sync=0;
 void *a=params?NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_analog"):0;
 if(a && NFN(0x08109566,int(*)(void*,void*))(a,&on))on=0;
 if(!on){analog_clear(handle);return;}
 a=NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_analog_sync");if(a && NFN(0x08109566,int(*)(void*,void*))(a,&sync))sync=0;
 analog_mark(handle,sync);
 u32 glide=0;a=NFN(0x08109c64,void*(*)(void*,const char*))(params,"bento_analog_glide");if(a && NFN(0x08109566,int(*)(void*,void*))(a,&glide))glide=0;
 if(glide>100)glide=100;KickKnob *e=analog_entry(handle);if(e && e->values[1]!=glide)update(e,1,glide);
}
#define current_track ui_current_track
__attribute__((weak,noinline,section(".text.sls"))) u32 ui_current_track(void){u32 t=0;return ui_owner(&t)?t:0;}
/* Instrument menu handler (view vtable 0819E52C, native 0814ECD4). */
__attribute__((used,retain)) u32 analog_menu_event(void *view,void *event){
 u32 code=H(event,0);
 if(code==ANALOG_ACTION){
  /* Same as the native Wavetable action (0814EF4E), then mark the track. */
  u32 index=0;ui_get((void*)0x30030164u,0x131,&index);
  u32 ev[5]={0x42,0,6,index,0};NFN(0x0816fc34,void(*)(void*,void*))(view,ev);
  u32 t=current_track();if(t && ui_type(&t)==18){analog_registry();analog_mark(t,0);}
  u32 nav[5]={0x16,0,0,0,0};NFN(0x0816fc34,void(*)(void*,void*))(view,nav);
  ui_commit();return 0;
 }
 if(code==NUI(0x102a)){u32 t=current_track();if(t)analog_clear(t);}
 return NFN(0x0814ecd4,u32(*)(void*,void*))(view,event);
}

/* D1: drum synths without files to copy (owner, 2026-10-24).
 * The firmware writes the five synth marker WAVs itself (only when missing)
 * and loads one onto the pad through the native "file onto pad" function the
 * recorder uses (08139DE0: model, track index, &cell or &0, pad, path, 0).
 * One-shot pad menus get a "Drum Synth" entry (Kick); the synth page's second
 * bottom knob, Engine, switches Kick/Snare/HiHat/Clap/Tom. */
#define DRUM_ACTION 0x1056u
#define MENUS ((u8*)0x30030168u)
static const char drum_label[]="Drum Synth";
/* P7: files live in the firmware's own SD folder "Drum Synths" (drum_path
   recognises them there), so Load on an empty cell finds them in the browser. */
static const char drum_dir[]="Drum Synths";
__attribute__((used)) const char *const drum_files[]={"Kick.wav","Snare.wav","HiHat.wav","Clap.wav","Tom.wav"
#ifdef BENTO_SYNCUSSION
 ,"Metal.wav" /* R6.6 (owner: browser showed Syncussion); run 14: "Syncussion Melodic.wav" retired */
#endif
};
static u32 drum_frames(u32 engine){return engine>=5?144023u+2u*engine:144019u+2u*engine;}
static void fs_zero(u32 *f){for(u32 i=0;i<22;i++)f[i]=0;}
static int fs_write(void *f,const void *data,u32 n){u32 done=0;return !NFN(0x08120604,u32(*)(void*,const void*,u32,u32*))(f,data,n,&done)&&done==n;}

#ifdef BENTO_DRUM_DIAG
/* Diagnostic build only (owner 7 Nov: drum crash / engine switch). A ring of
 * short lines on the native heap, rewritten to SD "Drum Synths/diag.txt" after
 * every event, so the last lines survive a crash. Title shows the live state. */
static __attribute__((noinline,section(".kitinput"))) void diag_resume(DiagLog *d){
static const char fs[]="\\Drum Synths\\diag.bin";u32 file[22],got=0;fs_zero(file); /* continue the previous boot's log */
  if(!NFN(0x08120148,u32(*)(void*,const char*,u32))(file,fs,1)){NFN(0x08120464,u32(*)(void*,void*,u32,u32*))(file,d,sizeof(*d),&got);NFN(0x08120974,u32(*)(void*))(file);}
  if(got!=sizeof(*d)||d->magic!=DIAG_MAGIC){zero(d,sizeof(*d));d->magic=DIAG_MAGIC;}d->last_o=0;
 /* a reboot shows as the time restarting near zero */
}
static __attribute__((noinline)) DiagLog *diag_log(int create){
 DiagLog *d=(DiagLog*)KNOBS->reserved[2];u32 p=(u32)d;
 if(p>=0xc0000010u&&p<0xc1000000u&&!(p&3u)&&d->magic==DIAG_MAGIC)return d;
 if(!create)return 0;
 d=(void*)ui_alloc(sizeof(DiagLog),sizeof(DiagLog)+32u);if(!d)return 0;
 zero(d,sizeof(*d));d->magic=DIAG_MAGIC;KNOBS->reserved[2]=(u32)d;
 diag_resume(d);
 return d;
}
static __attribute__((noinline,section(".cycleundo"))) char *hx(char *o,u32 v){
 int started=0;for(int i=28;i>=0;i-=4){u32 c=(v>>i)&15u;if(c||started||!i){*o++="0123456789abcdef"[c];started=1;}}return o;
}
/* Binary records {tag,time,a,b,c,d} (64-entry ring, oldest first after wrap);
 * decoded off-device. */
static __attribute__((noinline,section(".stepui"))) void diag(u32 tag,u32 a,u32 b,u32 c,u32 e){
 DiagLog *d=diag_log(tag>=4);if(!d)return;u32 *r=d->rec[d->n++&63u];
 r[0]=tag;r[1]=W((void*)0x3001fe2cu,0);r[2]=a;r[3]=b;r[4]=c;r[5]=e;
 if(tag!=4&&tag!=9)return; /* card writes only on a calm page open, never around a switch or a save */
 static const char fs[]="\\Drum Synths\\diag.bin";
 u32 file[22];fs_zero(file);if(NFN(0x08120148,u32(*)(void*,const char*,u32))(file,fs,10))return;
 fs_write(file,d,sizeof(*d));NFN(0x08120974,u32(*)(void*))(file);
}
static __attribute__((noinline,section(".kitlock"))) u32 diag_slot(u32 handle){
 for(u32 i=0;i<16;i++){u32 a=0x24042010u+i*0xecu;if(W((void*)a,0)&&W((void*)a,4)==handle)return 1;}return 0;
}
#endif
static void drum_header(u32 *h,u32 frames){
 u32 bytes=frames*2u;h[0]=0x46464952u;h[1]=36u+bytes;h[2]=0x45564157u;h[3]=0x20746d66u;h[4]=16;h[5]=0x00010001u;h[6]=48000;h[7]=96000;h[8]=0x00100002u;h[9]=0x61746164u;h[10]=bytes;
}
static void drum_signature(u8 *p){for(u32 i=0;i<32;i++){u32 v=(0xb1e70a5cu&(1u<<i))?1u:0xffffu;p[i*2]=(u8)v;p[i*2+1]=(u8)(v>>8);}}
/* P168 exp3: the main thread's report to the native watchdog monitor (081082F8 compares its tick +8 with
 * the main thread's last report +4; native 081082D8 does exactly this store and also timestamps an RTC
 * backup register, which we leave to native code). */
/* exp7: report the thread that runs the card work: the file thread inside card_poll (+0, as native 081082E8),
 * otherwise the main thread (+4). */
static void ui_watchdog_main(void){volatile u32 *w=(volatile u32*)0x3000f624u;w[CARD->on_file?0:1]=w[2];}
/* An existing file must be exactly our marker; a missing or altered one is
 * (re)written. Only our reserved "Drum Synths/<engine>.wav" names reach this:
 * the UI picks the page by that name, so a changed copy otherwise shows the
 * engine page but plays as a silent sample and refuses selection (owner). */
__attribute__((used,retain)) int drum_ensure(const char *path,u32 frames){
 u32 file[22],h[11];u8 buffer[512];drum_header(h,frames);fs_zero(file);
 if(!NFN(0x08120148,u32(*)(void*,const char*,u32))(file,path,1)){
  u32 size=file[4],high=file[5],got=0;zero(buffer,108);
  u32 r=NFN(0x08120464,u32(*)(void*,void*,u32,u32*))(file,buffer,108,&got);u32 c=NFN(0x08120974,u32(*)(void*))(file);
  u8 sig[64];drum_signature(sig);int ok=!r&&!c&&got==108&&size==44u+frames*2u&&!high;
  for(u32 i=0;ok&&i<44;i++)if(buffer[i]!=((u8*)h)[i])ok=0;for(u32 i=0;ok&&i<64;i++)if(buffer[44+i]!=sig[i])ok=0;if(ok)return 1;
 }
 fs_zero(file);if(NFN(0x08120148,u32(*)(void*,const char*,u32))(file,path,10))return 0; /* create always, write (as the K7 report) */
 int ok=fs_write(file,h,44);zero(buffer,sizeof(buffer));drum_signature(buffer);if(ok)ok=fs_write(file,buffer,64);zero(buffer,64);
 for(u32 left=frames*2u-64u;ok&&left;){u32 n=left>sizeof(buffer)?sizeof(buffer):left;ok=fs_write(file,buffer,n);left-=n;if(!((left>>9)&63u))ui_watchdog_main();}
 u32 c=NFN(0x08120974,u32(*)(void*))(file);return ok&&!c;
}
/* Pad cell of the track (types 1/2, property 73 = pad), or 0. */
static __attribute__((section(".stepnote"))) u32 drum_cell(u32 track,u32 pad){
 u32 cell=0,index=0;
 for(u32 i=0;i<128;i++){
  if(!ui_child(&track,i,&cell))return 0;
  u32 type=ui_type(&cell);if(type!=1&&type!=2)continue;
  index=99;ui_get(&cell,0x73,&index);if(index==pad)return cell;
 }return 0;
}
__attribute__((used,retain)) int drum_assign(u32 pad,u32 *cell,u32 engine){
 if(engine>=sizeof(drum_files)/sizeof(*drum_files)||pad>15)return 0;
 char path[256],fs[260];path[0]=0;
 /* Native project path join (08127D7C uses it for "Projects" + name). */
 NFN(0x08104648,void(*)(char*,void*,const char*,const char*))(path,(void*)0x300010f4u,drum_dir,drum_files[engine]);
 u32 n=0;if(path[0]!='\\'&&path[0]!='/')fs[n++]='\\';for(u32 i=0;path[i]&&n<259;i++)fs[n++]=path[i];fs[n]=0;
 u32 index=0,track=0;ui_get((void*)0x30030164u,0x131,&index);
 if(!NFN(0x08133960,int(*)(void*,u32,u32*))(MODEL,index,&track)||!track)return 0;
 u32 type=ui_type(&track);
 if(type!=14)return 0; /* run 14: one-shot tracks only (melodic Syncussion retired) */
 u32 target=cell&&*cell?*cell:drum_cell(track,pad);
 /* exp7: the file thread verifies every carrier once per boot; until it has (posted/running), no card work here */
 u32 card=CARD->install;if(card==1||card==2||(card!=3&&!drum_ensure(fs,drum_frames(engine))))return 0;
 DIAG(6,target,engine,pad,type);
 NFN(0x08139de0,void(*)(void*,u32,u32*,u32,const char*,u32))(MODEL,index,&target,pad,path,0);
 DIAG(7,target,0,0,0);
 ui_commit();return 1;
}
/* Every one-shot pad menu (a native menu that offers Load WAV) gets the
 * entry; other track types never show it. Menus: 20 x 0xE0 at 30030168,
 * id +0, cells +4 (20 bytes: code, label, 0, 0, enabled), count +CC. */
__attribute__((used,retain,section(".stepnote"))) void drum_menus(int show){
 for(u32 m=0;m<20;m++){
  u8 *menu=MENUS+m*0xe0;u32 n=B(menu,0xcc);if(n>10)continue;int load=-1,ours=-1;
  for(u32 i=0;i<n;i++){u32 c=H(menu,4+i*20);if(c==NUI(0x1046))load=(int)i;if(c==DRUM_ACTION)ours=(int)i;}
  if(load<0)continue;
  if(show&&ours<0&&n<9){ /* native menu apply shows at most nine entries (EU8) */u8 *c=menu+4+n*20;zero(c,20);W(c,0)=DRUM_ACTION;W(c,4)=(u32)drum_label;B(c,16)=1;B(menu,0xcc)=(u8)(n+1);ours=(int)n;}
  if(show&&ours>=0)W(menu,8+(u32)ours*20)=(u32)drum_label;
  if(!show&&ours>=0){for(u32 i=(u32)ours;i+1<n;i++)for(u32 j=0;j<20;j++)B(menu,4+i*20+j)=B(menu,4+(i+1)*20+j);zero(menu+4+(n-1)*20,20);B(menu,0xcc)=(u8)(n-1);}
 }
}
static u32 track_type(void){u32 t=current_track();return t?ui_type(&t):0;}
static u32 drum_menu_mode(void){return track_type()==14;}
/* Model events (081403EC hook): menu opens (F0..100, 100C..100E) refresh the
 * entry; the entry itself turns the selected pad (track property 74) into a
 * Kick. The event goes on to the native handler, which closes the menu. */
/* One action per press even if both the model and the view see the code. */
static __attribute__((section(".steptext"))) void drum_action(void){
 u32 mode=drum_menu_mode();if(!mode)return;
 static volatile u32 *const when=(volatile u32*)0x24043d78u;u32 now=W((void*)0x3001fe2cu,0);
 if(*when&&now+1u-*when<300u)return;*when=now+1u; /* stored +1 so 0 means never */
 u32 t=current_track(),pad=0;if(t)ui_get(&t,0x74,&pad);
 if(pad<16&&!drum_assign(pad,0,0))NFN(0x08104c00,void(*)(const char*))("Drum: assign failed");
}
__attribute__((used,retain)) int drum_menu_event(void *event){
 {extern int pg_launch_action(void*);if(pg_launch_action(event))return 1;} /* P168 exp3: Launch footer actions at the model event entry (called from analog_model_event) */
 u32 code=H(event,0);
 if((code>=0xf0&&code<=0x100)||(code>=0x100c&&code<=0x100e)){drum_menus(drum_menu_mode());return 0;}
 if(code==DRUM_ACTION){drum_action();return 0;}
 return 0;
}
/* P6: 1.6P5 showed no entry on hardware: the menu-open requests evidently do
 * not all pass the model event entry. The entry is now kept in the menus from
 * every UI message (fx_dispatch), following the current track type, and the
 * action is also taken from the pad page view's event handler (0814888C,
 * vtable slot 0819DC50) in case the menu code goes to the view only. */
/* P7: once per boot (first UI message), make "\Drum Synths" and its five
   marker files if they are missing (about 1.4 MB the very first time; later
   boots only read 108 bytes per file). f_mkdir 08121152; FR_EXIST is fine. */
__attribute__((used,retain)) int drum_install_folder(void){
 int ok=1;NFN(0x08121152,u32(*)(const char*))("\\Drum Synths");
 /* P168 exp3 (boot watchdog records): this runs on the main thread, and every open searches the card's root
  * directory. Report to the native watchdog between files, as native card work on this thread does. */
 for(u32 i=0;i<sizeof(drum_files)/sizeof(*drum_files);i++){ui_watchdog_main();char fs[40];u32 n=0;const char *a="\\Drum Synths\\";while(*a)fs[n++]=*a++;for(const char *b=drum_files[i];*b;)fs[n++]=*b++;fs[n]=0;if(!drum_ensure(fs,drum_frames(i))){ok=0;NFN(0x08104c00,void(*)(const char*))("Drum: no carrier");}}
 return ok;
}
/* exp7: called by the file thread (hook before its idle queue wait, see CardBox): all our card work. */
__attribute__((used,retain)) void card_poll(void){
 CardBox *b=CARD;
 if(b->install!=1&&b->state!=1)return;
 b->on_file=1;
 if(b->install==1){b->install=2;b->install=drum_install_folder()?3:4;}
 if(b->state==1)card_check(b);
 b->on_file=0;
}
/* The native call it replaces: xQueueReceive(queue, item, 10) of the idle file thread (08112BF0). */
__attribute__((used,retain)) u32 card_idle_wait(void *queue,void *item,u32 ticks){
 card_poll();return NFN(0x0812236e,u32(*)(void*,void*,u32))(queue,item,ticks);
}
__attribute__((used,retain,section(".steptext"))) void drum_menu_tick(void){
 /* Only once the native menus exist (built at boot by 081412EC). */
 int any=0;for(u32 m=0;m<20&&!any;m++){u8 *menu=MENUS+m*0xe0;u32 n=B(menu,0xcc);for(u32 i=0;i<n&&i<10;i++)if(H(menu,4+i*20)==NUI(0x1046))any=1;}
 if(!any)return;
 if(!CARD->install)CARD->install=1; /* the UI is up (menus built): the file thread checks the folder (exp7) */
 drum_menus((int)drum_menu_mode());
}
__attribute__((used,retain)) u32 drum_view_event(void *view,void *event){
 if(H(event,0)==DRUM_ACTION){drum_action();return 0;}
 return NFN(0x0814888c,u32(*)(void*,void*))(view,event);
}


/* P4: Analog oscillator display. The Wavetable page (view class 0819E894)
 * shows WT1/WT2 in two wave panes (class 081B3A18, view +3550 and +36C8 =
 * oscillator index 0 and 1; label child at pane +104). P6: P4 hooked class
 * 081B3A98 (+2E90/+31F0), which the Wavetable builder (0815F6DA) hides; those
 * are the Granular panes, so nothing was drawn on hardware. On an Analog track the
 * pane hides its "No WAV" label and draws two cycles of the shape the
 * base Shape: saw > square > narrow pulse. Modulation does not animate this
 * display. Shape comes from the page's Position value (+10154 + 4 x index).
 * Manual changes are coalesced to at most about 30 redraws per second.
 * Paint gets ctx {full, partial, -, -, surface}; fills use 08166EF6. */
#define WAVE_VIEW 0x0819e894u
#define WAVE_STATE ((volatile u8*)0x24043d34u) /* shape0, shape1, flags (dirty 1/2, hidden 4/8), - ; +4 two 16-bit redraw times; +8 counter */
#define WFILL(r,c,s) NFN(0x08166ef6,void(*)(const int*,u32,u32))(r,c,s)
static int analog_pane(void *w,u32 *idx){
 u8 *p=(u8*)W(w,0x2c);if(!p||W(p,0)!=WAVE_VIEW)return 0;
 if((u8*)w==p+0x3550)*idx=0;else if((u8*)w==p+NOFF_SYNTH_KNOB2)*idx=1;else return 0;
 u32 t=current_track();return t&&ui_type(&t)==18&&analog_entry(t);
}
static u32 wave_shape(void *w,u32 idx){
 u8 *p=(u8*)W(w,0x2c);
 u32 v=W(p,NOFF_SYNTH_VALUES+idx*4);return v>255?255:v;
}
/* Integer only (UI core code stays free of floating point). */
__attribute__((used,retain)) int analog_wave_value(u32 shape,u32 q){
 int blend=shape*2>256?256:(int)shape*2,width=512-(shape>128?(int)((shape-128)*3373/1000):0);
 int saw=(int)(q&1023)*2-1024,pulse=(int)(q&1023)<width?1024:-1024;return (saw*(256-blend)+pulse*blend)/256;
}
static void wave_draw(void *w,u32 shape,u32 surface){
 int x=(int)W(w,4),y=(int)W(w,8),wd=(int)W(w,12),ht=(int)W(w,16);if(wd<40||ht<20)return;
 /* P7: the pane's own colours (+174 line, +175 background), as native waveforms. */
 u32 track_index=0;ui_get((void*)0x30030164u,0x131,&track_index);
 u32 line=NFN(0x08140ebc,u32(*)(u32))(track_index),bg=B(w,NOFF_WAVE(0x175))?B(w,NOFF_WAVE(0x175)):0xf1u;
 int r[4]={x,y,wd,ht};WFILL(r,bg,surface);
 int cy=y+ht/2,amp=ht*3/8,left=x+12,span=wd-24,prev=0;
 int mid[4]={left,cy,span,1};WFILL(mid,0xf3,surface);
 int col[4]={left,0,0,0};
 for(int i=0;i<span;i++){
  int v=analog_wave_value(shape,(u32)(i*2048/span)),yy=cy+v*amp/1024; /* native y grows towards the top of the screen (emulator renders) */
  int top=i?(prev<yy?prev:yy):yy,bot=i?(prev>yy?prev:yy):yy;
  int height=bot-top+2;
  if(col[2]&&col[1]==top&&col[3]==height)col[2]++;
  else{if(col[2])WFILL(col,line,surface);col[0]=left+i;col[1]=top;col[2]=2;col[3]=height;}
  prev=yy;
 }
 if(col[2])WFILL(col,line,surface);
}
__attribute__((used,retain)) void analog_wave_tick(void *w,void *flags){
 u32 idx=0;void *label=(u8*)w+NOFF_WAVE(0x104);
 if(!analog_pane(w,&idx)){
  /* Not Analog (any more): give the native label back once. */
  u8 *p=(u8*)W(w,0x2c);u32 i=p&&(u8*)w==p+NOFF_SYNTH_KNOB2?1:0;
  if(p&&W(p,0)==WAVE_VIEW&&(WAVE_STATE[2]&(4u<<i))){B(label,0x30)=W(w,0x34)!=0;B(w,0x31)=1;WAVE_STATE[2]&=(u8)~(4u<<i);}
  NFN(0x081822a4,void(*)(void*,void*))(w,flags);return;
 }
 if(!B(label,0x30)){B(label,0x30)=1;WAVE_STATE[2]|=(u8)((4u<<idx)|(1u<<idx));} /* hidden by us; redraw */
 u32 ti=0;ui_get((void*)0x30030164u,0x131,&ti);
 u32 colour=NFN(0x08140ebc,u32(*)(u32))(ti);if(B(w,NOFF_WAVE(0x174))!=colour){B(w,NOFF_WAVE(0x174))=(u8)colour;WAVE_STATE[2]|=(u8)(1u<<idx);}
 u32 now=W((void*)0x3001fe2cu,0),s=wave_shape(w,idx);
 volatile unsigned short *last=(volatile unsigned short*)0x24043d38u; /* per pane, ms (16 bit) */
 if(s!=WAVE_STATE[idx]&&(unsigned short)(now-last[idx])>=33){WAVE_STATE[idx]=(u8)s;WAVE_STATE[2]|=(u8)(1u<<idx);last[idx]=(unsigned short)now;}
 if(WAVE_STATE[2]&(1u<<idx))B(w,0x32)=1; /* the native tick turns this into a partial repaint */
 NFN(0x081822a4,void(*)(void*,void*))(w,flags);
}
__attribute__((used,retain)) void analog_wave_paint(void *w,void *ctx){
 NFN(0x08182314,void(*)(void*,void*))(w,ctx);
 u32 idx=0;if(!analog_pane(w,&idx))return;
 if(!B(ctx,0)&&!(WAVE_STATE[2]&(1u<<idx)))return;
 wave_draw(w,WAVE_STATE[idx],W(ctx,4));WAVE_STATE[2]&=(u8)~(1u<<idx);
}

/* A1 Sync: key 1D1 (free in the stock registry) in WT2's empty fourth slot of
 * the native Wavetable osc page (table 0819E91C). Value reads go through the
 * fx_get property hook; changes (event CF) are taken at the model's event
 * entry (081403EC) so the native model never stores the private key. */
#define ANALOG_SYNC_KEY NKEY(0x1d1u)
#define ANALOG_GLIDE_KEY NKEY(0x142u)
static const char analog_sync_name[]="Sync",analog_glide_name[]="Glide",analog_shape_name[]="Shape";
static void analog_descriptor(u32 key,const char *name,u32 type,u32 hi){
 u32 r=*(volatile u32*)0x30031484u;if(!r)return;void *d=(void*)(r+key*32);
 if(H(d,0)==key && W(d,4)==(u32)name)return;
 if(H(d,0) && W(d,4)!=(u32)name)return; /* someone else owns it */
 zero(d,32);H(d,0)=(unsigned short)key;B(d,2)=(u8)type;W(d,4)=(u32)name;W(d,16)=0;W(d,20)=hi;
}
__attribute__((used,retain)) void analog_registry(void){
 analog_descriptor(ANALOG_SYNC_KEY,analog_sync_name,6,1);analog_descriptor(ANALOG_GLIDE_KEY,analog_glide_name,10,1000);
}
__attribute__((used,retain)) int analog_get(u32 key,void *out){
 if((key!=ANALOG_SYNC_KEY && key!=ANALOG_GLIDE_KEY) || !out)return 0;analog_registry();
 KickKnob *e=analog_entry(current_track());
 W(out,0)=!e?0:key==ANALOG_SYNC_KEY?(e->values[0]?1:0):(u32)e->values[1]*10;return 1;
}
__attribute__((used,retain,section(".text.bank1c"))) int analog_model_event(void *model,void *event){ /* R6.14: in a bank-1 cave */
 /* R6.10 (owner: Seq burger on the Proj page): native 0813430C opens the menu
    whose id is the event code (F0..100); set this page's burger right before. */
 if(event){unsigned c=*(volatile unsigned short*)event;if(c>=0xf0u&&c<=0x100u){extern void seq_nav_menus_tick(void);seq_nav_menus_tick();}}
 if(kit_seq_event(0,event))return 1;
 extern int motion_capture_event(void*);if(motion_capture_event(event))return 1;
 extern int macro_model_event(void*);if(macro_model_event(event))return 1;
 extern int perf_ratchet_event(void*);if(perf_ratchet_event(event))return 1; /* R6.14 Ratchet amount (macro target) */
 extern int seq_nav_global(void*,void*);if(seq_nav_global(model,event))return 1;
 if(drum_menu_event(event))return 1;
 (void)model;u32 key=W(event,8);if(H(event,0)!=0xcf || (key!=ANALOG_SYNC_KEY && key!=ANALOG_GLIDE_KEY))return 0;
 u32 t=current_track();KickKnob *e=analog_entry(t);
 if(e){
  if(key==ANALOG_SYNC_KEY)analog_mark(t,W(event,12)?1:0);
  else{int v=(int)W(event,12);if(v<0)v=0;if(v>1000)v=1000;u32 g=((u32)v+5)/10;if(e->values[1]!=g)update(e,1,g);}
  ui_commit();
 }
 return 1;
}
/* A1 page details, applied when the native synth page builder (0815F52C)
 * copies its control-key table (memcpy at 0815F5AE granular, 0815F68E
 * wavetable). An Analog track gets Glide in WT1's empty fourth slot and Sync
 * in WT2's; Position reads "Shape". Text setters resolve the current track
 * when called, before or after this key copy; no cross-track text buffers. */
#define POSITION_TITLE 0x0818d5b8u
__attribute__((used,retain,section(".pad2"))) void analog_pane_text(void *widget,const char *text){
 u32 t=current_track();
 if(t&&analog_entry(t))text=(u32)text==0x0818cb94u?"Analog":"Saw > Square > Pulse";
 NFN(0x0817e85e,void(*)(void*,const char*))(widget,text);
}
__attribute__((used,retain)) void analog_page_keys(unsigned short *dst,const unsigned short *src,u32 bytes,u32 wavetable){
 for(u32 i=0;i<bytes/2;i++)dst[i]=src[i];
 u32 t=wavetable?current_track():0;int analog=t && analog_entry(t);
 u32 r=*(volatile u32*)0x30031484u;void *position=r?(void*)(r+0xc9*32):0;
 if(analog){
  analog_registry();dst[3]=ANALOG_GLIDE_KEY;dst[8+3]=ANALOG_SYNC_KEY;
  if(position && H(position,0)==0xc9)W(position,4)=(u32)analog_shape_name;
 }else{
  if(position && H(position,0)==0xc9 && W(position,4)==(u32)analog_shape_name)W(position,4)=POSITION_TITLE;
 }
}
