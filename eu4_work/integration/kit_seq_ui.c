#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
#pragma clang section text=".stepui"
#include "step_lock_shared.h"
#pragma clang section text=""
#include "kit_seq.h"
#include "live_ui.h"
#include "header_actions.h"
#include "../drums/kick_knobs.h"
#include "../drums/drum_models.h"
#include "ui_native.h"
#define MODEL ((void*)0x30024b00u)
#define NOW W((void*)0x3001fe2cu,0)
#define INPUT ((void*)KIT_SEQ_INPUT)
typedef struct {u32 owner,seq,pad,page;} Page;
typedef struct {
 u32 view,project,owner,seq,cell,pad,length,page,on,epoch,held,used,error;
 /* settle: low 16 bits = taps awaiting the bounce window, high 16 bits =
  * non-tap releases whose bounce must not start a new tap; settled = time. */
 u32 stamp[16],next,poll,settle,revision,tap,settled;
 u32 focus,focus_touch,targets[2],choosing[2],picks[2];
 Page pages[32];
 u32 released,strip,played_project,played_owner,played_pad;
 u32 tracks; /* R6.2: Seq mode per track (bit = track), shared by INST and SEQ */
 u32 sounds,sounds_tick,sounds_track; /* R6.3: pads holding a sound (Pads-mode lights) */
 u32 sq_down,sq_tick,sq_hold; /* R6.4: SEQ-page Steps pad: 1+index pressed, press time, hold reached */
} KitSeq;
void **kit_seq_state_slot(int);
static KIT_CONTEXT KitSeq *state(int create){
 void **slot=kit_seq_state_slot(create);if(!slot)return 0;
 if(*slot||!create)return *slot;
 u32 n=(sizeof(KitSeq)+31)&~31u;KitSeq *s=(void*)ui_alloc(n,n+32);if(!s)return 0;
 for(u32 i=0;i<sizeof(*s)/4;i++)((u32*)s)[i]=0;*slot=s;return s;
}
u32 nav_track_index(void);void *step_current_view(void);
static __attribute__((noinline,section(".text.r62"))) u32 track_bit(void){return 1u<<(nav_track_index()&7u);}
__attribute__((used,retain)) int kit_seq_track_mode(void){KitSeq *s=state(0);return s&&(s->tracks&track_bit());}
static __attribute__((noinline,section(".text.r62"))) int seq_view_mode(KitSeq *s);static __attribute__((noinline,section(".text.r62"))) int seq_mode_toggle(KitSeq *s);static __attribute__((noinline,section(".text.r62"))) void inst_follow(KitSeq *s);
static KIT_CONTEXT int editor(KitSeq *s){
 void *v=s?(void*)s->view:0;
 return v&&B(MODEL,0x12c)==8&&W(v,0)==0x0819e624u&&!B(v,0x30)&&
  B(v,0x87cc)==14&&W(v,0x87bc)&&W(v,0x87bc)==s->cell;
}
static KIT_CONTEXT void gate(KitSeq *s,int on){
 B(INPUT,14)=0;__asm__ volatile("dmb" ::: "memory");
 s->epoch=(s->epoch+1u)&255u;if(!s->epoch)s->epoch=1;
 s->held=s->used=s->released=s->tap=s->focus=s->focus_touch=s->settle=s->strip=0;s->targets[0]=s->targets[1]=0;s->on=on;s->revision++;
 B(INPUT,15)=(u8)s->epoch;__asm__ volatile("dmb" ::: "memory");B(INPUT,14)=on?1:0;
}
static KIT_CONTEXT void refresh(KitSeq *s){
 s->revision++;if(editor(s))NFN(0x08152144,void(*)(void*))((void*)s->view);
 ui_commit();
 NFN(0x081257f0,void(*)(void*))((u8*)MODEL+NOFF_MODEL_PADS);
}
static KIT_CONTEXT void remember(KitSeq *s){
 u32 i;for(i=0;i<32;i++)if(s->pages[i].owner==s->owner&&s->pages[i].seq==s->seq&&s->pages[i].pad==s->pad)break;
 if(i==32)i=s->next++&31u;s->pages[i]=(Page){s->owner,s->seq,s->pad,s->page};
}
static KIT_CONTEXT u32 sequence(u32 owner){
 u32 index=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)MODEL+4,0x131);
 int row=-1,queued=-1,pos=NFN(0x081322ac,int(*)(void*,u32,int*,int*))(MODEL,index,&row,&queued);
 if(pos>=0&&(row<0||row>=16))return 0;
 for(u32 i=0;i<256;i++){
  u32 child=0,r=16;
  if(!ui_child(&owner,i,&child))break;
  if(NFN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&child)!=24)continue;
  if(pos<0){if(child==W(MODEL,0x144))return child;}
  else if(ui_get(&child,0x73,&r)&&r==(u32)row)return child;
 }
 return 0; /* Never edit a clip outside the selected sound's owning track. */
}
static KIT_CONTEXT int context(KitSeq *s){
 if(!editor(s))return 0;
 u32 held=s->held;
 u32 owner=0,pad=16,length=0,cell=W((void*)s->view,0x87bc);
 if(!ui_owner(&owner)||
    ui_type(&owner)!=14||
    !ui_get(&cell,0x73,&pad)||pad>=16)return 0;
 u32 seq=sequence(owner);
 if(!seq||!ui_get(&seq,0x62,&length)||!length||length>256)return 0;
 length=live_cycle_steps(owner,seq,pad,length);
 if(s->project!=W(MODEL,0)||s->owner!=owner||s->seq!=seq||s->pad!=pad){
  if(s->project!=W(MODEL,0))for(u32 i=0;i<32;i++)s->pages[i].owner=0;
  else if(s->seq)remember(s);
  gate(s,s->on);s->project=W(MODEL,0);s->owner=owner;s->seq=seq;s->pad=pad;s->page=0;s->error=0;
  for(u32 i=0;i<32;i++)if(s->pages[i].owner==owner&&s->pages[i].seq==seq&&s->pages[i].pad==pad){s->page=s->pages[i].page;break;}
 }
 if(s->length!=length){s->length=length;if(s->page>=length)s->page=(length-1)&~15u;if(s->held)gate(s,s->on);}
 if(held&&!s->held)refresh(s);
 return 1;
}
void kit_seq_bind(void *v){
 if(!v||B(v,0x87cc)!=14||W(v,0)!=0x0819e624u)return;
 KitSeq *s=state(1);if(!s)return;
 if(s->view!=(u32)v||s->cell!=W(v,0x87bc)){if(s->seq)remember(s);gate(s,0);s->view=(u32)v;s->cell=W(v,0x87bc);s->error=0;}
}
void kit_seq_nav(void){
 B(INPUT,14)=0;KitSeq *s=state(0);if(s){if(s->seq)remember(s);gate(s,0);}
}
int kit_seq_holding(void){KitSeq *s=state(0);return editor(s)&&s->on&&s->held;}
static STEP_DRAW int strip_visible(KitSeq *s){
 if(!kit_seq_holding())return 0;
 for(u32 i=0;i<16;i++)if((s->held&(1u<<i))&&NOW-s->stamp[i]>=1000u)return 1;
 return 0;
}
static KIT_CONTEXT int slot_index(KitSeq *s,void *slot){
 if(!editor(s)||!slot)return -1;
 for(u32 row=0;row<3;row++)for(u32 i=0;i<8;i++)
  if(slot==(u8*)s->view+0x70+row*0x23f8+i*0x468&&!B(slot,0x30)&&!B((u8*)s->view+0x38+row*0x23f8,0x30))return (int)(row*8+i);
 return -1;
}
static KIT_CONTEXT u32 target(KitSeq *s,u32 key){
 extern int kick_ui_supported(void*);
 return locks_direct_kind(key,(u32)kick_ui_supported((void*)s->view));
}
static KIT_CONTEXT void message(KitSeq *s,u32 error){s->error=error;s->revision++;ui_commit();}
int kit_seq_increment(void *slot){
 KitSeq *s=state(0);if(!kit_seq_holding()||slot_index(s,slot)<0)return 0;
 /* A held gesture owns every sound encoder, even an unsupported destination. */
 s->used|=s->held;s->tap=0;
 if(!context(s)||!s->held){message(s,4);return 2;}
 if(s->focus){
  KitStep snap;
  if(slot_index(s,slot)<16||!H(slot,0x9c))return 2;
  if(!locks_step_snapshot(s->seq,s->pad,s->page,s->held,&snap)||snap.empty){message(s,7);return 2;}
  return 1;
 }
 u32 kind=target(s,H(slot,0x9c));if(!kind){message(s,5);return 2;}
 int result=locks_direct_edit(s->seq,s->pad,s->page,s->held,kind,0,2);
 if(result>1){message(s,(u32)result);return 2;}
 s->error=0;return 1;
}
int kit_seq_value(u32 key,int base,int *status){
 KitSeq *s=state(0);*status=0;if(!kit_seq_holding())return base;
 u32 kind=target(s,key),used=0;int value=base;
 if(!kind){*status=4;return base;}
 *status=locks_direct_value(s->seq,s->pad,s->page,s->held,kind,base,&value,&used);
 return value;
}
u32 kit_seq_signature(void){KitSeq *s=state(0);return kit_seq_holding()?s->revision^s->held^((u32)strip_visible(s)<<16):0;}
void kit_seq_after(void *v){
 KitSeq *s=state(0);if(!editor(s)||s->view!=(u32)v||!s->on||!s->held)return;
 for(u32 row=0;row<3;row++)for(u32 i=0;i<8;i++){
  void *bar=(u8*)v+0x38+row*0x23f8,*slot=(u8*)bar+0x38+i*0x468;u32 key=H(slot,0x9c);int base=0,status=0;
  if(!key||!kick_base_value(v,key,&base))continue;
  int value=kit_seq_value(key,base,&status);
  NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,0);
  ui_slot_set(slot,key,value);
  if(status==3||status==4||status==5)NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,status==3?"Mixed":status==4?"No lock":"Empty");
  u32 reg=W((void*)0x30031484u,0);const char *name=reg?(const char*)W((void*)(reg+key*32),4):0;
  if(name){char title[32];title[0]=status==2?'*':status==3?'~':'=';title[1]=' ';u32 j=0;while(j<28&&name[j]){title[j+2]=name[j];j++;}title[j+2]=0;ui_slot_title(slot,title);}
  B(bar,0x31)=1;
 }
 kit_seq_strip_bind(v);
}
static KIT_CONTEXT void *notes(KitSeq *s){
 void *node=0;return NFN(0x0812dfe8,int(*)(void*,u32,void*))((void*)W(MODEL,0),s->seq,&node)&&node?(u8*)node+12:0;
}
static __attribute__((noinline,section(".stepui"))) int step(u32 *e){
 int t=(int)e[1],q=t%960;if(q>480)q-=960;return (t-q)/960;
}
static KIT_CONTEXT void toggle(KitSeq *s,u32 local){
 void *c=notes(s);if(!c||W(c,0x3000)>511){message(s,4);return;}
 u32 n[6],at=s->page+local,found=0,maxid=0;
 for(u32 i=0;i<W(c,0x3000);i++){
  if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))(c,i,n)){message(s,4);return;}
  if(n[3]>maxid)maxid=n[3];
  if(B(n,0)==1&&H(n,2)==s->pad&&step(n)==(int)at)found++;
 }
 if(!live_manual_steps(s->owner,s->seq,s->pad,0)){message(s,4);return;}
 if(found){u32 bits[8]={0};bits[at/32]=1u<<(at&31);extern int eu_clear_steps(u32,u32,const u32*,void*);
  if(!eu_clear_steps(s->seq,s->pad,bits,MODEL))message(s,3);
  else if(!live_manual_steps(s->owner,s->seq,s->pad,1))message(s,4);
  return;}
 if(W(c,0x3000)==511){message(s,6);return;}
 void *root=(void*)W(MODEL,0);u32 next=W(root,0x68);
 if(!next||next<=maxid||next==0xffffffffu){message(s,4);return;}
 extern void *locks_direct_scratch(void);void *temp=locks_direct_scratch();if(!temp){message(s,3);return;}
 u32 e[6]={1u|(s->pad<<16),at*960,960,0,100u<<16,0};
 ui_touch(&s->seq);
 e[3]=NFN(0x0812e070,u32(*)(void*,u32,void*))(root,s->seq,e);
 NFN(0x0810d16c,void(*)(void*))(temp);NFN(0x0810d176,void(*)(void*,void*))(temp,e);
 NFN(0x08136544,void(*)(void*,void*,void*))(MODEL,&s->seq,temp);W(MODEL,NOFF_MODEL_CHANGED)=1;
 if(!live_manual_steps(s->owner,s->seq,s->pad,1))message(s,4);
 u32 event[5]={0xc7,s->seq,0,0,0};NFN(0x08173272,void(*)(void*,void*))((u8*)MODEL+0x160,event);
}
#define SEQ_TAP_MS 500u
#define SEQ_BOUNCE_MS 40u
/* Pad pressure can dip through zero during one physical press. Hold a tap
 * until no re-press arrived within the bounce window, then toggle once. */
