#include "fx_shared.h"

static const char unavailable[] __attribute__((section(".pad3r")))="PLAY mute: no track 1 slot";
static const char memory[] __attribute__((section(".pad3r")))="PLAY mute: memory";
int play_mute_bank(int);
#define PADS ((u8*)MODEL+0x19c4)

__attribute__((naked,used,section(".pad3"))) static void native_flush(void *pads){
 __asm__ volatile("push.w {r4-r11,lr}\nsub sp,#44\nmov r4,r0\nmovw r12,#0x57f9\nmovt r12,#0x0812\nbx r12");
}

__attribute__((used,section(".pad3"))) void play_mute_flush(void *pads){
 if(pads!=PADS||!play_mute_bank(-1)){native_flush(pads);return;}
 u32 track=0;
 if(!FN(0x08133960,int(*)(void*,u32,u32*))(MODEL,0,&track)||!track||
    FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&track)!=14){native_flush(pads);return;}
 u32 saved[64],colour=FN(0x08140f50,u32(*)(u32))(0);
 for(u32 i=0;i<64;i++){saved[i]=W(pads,i*4);W(pads,i*4)=0;}
 for(u32 i=0;i<128;i++){
  u32 child=0,number=16,muted=1;
  if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,&track,i,&child))break;
  u32 kind=FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&child);
  if((kind==1||kind==2)&&FN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x73,&number)&&number<16&&
     FN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x1e0,&muted)&&!muted){
   for(u32 j=0;j<3;j++)W(pads,number*16+j*4)=colour;
  }
 }
 native_flush(pads);
 for(u32 i=0;i<64;i++)W(pads,i*4)=saved[i];
}

__attribute__((section(".pad3"))) static int mute_slot(u32 track,u32 pad){
 for(u32 i=0;i<128;i++){
  u32 child=0,number=16;
  if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,&track,i,&child))break;
  u32 kind=FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&child);
  if((kind!=1&&kind!=2)||!FN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x73,&number)||number!=pad)continue;
  u32 muted=0;
  if(!FN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x1e0,&muted))return 0;
  u32 event[5]={0xcf,child,0x1e0,!muted,0};
  FN(0x0813bfb0,void(*)(void*,void*))(MODEL,event);
  u32 after=muted;
  return FN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&child,0x1e0,&after)&&after==!muted;
 }
 return 0;
}

__attribute__((section(".pad3"))) int play_mute_dispatch(void *m,u32 pad,const u32 *record){
 if(m!=MODEL||pad>=16||!record||record[0]!=0xfe||record[1]!=0x314d5442u||record[2]!=0x31544d50u||record[3]!=pad||record[5]!=0x31525442u)return 1;
 if(record[4]==11){
  if(pad<=1){if(play_mute_bank((int)pad)!=(int)pad)FN(0x08104c00,void(*)(const char*))(memory);FN(0x081257f0,void(*)(void*))(PADS);}
  return 1;
 }
 if(record[4]!=10)return 1;
 u32 track=0;
 if(!FN(0x08133960,int(*)(void*,u32,u32*))(m,0,&track)||!track||FN(0x08133f7c,u32(*)(void*,u32*))(m,&track)!=14||!mute_slot(track,pad)){
  FN(0x08104c00,void(*)(const char*))(unavailable);
  return 1;
 }
 FN(0x081257f0,void(*)(void*))(PADS);
 return 1;
}
