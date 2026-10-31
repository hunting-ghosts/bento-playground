/* Native clip-step capture. Native routes own the sound; base values stay put.
 * Only evidenced normalized modulation destinations are admitted. */
#ifndef BENTO_CLIP_MOTION_H
#define BENTO_CLIP_MOTION_H

typedef struct {
 u32 handle,key,lane,route;
 int depth,current,source,remainder;
} ClipMotionTarget;
typedef struct {
 u32 enabled,tree,owner,sequence,row,track,steps,snapshot,count,error;
 u32 pending,handle,key,time,echo;
 int before;
 ClipMotionTarget targets[4];
} ClipMotion;
enum {CM_OK,CM_CLIP,CM_CHANGED,CM_PLAY,CM_ASSIGN,CM_ROUTE,CM_RANGE,CM_MEMORY,CM_TARGET};
static u32 cm_now(void){return W((void*)0x3001fe2cu,0);}
static void cm_zero(void *p,u32 n){for(u32 i=0;i<n;i++)B(p,i)=0;}
static int cm_property(u32 h,u32 k,u32 *out){
 return FN(0x08133614,int(*)(void*,u32*,u32,u32*))(MODEL,&h,k,out);
}
__attribute__((noinline,section(".pad"))) static int cm_selected(u32 *owner,u32 *sequence,u32 *row,u32 *track,u32 *steps){
 *owner=*sequence=0;
 if(!FN(0x08133cfc,int(*)(void*,u32*))(MODEL,owner)||
    !FN(0x08133614,int(*)(void*,void*,u32,u32*))(MODEL,(void*)0x30030164u,0x131,track)||
    *track>=8||!cm_property(*owner,0x133,row)||*row>=16)return 0;
 for(u32 i=0;i<512;i++){
  u32 h=0,r=16;
  if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,owner,i,&h))break;
  if(FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&h)!=0x18)continue;
  if(cm_property(h,0x73,&r)&&r==*row){
   if(!cm_property(h,0x62,steps)||!*steps||*steps>256)return 0;
   *sequence=h;return 1;
  }
 }
 return 0;
}
static void cm_end(ClipMotion *s){
 s->pending=s->snapshot=s->count=s->echo=0;
}
static int cm_enable(ClipMotion *s,int on){
 cm_zero(s,sizeof(*s));if(!on)return 1;
 if(!W(MODEL,0)||!cm_selected(&s->owner,&s->sequence,&s->row,&s->track,&s->steps)){
  s->error=CM_CLIP;return 0;
 }
 s->tree=W(MODEL,0);s->enabled=1;return 1;
}
static int cm_context(ClipMotion *s,int *position){
 u32 owner=0,sequence=0,row=16,track=8,steps=0;
 if(!s->enabled)return 0;
 if(s->tree!=W(MODEL,0)||!cm_selected(&owner,&sequence,&row,&track,&steps)||
    owner!=s->owner||sequence!=s->sequence||row!=s->row||track!=s->track||steps!=s->steps){
  cm_end(s);s->enabled=0;s->error=CM_CHANGED;return 0;
 }
 int playing=-1,queued=-1;
 if(!W((void*)0x3000f650u,0)){cm_end(s);s->error=CM_PLAY;return 0;}
 int at=FN(0x081322ac,int(*)(void*,u32,int*,int*))(MODEL,track,&playing,&queued);
 if(at<0||at>=(int)steps||playing!=(int)row){
  cm_end(s);s->error=CM_PLAY;return 0;
 }
 *position=at;return 1;
}
static int cm_route(u32 handle,u32 key,u32 slot,u32 *out){
 return FN(0x08131244,int(*)(void*,u32*,u32,u32,u32*))(MODEL,&handle,key,slot,out);
}
static int cm_supported(u32 h,u32 key){
 u32 type=FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&h);
 if(type==1||type==2){
  static const u16 keys[]={0x1e,0x1f,0x21,0x32,0x33,0x4b,0x4c};
  for(u32 i=0;i<sizeof(keys)/sizeof(*keys);i++)if(key==keys[i])return 1;
 }else for(u32 i=0;i<60;i++){
  const u32 *d=(const u32*)(0x0819de54u+24*i);
  if(d[0]==type&&d[2]==key)return 1;
 }
 return 0;
}
/* The route setter resolves only tracks and their direct children. */
__attribute__((noinline,section(".pad"))) static void *cm_object(ClipMotion *s,u32 handle){
 void *owner=0;
 if(!FN(0x0812d80e,int(*)(void*,u32,void**))((void*)s->tree,s->owner,&owner)||!owner)return 0;
 if(handle==s->owner)return owner;
 void *out=0;
 FN(W((void*)W(owner,0),0x14),int(*)(void*,u32,void**))(owner,handle,&out);return out;
}
/* Reserve every routed lane and every stored lane on this track, even in
 * another clip. A zero-depth route still belongs to its original target. */