static __attribute__((noinline)) int settle(KitSeq *s,int force){
 if(!s->settle||(!force&&NOW-s->settled<SEQ_BOUNCE_MS))return 0;
 u32 taps=s->settle&0xffffu;s->settle=0;
 for(u32 i=0;i<16;i++)if(taps&(1u<<i))toggle(s,i);
 return taps!=0;
}
/* Press/release of one step pad; kept out of the fixed .kitinput region. */
static __attribute__((noinline)) void gesture(KitSeq *s,u32 index,int press){
 u32 bit=1u<<index,bounce=NOW-s->settled<SEQ_BOUNCE_MS?s->settle&(bit|bit<<16):0;
 if(!press||!bounce)settle(s,0);
 if(press){if(!(s->held&bit)){s->released&=~bit;s->held|=bit;s->error=0;s->tap=0;
   /* A bounce continues the earlier gesture with its original timing. */
   if(bounce){s->settle&=~(bit|bit<<16);if(bounce>>16)s->used|=bit;}
   else{s->stamp[index]=NOW;s->used&=~bit;}}}
 else if((s->held|s->released)&bit){int tap=!(s->used&bit)&&NOW-s->stamp[index]<SEQ_TAP_MS;s->held&=~bit;s->released&=~bit;s->used&=~bit;s->tap=0;s->settle|=tap?bit:bit<<16;s->settled=NOW;}
}
static KIT_INPUT void holds_changed(KitSeq *s,u32 before){
 if(!before){s->focus=0;drum_panel_hold_reset();}
 if(!s->held)s->focus=0;s->targets[0]=s->targets[1]=s->focus_touch=0;
 extern void drum_panel_cancel_touch(void);drum_panel_cancel_touch();
}
/* R6.2 (owner spec): on the one-shot SEQ page the M7 Kit/Seq gate owns the
   pads. Pads mode: a press selects that sound silently. Seq mode: the pads are
   16 steps of the selected sound (tap adds/removes), Left/Right page by 16. */
