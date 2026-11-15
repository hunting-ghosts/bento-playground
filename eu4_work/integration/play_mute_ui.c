#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
#include "fx_shared.h"
#include "kit_seq.h"

static const char unavailable[] __attribute__((section(".pad2r")))="PLAY mute: no track 1 slot";
static const char memory[] __attribute__((section(".pad3r")))="PLAY mute: memory";
int play_mute_bank(int);
#define PADS ((u8*)MODEL+NOFF_MODEL_PADS)

__attribute__((naked,used,section(".pad3"))) static void native_flush(void *pads){
 /* 1.6.8 port: the continuation is written as one address (native flush 081257F0 + its 8-byte
  * prologue) so that the tree translation sees it; as movw/movt halves it stayed a 1.6.1 address. */
 __asm__ volatile("push.w {r4-r11,lr}\nsub sp,#44\nmov r4,r0\nmovw r12,#:lower16:(0x081257f8+1)\nmovt r12,#:upper16:(0x081257f8+1)\nbx r12");
}

/* P168 exp3 (owner: while MIXER is held the pads fall back to the instrument's pads within a split
 * second). The hold sets the native pad mode to the mixer lights once, at the press (K16 controls:
 * native 0813BC24 writes the mode byte and rebuilds the pads). Whatever sets the mode byte back
 * afterwards, every pad flush during the hold finds it and sets it again, as run 4 did for TRACKS. */
static __attribute__((noinline)) void mixer_hold_pads(void){
 if(W((void*)0x24048d40u,0)&&B(MODEL,NOFF_MODEL_PADMODE)!=1){u32 e[5]={0x10c,0,1,0,0};NFN(0x0813bc24,void(*)(void*,void*))(MODEL,e);}
}
__attribute__((used,section(".pad3"))) void play_mute_flush(void *pads){
 /* MIXER's physical hold owns the pads until release, even if a delayed PLAY
  * bank update or the previous Instrument Seq still has an active overlay. */
 if(pads==PADS&&W((void*)0x24048cc0u,0)==0x354d5442u&&W((void*)0x24048cc0u,4)==5){
  mixer_hold_pads();native_flush(pads);return;
 }
 extern int tracks_hold_active(void);extern int tr_lights(void*);
 if(pads==PADS&&!tracks_hold_active()&&tr_lights(pads)){native_flush(pads);return;} /* R6.6 transpose pads */
 if(pads==PADS&&tracks_hold_active()){extern void tracks_hold_paint(void);tracks_hold_paint();native_flush(pads);return;} /* R6.4: TRACKS hold wins; exp3: painted here */
 if(pads==PADS){
  u32 saved[64];for(u32 i=0;i<64;i++)saved[i]=W(pads,i*4);
  if(kit_seq_lights(pads)){native_flush(pads);for(u32 i=0;i<64;i++)W(pads,i*4)=saved[i];return;}
 }
 if(pads!=PADS||!play_mute_bank(-1)){native_flush(pads);return;}
 u32 track=0;
 if(!NFN(0x08133960,int(*)(void*,u32,u32*))(MODEL,0,&track)||!track||
    NFN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&track)!=14){native_flush(pads);return;}
 u32 saved[64],colour=NFN(0x08140f50,u32(*)(u32))(0);
 for(u32 i=0;i<64;i++){saved[i]=W(pads,i*4);W(pads,i*4)=0;}
 for(u32 i=0;i<128;i++){
  u32 child=0,number=16,muted=1;
  if(!NFN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,&track,i,&child))break;
  u32 kind=NFN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&child);
  if((kind==1||kind==2)&&NFN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x73,&number)&&number<16&&
     NFN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,NKEY(0x1e0),&muted)&&!muted){
   for(u32 j=0;j<3;j++)W(pads,number*16+j*4)=colour;
  }
 }
 native_flush(pads);
 for(u32 i=0;i<64;i++)W(pads,i*4)=saved[i];
}

__attribute__((section(".pad3"))) static int mute_slot(u32 track,u32 pad){
 for(u32 i=0;i<128;i++){
  u32 child=0,number=16;
  if(!NFN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,&track,i,&child))break;
  u32 kind=NFN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&child);
  if((kind!=1&&kind!=2)||!NFN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x73,&number)||number!=pad)continue;
  u32 muted=0;
  if(!NFN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,NKEY(0x1e0),&muted))return 0;
  u32 event[5]={0xcf,child,NKEY(0x1e0),!muted,0};
  NFN(0x0813bfb0,void(*)(void*,void*))(MODEL,event);
  u32 after=muted;
  return NFN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,NKEY(0x1e0),&after)&&after==!muted;
 }
 return 0;
}

__attribute__((section(".pad3"))) int play_mute_dispatch(void *m,u32 pad,const u32 *record){
 if(m!=MODEL||pad>=16||!record||record[0]!=0xfe||record[1]!=0x314d5442u||record[2]!=0x31544d50u||record[3]!=pad||record[5]!=0x31525442u)return 1;
 if(record[4]==11){
  if(pad<=1){if(play_mute_bank((int)pad)!=(int)pad)NFN(0x08104c00,void(*)(const char*))(memory);NFN(0x081257f0,void(*)(void*))(PADS);}
  return 1;
 }
 if(record[4]!=10)return 1;
 u32 track=0;
 if(!NFN(0x08133960,int(*)(void*,u32,u32*))(m,0,&track)||!track||NFN(0x08133f7c,u32(*)(void*,u32*))(m,&track)!=14||!mute_slot(track,pad)){
  NFN(0x08104c00,void(*)(const char*))(unavailable);
  return 1;
 }
 NFN(0x081257f0,void(*)(void*))(PADS);
 return 1;
}