__attribute__((noinline,section(".pad"))) static int cm_inventory(ClipMotion *s,u32 *used,u32 *shared){
 void *owner=cm_object(s,s->owner);if(!owner)return 0;
 *used=*shared=0;
 for(u32 i=0;i<=512;i++){
  void *obj=owner;
  if(i){
   obj=0;
   if(!FN(W((void*)W(owner,0),0x18),int(*)(void*,u32,void**))(owner,i-1,&obj))return 1;
   if(!obj||i==512)return 0;
  }
  void *r=(void*)W(obj,0x14);
  for(u32 n=0;r;n++,r=(void*)W(r,4)){
   if(n==512)return 0;
   u32 source=H(r,0x10);
   if(B(r,8)==1&&source>=9&&source<=12){
    u32 bit=1u<<(source-9);*used|=bit;
    if(W(obj,0x10)!=s->handle||H(r,0x12)!=s->key)*shared|=bit;
   }
  }
  if(FN(W((void*)W(obj,0),0),u32(*)(void*))(obj)==0x18){
   void *node=0;
   if(FN(0x0812ea72,int(*)(void*,u32,void**,int))((void*)s->tree,W(obj,0x10),&node,0)&&node){
    for(u32 lane=0;lane<4;lane++){
     if(B(node,0x80a+lane)||B(node,0x80e + lane))*used|=1u<<lane;
     else for(u32 step=0;step<256;step++)if(H(node,10+lane*512+step*2)){*used|=1u<<lane;break;}
    }
   }
  }
 }
 return 0;
}
static void cm_set_route(u32 handle,u32 key,u32 slot,u32 source,int depth){
 u32 e[5]={0xd1,handle,key|1u<<16,source|slot<<16,(u32)depth};
 FN(0x08133388,void(*)(void*,void*))(MODEL,e);
}
static void cm_begin(ClipMotion *s,void *slot,int delta){
 if(!s||!s->enabled)return;s->pending=s->echo=0;
 if(!slot||!delta)return;
 u32 h=W(slot,0x34),key=H(slot,0x9c);
 if(!cm_supported(h,key)){
  s->error=CM_TARGET;return;
 }
 s->pending=(u32)slot;s->handle=h;s->key=key;s->before=(int)W(slot,0xa0);s->time=cm_now();
}
static int cm_event(ClipMotion *s,void *event){
 if(!s||!s->enabled||!event)return 0;
 u32 code=H(event,0);
 /* Native synth views send D0, then bubble the original CF to the model. */
 if(s->echo){
  s->echo=0;
  if(code==0xcf&&W(event,4)==s->handle&&W(event,8)==s->key&&
     (int)W(event,12)==s->before&&cm_now()-s->time<=100)return 1;
 }
 if(!s->pending||(code!=0xcf&&code!=0xd0)||W(event,4)!=s->handle||W(event,8)!=s->key){
  if(code==0xcf||code==0xd0||code==0xd1||code==0x1032)cm_end(s);
  return 0;
 }
 void *slot=(void*)s->pending;s->pending=0;
 int position=0;
 if(!cm_context(s,&position))return 1;
 if(cm_now()-s->time>100||W(slot,0x34)!=s->handle||H(slot,0x9c)!=s->key||
    (int)W(slot,0xa0)!=s->before)return 0;
 if(!cm_object(s,s->handle)){s->error=CM_TARGET;return 1;}
 /* WT Position is 0..255 on M4, but its M7 modulation input is normalized. */
 u32 span=s->key==0xc9?255:1000;
 if((int)W(slot,0x450)!=0||W(slot,0x454)!=span||
    W(event,12)>span||(u32)s->before>span){s->error=CM_RANGE;return 1;}
 u32 lane=4,route=0,free=3;int depth=0;
 for(u32 i=0;i<3;i++){
  u32 r[3]={0};if(!cm_route(s->handle,s->key,i,r)){if(free==3)free=i;continue;}
  u32 source=r[1]&65535;
  if(source>=9&&source<=12){
   if(!r[0]||(int)r[0]<-1000||(int)r[0]>1000){s->error=CM_ROUTE;return 1;}
   if(lane!=4){s->error=CM_ROUTE;return 1;}
   lane=source-9;route=i;depth=(int)r[0];
  }
 }
 ClipMotionTarget *t=0;
 for(u32 i=0;i<s->count;i++){
  ClipMotionTarget *p=s->targets+i;
  if(p->handle==s->handle&&p->key==s->key)t=p;
  else if(p->lane==lane){s->error=CM_ROUTE;return 1;}
 }
 if(t&&(t->lane!=lane||t->route!=route||t->depth!=depth)){
  s->error=CM_ROUTE;return 1;
 }
 if(!t){
  if(s->count==4){s->error=CM_ROUTE;return 1;}
  u32 used=0,shared=0;
  if(!cm_inventory(s,&used,&shared)){s->error=CM_ROUTE;return 1;}
  if(lane<4&&(shared>>lane&1)){s->error=CM_ROUTE;return 1;}
  if(lane==4){
   for(lane=0;lane<4&&(used>>lane&1);lane++);
   if(lane==4||free==3){s->error=CM_ASSIGN;return 1;}
   route=free;depth=1000;
  }
  t=s->targets+s->count;cm_zero(t,sizeof(*t));
  t->handle=s->handle;t->key=s->key;t->lane=lane;t->route=route;t->depth=depth;
  t->source=FN(0x081322f6,int(*)(void*,u32*,u32,u32))(MODEL,&s->sequence,lane,(u32)position);
 }
 int divisor=depth*(span==255?255:1);
 int numerator=((int)W(event,12)-s->before)*(span==255?1000000:1000)+t->remainder;
 int value=t->source+numerator/divisor;
 if(value<-1000||value>1000){s->error=CM_RANGE;return 1;}
 int created=0;
 if(free==route){
  void *node=0,*object=cm_object(s,s->handle),*record=0;
  if(!object){s->error=CM_ROUTE;return 1;}
  if(!s->snapshot){FN(0x081338dc,void(*)(void*))(MODEL);s->snapshot=1;}
  if(!FN(0x0812ea72,int(*)(void*,u32,void**,int))((void*)s->tree,s->sequence,&node,1)||!node||
     !FN(0x0812e7dc,int(*)(void*,u32,void*,void**))((void*)s->tree,1,object,&record)||!record){
   s->error=CM_MEMORY;return 1;
  }
  /* Preallocate the native record so its setter cannot dereference a failed
   * route allocation. It finds this exact key/slot and publishes normally. */
  H(record,0x12)=(u16)s->key;H(record,0x14)=(u16)route;
  cm_set_route(s->handle,s->key,route,lane+9,depth);
  u32 r[3]={0};
  if(!cm_route(s->handle,s->key,route,r)||(r[1]&65535)!=lane+9||(int)r[0]!=depth){
   cm_set_route(s->handle,s->key,route,0,0);
   s->error=CM_ROUTE;return 1;
  }
  created=1;
 }
 FN(0x0813706c,void(*)(void*,u32*,u32,u32,int,u32))(MODEL,&s->sequence,lane,(u32)position,(int)value,!s->snapshot);
 void *node=0;
 if(!FN(0x0812ea72,int(*)(void*,u32,void**,int))((void*)W(MODEL,0),s->sequence,&node,0)||
    !node||!B(node,0x80a+lane)||
    FN(0x081322f6,int(*)(void*,u32*,u32,u32))(MODEL,&s->sequence,lane,(u32)position)!=(int)value){
  if(created)cm_set_route(s->handle,s->key,route,0,0);
  s->error=CM_MEMORY;return 1;
 }
 if(t==s->targets+s->count)s->count++;
 t->remainder=numerator%divisor;t->source=value;t->current=(int)W(event,12);
 if(code==0xd0){s->echo=1;s->before=t->current;}
 s->snapshot=1;s->error=CM_OK;return 1;
}
static int cm_get(ClipMotion *s,void *handle,u32 key,void *out){
 if(!s||!s->enabled||!handle||!out)return 0;
 for(u32 i=0;i<s->count;i++){
  ClipMotionTarget *t=s->targets+i;
  if(t->handle==W(handle,0)&&t->key==key){
   int position=0;if(!cm_context(s,&position))return 0;
   W(out,0)=(u32)t->current;return 1;
  }
 }
 return 0;
}
static const char *cm_label(ClipMotion *s){
 if(!s||!s->error)return "Motion";
 static const char *const errors[]={"Motion","Select clip","Clip changed","Play clip","No free A-D","Check route","Motion range","Motion memory","Not a motion target"};
 return s->error<=CM_TARGET?errors[s->error]:"Motion";
}
#endif
