/* Toggle-enabled producer. No retired motion code, enlarged nodes or sample side
 * store. The native writer owns data, Undo notifications and audio packets. */
#include "native_motion.h"
#ifdef BENTO_NATIVE_MOTION
#define NOW W((void*)0x3001fe2cu,0)
#define LENGTH_KEY 0x176u
#define META_COUNT 512u
static const char length_name[]="Lane Steps";
typedef struct {u32 seq;u16 length[4];u32 loaded,tree;} Meta;
typedef struct {
 u32 handle,key,lane,slot,step,time;int amount,span,current,source;
 i64 remainder;
} Target;
typedef struct {u32 widget,handle,key,mask;int value;} Mark;
typedef struct {
 u32 magic,shared,enabled,used,serial,seq,owner,row,steps,snapshot,view,pending;
 u32 count,lanes,started,error_until,descriptors_saved,clearing;
 i64 start,last;
 int before;
 Target targets[4];Meta meta[META_COUNT];
 u32 descriptors[8];
 char message[32],name[16];
 Mark marks[24];
 u32 written,write_time;
 u32 pending_owner,pending_seq,pending_row,clock_sequence,clock_epoch,clock_generation;
} Recorder;
void **native_motion_state_slot(int create);
static void zero(void *p,u32 n){for(u32 i=0;i<n;i++)B(p,i)=0;}
static void barrier(void){__asm__ volatile("dmb" ::: "memory");}
static void *allocate(u32 bytes){
 u32 n=(bytes+31u)&~31u,p=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0);
 if(!eu_memory(p,n)||p<0xc0000000u||end>0xc8000000u||end<p||end-p<n)return 0;
 void *out=FN(0x08104c08,void*(*)(u32))(n);return (u32)out==p?out:0;
}
static Recorder *state(int create){
 void **slot=native_motion_state_slot(create);
 if(!slot){if(create){NC->error=1;NC->enabled=0;}return 0;}Recorder *s=*slot;
 if(s)return s->magic==NM_MAGIC?s:0;if(!create)return 0;
 u32 offset=(sizeof(*s)+31u)&~31u;
 u32 bytes=offset+sizeof(NmShared);
 if(!NC->initializing){
  s=allocate(bytes);
  if(!s){NC->error=1;NC->enabled=0;return 0;}
  NC->initializing=(u32)s;NC->progress=0;
 }
 s=(Recorder*)NC->initializing;
 u32 count=bytes-NC->progress;if(create==2&&count>1024)count=1024;
 zero((u8*)s+NC->progress,count);NC->progress+=count;
 if(NC->progress<bytes)return 0;
 NmShared *d=(NmShared*)((u8*)s+offset);d->bytes=sizeof(*d);d->epoch=1;d->magic=NM_MAGIC;
 s->shared=(u32)d;s->magic=NM_MAGIC;s->enabled=NC->enabled;*slot=s;
 NC->bytes=sizeof(*d);NC->epoch=1;barrier();NC->pointer=(u32)d;
 NC->initializing=NC->progress=0;barrier();NC->magic=NM_MAGIC;return s;
}
static void message(Recorder *s,const char *text){
 u32 i=0;while(text[i]&&i<31){s->message[i]=text[i];i++;}s->message[i]=0;s->error_until=NOW+1600;
}
static int alive(u32 tree,u32 seq){
 if(!tree)return 0;
 for(u32 i=0;i<64;i++){
  void *c=0,*out=0;if(!FN(0x0812d78a,int(*)(void*,u32,void**))((void*)tree,i,&c)||!c)return 0;
  if(FN(W((void*)W(c,0),0x14),int(*)(void*,u32,void**))(c,seq,&out))return 1;
 }
 return 1;
}
static Meta *meta_new(Recorder *s,u32 seq,u32 tree,u32 keep){
 Meta *free=0;
 for(u32 i=0;i<META_COUNT;i++){
  Meta *m=s->meta+i;if(m->seq==seq)return m;if(!m->seq&&!free)free=m;
 }
 if(!free)for(u32 i=0;i<META_COUNT;i++){
  Meta *m=s->meta+i;if(m->seq!=s->seq&&m->seq!=keep&&!alive(m->tree,m->seq)){m->seq=0;if(!free)free=m;}
 }
 if(!free){message(s,"! MEMORY");return 0;}zero(free,sizeof(*free));free->seq=seq;free->tree=tree;return free;
}
static Meta *meta(Recorder *s,u32 seq,int create){
 for(u32 i=0;i<META_COUNT;i++)if(s->meta[i].seq==seq)return s->meta+i;
 return create?meta_new(s,seq,W(MODEL,0),0):0;
}
static void *node(u32 seq,int create){
 void *n=0;return seq&&FN(0x0812ea72,int(*)(void*,u32,void**,int))((void*)W(MODEL,0),seq,&n,create)?n:0;
}
static int get(u32 h,u32 k,u32 *out){return FN(0x08133614,int(*)(void*,u32*,u32,void*))(MODEL,&h,k,out);}
static int selected(u32 *owner,u32 *seq,u32 *row){
 *owner=*seq=0;*row=16;
 if(!FN(0x08133cfc,int(*)(void*,u32*))(MODEL,owner)||!get(*owner,0x133,row)||*row>=16)return 0;
 for(u32 i=0;i<512;i++){
  u32 h=0,r=16;
  if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,owner,i,&h))break;
  if(get(h,0x73,&r)&&r==*row){*seq=h;return 1;}
 }
 return 0;
}
static void end_take(Recorder *s){
 s->used=s->seq=s->owner=s->snapshot=s->count=s->lanes=s->pending=s->started=s->clearing=s->written=0;
}
int nm_enabled(void){return NC->enabled==1;}
int nm_set_enabled(int on){
 on=on!=0;
 if(on==nm_enabled())return 1;
 Recorder *s=state(0);if(s){end_take(s);s->enabled=(u32)on;s->error_until=0;}
 NC->error=0;NC->enabled=(u32)on;return 1;
}
static u32 next_serial(u32 s){s=(s+2)&~1u;return s?s:2;}
void nm_rebuild(u32 seq,u32 owner){
 Recorder *s=state(0);if(!s||!seq||!owner)return;u32 row=16;if(!get(seq,0x73,&row)||row>=16)return;
 NmShared *d=(NmShared*)s->shared;NmClip *c=0,*free=0;
 u32 count=d->spare[0];if(count>NM_CLIPS){message(s,"! MOTION STATE");return;}
 for(u32 i=0;i<count;i++){NmClip *p=d->clips+i;if(p->owner==owner&&p->row==row){c=p;break;}if(!p->owner&&!free)free=p;}
 if(!free&&count<NM_CLIPS)free=d->clips+count;
 Meta *m=meta(s,seq,0);if(!c){if(!m)return;c=free;}if(!c){message(s,"! MEMORY");return;}
 u32 serial=next_serial(c->serial);c->serial=serial|1;barrier();c->owner=owner;c->row=row;c->sequence=seq;
 for(u32 i=0;i<4;i++)c->length[i]=m?m->length[i]:0;barrier();c->serial=serial;
 if(c==d->clips+count){barrier();d->spare[0]=count+1;}
}
static int clock(Recorder *s,u32 owner,NmClock *out){
 NmShared *d=(NmShared*)s->shared;
 for(u32 i=0;i<8;i++){
  volatile NmClock *r=d->clock+i;u32 serial=r->serial;if(!serial||(serial&1)||r->owner!=owner||!r->valid||r->epoch!=d->epoch)continue;
  *out=*(const NmClock*)r;barrier();if(serial==r->serial)return 1;
 }
 return 0;
}
static void growth(Recorder*,const NmClock*);
static int context(Recorder *s,NmClock *c){
 u32 owner=0,seq=0,row=16;
 if(!selected(&owner,&seq,&row)){end_take(s);return 0;}
 if(s->seq&&(seq!=s->seq||owner!=s->owner||row!=s->row))end_take(s);
 if(!clock(s,owner,c)||c->row!=row||!c->sequence){end_take(s);return 0;}
 if(s->seq&&c->tick>=s->last&&s->clock_sequence==c->sequence&&
    s->clock_epoch==c->epoch&&s->clock_generation==c->spare)return 1;
 if(s->seq)end_take(s);
 u32 steps=0,grid=10,absolute=0;if(!get(seq,0x62,&steps)||!steps)return 0;
 get(seq,0x60,&grid);get(seq,0x61,&absolute);
 static const u16 units[15]={30720,15360,7680,3840,1920,1280,960,640,480,320,240,160,120,80,60};
 if(grid>=15)return 0;u32 ticks=steps*(absolute?960u:units[grid]);
 steps=(ticks+NM_TICK-1)/NM_TICK;if(!steps||steps>NM_STEPS){message(s,"! CLIP >16 BARS");return 0;}
 s->seq=seq;s->owner=owner;s->row=row;s->steps=steps;s->start=s->last=c->tick;s->started=1;
 s->clock_sequence=c->sequence;s->clock_epoch=c->epoch;s->clock_generation=c->spare;return 1;
}
unsigned nm_status(void){
 Recorder *s=state(nm_enabled()&&!NC->error?2:0);
 u32 owner=0,seq=0,row=16;int valid=selected(&owner,&seq,&row);
 if(s&&s->seq&&(!valid||seq!=s->seq||owner!=s->owner||row!=s->row))end_take(s);
 if(nm_enabled()){
  NmClock c;
  if(s&&s->snapshot&&context(s,&c)){growth(s,&c);s->last=c.tick;}
  return s&&s->written&&NOW-s->write_time<=160?NM_WRITING:NM_WAITING;
 }
 void *n=valid?node(seq,0):0;
 for(u32 i=0;n&&i<4;i++)if(B(n,0x80a+i))return NM_HAS_MOTION;
 return NM_EMPTY;
}
static void snapshot(Recorder *s,u32 target){
 if(!s->snapshot){
  FN(0x081338dc,void(*)(void*,u32*))(MODEL,&s->seq);s->snapshot=1;
 }
 /* Add destination nodes to the same native Undo transaction, without the
  * reset performed by 081338DC. Routes do not live in the clip subtree. */
 if(target)FN(0x08124a7e,int(*)(void*,void*,u32))((u8*)MODEL+0xb26c,(void*)W(MODEL,0),target);
}
static void growth(Recorder *s,const NmClock *c){
 if(!s->snapshot)return;Meta *m=meta(s,s->seq,0);if(!m)return;
 u32 n=s->steps,mul=1;u64 elapsed=(u64)(c->tick-s->start);
 while(mul<8&&elapsed>=(u64)n*NM_TICK&&n<NM_STEPS){n*=2;mul*=2;}
 if(n>NM_STEPS)n=NM_STEPS;
 int changed=0;for(u32 i=0;i<4;i++)if((s->lanes>>i&1)&&m->length[i]<n){m->length[i]=(u16)n;changed=1;}
 if(changed)nm_rebuild(s->seq,s->owner);
}
void nm_dispatch(u32 code,u32 index){
 (void)code;(void)index;
}
void nm_increment(void *slot,int delta){
 Recorder *s=state(0);if(!s||!s->enabled||!slot||!delta)return;
 extern int macro_overlay(void);
 if(macro_overlay()){s->used=1;s->pending=0;message(s,"! NOT A TARGET");return;}
 if(!selected(&s->pending_owner,&s->pending_seq,&s->pending_row)){s->pending=0;message(s,"! NO SELECTED CLIP");return;}
 s->used=1;s->pending=(u32)slot;s->before=(int)W(slot,0xa0);
}
static int belongs(u32 owner,u32 h){
 u32 queue[256],count=1;queue[0]=owner;
 for(u32 at=0;at<count;at++){
  if(queue[at]==h)return 1;
  for(u32 i=0;i<512;i++){u32 child=0;if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,queue+at,i,&child))break;
   u32 j=0;while(j<count&&queue[j]!=child)j++;if(j<count)continue;if(count==256)return 0;queue[count++]=child;}
 }
 return 0;
}
static u32 used_lanes(Recorder *s,void *n){
 u32 mask=0,queue[256],count=1;queue[0]=s->owner;
 for(u32 i=0;i<4;i++)if(n&&B(n,0x80a+i))mask|=1u<<i;
 for(u32 at=0;at<count;at++){
  for(u32 i=0;i<512;i++){u32 r[3]={0};if(!FN(0x08131238,int(*)(void*,u32*,u32,u32*))(MODEL,queue+at,i,r))break;
   u32 src=r[1]&65535;if(src>=9&&src<=12)mask|=1u<<(src-9);}
  for(u32 i=0;i<512;i++){u32 child=0;if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,queue+at,i,&child))break;
   u32 j=0;while(j<count&&queue[j]!=child)j++;if(j<count)continue;if(count==256)return 15;queue[count++]=child;}
 }
 return mask;
}
static int destination(u32 owner,u32 h,u32 key){
 u32 type=FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&h);
 if(type==1||type==2){
  for(u32 i=0;i<10;i++)if(H((void*)0x0819e428u,2*i)==key)return 1;
  extern int motion_drum_destination(u32,u32,u32);
  return motion_drum_destination(owner,h,key)?2:0;
 }
 for(u32 i=0;i<60;i++){const u32 *r=(const u32*)(0x0819de54u+i*24);if(r[0]==type&&r[2]==key)return 1;}
 return 0;
}
static int route(u32 h,u32 key,u32 slot,u32 *out){return FN(0x08131244,int(*)(void*,u32*,u32,u32,u32*))(MODEL,&h,key,slot,out);}
static Target *target(Recorder *s,void *w,NmClock *c){
 u32 h=W(w,0x34),key=H(w,0x9c);
 for(u32 i=0;i<s->count;i++)if(s->targets[i].handle==h&&s->targets[i].key==key)return s->targets+i;
 int dest=belongs(s->owner,h)?destination(s->owner,h,key):0;
 if(!dest){message(s,"! NOT A TARGET");return 0;}
 int span=(int)W(w,0x454)-(int)W(w,0x450);if(span<=0){message(s,"! NO RANGE");return 0;}
 u32 lane=4,free=3,at=0;int amount=0;
 for(u32 i=0;i<3;i++){u32 r[3]={0};if(!route(h,key,i,r)||!(r[1]&65535)){if(free==3)free=i;continue;}
  u32 src=r[1]&65535;if(src>=9&&src<=12&&r[0]){if(lane!=4){message(s,"! MULTI LANE");return 0;}lane=src-9;amount=(int)r[0];at=i;}}
 void *n=node(s->seq,0);
 if(lane==4){
  u32 mask=used_lanes(s,n);for(lane=0;lane<4&&(mask>>lane&1);lane++){}
  if(lane==4||free==3){message(s,"! FULL");return 0;}at=free;amount=1000;
 }
 for(u32 i=0;i<s->count;i++)if(s->targets[i].lane==lane){message(s,"! SHARED LANE");return 0;}
 if(s->count==4){message(s,"! FULL");return 0;}
 Meta *m=meta(s,s->seq,1);if(!m)return 0;
 snapshot(s,h);
 if(!node(s->seq,1)){message(s,"! NO MEMORY");return 0;}
 u32 check[3]={0};
 if(dest==2||!route(h,key,at,check)||(check[1]&65535)!=lane+9){
  u32 e[5]={0xd1,h,key|1u<<16,(lane+9)|(at<<16),(u32)amount};
  FN(0x081403ec,int(*)(void*,void*))(MODEL,e);
  if(!route(h,key,at,check)||(check[1]&65535)!=lane+9){message(s,"! ROUTE FAILED");return 0;}
 }
 if(!m->length[lane])m->length[lane]=(u16)s->steps;
 Target *t=s->targets+s->count++;zero(t,sizeof(*t));t->handle=h;t->key=key;t->lane=lane;t->slot=at;t->amount=amount;t->span=span;t->current=s->before;t->step=~0u;
 u32 step=(u32)((u64)(c->tick-c->origin)/NM_TICK)%m->length[lane];
 t->source=(int)(short)H(node(s->seq,0),10+2*(lane*256+step));
 s->lanes|=1u<<lane;nm_rebuild(s->seq,s->owner);return t;
}
int nm_model_event(void *event){
 Recorder *s=state(0);if(!s||!s->enabled||!s->pending||!event||(H(event,0)!=0xcf&&H(event,0)!=0xd0))return 0;
 void *w=(void*)s->pending;s->pending=0;
 if(W(event,4)!=W(w,0x34)||W(event,8)!=H(w,0x9c))return 0;
 u32 owner=0,seq=0,row=16;
 if(!selected(&owner,&seq,&row)||owner!=s->pending_owner||seq!=s->pending_seq||row!=s->pending_row){
  end_take(s);message(s,"! CLIP CHANGED");return 1;
 }
 NmClock c;if(!context(s,&c)){message(s,"! NO PLAYING CLIP");return 1;}
 growth(s,&c);Target *t=target(s,w,&c);if(!t)return 1;
 int value=(int)W(event,12),delta=value-s->before;
 i64 divisor=(i64)t->amount*t->span,numerator=(i64)delta*1000000+t->remainder;
 i64 change=numerator/divisor,v=(i64)t->source+change;
 if(v<-32768||v>32767){message(s,"! RANGE");return 1;}
 t->remainder=numerator%divisor;
 Meta *m=meta(s,s->seq,0);u32 step=(u32)((u64)(c.tick-c.origin)/NM_TICK)%m->length[t->lane];
 /* Interpolate only a continuous moved span. A pause is not a request to
  * erase the intervening native automation. */
 u32 n=1;if(t->step!=~0u&&NOW-t->time<=160){n=(step+m->length[t->lane]-t->step)%m->length[t->lane];if(!n)n=1;}
 for(u32 i=1;i<=n;i++){
  u32 at=n==1?step:(t->step+i)%m->length[t->lane];int sample=t->source+(int)((v-t->source)*i/n);
  FN(0x0813706c,void(*)(void*,u32*,u32,u32,int,u32))(MODEL,&s->seq,t->lane,at,sample,0);
 }
 t->source=(int)v;t->current=value;t->step=step;t->time=NOW;s->last=c.tick;
 s->written=1;s->write_time=NOW;
 u32 k=0;const char *name=(const char*)w+0x3f9;while(name[k]&&k<15){s->name[k]=name[k];k++;}s->name[k]=0;
 return 1;
}
int nm_get(void *model,void *handle,u32 key,void *out,u32 caller){
 Recorder *s=state(0);if(!s||model!=MODEL||!handle||!out)return 0;u32 h=W(handle,0);caller&=~1u;
 if(s->enabled)for(u32 i=0;i<s->count;i++){Target *t=s->targets+i;if(t->handle==h&&t->key==key){W(out,0)=(u32)t->current;return 1;}}
 Meta *m=meta(s,h,0);if(!m)return 0;
 if(key==0x62&&caller==0x08136846){
  u32 n=0;for(u32 i=0;i<4;i++)if(m->length[i]>n)n=m->length[i];if(n){W(out,0)=256;return 1;}
 }
 void *v=(void*)s->view;if(!v||W(v,0x11cd00)!=h||B(v,0x125dac)!=2||B(MODEL,0x12c)!=0x17)return 0;
 u32 lane=W(v,0x125d34);if(lane>=4||!m->length[lane])return 0;
 if((key==0x62&&caller==0x08159a1a)||(key==0x60&&caller==0x08159a0c)){W(out,0)=key==0x62?m->length[lane]:10;return 1;}return 0;
}
u32 nm_serialized_steps(void *object,u32 key){
 Recorder *s=state(0);Meta *m=s&&object?meta(s,W(object,0x10),0):0;
 if(m)for(u32 i=0;i<4;i++)if(m->length[i])return NM_STEPS;
 return FN(0x0812dc74,u32(*)(void*,u32))(object,key);
}
void nm_readout(void *out){
 if(NC->error&&out){const char *p="! MOTION MEMORY";u32 i=0;do{B(out,i)=p[i];}while(p[i++]);B(out,0x60)=0;B(out,0x68)=0xf4;return;}
 Recorder *s=state(0);if(!s||!out)return;
 if(s->enabled&&s->snapshot){NmClock c;if(context(s,&c)){growth(s,&c);s->last=c.tick;}else message(s,"! NO PLAYING CLIP");}
 char text[32];u32 k=0;
 if((int)(s->error_until-NOW)>0){while(s->message[k]&&k<31){text[k]=s->message[k];k++;}}
 else if(s->enabled&&s->count){
  const char *p="MOTION ";while(*p)text[k++]=*p++;for(u32 i=0;s->name[i]&&k<17;i++)text[k++]=s->name[i];
  Meta *m=meta(s,s->seq,0);u32 n=m?m->length[s->targets[s->count-1].lane]:s->steps;
  text[k++]=' ';
  if(n==NM_STEPS){const char *cap="CAP ";while(*cap)text[k++]=*cap++;}
  else if(s->steps&&n%s->steps==0&&n/s->steps<=8){text[k++]='0'+n/s->steps;text[k++]='x';text[k++]=' ';}
  u32 amount=n%16?n:n/16;if(amount>=100)text[k++]='0'+amount/100;
  if(amount>=10)text[k++]='0'+amount/10%10;text[k++]='0'+amount%10;text[k++]=n%16?'s':'b';
 }else return;
 text[k]=0;for(u32 i=0;i<=k;i++)B(out,i)=text[i];B(out,0x60)=0;B(out,0x68)=0xf4;
}
void nm_bar_tick(void *bar){
 Recorder *s=state(0);if(!s||B(bar,0x30))return;
 for(u32 i=0;i<8;i++){
  void *w=(u8*)bar+0x38+i*0x468;u32 h=W(w,0x34),key=H(w,0x9c),mask=0;
  for(u32 j=0;h&&key&&j<3;j++){u32 r[3]={0};if(route(h,key,j,r)){u32 src=r[1]&65535;if(src>=9&&src<=12)mask|=1u<<(src-9);}}
  Mark *m=0,*free=0;for(u32 j=0;j<24;j++){Mark *p=s->marks+j;if(p->widget==(u32)w)m=p;else if(!p->widget&&!free)free=p;}
  if(!m&&!mask)continue;
  if(!m){m=free?free:s->marks+i;zero(m,sizeof(*m));m->widget=(u32)w;}
  int value=(int)W(w,0xa0);
  if(mask&&m->handle==h&&m->key==key&&m->mask==mask&&m->value==value)continue;
  FN(0x08170656,void(*)(void*,u32,const char*))(bar,i,0);
  if(!mask){zero(m,sizeof(*m));continue;}
  char text[32];u32 n=0;const char *base=(const char*)w+0xd9;
  while(base[n]&&n<22){text[n]=base[n];n++;}text[n++]=' ';
  for(u32 j=0;j<4;j++)if(mask>>j&1)text[n++]='A'+j;text[n]=0;
  FN(0x08170656,void(*)(void*,u32,const char*))(bar,i,text);
  m->handle=h;m->key=key;m->mask=mask;m->value=value;
 }
}
int nm_tap(void *bar,void *point){
 (void)bar;(void)point;
 return 0;
}
void nm_clear_snapshot(void *model,u32 *seq){
 Recorder *s=state(0);if(!s||!s->clearing)FN(0x081338dc,void(*)(void*,u32*))(model,seq);
}
static int length_descriptor(void *d){
 return H(d,0)==LENGTH_KEY&&B(d,2)==2&&W(d,4)==(u32)length_name&&W(d,16)==1&&W(d,20)==256;
}
void nm_header_before(void *v){
 Recorder *s=state(0);if(!s)return;s->view=(u32)v;
 if(s->descriptors_saved){
  u32 r=W((void*)0x30031484u,0);void *d=(void*)(r+LENGTH_KEY*32);
  if(r&&length_descriptor(d))for(u32 i=0;i<8;i++)W(d,i*4)=s->descriptors[i];else message(s,"! LENGTH OWNER");
  s->descriptors_saved=0;
 }
}
void nm_header_after(void *v){
 Recorder *s=state(0);if(!s||B(MODEL,0x12c)!=0x17||B(v,0x125dac)!=2)return;
 u32 lane=W(v,0x125d34);Meta *m=meta(s,W(v,0x11cd00),0);if(lane>=4||!m||!m->length[lane])return;
 u32 r=W((void*)0x30031484u,0);if(!r)return;void *d=(void*)(r+LENGTH_KEY*32);
 /* 176 belongs to the matrix's Amount 3. Borrow only that exact native
  * descriptor while Automation is visible, and restore it before navigation. */
 if(H(d,0)!=LENGTH_KEY||B(d,2)!=11||W(d,4)!=0x0818e1bcu||(int)W(d,16)!=-1000||W(d,20)!=1000){message(s,"! LENGTH OWNER");return;}
 for(u32 i=0;i<8;i++)s->descriptors[i]=W(d,i*4);s->descriptors_saved=1;zero(d,32);
 H(d,0)=LENGTH_KEY;B(d,2)=2;W(d,4)=(u32)length_name;W(d,16)=1;W(d,20)=256;
 u32 i=2,n=m->length[lane];void *bar=(u8*)v+0x55f0,*w=(u8*)bar+0x38+i*0x468;
 H(v,0x11bcc0+i*2)=LENGTH_KEY;W(v,0x11bcd0+i*4)=n;W(v,0x11bca0+i*4)=W(v,0x11cd00);
 FN(0x08171c1c,void(*)(void*,u32,int,u32))(w,LENGTH_KEY,(int)n,1);
}
int nm_view_event(void *v,void *e){
 Recorder *s=state(0);if(!s||B(v,0x125dac)!=2||H(e,0)!=0xcf||W(e,8)!=LENGTH_KEY)return 0;
 u32 lane=W(v,0x125d34),seq=W(v,0x11cd00),n=W(e,12);Meta *m=meta(s,seq,0);
 if(lane>=4||!m||!n||n>256){message(s,"! LENGTH");return 1;}
 if(s->enabled){message(s,"! MOTION ON");return 1;}
 if(m->length[lane]==n)return 1;
 FN(0x081338dc,void(*)(void*,u32*))(MODEL,&seq);m->length[lane]=(u16)n;
 u32 owner=W(v,0x11cd08);nm_rebuild(seq,owner);FN(0x0813130c,void(*)(void*))(MODEL);FN(0x081599bc,void(*)(void*))(v);return 1;
}
static void attrname(char *out,u32 lane){const char *p="bento_motion_v1_A";u32 i=0;do{out[i]=p[i];}while(p[i++]);out[16]='A'+lane;}
void nm_save(void *object,void *params){
 Recorder *s=state(0);if(!s||!object||!params)return;Meta *m=meta(s,W(object,0x10),0);if(!m)return;
 for(u32 i=0;i<4;i++){char name[24];attrname(name,i);void *a=FN(0x08109cdc,void*(*)(void*,const char*))(params,name);if(a)FN(0x0810958e,void(*)(void*,u32))(a,m->length[i]);else message(s,"! MOTION SAVE");}
}
void nm_load(void *node,void *object){
 if(!node||!object||!W(object,0x10))return;
 void *p=FN(0x08109268,void*(*)(void*,const char*))(node,"params");u16 lengths[4];u32 any=0;
 for(u32 i=0;i<4;i++){char name[24];u32 n=0;attrname(name,i);void *a=p?FN(0x08109c64,void*(*)(void*,const char*))(p,name):0;
  if(a&&!FN(0x08109566,int(*)(void*,void*))(a,&n)&&n<=256)lengths[i]=(u16)n;else lengths[i]=0;any|=lengths[i];}
 Recorder *s=state(any!=0);if(!s)return;Meta *m=meta(s,W(object,0x10),any!=0);if(!m)return;
 for(u32 i=0;i<4;i++)m->length[i]=lengths[i];m->loaded=1;
}
void nm_finish(void){
 NC->enabled=0;Recorder *s=state(0);if(!s)return;end_take(s);s->enabled=0;
 for(u32 i=0;i<META_COUNT;i++){if(!s->meta[i].loaded)s->meta[i].seq=0;s->meta[i].loaded=0;}
 NmShared *d=(NmShared*)s->shared;d->epoch++;barrier();
 for(u32 i=0;i<NM_CLIPS;i++){
  NmClip *c=d->clips+i;u32 serial=next_serial(c->serial);c->serial=serial|1;barrier();
  c->owner=c->row=c->sequence=0;for(u32 j=0;j<4;j++)c->length[j]=0;barrier();c->serial=serial;
 }
 barrier();d->spare[0]=0;
 for(u32 t=0;t<8;t++){
  u32 owner=0;if(!FN(0x08133960,int(*)(void*,u32,u32*))(MODEL,t,&owner))continue;
  for(u32 j=0;j<512;j++){u32 seq=0;if(!FN(0x0813391a,int(*)(void*,u32*,u32,u32*))(MODEL,&owner,j,&seq))break;
   if(meta(s,seq,0))nm_rebuild(seq,owner);}
 }
}
void nm_clone(u32 tree,void *source,void **out,int ok){
 Recorder *s=state(0);if(!s||!ok||!source||!out||!*out)return;
 u32 a[256],b[256],count=1;a[0]=(u32)source;b[0]=(u32)*out;
 for(u32 at=0;at<count;at++){
  Meta *m=meta(s,W((void*)a[at],0x10),0);Meta *n=m?meta_new(s,W((void*)b[at],0x10),tree,m->seq):meta(s,W((void*)b[at],0x10),0);
  if(n){if(m)for(u32 i=0;i<4;i++)n->length[i]=m->length[i];else for(u32 i=0;i<4;i++)n->length[i]=0;}
  for(u32 i=0;i<512;i++){
   void *x=0,*y=0;u32 av=W((void*)a[at],0),bv=W((void*)b[at],0);
   if(!FN(W((void*)av,0x18),int(*)(void*,u32,void**))((void*)a[at],i,&x))break;
   if(!FN(W((void*)bv,0x18),int(*)(void*,u32,void**))((void*)b[at],i,&y)||!x||!y){message(s,"! CLONE");return;}
   if(count==256){message(s,"! CLONE FULL");return;}a[count]=(u32)x;b[count++]=(u32)y;
  }
 }
}
__attribute__((used,retain)) void nm_bar_paint(void *bar,void *ctx){
 FN(0x0816faec,void(*)(void*,void*))(bar,ctx);
 Recorder *s=state(0);if(!s||!s->enabled||!ctx||!W(ctx,4))return;
 for(u32 i=0;i<8;i++){void *w=(u8*)bar+0x38+i*0x468;
  for(u32 j=0;j<s->count;j++)if(W(w,0x34)==s->targets[j].handle&&H(w,0x9c)==s->targets[j].key){
   int rect[4]={(int)W(w,4),(int)W(w,8),(int)W(w,12),(int)W(w,16)};
   FN(0x08166e9e,void(*)(void*,u32,u32))(rect,0xf4,W(ctx,4));
  }}
}
#endif
