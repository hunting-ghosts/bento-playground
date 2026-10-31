#define _Static_assert static_assert
#define BENTO_NATIVE_MOTION
#include "native_motion.h"
static void cache(u32 p,u32 n,int clean){
 __asm__ volatile("dsb" ::: "memory");
 if(W((void*)0xe000ed14u,0)&(1u<<16)){
  u32 end=(p+n+31)&~31u;
  for(p&=~31u;p<end;p+=32)W((void*)(clean?0xe000ef68u:0xe000ef5cu),0)=p;
 }
 __asm__ volatile("dsb" ::: "memory");
}
static NmShared *device(){
 cache(NM_CONTROL_ADDR,32,0);
 if(NC->magic!=NM_MAGIC||NC->bytes!=sizeof(NmShared))return 0;
 u32 p=NC->pointer;
 if(p<0xc0000000u||!eu_memory(p,sizeof(NmShared)))return 0;
 cache(p,32,0);NmShared *d=(NmShared*)p;return d->magic==NM_MAGIC&&d->bytes==sizeof(*d)?d:0;
}
static NmClock *runtime(NmShared *d,void *s){
 NmClock *free=0;for(u32 i=0;i<8;i++){NmClock *r=d->clock+i;if(r->sequence==(u32)s)return r;if((!r->sequence||r->epoch!=d->epoch||!r->valid)&&!free)free=r;}return free;
}
static void stop_clock(NmClock *r){
 if(!r)return;
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1u;
 r->restart=1;r->valid=0;
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;cache((u32)r,sizeof(*r),1);
}
extern "C" __attribute__((used,retain)) void nm_audio_restart(void *s){
 if((int)W(s,0x14)>=0)return;NmShared *d=device();if(!d)return;
 NmClock *r=runtime(d,s);if(r&&r->sequence==(u32)s)stop_clock(r);
}
extern "C" __attribute__((used,retain)) void nm_audio_automation(void *s,const i64 *now){
 float previous[4];for(u32 i=0;i<4;i++)previous[i]=*(float*)((u8*)s+0x8740+i*8);
 FN(0x08061040,void(*)(void*,const i64*))(s,now);
 NmShared *d=device();if(!d)return;
 if(!now||*now<0){NmClock *r=runtime(d,s);if(r&&r->sequence==(u32)s)stop_clock(r);return;}
 u32 rowp=W(s,0x86c0),first=(u32)s+0x240;
 if(rowp<first||rowp>=first+16*0x848||(rowp-first)%0x848)return;
 u32 row=(rowp-first)/0x848,owner=W(s,12);NmClock *r=runtime(d,s);if(!r)return;
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;
 if(r->sequence!=(u32)s||r->owner!=owner||r->row!=row||r->epoch!=d->epoch||r->restart||*now<r->tick){
  r->spare++;if(!r->spare)r->spare=1;
  i64 origin=*(i64*)((u8*)rowp+0x20);
  r->origin=origin>=0&&origin<=*now?origin:*now;
  r->config_serial=r->config_sequence=0;for(u32 i=0;i<4;i++)r->length[i]=0;
 }
 r->sequence=(u32)s;r->owner=owner;r->row=row;r->tick=*now;r->epoch=d->epoch;r->restart=0;r->valid=B(s,0x20)!=0;
 NmClip *found=0;
 cache((u32)d,32,0);u32 count=d->spare[0];if(count>NM_CLIPS)count=0;
 for(u32 i=0;i<count;i++){NmClip *c=d->clips+i;cache((u32)c,32,0);if(c->owner==owner&&c->row==row){found=c;break;}}
 if(found){
  u32 cs=found->serial,sequence=found->sequence;u16 lengths[4];int valid=cs&&!(cs&1);
  for(u32 i=0;i<4;i++){lengths[i]=found->length[i];if(lengths[i]>NM_STEPS)valid=0;}
  __asm__ volatile("dmb" ::: "memory");cache((u32)found,32,0);
  if(valid&&found->serial==cs){for(u32 i=0;i<4;i++)r->length[i]=lengths[i];r->config_serial=cs;r->config_sequence=sequence;}
 }else {for(u32 i=0;i<4;i++)r->length[i]=0;}
 if(r->valid&&*now>=r->origin){
  u64 elapsed=(u64)(*now-r->origin);u32 step=(u32)(elapsed/NM_TICK),fraction=(u32)(elapsed%NM_TICK);
  for(u32 i=0;i<4;i++)if(r->length[i]){
   u32 at=step%r->length[i];void *data=(u8*)rowp+i*0x202;
   float value=0;
   if(B(data,0x23a)){
    int a=(short)H(data,0x3a+at*2);
    if(B((void*)rowp,0x842+i)){
     int b=(short)H(data,0x3a+((at+1)%r->length[i])*2);
     value=((float)a+(float)(b-a)*(float)fraction/(float)NM_TICK)*.001f;
    }else value=(float)a*.001f;
   }
   *(float*)((u8*)s+0x8720+i*8)=value;
   float coef=*(float*)((u8*)s+0x8764);
   float filtered=previous[i]+coef*(value-previous[i]);
   *(float*)((u8*)s+0x8740+i*8)=filtered;
   *(float*)((u8*)s+0x8770+i*8)=filtered;
  }
 }
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;cache((u32)r,sizeof(*r),1);
}