static __attribute__((noinline,section(".text.r62"))) void *seq_view(KitSeq *s){
 void *v=s&&!s->on&&B(MODEL,0x12c)==0x27?step_current_view():0;u32 seq,pad,length=0;
 if(!v||!(seq=W(v,0x113e4))||(pad=W(v,0x11400))>=16||!ui_get(&seq,0x62,&length)||!length||length>256)return 0;
 if(s->seq!=seq||s->pad!=pad)s->page=0;
 s->seq=seq;s->pad=pad;s->owner=W(v,0x113e8);s->length=live_cycle_steps(s->owner,seq,pad,length);if(s->page>=s->length)s->page=0;
 return v;
}
static __attribute__((noinline,section(".text.r62"))) int seq_view_mode(KitSeq *s){return (s->tracks&track_bit())&&seq_view(s);}
/* R6.3 (owner): one shared selected sound. The track's selected pad is
 * native track property 0x74 (INST and the pad selector follow it). */
static __attribute__((noinline,section(".text.r62"))) void pads_select(void *v,u32 pad){
 u32 t=0;if(ui_owner(&t)&&t){ui_post((u32)(0xcf),(u32)(t),(u32)(0x74),(u32)(pad));}
 W(v,0x11400)=pad;NFN(0x0815c4b8,void(*)(void*))(v);
 NFN(0x0815b82a,void(*)(void*))(v); /* R6.5: native refresh of both pad selectors (footer miniature +E0F4, overlay +E5F8) from +11400 */
}
/* Pads-mode lights like INST: pads with a sound dim in the track colour, the
 * selected one bright. Pad cells (types 1/2, property 0x73) every 250 ms. */
