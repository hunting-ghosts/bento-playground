#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
/* P14 note-owned p-locks in melodic Event encoders 7 and 8. */
#include "fx_shared.h"
#include "step_lock_shared.h"
#include "ratchet_ui.h"
#include "ui_native.h"
#define MRT __attribute__((section(".text.bank1e")))
#define PK1 NKEY(0x1dau)
#define PK2 NKEY(0x1e4u)
#define AUTO_ACTION 0x1059u
void **melodic_lock_state_slot(void);int mel_audio_prepare(u32);
int melodic_lock_registry(int);u32 melodic_lock_pack(u32,u32,u32);
int melodic_locks_choose(void*,u32,u32);
typedef struct {u32 view,seq,owner,kind[2],pick[2],shift,changed,selection,scratch,error,track_type,rt_page;} MelUI; /* R6.14 rt_page: ratchet page */
#define zero ui_zero
__attribute__((weak,noinline,section(".text.sls"))) void ui_zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static MelUI *state(int create){void **slot=melodic_lock_state_slot();if(!slot)return 0;if(*slot)return *slot;if(!create)return 0;
 u32 n=(sizeof(MelUI)+31)&~31u,p=ui_alloc(n,n+32);if(!p)return 0;zero((void*)p,n);*slot=(void*)p;return *slot;}
static u32 type(u32 owner){return ui_type(&owner);}
static int limited(MelUI *s){return s->track_type!=15;}
static int allowed(MelUI *s,u32 k){return k&&((k<=11&&(!limited(s)||k==1||k==3||k==4||k==5||k==7||k>=9))||(limited(s)&&(k==30||k==31)));}
static u32 to_kind(MelUI *s,u32 pick){static const u8 ks[11]={0,1,3,4,5,30,31,7,9,10,11};return limited(s)?ks[pick<11?pick:0]:pick<12?pick:0;}
static u32 to_pick(MelUI *s,u32 k){if(!limited(s))return k;for(u32 i=0;i<11;i++)if(to_kind(s,i)==k)return i;return 0;}
/* R6.7b: seq=1 also accepts the Seq view (native Sequence tab 1) of pitched tracks, for transpose. */
static int ctx(MelUI *s,void *v,int seq){
 u32 owner=W(v,0x11cd08),current=0,t=type(owner),tab=B(v,0x125dac);
 if(B(MODEL,0x12c)!=0x17||B(v,0x125dae)||(tab!=0&&!(t==14&&tab==1)&&!(seq&&tab==1&&t!=14))||!(t==14||t==15||t==18||t==19)||!W(v,0x11cd00)||W(MODEL,0x144)!=W(v,0x11cd00)||!ui_owner(&current)||current!=owner)return 0;
 if(s->seq!=W(v,0x11cd00)||s->owner!=owner){s->seq=W(v,0x11cd00);s->owner=owner;s->kind[0]=4;s->kind[1]=5;s->selection=0;s->shift=s->changed=s->error=0;}
 s->view=(u32)v;s->track_type=t;if(t==18||t==19)mel_audio_prepare(owner);return 1;
}
static int context(MelUI *s,void *v){return ctx(s,v,0);}
static void *container(MelUI *s){void *node=0;if(!NFN(0x0812dfe8,int(*)(void*,u32,void*))((void*)W(MODEL,0),s->seq,&node)||!node)return 0;void *c=(u8*)node+12;return W(c,0x3000)<=511?c:0;}
static int selected(void *v,u32 id){void *g=(u8*)v+0x38;u32 n=W(g,0x1254);if(n>511)return 0;for(u32 i=0;i<n;i++){u32 x=0;if(NFN(0x08174d70,int(*)(void*,u32,void*))(g,i,&x)&&id==x)return 1;}return 0;}
static int first(MelUI *s,void *v,u32 *out){void *c=container(s);if(!c)return 0;for(u32 i=0;i<W(c,0x3000);i++){if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))(c,i,out))break;if(B(out,0)==1&&selected(v,out[3]))return 1;}return 0;}
static void refresh(void *v){NFN(0x081599bc,void(*)(void*))(v);}
static int scratch(MelUI *s){if(s->scratch)return 1;u32 p=ui_alloc(0x3004,0x3020);if(!p)return 0;s->scratch=p;return 1;}
static void edit(MelUI *s,void *v,u32 which,u32 word){
 void *c=container(s);if(!c||!scratch(s)){s->error=2;return;}void *temp=(void*)s->scratch;NFN(0x0810d16c,void(*)(void*))(temp);u32 n=W(c,0x3000),e[6],count=0;
 for(u32 i=0;i<n;i++){if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))(c,i,e))return;if(B(e,0)!=1||!selected(v,e[3]))continue;
  u32 packed;
  if(which==2){extern u32 locks_condition_word(u32,u32);packed=locks_condition_word(e[5],word);}
  else if(which>=3)packed=rt_ui_word(e[5],which-3,(int)word); /* R6.14 ratchet field */
  else{u32 a,b;lock_slots(e[5],&a,&b);if(which==0)a=word;else b=word;
   if(lock_kind(a)&&lock_kind(a)==lock_kind(b)){s->error=1;return;}packed=melodic_lock_pack(e[5],a,b);}
  if(packed==0xffffffffu){s->error=2;return;}if(packed==e[5])continue;e[5]=packed;NFN(0x0810d176,void(*)(void*,void*))(temp,e);count++;
 }
 if(!count)return;
 ui_touch(&s->seq);NFN(0x08136544,void(*)(void*,void*,void*))(MODEL,&s->seq,temp);
 W(MODEL,NOFF_MODEL_CHANGED)=1;u32 ev[5]={0xc7,s->seq,0,0,0};NFN(0x08173272,void(*)(void*,void*))((u8*)MODEL+0x160,ev);
}
static const char *const titles[12]={"Target","Level","Pitch","Pan","Filter","Resonance","Attack","Env 1 Decay","Sustain","Env 1 Release","Delay Send","Reverb Send"};
static const char *target_title(u32 k){return k==30?"Filter 2":k==31?"Resonance 2":k<=11?titles[k]:titles[0];}
static __attribute__((noinline,section(".pad"))) void parameter(MelUI *s,void *v,u32 i,u32 key,int value){
 H(v,0x11bcc0+2*i)=key;W(v,0x11bcd0+4*i)=(u32)value;W(v,0x11bca0+4*i)=s->seq;
 void *bar=(u8*)v+0x55f0,*slot=(u8*)bar+0x38+i*0x468;
 NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,0);ui_slot_set(slot,key,value);
}
/* R6.6 Berlin-school transpose (owner): with no note selected, encoders 7/8 of
 * the melodic Seq view are Transpose (Off/On) and Mode (Chromatic/Diatonic).
 * Keys 9D/9E are empty after native registry construction and unused. */
