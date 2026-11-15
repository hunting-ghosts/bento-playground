#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
/* Native A-D routes remain in the project model; unsupported send destinations
 * are evaluated here before the existing note-lock/native bus mixers. */
#include "melodic_lock_shared.h"
#include "melodic_send_shared.h"
#include "lock_api.h"
static MelSends *motion_sends(){return state();}
static u32 motion_gain(int value){return NFN(0x080d33c0,u32(*)(int))(value);}
static int motion_base(u32 bits){
 if(!bits)return 0;int lo=0,hi=1000;
 while(lo<hi){int mid=(lo+hi)/2;if(motion_gain(mid)<bits)lo=mid+1;else hi=mid;}
 return lo;
}
static u32 motion_gain_at(u32 base,float delta){
 int value=motion_base(base)+(int)(delta*1000.f);
 return motion_gain(value<0?0:value>1000?1000:value);
}
static float motion_source(void *root,u32 source,u32 offset){
 return source>=9&&source<=12?*(volatile float*)((u8*)root+offset+8*(source-9)+4):0;
}
extern "C" __attribute__((used,retain)) int motion_send_route(void *root,void *record){
 u32 key=H(record,12),slot=H(record,16),source=H(record,20);
 if((key!=0x36&&key!=0x37)||H(record,2)>1||slot>=3)return 0;
 MelSends *s=motion_sends();if(!s)return 0;
 MotionSendTrack *t=0;u32 bus=W(root,0x284);
 for(u32 i=0;i<8;i++)if(s->motion[i].root==(u32)root&&s->motion[i].handle==W(root,12)){t=s->motion+i;break;}
 if(!t)for(u32 i=0;i<8;i++)if(!s->motion[i].root||s->motion[i].bus==bus){t=s->motion+i;break;}
 if(!t)return 0;
 if(t->root!=(u32)root||t->handle!=W(root,12)){
  for(u32 i=0;i<sizeof(*t)/4;i++)((u32*)t)[i]=0;
  t->root=(u32)root;t->handle=W(root,12);t->bus=bus;
 }
 t->routes[(key-0x36)*3+slot]=source>=9&&source<=12?W(record,20):0;
 return 1;
}
extern "C" __attribute__((used,retain)) void motion_send_dispatch(void *root,void *record){
 if(!motion_send_route(root,record))NFN(0x0807c120,void(*)(void*,void*))(root,record);
}
extern "C" __attribute__((used,retain)) void motion_send_begin(void *root,void *router){
 MelSends *s=motion_sends();if(!s)return;
 u32 bus=W(root,0x284);
 for(u32 i=0;i<8;i++){MotionSendTrack *t=s->motion+i;
  if(t->root==(u32)root||t->bus==bus)t->input=t->strip=0;
  if(t->root==(u32)root&&t->handle==W(root,12)&&bus<17){
   t->bus=bus;t->input=(u32)router+0x5ac+bus*20;
  }
 }
}
extern "C" __attribute__((used,retain)) void motion_send_prepare(void *strip,void *input){
 MelSends *s=motion_sends();if(!s)return;
 for(u32 i=0;i<8;i++)if(s->motion[i].input==(u32)input)s->motion[i].strip=(u32)strip;
}
extern "C" __attribute__((used,retain)) void motion_send_mix(void *control,void *input,void *bus,void *strip){
 MelSends *s=motion_sends();MotionSendTrack *t=0;
 if(s)for(u32 i=0;i<8;i++)if(s->motion[i].strip==(u32)strip&&s->motion[i].handle==W((void*)s->motion[i].root,12)){t=s->motion+i;break;}
 u32 j=(u32)control==(u32)strip+0x50?0:1,active=0;float delta=0;
 if(t)for(u32 i=0;i<3;i++){u32 route=t->routes[j*3+i];if(route){active=1;delta+=motion_source((void*)t->root,route&65535,0x140 /* root offset of the source values, not a key */)*(float)(short)(route>>16)*.001f;}}
 if(!active){if(t)t->running&=~(1u<<j);mel_send_mix(control,input,bus,strip);return;}
 u32 copy[6];for(u32 i=0;i<6;i++)copy[i]=W(control,i*4);
 copy[5]=motion_gain_at(copy[5],delta);
 if(t->running&(1u<<j))copy[4]=t->current[j];
 u32 saved[6];for(u32 i=0;i<6;i++)saved[i]=W(control,i*4);
 copy[3]=0;for(u32 i=0;i<6;i++)W(control,i*4)=copy[i];
 mel_send_mix(control,input,bus,strip);
 t->current[j]=W(control,0x10);t->running|=1u<<j;
 for(u32 i=0;i<6;i++)W(control,i*4)=saved[i];
}
/* Sampler roots are processed serially. These three previously unused,
 * M7-owned words save the true base outside the existing step-lock override. */
extern "C" __attribute__((used,retain)) void motion_pad_begin(void *root){
 if(W((void*)0x24044000u,0)!=0x37535042u)FN(NATIVE_SENDS_BEGIN,void(*)(void*))(root);
 volatile u32 *save=(volatile u32*)0x24044004u;save[0]=0;
 u32 n=W(root,0x5fc);if(n>9)return;float delta[2]={0,0};u32 active=0;
 for(u32 i=0;i<n;i++){void *r=(u8*)root+0x590+i*12;u32 key=H(r,4),source=H(r,6);
  if((key==0x36||key==0x37)&&source>=9&&source<=12){
   active|=1u<<(key-0x36);delta[key-0x36]+=motion_source(root,source,0x650) * *(volatile float*)r;
  }
 }
 if(!active)return;
 save[1]=W(root,0x608);save[2]=W(root,0x60c);save[0]=(u32)root|(B(root,0x624)!=0);
 for(u32 j=0;j<2;j++)if(active&(1u<<j))W(root,0x608+j*4)=motion_gain_at(save[j+1],delta[j]);
 if(W(root,0x608)||W(root,0x60c))B(root,0x624)=1;
}
extern "C" __attribute__((used,retain)) void motion_pad_end(void *root){
 volatile u32 *save=(volatile u32*)0x24044004u;
 if((save[0]&~1u)!=(u32)root)return;
 W(root,0x608)=save[1];W(root,0x60c)=save[2];B(root,0x624)=(u8)(save[0]&1);save[0]=0;
}
extern "C" __attribute__((used,retain)) void motion_pad_start(void *root){
 motion_pad_begin(root);FN(NATIVE_SENDS_BEGIN,void(*)(void*))(root);
}
extern "C" __attribute__((used,retain)) void motion_pad_finish(void *root){
 FN(NATIVE_SENDS_END,void(*)(void*))(root);motion_pad_end(root);
}
