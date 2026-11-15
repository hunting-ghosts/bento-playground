/* R6.14 ratchet UI (M4), shared helpers. Owner spec (8 Nov 2026):
 * - With a step held/inspected in the one-shot Steps view (SEQ page 27), or a
 *   note selected in the melodic piano page (Seq view = Sequence tab 1, or the
 *   Event tab 0), Right switches encoders 5..8 to Count / Shape / Depth / Prob
 *   and Left switches back. Otherwise the arrows keep their behaviour. The page
 *   is remembered until changed (per context state).
 * - Edits apply to every held/selected note through the immutable EU7 record
 *   (preflight, one native Undo snapshot, commit). Count 1 = off and forgets
 *   Shape/Depth/Prob (no ratchet word).
 * - Notes/steps that carry a ratchet get small ticks; pads keep track colour.
 * - The track's Step Len (Seq view) and the Perform Ratchet amount are
 *   published into the RtBlock config (ratchet_shared.h) for the M7 player.
 * All code in the bank-1 M4 sections (needs BENTO_M4_MPU_WIDE=1). */
#include "fx_shared.h"
#include "step_lock_shared.h"
#include "ratchet_shared.h"
#include "ratchet_ui.h"
#define RTUI __attribute__((section(".text.bank1c")))
#define RTUI2 __attribute__((section(".text.bank1d")))
#define RTUI3 __attribute__((section(".text.bank1e")))
u32 locks_ratchet_pack(u32,u32,u32,u32);u32 locks_ratchet_word(u32,u32);u32 locks_ratchet_get(u32);
static const char t_count[]="Count",t_shape[]="Shape",t_depth[]="Depth",t_prob[]="Prob";
static const char *const shape_names[3]={"Flat","Fade","Swell"};
RTUI u32 rt_ui_key(u32 f){return f==0?RT_KEY_COUNT:f==1?RT_KEY_SHAPE:f==2?RT_KEY_DEPTH:RT_KEY_PROB;}
RTUI u32 rt_ui_field(u32 key){return key==RT_KEY_COUNT?0:key==RT_KEY_SHAPE?1:key==RT_KEY_DEPTH?2:key==RT_KEY_PROB?3:4;}
RTUI const char *rt_ui_title(u32 f){return f==0?t_count:f==1?t_shape:f==2?t_depth:t_prob;}
/* Four descriptors (keys found empty after native registry construction and
 * unused in the repo). Never take one someone else owns. Prob reuses the
 * lock-condition labels (081B6000: 1..99 %, Always at 99, A:B after). */
RTUI int rt_ui_registry(void){
 u32 r=W((void*)0x30031484u,0);if(!r)return 0;
 for(u32 f=0;f<4;f++){void *d=(void*)(r+rt_ui_key(f)*32);if(H(d,0)&&W(d,4)!=(u32)rt_ui_title(f))return 0;}
 for(u32 f=0;f<4;f++){void *d=(void*)(r+rt_ui_key(f)*32);for(u32 j=0;j<8;j++)W(d,j*4)=0;H(d,0)=(unsigned short)rt_ui_key(f);W(d,4)=(u32)rt_ui_title(f);
  if(f==1){B(d,2)=7;W(d,8)=(u32)shape_names;W(d,12)=3;}
  else if(f==3){B(d,2)=7;W(d,8)=0x081b6000u;W(d,12)=COND_OFFERED;} /* R6.17; exp5 picker order */
  else{B(d,2)=2;W(d,16)=f?0:1;W(d,20)=f?100:8;}
 }
 return 1;
}
/* Encoder value of field f for a note's lock word (no ratchet: Count 1). */
RTUI int rt_ui_value(u32 word,u32 f){
 u32 r=locks_ratchet_get(word);if(!r)return f==0?1:f==3?99:0;
 if(f==0)return (int)(r&7u)+1;if(f==1)return (int)((r>>3)&3u);if(f==2)return (int)((r>>8)&127u);
 return (int)cond_pos((r>>16)&255u);
}
/* The note's lock word with field f set from encoder value v; ~0 = no record
 * memory. Count 1 removes the ratchet (and its Shape/Depth/Prob); other fields
 * do nothing while Count is 1. */