#define TR_KEY 0x9du
#define TR_MODE_KEY 0x9eu
int tr_get(u32,u32) __attribute__((weak));void tr_set(u32,u32,u32) __attribute__((weak)); /* weak: partial test builds */
static const char tr_title[]="Transpose",trm_title[]="Mode";
static const char *const tr_names[2]={"Off","On"},*const trm_names[2]={"Chromatic","Diatonic"};
static __attribute__((noinline,section(".pad5"))) void tr_header(MelUI *s,void *v){
 u32 r=W((void*)0x30031484u,0);if(!r||!tr_get)return;
 for(u32 i=0;i<2;i++){void *d=(void*)(r+(i?TR_MODE_KEY:TR_KEY)*32);for(u32 j=0;j<8;j++)W(d,j*4)=0;
  H(d,0)=i?TR_MODE_KEY:TR_KEY;B(d,2)=7;W(d,4)=(u32)(i?trm_title:tr_title);W(d,8)=(u32)(i?trm_names:tr_names);W(d,12)=2;}
 u32 on=(u32)tr_get(s->owner,0);parameter(s,v,6,TR_KEY,(int)on);parameter(s,v,7,TR_MODE_KEY,tr_get(s->owner,1));
 /* R6.7 (owner: encoders 7/8 showed nothing): label the slots like the lock path does. */
 for(u32 j=0;j<2;j++)ui_slot_title((u8*)v+0x55f0+0x38+(6+j)*0x468,j?trm_title:tr_title);
 if(on){int off=tr_get(s->owner,2);char t[8];u32 n=0;t[n++]=off<0?'-':'+';u32 a=(u32)(off<0?-off:off);if(a>=10)t[n++]=(char)('0'+a/10);t[n++]=(char)('0'+a%10);t[n]=0;
  NFN(0x08170656,void(*)(void*,u32,const char*))((u8*)v+0x55f0,6,t);}
}
/* R6.8b: a new transposition (or Transpose on/off) rebuilds the Seq view's encoder row. */
__attribute__((noinline,section(".pad5"))) void tr_changed(void){
 MelUI *s=state(0);void *v=s?(void*)s->view:0;
 if(v&&ctx(s,v,1)&&B(v,0x125dac)==1&&s->track_type!=14)refresh(v);
}
/* R6.14 ratchet page: encoders 5..8 = Count / Shape / Depth / Prob of the selected notes. */
static MRT void mel_rt_header(MelUI *s,void *v,u32 word){
 for(u32 j=0;j<4;j++){parameter(s,v,4+j,rt_ui_key(j),rt_ui_value(word,j));ui_slot_title((u8*)v+0x55f0+0x38+(4+j)*0x468,rt_ui_title(j));}
 if(s->error==2)NFN(0x08170656,void(*)(void*,u32,const char*))((u8*)v+0x55f0,4,"No lock memory");
}
MRT int melodic_rt_arrow(u32 right,int act){
 MelUI *s=state(0);void *v=s?(void*)s->view:0;u32 e[6];
 if(!v||!ctx(s,v,1)||s->track_type==14||!first(s,v,e))return 0;
 if(act&&s->rt_page!=right){s->rt_page=right;refresh(v);}return 1;
}
void melodic_locks_header(void *v){
 MelUI *s=state(1);if(!s||!ctx(s,v,1)||!melodic_lock_registry(s->track_type!=14&&limited(s)))return;
 if(B(v,0x125dac)==1&&s->track_type!=14)rt_ui_publish(s->owner,(int)rt_ui_grid_ticks(W(v,0x11cd14)),-1); /* R6.14: Step Len = one ratchet step */
 if(s->track_type!=14&&s->rt_page){u32 e[6]={0};if(first(s,v,e)&&rt_ui_registry()){mel_rt_header(s,v,e[5]);return;}}
 /* R6.7b (owner): the Seq view's encoders 7/8 are free: Transpose / Mode, always. */
 if(B(v,0x125dac)==1&&s->track_type!=14){tr_header(s,v);return;}
 if(s->track_type==14){
  if(B(v,0x125dac)==1){parameter(s,v,7,NKEY(0x1df),(int)W(v,0x125da8));return;}
  u32 e[6]={0};int has=first(s,v,e);u32 c=lc_condition(e[5]),value=cond_pos(c);
  void *bar=(u8*)v+0x55f0;parameter(s,v,7,NKEY(0x198),(int)value);
  NFN(0x08170656,void(*)(void*,u32,const char*))(bar,7,s->error?"No lock memory":has?0:"Select note");return;
 }
 u32 e[6]={0},slots[2];int has=first(s,v,e);lock_slots(e[5],&slots[0],&slots[1]);if(s->selection!=(has?e[3]:0)){s->shift=0;for(u32 j=0;j<2;j++){u32 k=lock_kind(slots[j]);if(allowed(s,k))s->kind[j]=k;}if(s->kind[0]==s->kind[1])s->kind[1]=s->kind[0]==5?4:5;s->selection=has?e[3]:0;}
 for(u32 j=0;j<2;j++){
  u32 choosing=(s->shift>>j)&1u,k=s->kind[j],key=choosing?(j?PK2:PK1):native_key(k),w=has?slots[j]:0;
  int value=choosing?(int)to_pick(s,s->pick[j]):lock_kind(w)==k?decode_value(w):k==4?1000:0;
  void *bar=(u8*)v+0x55f0,*slot=(u8*)bar+0x38+(6+j)*0x468;
  parameter(s,v,6+j,key,value);
  char label[32];u32 at=0;const char *p=j?"Lock 2 ":"Lock 1 ";while(*p)label[at++]=*p++;p=target_title(choosing?0:k);while(*p&&at<30)label[at++]=*p++;if(!choosing&&has&&lock_kind(w)==k&&at<30)label[at++]='*';label[at]=0;
  ui_slot_title(slot,label);
  if(s->error)NFN(0x08170656,void(*)(void*,u32,const char*))(bar,6+j,s->error==1?"Target already used":"No lock memory");
  else if(!choosing&&(!has||lock_kind(w)!=k))NFN(0x08170656,void(*)(void*,u32,const char*))(bar,6+j,has?"--":"Select note");
 }
}
int melodic_locks_event(void *v,void *event){
 if(H(event,0)==AUTO_ACTION){u32 seq=W(v,0x11cd00),value=!W(v,0x125da8),e[5]={0xcf,seq,NKEY(0x1df),value,0};return NFN(0x0815a598,int(*)(void*,void*))(v,e),1;}
 MelUI *s=state(0);if(!s||!ctx(s,v,1)||H(event,0)!=0xcf)return 0;u32 key=W(event,8);int value=(int)W(event,12);
 if(rt_ui_field(key)<4&&s->track_type!=14){if(s->rt_page){s->error=0;edit(s,v,3+rt_ui_field(key),(u32)value);refresh(v);}return 1;}
 if(B(v,0x125dac)==1&&s->track_type!=14){if((key==TR_KEY||key==TR_MODE_KEY)&&tr_set){tr_set(s->owner,key==TR_MODE_KEY,value>0);refresh(v);return 1;}return 0;} /* R6.7b: Seq view = transpose only */
 if(s->track_type==14){if(key!=NKEY(0x198)||B(v,0x125dac))return 0;s->error=0;edit(s,v,2,cond_code(value));refresh(v);return 1;}
 if(key==PK1||key==PK2)return melodic_locks_choose(v,key,(u32)value);
 for(u32 j=0;j<2;j++)if(!(s->shift&(1u<<j))&&key==native_key(s->kind[j])){s->error=0;edit(s,v,j,encode_value(s->kind[j],value));refresh(v);return 1;}
 return 0;
}
int melodic_locks_choose(void *v,u32 key,u32 value){
 MelUI *s=state(0);if(!s||!context(s,v)||(key!=PK1&&key!=PK2))return 0;
 {u32 j=key==PK2,k=to_kind(s,value);s->error=0;
  if(!(s->shift&(1u<<j)))return 1;
  if(k&&!allowed(s,k))return 1;
  if(k&&k==s->kind[1-j]){s->error=1;refresh(v);return 1;}
  s->pick[j]=k;if(k)s->kind[j]=k;refresh(v);return 1;}
}
void melodic_locks_proj(void *model,u32 down){
 (void)model;(void)down;
}
static int touch_slot(MelUI *s,void *slot){
 if(!s||!s->view||!context(s,(void*)s->view))return -1;void *v=(void*)s->view;
 if(B(v,0x30)||B(v,0x55f0+0x30))return -1;
 for(u32 j=0;j<2;j++)if(slot==(u8*)v+0x55f0+0x38+(6+j)*0x468&&!B(slot,0x30)&&H(slot,0x9c)==((s->shift&(1u<<j))?(j?PK2:PK1):native_key(s->kind[j])))return (int)j;
 return -1;
}
u32 melodic_locks_touch_context(void *slot){
 MelUI *s=state(0);if(touch_slot(s,slot)<0)return 0;void *v=(void*)s->view,*g=(u8*)v+0x38;u32 n=W(g,0x1254);
 if(n>511)return 0;u32 h=((2166136261u^(u32)slot)*16777619u^s->seq)*16777619u;
 h=(h^s->owner)*16777619u;h=(h^s->kind[0])*16777619u;h=(h^s->kind[1])*16777619u;h=(h^n)*16777619u;
 for(u32 j=0;j<n;j++){u32 id=0;if(!NFN(0x08174d70,int(*)(void*,u32,void*))(g,j,&id))return 0;h=(h^id)*16777619u;}
 return h?h:1;
}
int melodic_locks_touch(void *slot,int twice){
 MelUI *s=state(0);int j=touch_slot(s,slot);if(j<0)return 0;void *v=(void*)s->view;s->error=0;
 if(twice){s->shift&=~(1u<<j);edit(s,v,(u32)j,0);refresh(v);return 1;}
 if(!melodic_lock_registry(limited(s)))return 1;
 if(s->shift&(1u<<j)){s->shift&=~(1u<<j);if(!s->pick[j])edit(s,v,(u32)j,0);}
 else{s->pick[j]=s->kind[j];s->shift|=1u<<j;}
 refresh(v);
 return 1;
}
void melodic_locks_menu(int pitched){
 MelUI *s=state(0);int event_page=pitched&&s&&s->view&&!B((void*)s->view,0x125dac);
 for(u32 m=0;m<20;m++){u8 *menu=(u8*)0x30030168u+m*0xe0;if(W(menu,0)!=0xf9)continue;u32 n=B(menu,0xcc);if(n>9)continue;
  for(u32 i=0;i<n;i++){void *cell=menu+4+i*20;u32 code=W(cell,0);
   if(code==NUI(0x102d)||code==AUTO_ACTION){W(cell,0)=event_page?AUTO_ACTION:NUI(0x102d);W(cell,4)=(u32)(event_page?"Show/Hide Automation":"Clear Auto");}
  }
 }
}
/* Register loaded synth tracks before PLAY, including projects whose SEQ page
   has not been visited. Only UI-side lookups/allocation, never on the M7. */
void melodic_register_tracks(void){
 if(!W(MODEL,0))return; /* no project tree during startup/empty-session navigation */
 for(u32 i=0;i<8;i++){u32 owner=0;if(NFN(0x08133960,u32(*)(void*,u32,void*))(MODEL,i,&owner)&&owner){u32 t=type(owner);if(t==18||t==19)mel_audio_prepare(owner);}}
}
