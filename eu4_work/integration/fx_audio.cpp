#include "fx_shared.h"
#include "../track_fx/track_fx.h" /* run 17: this tree's DSP header (identical to tf2_work's without TF_SATURATOR) */
#if BENTO_FW==168&&!defined(TF_SATURATOR)
#error "1.6.8 Track FX mailbox carries the packed saturator word: build the DSP with TF_SATURATOR"
#endif
struct Meta {u32 magic,serial,ready;int prior[8][18];u32 handles[8],active[8],calls[8],bad,requested_track;FxMeterPub meter;};
#define A ((Meta*)META_ADDR)
static_assert(sizeof(Meta)<=0x340,"Audio metadata overlaps UI state");
/* Motion's M7 transport latch owns 24041980..2404199F, inside the existing
 * startup-zeroed M7 metadata reservation. No M4 writer may use this line. */
static_assert(sizeof(Meta)==0x2c0,"Audio metadata must end before motion transport latch");
static_assert(__builtin_offsetof(Meta,requested_track)==FX_METER_REQUEST_OFFSET,"Track FX request layout changed");
static_assert(__builtin_offsetof(Meta,meter)==FX_METER_PUB_OFFSET,"Track FX meter layout changed");
static void invalidate(u32 a,u32 end){
 __asm__ volatile("dsb" ::: "memory");
 if(W((void*)0xe000ed14u,0)&(1u<<16))for(;a<end;a+=32)W((void*)0xe000ef5cu,0)=a;
 __asm__ volatile("dsb" ::: "memory");
}
static void clean(u32 a,u32 end){
 __asm__ volatile("dsb" ::: "memory");
 if(W((void*)0xe000ed14u,0)&(1u<<16))for(a&=~31u;a<end;a+=32)W((void*)0xe000ef68u,0)=a;
 __asm__ volatile("dsb" ::: "memory");
}
static void publish_meter(u32 track,float db){
 volatile FxMeterPub *m=&A->meter;
 u32 serial=(m->serial+2u)&~1u;if(!serial)serial=2;
 m->serial=serial|1u;__asm__ volatile("dmb" ::: "memory");
 clean(FX_METER_CACHE_LINE,FX_METER_CACHE_LINE+32);
 m->request_tag=FX_METER_TAG(A->serial,track);m->reduction_db=db;
 __asm__ volatile("dmb" ::: "memory");m->serial=serial;
 clean(FX_METER_CACHE_LINE,FX_METER_CACHE_LINE+32);
}
static int memory(u32 p,u32 n){return p && !(p&3) && p+n>=p && ((p>=0x20000000u&&p+n<=0x20040000u)||(p>=0x24000000u&&p+n<=0x24080000u)||(p>=0x30000000u&&p+n<=0x30040000u)||(p>=0xc0000000u&&p+n<=0xc6000000u));}
static void sync(){
 if(A->magic!=0x32415846u){for(u32 j=0;j<sizeof(Meta)/4;j++)((u32*)A)[j]=0;A->magic=0x32415846u;}
 invalidate(MAIL_ADDR,MAIL_ADDR+32);
 u32 serial=MAIL->serial;if(MAIL->magic!=MAIL_MAGIC||!serial||(serial&1)||serial==A->serial)return;
 invalidate(MAIL_ADDR,MAIL_ADDR+((sizeof(FxMail)+31u)&~31u));
 int values[8][18];u32 handles[8];int any=0;
 for(int t=0;t<8;t++)handles[t]=MAIL->handles[t];
 u32 meter_track=MAIL->meter_track;if(meter_track>FX_METER_TRACKS)return;
#if BENTO_FW==168
 /* run 17: value 16 is the packed saturator word (On | Mode<<1 | Level<<8, track_fx.h), 17 the Drive in dB */
 for(int t=0;t<8;t++)for(int i=0;i<18;i++){int v=MAIL->values[t][i];
  if(i==16?((u32)v&~0xff03u)||TF_CLIP_LEVEL_DB((u32)v)<FX_LEVEL_LO||TF_CLIP_LEVEL_DB((u32)v)>FX_LEVEL_HI:v<fx_lo[i]||v>fx_hi[i])return;values[t][i]=v;}
#else
 for(int t=0;t<8;t++)for(int i=0;i<18;i++){int v=MAIL->values[t][i];if(v<fx_lo[i]||v>fx_hi[i])return;values[t][i]=v;}
#endif
 __asm__ volatile("dmb" ::: "memory");invalidate(MAIL_ADDR,MAIL_ADDR+32);
 if(serial!=MAIL->serial)return;
 for(int t=0;t<8;t++)if(values[t][0]||values[t][8]||FX_CLIP_ON(values[t][16]))any=1;
 if(!A->ready&&any){if(tf_bank_bytes()>DSP_BYTES||!tf_init((void*)DSP_ADDR,48000))return;A->ready=1;}
 for(int t=0;t<8;t++){
  int changed=!A->serial;
  for(int i=0;i<18;i++)if(A->prior[t][i]!=values[t][i])changed=1;
  if(A->ready&&(changed||A->handles[t]!=handles[t])){
   TfSettings s;tf_defaults(&s);int *v=values[t];
   s.eq_enabled=v[0];s.low_hz=v[1];s.low_db=(float)v[2]*.1f;s.mid_hz=v[3];s.mid_db=(float)v[4]*.1f;s.mid_q=(float)v[5]*.01f;s.high_hz=v[6];s.high_db=(float)v[7]*.1f; /* exp6: tenths of dB, Q hundredths */
   s.comp_enabled=v[8];s.threshold_db=v[9];s.ratio=v[10];s.attack_ms=v[11];s.release_ms=v[12];s.auto_makeup=v[13];s.makeup_db=v[14];s.comp_mix=(float)v[15]*.01f;
#if BENTO_FW==168
   s.clip_enabled=(u32)v[16];s.clip_ceiling_db=(float)-v[17]; /* run 17: packed saturator word; Drive d dB = ceiling -d dB */
#else
   s.clip_enabled=v[16];s.clip_ceiling_db=v[17];
#endif
   if(!tf_configure((void*)DSP_ADDR,t,&s))return;
   if(A->handles[t]!=handles[t])tf_reset_track((void*)DSP_ADDR,t);
  }
  for(int i=0;i<18;i++)A->prior[t][i]=values[t][i];
  A->handles[t]=handles[t];
  A->active[t]=values[t][0]||values[t][8]||FX_CLIP_ON(values[t][16])||A->active[t];
 }
 int request_changed=A->requested_track!=meter_track;
 A->requested_track=meter_track;
 A->serial=serial;
 if(request_changed)publish_meter(FX_METER_TRACKS,0);
}
extern "C" __attribute__((used)) void fx_audio(void *mixer,void *buffer,u32 track,void *strip){
 // Native 080A04C0 is called once per track; hook AFTER input gain copied to
 // the track-owned scratch, before pan, ducking, sends and dry-bus combination.
 if(track>=8||W(mixer,0)!=0x080aca1cu||W(mixer,0x860)>8||(u32)strip!=(u32)mixer+0x18+track*0x108||(u32)buffer!=(u32)strip+12)return;
 sync();if(A->magic!=0x32415846u)return;
 if(!A->ready||!A->active[track]){
  if(track==A->requested_track)publish_meter(track,0);
  return;
 }
 u32 n=W(buffer,4);if(!n)n=W(buffer,0);u32 left=W(buffer,8),right=B(buffer,0x11)?W(buffer,12):0;
 if(!n||n>1024||W(buffer,0)<n||!memory(left,n*4)||(right&&!memory(right,n*4))||(right&&(left>right?left-right<n*4:right-left<n*4))){A->bad++;if(track==A->requested_track)publish_meter(FX_METER_TRACKS,0);return;}
 if(B(buffer,0x10)){for(u32 i=0;i<n;i++){((float*)left)[i]=0;if(right)((float*)right)[i]=0;}B(buffer,0x10)=0;W(buffer,4)=n;}
 int processed=tf_process((void*)DSP_ADDR,track,(float*)left,(float*)right,n);
 if(processed)A->calls[track]++;
 if(track==A->requested_track){
  TfMeters meters={};float reduction=0;
  if(processed&&tf_meters((void*)DSP_ADDR,track,&meters)&&
     meters.reduction_db==meters.reduction_db&&meters.reduction_db>=0&&meters.reduction_db<=3.402823466e38f){
   reduction=meters.reduction_db;publish_meter(track,reduction);
  }else publish_meter(FX_METER_TRACKS,0);
 }
 // Preserve tails during the bypass fade. The DSP will make its inactive path
 // exact bypass; no native buffer pointers, counts or routing are replaced.
}