RTUI u32 rt_ui_word(u32 word,u32 f,int v){
 u32 r=locks_ratchet_get(word),n=r?(r&7u)+1:1,sh=r?(r>>3)&3u:0,dp=r?(r>>8)&127u:0,pr=r?(r>>16)&255u:0;
 if(f==0){n=v<1?1:v>8?8:(u32)v;}
 else{if(n<2)return word;
  if(f==1){sh=v<0?0:v>2?2:(u32)v;if(sh&&!dp)dp=60;} /* P168 exp3 (owner: Shape does not change velocity): Fade/Swell are scaled by Depth, which started at 0 = no change; choosing a shape now starts at 60 % */
  else if(f==2)dp=v<0?0:v>100?100:(u32)v;
  else pr=cond_code(v);}
 u32 nr=locks_ratchet_pack(n,sh,dp,pr);if(nr==0xffffffffu)return 0xffffffffu;
 return nr==r?word:locks_ratchet_word(word,nr);
}
/* RtBlock config slot of a track (M4 owns these lines). */
static RtBlock *rt_block(void){u32 q=*RT_EC_POINTER;return q>=0xc0000000u&&q<0xc8000000u&&!(q&31)&&W((void*)q,0)==RT_BLOCK_MAGIC?(RtBlock*)q:0;}
RTUI2 void rt_ui_publish(u32 owner,int step,int amount){
 RtBlock *b=rt_block();if(!b||!owner)return;int at=-1;
 for(u32 i=0;i<RT_TRACKS;i++)if(b->cfg.owner[i]==owner){at=(int)i;break;}
 if(at<0){if(amount<0?step<=0:amount==100&&step<=0)return; /* defaults need no slot */
  for(u32 i=0;i<RT_TRACKS;i++)if(!b->cfg.owner[i]||(b->cfg.amount[i]==100&&!b->cfg.step[i])){at=(int)i;break;}
  if(at<0)return;b->cfg.amount[at]=100;b->cfg.step[at]=0;__asm__ volatile("dmb" ::: "memory");b->cfg.owner[at]=owner;}
 if(amount>=0)b->cfg.amount[at]=(u8)(amount>100?100:amount);
 if(step>0)b->cfg.step[at]=(unsigned short)(step>65535?65535:step);
}
/* Native step grid scale (float table 080BDBEC) x 960 ticks, without the FPU. */
RTUI2 u32 rt_ui_grid_ticks(u32 grid){
 if(grid>=15)return 0;u32 bits=W((void*)0x080bdbecu,grid*4),e=(bits>>23)&255u;if(!e||e==255||(bits>>31))return 0;
 unsigned long long m=(unsigned long long)((bits&0x7fffffu)|0x800000u)*960u;int s=(int)e-127-23;
 u32 t=s>=0?(u32)(m<<s):(u32)((m+(1ull<<(-s-1)))>>(-s));return t<=30720?t:0;
}
/* Left/Right while a ratchet context is active: switch the page (on release;
 * the press is swallowed too, and only a swallowed press's release). */
int locks_rt_arrow(void*,u32,int);int melodic_rt_arrow(u32,int);void *step_current_view(void);u32 *locks_rt_state(void);
__attribute__((section(".text.bank1g"))) int rt_ui_arrows(u32 code,u32 index){
 if((code!=0xaf&&code!=0xb0)||(index!=0&&index!=9))return 0;
 u32 *st=locks_rt_state();if(!st)return 0;u32 bit=index?0x400u:0x200u,page=B(MODEL,0x12c); /* bits 9/10 of the lock UI's auto_eu word */
 if(code==0xb0){if(!(*st&bit))return 0;*st&=~bit;}
 else if(W((void*)0x24048cc0u,8))return 0; /* a K16 modifier is held: native */
 int ok=page==0x17?melodic_rt_arrow(index==9,code==0xb0):page==0x27&&step_current_view()?locks_rt_arrow(step_current_view(),index==9,code==0xb0):0;
 if(code==0xaf&&ok)*st|=bit;return code==0xb0?1:ok;
}
/* R6.14: kit_seq_arrows (which owns the Steps page's arrows and the
 * Left+Right combo) calls this on a lone arrow's release. */
__attribute__((section(".text.bank1d"))) int rt_ui_step_arrow(u32 index){void *v=step_current_view();return v?locks_rt_arrow(v,index==9,1):0;}
/* Piano-roll ticks: count-1 thin dividers across each note that carries a
 * ratchet, drawn after the native grid paint (full and partial passes). */
#define FILL(r,c,s) NFN(0x08166ef6,void(*)(const int*,u32,u32))(r,c,s)
RTUI3 void rt_note_ticks(void *grid,void *ctx){
 u8 *g=(u8*)grid,*v=g-0x38;if(!ctx||(!B(ctx,0)&&!B(ctx,1))||W(v,0)!=0x0819e7b0u||B(g,0x30))return;
 u32 surface=W(ctx,4),seq=W(v,0x11cd00);void *node=0;
 if(!seq||!W(MODEL,0)||!NFN(0x0812dfe8,int(*)(void*,u32,void*))((void*)W(MODEL,0),seq,&node)||!node)return;
 void *c=(u8*)node+12;u32 n=W(c,0x3000);if(n>511)return;u32 e[6];
 for(u32 i=0;i<n;i++){
  if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))(c,i,e))break;if(B(e,0)!=1)continue;
  u32 r=locks_ratchet_get(e[5]);if(!r)continue;u32 k=(r&7u)+1;
  u32 row=B(g,0xa10)?NFN(0x081751ec,u32(*)(void*,u32))(g,H(e,2)):H(e,16);
  int rc[4];NFN(0x0817566a,void(*)(int*,void*,u32,u32,u32))(rc,g,e[1],e[2],row);if(rc[2]<4||rc[3]<4)continue;
  for(u32 j=1;j<k;j++){int t[4]={rc[0]+(int)((u32)rc[2]*j/k),rc[1]+1,1,rc[3]-2};FILL(t,0xf1u,surface);}
 }
}