static __attribute__((noinline,section(".text.r62"))) int pads_lights(KitSeq *s,void *v,void *pads){
 u32 t=0;if(!ui_owner(&t)||!t)return 0;
 if(t!=s->sounds_track||(u32)(W((void*)0x3001fe2cu,0)-s->sounds_tick)>250u){
  u32 m=0,cell=0;for(u32 i=0;i<128&&ui_child(&t,i,&cell);i++){
   u32 type=ui_type(&cell);if(type!=1&&type!=2)continue;
   u32 n=99;ui_get(&cell,0x73,&n);if(n<16)m|=1u<<n;}
  s->sounds=m;s->sounds_track=t;s->sounds_tick=W((void*)0x3001fe2cu,0);
 }
 /* R6.4 (owner): only the track's own native colours (08140F50 dim, 08140EF0
    bright); sounds dim, the selected sound bright. */
 u32 index=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)MODEL+4,0x131),dim=NFN(0x08140f50,u32(*)(u32))(index),bright=NFN(0x08140ef0,u32(*)(u32))(index),sel=16;
 if(v)sel=W(v,0x11400);else ui_get(&t,0x74,&sel); /* R6.5: page 17 (Auto) has no step view: the track's selected pad */
 for(u32 i=0;i<64;i++)W(pads,i*4)=0;
 /* R6.5 (owner: selected showed white): selected = the dim track colour 1.5x
    per channel, just a bit more intense. */
 u32 more=0;for(u32 k=0;k<24;k+=8){u32 v=(dim>>k&255u)*2u; /* R6.6: x2 (x1.5 barely visible) */more|=(v>255u?255u:v)<<k;}(void)bright;
 for(u32 i=0;i<16;i++){u32 c=i==sel?more:(s->sounds>>i&1u)?dim:0;W(pads,i*16)=c;W(pads,i*16+4)=c;W(pads,i*16+8)=c;}
 return 1;
}
static __attribute__((noinline)) int seq_page(u32 code,u32 index,const u32 *record){
 KitSeq *s=state(B(MODEL,0x12c)==0x27);if(!s)return 0;
 void *v=seq_view(s);
 if(!v){if(B(MODEL,0x12c)==0x27&&!s->on)B(INPUT,14)=0;return 0;}
 if(!B(INPUT,14)){gate(s,0);B(INPUT,14)=1;}
 int seq=(s->tracks&track_bit())!=0;
 if(code==0xfe&&record&&record[2]==KIT_SEQ_CONTEXT){
  if(record[0]==0xfe&&record[1]==0x314d5442u&&index<16&&record[3]==index&&record[5]==(0x31525400u|s->epoch)&&record[4]==12){
   if(!seq)pads_select(v,index);
   /* R6.4 (owner): tap toggles on release; a hold opens the step (below). */
   else if(s->page+index<s->length){s->sq_down=1+index;s->sq_tick=NOW;s->sq_hold=0;}
  }
  else if(seq&&record[0]==0xfe&&record[1]==0x314d5442u&&index<16&&record[3]==index&&record[4]==13&&s->sq_down==1+index){
   s->sq_down=0;if(!s->sq_hold&&s->page+index<s->length){toggle(s,index);NFN(0x0815c27c,void(*)(void*))(v);}
   /* R6.7b (owner: R6.4 + releasing deselects): a held step ends like the native
    * >=1 s release: its press slot (view+11420, index step+11404-113F4) cleared, no toggle. */
   /* R6.8b (owner: still held after release, pad lit, frame, encoders, next tap
    * edits it): any set press slot keeps the step held (081B6840), so the
    * release clears all 32; the SEQ page holds one step at a time. */
   else if(s->sq_hold){for(u32 j=0;j<32;j++)W(v,0x11420+j*4)=0;NFN(0x0815c27c,void(*)(void*))(v);}
   s->sq_hold=0;
  }
  return 1;
 }
 if(seq&&(code==0xaf||code==0xb0)&&(index==0||index==9)){
  u32 max=(s->length-1)&~15u;if(code==0xaf)s->page=index==0?(s->page>=16?s->page-16:0):(s->page<max?s->page+16:max);
  return 1;
 }
 return 0;
}
static __attribute__((noinline,section(".text.r62"))) int seq_mode_toggle(KitSeq *s){u32 page=B(MODEL,0x12c);if(page!=0x27&&page!=0x17)return 0;s->tracks^=track_bit();s->page=0;return 1;}
static __attribute__((noinline,section(".text.r62"))) void inst_follow(KitSeq *s){if(!s->on&&(s->tracks&track_bit())&&context(s))gate(s,1);}
/* R6.3 (owner 7 Nov): Left+Right together toggles Pads/Steps on the one-shot
 * INST page and SEQ page. Alone, an arrow acts on release, and only if the
 * other arrow was not pressed meanwhile, so the combo never moves anything.
 * The arrow actions are the ones these pages already had: SEQ page = our step
 * cursor (seq_eu_arrows) or Steps paging; INST = previous/next pad (native
 * 08152ACC) or Steps paging. Word 24043D54: bit0 Left held, bit1 Right, bit2 combo. */
#define ARROWS (*(volatile u32*)0x24043d54u)
int seq_eu_arrows(void*,void*);
static __attribute__((noinline,section(".text.r62"))) void *inst_view(KitSeq *s){
 void *v=s?(void*)s->view:0;
 return v&&B(MODEL,0x12c)==8&&W(v,0)==0x0819e624u&&!B(v,0x30)&&B(v,0x87cc)==14&&W(v,0x87bc)?v:0;
}
u32 kit_seq_inst_cell(void){KitSeq *s=state(0);void *v=inst_view(s);return v?W(v,0x87bc):s&&B(MODEL,0x12c)==0x11?s->cell:0;} /* run 18: the opened one-shot pad (footer label, Load; WAV page 11: the pad last opened) */
static __attribute__((noinline,section(".text.r62"))) void steps_page(KitSeq *s,u32 index){
 u32 max=(s->length-1)&~15u;s->page=index==0?(s->page>=16?s->page-16:0):(s->page<max?s->page+16:max);
}
static __attribute__((noinline,section(".text.r62"))) int kit_seq_arrows(u32 code,u32 index){
 if((code!=0xaf&&code!=0xb0)||(index!=0&&index!=9))return 0;
 u32 page=B(MODEL,0x12c);KitSeq *s=state(page==0x27||page==8);if(!s){ARROWS=0;return 0;}
 void *iv=page==8?inst_view(s):0,*sv=page==0x27&&!s->on?seq_view(s):0;
 if((!iv&&!sv)||W((void*)0x24048cc0u,8)){ARROWS=0;return 0;} /* other pages, or a K16 modifier held: native */
 u32 bit=index==0?1u:2u;
 if(code==0xaf){
  if(ARROWS&(bit^3u)){ARROWS|=bit|4u;u16 ev[8]={KIT_SEQ_ACTION};kit_seq_event(0,ev);B((void*)0x30034d48u,NOFF_ROOT_LAYOUT)=1;return 1;}
  ARROWS|=bit;return 1;
 }
 int used=(ARROWS&4u)!=0;ARROWS&=~bit;if(!(ARROWS&3u))ARROWS=0;
 if(used)return 1;
 if(sv){
  {extern int rt_ui_step_arrow(u32);if(rt_ui_step_arrow(index))return 1;} /* R6.14: a held/selected step: ratchet page */
  if(s->tracks&track_bit()){steps_page(s,index);return 1;}
  u32 ev[4]={0x68,0,index,1};seq_eu_arrows(sv,ev);return 1;
 }
 if(s->on){if(context(s)&&!s->held){settle(s,1);steps_page(s,index);remember(s);s->error=0;gate(s,1);refresh(s);}return 1;}
 u32 cell=W(iv,0x87bc),pad=0;ui_get(&cell,0x73,&pad);
 NFN(0x08152acc,void(*)(void*,u32))(iv,index==0?(pad+15u)&15u:(pad+1u)&15u);return 1;
}
int kit_seq_dispatch(u32 code,u32 index,const u32 *record){
 if(kit_seq_arrows(code,index))return 1;
 if(seq_page(code,index,record))return 1;
 KitSeq *s=state(0);
 if(code==0xac&&index<16&&(!s||!s->on)&&(B(MODEL,0x12c)==7||B(MODEL,0x12c)==8)){
  u32 owner=0;
  if(ui_owner(&owner)&&owner&&
     ui_type(&owner)==14){
   s=state(1);if(s){s->played_project=W(MODEL,0);s->played_owner=owner;s->played_pad=index;}
  }
 }
 if(code==0xfe&&record&&record[2]==KIT_SEQ_CONTEXT){
  if(!s||record[0]!=0xfe||record[1]!=0x314d5442u||index>=16||record[3]!=index||record[5]!=(0x31525400u|s->epoch))return 1;
  u32 epoch=s->epoch;if(!s->on||!context(s)||epoch!=s->epoch)return 1;
  u32 before=s->held;if(s->page+index>=s->length)return 1;
  if(record[4]==12||record[4]==13)gesture(s,index,record[4]==12);
  holds_changed(s,before);
  refresh(s);return 1;
 }
 if(!s||!s->on||!editor(s))return 0;
 /* Physical Left/Right are button indices 0/9 (native previous/next pad). */
 if((code==0xaf||code==0xb0)&&(index==0||index==9)){
  if(code==0xaf){if(!context(s))return 1;if(s->held){s->used|=s->held;return 1;}
   settle(s,1);
   u32 max=(s->length-1)&~15u;s->page=index==0?(s->page>=16?s->page-16:0):(s->page<max?s->page+16:max);remember(s);s->error=0;gate(s,1);refresh(s);}
  return 1;
 }
 return 0;
}
static __attribute__((noinline,section(".stepdraw"))) void restore_played(KitSeq *s){
 u32 owner=0;
 if(s->played_project!=W(MODEL,0)||!s->played_owner||
    !ui_owner(&owner)||owner!=s->played_owner)return;
 void *view=(void*)s->view;
 NFN(0x08152acc,void(*)(void*,u32))(view,s->played_pad);kit_seq_bind(view);
}
int kit_seq_event(void *v,void *event){
 if(!event)return 0;KitSeq *s=state(H(event,0)==KIT_SEQ_ACTION);if(!s)return 0;
 if(H(event,0)==KIT_SEQ_ACTION){
  if(!editor(s)){if(!seq_mode_toggle(s))return 0;}
  else if(s->on){remember(s);gate(s,0);s->error=0;s->tracks&=~track_bit();}
  else{
   restore_played(s);
   if(context(s)){gate(s,1);s->error=0;s->tracks|=track_bit();extern void macro_disarm(void);macro_disarm();}
   else message(s,4);
  }
  B((void*)0x30034d48u,NOFF_ROOT_LAYOUT)=1;refresh(s);return 1;
 }
 if(H(event,0)==NUI(0x1032)&&s->on&&editor(s)){W(event,4)=s->seq;return 0;}
 if(H(event,0)!=0xcf||!kit_seq_holding()||(v&&v!=(void*)s->view))return 0;
 if(W(event,4)!=s->cell&&W(event,4))return 0;
 s->used|=s->held;
 if(!context(s)||!s->held){message(s,4);return 1;}
 if(s->focus)return kit_seq_step_event(W(event,8),(int)W(event,12));
 u32 kind=target(s,W(event,8));if(!kind){message(s,5);return 1;}
 int result=locks_direct_edit(s->seq,s->pad,s->page,s->held,kind,(int)W(event,12),0);
 s->error=result>1?(u32)result:0;s->targets[0]=s->targets[1]=0;refresh(s);return 1;
}
u32 kit_seq_touch_context(void *slot){
 KitSeq *s=state(0);if(!kit_seq_holding()||slot_index(s,slot)<0)return 0;
 return ((s->seq*16777619u)^s->cell^s->held^(s->page<<16)^(s->epoch<<24)^(s->focus<<20)^
  (s->targets[0]<<8)^(s->targets[1]<<13)^(s->choosing[0]<<22)^(s->choosing[1]<<23))|1u;
}
int kit_seq_touch(void *slot,int twice){
 KitSeq *s=state(0);if(!kit_seq_touch_context(slot))return 0;
 int index=slot_index(s,slot);if(index>=16)return s->focus&&index>=22?kit_seq_step_touch((u32)index-22,twice):1;
 s->used|=s->held;if(!twice)return 1;
 if(!context(s)||!s->held)return 1;
 u32 kind=target(s,H(slot,0x9c));if(!kind){message(s,5);return 1;}
 int result=locks_direct_edit(s->seq,s->pad,s->page,s->held,kind,0,1);
 s->error=result>1?(u32)result:0;refresh(s);return 1;
}
int kit_seq_value_hit(void *slot,void *point){
 KitSeq *s=state(0);if(!kit_seq_holding())return -1;if(slot_index(s,slot)<0)return 0;
 void *bar=(void*)W(slot,0x2c);int y=(int)W(point,4);
 extern int drum_panel(void*,u32*);int panel=drum_panel(bar,0);
 if(panel==2)return y>=(int)W(bar,8)+8&&y<(int)W(bar,8)+62;
 if(panel==1)return y>=(int)W(bar,8)+8&&y<(int)W(bar,8)+40;
 /* Native value label rectangle; not the parameter title or slider. */
 void *label=(u8*)slot+0x2cc;return y>=(int)W(label,8)&&y<(int)(W(label,8)+W(label,16));
}
int kit_seq_point(void *widget,void *point,void **out){
 KitSeq *s=state(0);if(!point||!out||!kit_seq_holding())return 0;
 for(u32 row=0;row<3;row++)if(widget==(u8*)s->view+0x38+row*0x23f8&&!B(widget,0x30)){*out=widget;return 1;}
 return 0;
}
void kit_seq_header_reset(void *out){
 if(H(out,NOFF_HDR(0x74)+5*48+44)!=KIT_SEQ_ACTION||B(out,NOFF_HDR(0x1c2))!=8)return;
 for(u32 i=5;i;i--)for(u32 j=0;j<48;j++)B(out,NOFF_HDR(0x74)+i*48+j)=B(out,NOFF_HDR(0x74)+(i-1)*48+j);
 for(u32 j=0;j<48;j++)B(out,NOFF_HDR(0x74)+j)=j==0x20;
}
int kit_seq_toolbar(void *out){
 KitSeq *s=state(0);if(!out||!editor(s)||B(out,NOFF_HDR(0x1c2))!=8)return 0;
 inst_follow(s); /* R6.2: shared with SEQ */
 /* Idempotent: the native snapshot may already have passed this hook. */
 int change=0; /* R6.3 (owner): no Pads/Steps footer button; Left+Right toggles it */
 B((u8*)s->view+0x80b4,0x30)=!s->on; /* run 18 (owner): the sample name moves to the footer label; the box keeps the Steps readout */
 extern int motion_one_shot_toolbar(void*);change|=motion_one_shot_toolbar(out);
 if(s->on){
  char name[256]={0},title[32];u32 end=s->page+16;if(end>s->length)end=s->length;
  NFN(0x0813390e,int(*)(void*,void*,u32,char*))(MODEL,&s->cell,0x82,name);
  if(!name[0]){name[0]='P';name[1]='a';name[2]='d';name[3]=0;}name[8]=0;
  if(s->error)NFN(0x08186ee6,int(*)(char*,u32,const char*,...))(title,sizeof(title),"%s %s",name,s->error==2?"2/2 locks used":s->error==3?"No edit memory":s->error==5?"Target not lockable":s->error==6?"Clip note limit":s->error==7?"Empty step":"No sequence");
  else if(s->held){
   u32 first=0,used=0;int value=0;while(!(s->held&(1u<<first)))first++;
   int mode=locks_direct_value(s->seq,s->pad,s->page,s->held,0,0,&value,&used);
   NFN(0x08186ee6,int(*)(char*,u32,const char*,...))(title,sizeof(title),"%s S%u%s Locks %s",name,s->page+first+1,s->held&(s->held-1)?"+":"",mode==5?"empty":used==3?"mixed":used==2?"2/2":used==1?"1/2":"0/2");
  }else NFN(0x08186ee6,int(*)(char*,u32,const char*,...))(title,sizeof(title),"%s Steps %u-%u/%u",name,s->page+1,end,s->length);
  for(u32 i=0;i<32;i++){B(out,i)=(u8)title[i];if(!title[i])break;}B(out,0x60)=0;
  NFN(0x0817e85e,void(*)(void*,const char*))((u8*)s->view+0x80b4,title);
 }
 return change;
}
int kit_seq_lights(void *pads){
 u32 pg=B(MODEL,0x12c);KitSeq *s=state(pg==8||pg==7);if(!s||pads!=(u8*)MODEL+NOFF_MODEL_PADS)return 0;
 /* R6.6 (owner: the selected pad is an intense white on the one-shot INST and
    Auto pages): the same sound lights there. R6.8b (owner: still white in the
    INST 16-sound overview): INST outside the Kit/Seq editor always (the pads
    are the sounds there whatever the Steps/Pads mode), state created on demand there (not on 17: bank lights). */
 {extern int play_mute_bank(int);u32 page=pg;if(!s->on&&(page==0x17||page==8||page==7)&&!play_mute_bank(-1)){u32 t=0; /* P168 exp3 (owner: still white): page 7 is an Instrument page of a one-shot track too (pad presses are taken there, kit_seq_dispatch) and was never covered */ /* a held PLAY bank keeps its mute lights */
  if(ui_owner(&t)&&t&&ui_type(&t)==14)return pads_lights(s,0,pads);}}
 if(!s->on&&!(s->tracks&track_bit())){void *v=seq_view(s);return v?pads_lights(s,v,pads):0;} /* R6.3: Pads mode */
 if(!(s->on?editor(s):seq_view_mode(s)))return 0;
 u32 lit=0,e[6];void *c=notes(s);
 if(c&&W(c,0x3000)<=511)for(u32 i=0;i<W(c,0x3000);i++){
  if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))(c,i,e))break;int at=step(e);
  if(B(e,0)==1&&H(e,2)==s->pad&&at>=(int)s->page&&at<(int)s->page+16)lit|=1u<<(at-s->page);
 }
 u32 index=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)MODEL+4,0x131),dim=NFN(0x08140f50,u32(*)(u32))(index),bright=NFN(0x08140ef0,u32(*)(u32))(index);
 int row=-1,q=-1,pos=NFN(0x081322ac,int(*)(void*,u32,int*,int*))(MODEL,index,&row,&q);u32 cliprow=16;
 ui_get(&s->seq,0x73,&cliprow);
 for(u32 i=0;i<64;i++)W(pads,i*4)=0;
 for(u32 i=0;i<16;i++){
  u32 at=s->page+i;if(at>=s->length)continue;
  /* Native flush picks +4 for held, else +8 for playhead, else +0. */
  /* R6.4 (owner): only real steps light (track colour); the playing step and
     a held pad brighter; empty steps dark. */
  u32 on=lit&(1u<<i);
  W(pads,i*16)=on?dim:0;
  W(pads,i*16+4)=bright;
  W(pads,i*16+8)=on?bright:0;
  if(s->held&(1u<<i))B(pads,i*16+12)=1;
  if(pos>=0&&row==(int)cliprow&&(u32)pos==at)B(pads,i*16+13)=1;
 }
 return 1;
}
void kit_seq_periodic(void){
 KitSeq *s=state(0);
 /* R6.4 (owner): holding a Steps pad on the SEQ page opens that step natively
  * (0815D1EC, as a touch on the step would), so its values are on the encoders. */
 if(s&&!s->on&&s->sq_down&&!s->sq_hold&&NOW-s->sq_tick>=350u){
  void *v=seq_view(s);if(v){s->sq_hold=1;NFN(0x0815d1ec,void(*)(void*,u32))(v,s->page+s->sq_down-1);}else s->sq_down=0;
 }
 if(!s||!s->on)return;
 if(!editor(s)||!context(s)){gate(s,0);refresh(s);return;}
 if(settle(s,0))refresh(s);
 if(NOW-s->poll<33)return;s->poll=NOW;
 /* Physical release precedes queued UI delivery. Cancel the held overlay,
  * but retain its gesture until the release arrives; never invent a tap. */
 u32 physical=H(INPUT,6),held=0;
 for(u32 i=0;i<16;i++)if((physical&(1u<<i))&&B(INPUT,16+i)<16)held|=1u<<B(INPUT,16+i);
 if(s->held&~held){s->released|=s->held&~held;s->held&=held;s->tap=0;if(!s->held)s->focus=0;s->targets[0]=s->targets[1]=0;refresh(s);}
 u32 visible=(u32)strip_visible(s);if(visible!=s->strip){s->strip=visible;refresh(s);}
 NFN(0x081257f0,void(*)(void*))((u8*)MODEL+NOFF_MODEL_PADS);
}
int kit_seq_strip_snapshot(void *bar,KitStep *out){
 KitSeq *s=state(0);extern int drum_panel(void*,u32*);
 if(!strip_visible(s)||bar!=(u8*)s->view+0x4828||drum_panel(bar,0)!=2)return 0;
 if(!locks_step_snapshot(s->seq,s->pad,s->page,s->held,out))out->empty=1;
 if(s->held&(s->held-1))out->mixed|=64u;
 for(u32 i=0;i<2;i++){
  out->picks[i]=s->choosing[i]?s->picks[i]:s->targets[i];
  if(s->choosing[i])out->choosing|=1u<<i;
  else if(s->picks[i]&&s->targets[i]&&lock_kind((u32)out->value[3+i])!=s->targets[i]){
   out->choosing|=4u<<i;out->mixed&=~(1u<<(3+i));
  }
 }
 return 1;
}
int kit_seq_step_focus(int set){
 KitSeq *s=state(0);if(!kit_seq_holding())return 0;
 if(set>0&&!strip_visible(s))return 0;
 if(set>=0){
  s->used|=s->held;s->tap=0;
  if(s->focus!=(u32)set){s->focus=(u32)set;s->choosing[0]=s->choosing[1]=0;refresh(s);}
 }
 return (int)s->focus;
}
void kit_seq_strip_bind(void *v){
 KitSeq *s=state(0);KitStep snap;void *bar=(u8*)v+0x4828;
 if(!kit_seq_strip_snapshot(bar,&snap))return;
 extern int kick_ui_supported(void*);u32 model=(u32)kick_ui_supported(v);
 if(!locks_step_registry(model))return;
 if(!s->targets[0]){
  for(u32 i=0;i<2;i++){s->targets[i]=lock_kind((u32)snap.value[3+i]);if(!locks_step_choice(model,s->targets[i],0))s->targets[i]=i?4:1;s->choosing[i]=s->picks[i]=0;}
  if(s->targets[0]==s->targets[1])s->targets[1]=s->targets[0]==4?1:4;
 }
 for(u32 i=0;i<8;i++){
  u32 key=i==0?NKEY(0x186):i==1?NKEY(0x183):i==2?NKEY(0x184):i==3?NKEY(0x18c):i==5?NKEY(0x199):0;
  int value=i==0?(int)s->pad+1:i==1?snap.value[0]:i==2?snap.value[2]:i==3?snap.value[1]:0;
  if(i==5){u32 c=snap.condition;value=c==~0u?99:(int)cond_pos(c);}
  if(i>=6){
   u32 j=i-6,k=s->targets[j],w=(u32)snap.value[3+j];
   key=s->choosing[j]?(j?NKEY(0x1e4):NKEY(0x1da)):native_key(k);
   if(s->choosing[j])value=(int)s->picks[j];
   else if(lock_kind(w)==k)value=decode_value(w);
   else kick_base_value(v,native_key(k),&value);
  }
  void *slot=(u8*)bar+0x38+i*0x468;
  NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,0);
  ui_slot_set(slot,key,value);
  if(i>=6&&!s->choosing[i-6]){
   u32 j=i-6,k=s->targets[j],w=(u32)snap.value[3+j];const char *text=0;char number[24];
   if(snap.empty)text="Empty";
   else if(snap.mixed&(1u<<(3+j)))text="Mixed";
   else if(lock_kind(w)!=k)text=w&&!(snap.choosing&(4u<<j))?"Inactive lock":"--";
   else if(k>=12){
    int hz=k==12||k==20||k==25;
    NFN(0x08186ee6,int(*)(char*,u32,const char*,...))(number,sizeof(number),"%u%s",hz?drum_tune_hz(model,(u32)value):(u32)value,hz?" Hz":"%");text=number;
   }
   if(text)NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,text);
  }
  if(i&&i<4&&(snap.empty||(snap.mixed&(1u<<(i==1?0:i==2?2:1)))))
   NFN(0x08170656,void(*)(void*,u32,const char*))(bar,i,snap.empty?"Empty":"Mixed");
  B(slot,0x30)=!key;
 }
}
int kit_seq_step_event(u32 key,int value){
 KitSeq *s=state(0);if(!s||!s->focus)return 1;
 u32 field=key==NKEY(0x183)?0:key==NKEY(0x18c)?1:key==NKEY(0x184)?2:key==NKEY(0x199)?3:6;
 extern int kick_ui_supported(void*);u32 model=(u32)kick_ui_supported((void*)s->view);
 if(key==NKEY(0x1da)||key==NKEY(0x1e4)){
  u32 i=key==NKEY(0x1e4);if(!s->choosing[i])return 1;
  u32 k=locks_step_choice(model,value<0?0:(u32)value,1);
  if(k&&k==s->targets[1-i]){message(s,2);return 1;}
  s->picks[i]=locks_step_choice(model,k,0);if(k)s->targets[i]=k;
  refresh(s);return 1;
 }
 for(u32 i=0;i<2;i++)if(!s->choosing[i]&&key==native_key(s->targets[i])){field=4+i;value=(int)encode_value(s->targets[i],value);break;}
 if(field>5)return 1;
 int result=locks_step_edit(s->seq,s->pad,s->page,s->held,field,value,1);
 s->error=result>1?(u32)result:0;refresh(s);return 1;
}
int kit_seq_step_touch(u32 which,int twice){
 KitSeq *s=state(0);if(!s||which>1||!s->focus)return 1;
 s->used|=s->held;s->tap=0;
 if(!context(s)||!s->held)return 1;
 if(twice||(s->choosing[which]&&!s->picks[which])){
  int result=locks_step_edit(s->seq,s->pad,s->page,s->held,4+which,0,1);
  s->error=result>1?(u32)result:0;s->choosing[which]=0;
 }else if(s->choosing[which])s->choosing[which]=0;
 else{
  extern int kick_ui_supported(void*);
  s->picks[which]=locks_step_choice((u32)kick_ui_supported((void*)s->view),s->targets[which],0);
  s->choosing[which]=1;
 }
 refresh(s);return 1;
}
int kit_seq_strip_touch(void *bar,void *point,u32 id,int phase){
 (void)point;(void)id;KitSeq *s=state(0);extern int drum_panel(void*,u32*);
 if(!s||!kit_seq_holding())return 0;
 int row=drum_panel(bar,0);if(row!=1&&row!=2)return 0;
 if(row==2&&!strip_visible(s))return 1;
 if(!phase){
  s->used|=s->held;
  s->focus_touch=s->focus!=(u32)(row==2);
  if(s->focus_touch)kit_seq_step_focus(row==2);
 }
 int handled=(int)s->focus_touch;if(phase==2)s->focus_touch=0;return handled;
}
