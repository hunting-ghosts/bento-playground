#include "native_ids.h" /* 1.6.8 port: NOFF */
/* EU2 settings, native allocation and versioned per-track/clip-row XML. */
#include "live_ui.h"
#include "kit_seq.h"
#include "ui_native.h"
static void clear(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static EuBank *bank(int create){
 if(EC->magic==EU_MAGIC&&EC->bytes==sizeof(EuBank)&&eu_memory(EC->pointer,sizeof(EuBank)))return (EuBank*)EC->pointer;
 if(!create)return 0;
 u32 p=W((void*)0x3000004c,0),end=W((void*)0x30000048,0),n=(sizeof(EuBank)+31)&~31u;
 if(!eu_memory(p,n)||end<p||end-p<n)return 0;
 u32 allocated=NFN(0x08104c08,u32(*)(u32))(n);if(allocated!=p)return 0;
 clear((void*)p,n);EuBank *b=(EuBank*)p;b->epoch=1;b->serial=2;
 EC->magic=0;EC->pointer=p;EC->bytes=sizeof(EuBank);EC->epoch=1;__asm__ volatile("dmb" ::: "memory");EC->magic=EU_MAGIC;return b;
}
static EuRecord *record(EuRecord *r,u32 *count,u32 owner,u32 row,int create){
 for(u32 i=0;i<*count;i++)if(r[i].owner==owner&&r[i].row==row)return r+i;
 if(!create||*count>=EU_RECORDS||!owner||row>=16)return 0;
 EuRecord *out=r+(*count)++;clear(out,sizeof(*out));out->owner=owner;out->row=row;out->serial=2;return out;
}
static EuRecord *selected(Euclid *e,int create){
 EuBank *b=bank(create);u32 row=16;if(!b||e->pad>=16||!e->valid)return 0;
 if(!ui_get(&e->seq,0x73,&row)||row>=16)return 0;
 return record(b->records,&b->count,e->owner,row,create);
}
int live_begin(Euclid *e){return selected(e,1)!=0;}
/* Native Undo clones notes, not EuBank. Between project loads the unindexed
 * last pending record is M4-only scratch for that same one-level snapshot. */
__attribute__((used,retain,noinline,section(".cycleundo")))
void live_cycle_snapshot(void *model,u32 *sequence){
 EuBank *b=bank(0);if(!b||b->pending_count)return;
 EuRecord *s=&b->pending[EU_RECORDS-1];clear(s,sizeof(*s));
 u32 owner=0,row=16;
 if(!NFN(0x08133cfc,int(*)(void*,u32*))(model,&owner)||
    NFN(0x08133f7c,u32(*)(void*,u32*))(model,&owner)!=14||
    !NFN(0x08133614,int(*)(void*,void*,u32,void*))(model,sequence,0x73,&row)||row>=16)return;
 u32 count=b->count;EuRecord *r=record(b->records,&count,owner,row,0);
 if(r)*s=*r;
 s->owner=owner;s->row=row;
}
__attribute__((used,retain,noinline,section(".cycleundo")))
void live_cycle_restore(u32 owner,u32 row,u32 restored){
 EuBank *b=bank(0);if(!b||b->pending_count||!restored)return;
 EuRecord *s=&b->pending[EU_RECORDS-1];
 if(!s->owner||row>=16||NFN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&owner)!=14)return;
 u32 serial=(b->serial+2u)&~1u;if(!serial)serial=2;b->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 EuRecord *r=record(b->records,&b->count,owner,row,1);
 if(r){u32 rs=(r->serial+2u)&~1u;if(!rs)rs=2;*r=*s;r->owner=owner;r->row=row;r->serial=rs;}
 __asm__ volatile("dmb" ::: "memory");b->serial=serial;
 if(!r)NFN(0x08104c00,void(*)(const char*))("Undo: no record");
}
STEP_DRAW int live_manual_steps(u32 owner,u32 seq,u32 pad,int commit){
 EuBank *b=bank(0);if(!b)return 1;
 u32 row=16;if(pad>=16||(b->serial&1)||
  !ui_get(&seq,0x73,&row)||row>=16)return 0;
 u32 count=b->count;EuRecord *r=record(b->records,&count,owner,row,0);
 if(!r||!eu_enabled(r->pads[pad]))return 1;
 if(eu_record_melodic(r)||(r->serial&1))return 0;
 if(commit){
  u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
  r->pads[pad].pattern&=~(1u<<25);
  __asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();
 }
 return 1;
}
EuPad live_value(Euclid *e){
 EuRecord *r=selected(e,0);EuPad p={0,0};if(r)p=r->pads[e->pad];
 if(!eu_pad_valid(p))p=eu_pack(e->steps,e->hits<=e->steps?e->hits:0,0,100,0);return p;
}
u32 live_cycle_steps(u32 owner,u32 seq,u32 pad,u32 fallback){
 Euclid e={0};e.owner=owner;e.seq=seq;e.pad=pad;e.valid=1;e.steps=fallback;
 EuPad p=live_value(&e);return eu_manual_cycle(p)?eu_length(p):fallback;
}
int live_cycle(Euclid *e,u32 length){
 if(length<1||length>256)return 0;
 EuRecord *r=selected(e,1);if(!r||eu_record_melodic(r))return 0;
 EuPad p=eu_pack(length,0,0,100,0);p.pattern|=(1u<<26)|(1u<<27);
 if(r->pads[e->pad].pattern==p.pattern&&r->pads[e->pad].velocity==p.velocity)return 1;
 ui_touch(&e->seq);
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 r->pads[e->pad]=p;
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();return 1;
}
int live_edit(Euclid *e,u32 key,int value){
 if(key==0){e->pad=value<1?0:value>16?15:(u32)value-1;return 1;}
 if(key==6){e->preview=value<1?1:value>8?8:(u32)value;return 1;}
 EuRecord *r=selected(e,1);if(!r)return 0;EuPad p=live_value(e);
 u32 n=eu_length(p),k=eu_pulses(p),rot=eu_rotation(p),vel=eu_base(p),on=eu_enabled(p);
 if(key==1){n=value<1?1:value>256?256:(u32)value;if(k>n)k=n;if(rot>=n)rot%=n;}
 if(key==2)k=value<0?0:(u32)value>n?n:(u32)value;
 if(key==3)rot=value<0?0:(u32)value>=n?n-1:(u32)value;
 if(key==4)vel=value<1?1:value>127?127:(u32)value;
 if(key==5)on=value>0;
 u32 serial=(r->serial+2)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 r->pads[e->pad]=eu_pack(n,k,rot,vel,on);r->pads[e->pad].velocity=eu_dynamics_gate(vel,eu_mode(p),eu_depth(p),eu_gate(p));r->pads[e->pad].pattern|=p.pattern&(1u<<26);__asm__ volatile("dmb" ::: "memory");r->serial=serial;
 ui_commit();return 1;
}
static int read(void *p,const char *name,u32 *v){void *a=p?NFN(0x08109c64,void*(*)(void*,const char*))(p,name):0;return a&&!NFN(0x08109566,int(*)(void*,void*))(a,v);}
static void write(void *p,const char *name,u32 v){void *a=NFN(0x08109cdc,void*(*)(void*,const char*))(p,name);if(a)NFN(0x0810958e,void(*)(void*,u32))(a,v);}
static void name(char *s,u32 row,u32 pad,u32 word){const char *p="bento_eu2_00_00_0";u32 i=0;do{s[i]=p[i];}while(p[i++]);s[10]='0'+row/10;s[11]='0'+row%10;s[13]='0'+pad/10;s[14]='0'+pad%10;s[16]='0'+word;}
void live_save(void *object,void *params){
 extern u32 ui_key(u32);EuBank *b=bank(0);if(!b||!object||!params)return;u32 owner=ui_key(W(object,0x10));if(!owner||(B(object,4)!=14&&!eu_pitched_type(B(object,4))))return;
 write(params,"bento_eu2_version",1);
 for(u32 i=0;i<b->count;i++){EuRecord *r=b->records+i;if(r->owner!=owner)continue;
  for(u32 pad=0;pad<16;pad++){EuPad p=r->pads[pad];if(!eu_pad_valid(p))continue;char key[20];name(key,r->row,pad,0);write(params,key,p.pattern);name(key,r->row,pad,1);write(params,key,eu_base(p));name(key,r->row,pad,2);write(params,key,eu_mode(p));name(key,r->row,pad,3);write(params,key,eu_depth(p));
   if(eu_record_melodic(r)){name(key,r->row,pad,4);write(params,key,eu_record_pitch(r,pad));name(key,r->row,pad,5);write(params,key,eu_gate(p));}}
 }
}
void live_load(void *node,void *object){
 if(!node||!object||(B(object,4)!=14&&!eu_pitched_type(B(object,4)))||!W(object,0x10))return;
 void *params=NFN(0x08109268,void*(*)(void*,const char*))(node,"params");u32 ver=0;
 if(!read(params,"bento_eu2_version",&ver)||ver!=1)return;EuBank *b=bank(1);if(!b)return;
 u32 owner=W(object,0x10);
 for(u32 row=0;row<16;row++)for(u32 pad=0;pad<16;pad++){
  char key[20];EuPad p={0,0};name(key,row,pad,0);if(!read(params,key,&p.pattern))continue;name(key,row,pad,1);if(!read(params,key,&p.velocity)||!eu_pad_valid(p))continue;
  u32 mode=0,depth=0;name(key,row,pad,2);read(params,key,&mode);name(key,row,pad,3);read(params,key,&depth);if(mode>9)mode=0;if(depth>100)depth=0;u32 pitch=0,gate=0;name(key,row,pad,4);int mel=read(params,key,&pitch)&&pitch<=127;name(key,row,pad,5);if(mel)read(params,key,&gate);if(gate>64)gate=0;
  if(mel&&eu_manual_cycle(p))continue;
  p.velocity=eu_dynamics_gate(eu_base(p),mode,depth,mel?gate:0);
  EuRecord *r=record(b->pending,&b->pending_count,owner,row,1);if(r){r->pads[pad]=p;if(mel){r->reserved[0]|=EU_MELODIC;eu_record_set_pitch(r,pad,pitch);}}
 }
}
/* P168 exp3 (ui_key, kick_ui.c): the records of a copied track follow it, under the M7 snapshot protocol. */
void live_rekey(u32 from,u32 to){
 EuBank *b=bank(0);if(!b)return;
 b->serial|=1;__asm__ volatile("dmb" ::: "memory");
 for(u32 i=0;i<EU_RECORDS;i++){if(b->records[i].owner==from)b->records[i].owner=to;if(b->pending[i].owner==from)b->pending[i].owner=to;}
 b->epoch++;if(!b->epoch)b->epoch=1;__asm__ volatile("dmb" ::: "memory");b->serial=(b->serial+1)&~1u;if(!b->serial)b->serial=2;
}
void melodic_register_tracks(void);
void live_finish(void){
 EuBank *b=bank(0);if(!b)return;
 b->serial|=1;__asm__ volatile("dmb" ::: "memory");clear(b->records,sizeof(b->records));b->count=b->pending_count;
 for(u32 i=0;i<b->count;i++)b->records[i]=b->pending[i];clear(b->pending,sizeof(b->pending));b->pending_count=0;
 melodic_register_tracks();
 b->epoch++;if(!b->epoch)b->epoch=1;__asm__ volatile("dmb" ::: "memory");b->serial=(b->serial+1)&~1u;if(!b->serial)b->serial=2;
}

static int position(EuBank *b,u32 owner,u32 row,u32 *step);
int live_position(Euclid *e,u32 *step){
 EuBank *b=bank(0);u32 row=16;if(!b||!e->valid||!step)return 0;
 if(!ui_get(&e->seq,0x73,&row)||row>=16)return 0;
 return position(b,e->owner,row,step);
}
/* CH6 piano-roll lanes: the committed record and the published phase for one
   sequence. *step = ~0 while the generator is not playing. */
int live_lanes(u32 seq,u32 owner,EuPad *pads,u8 *pitch,u32 *mel,u32 *step){
 EuBank *b=bank(0);u32 row=16;if(!b||(b->serial&1))return 0;
 if(!ui_get(&seq,0x73,&row)||row>=16)return 0;
 u32 count=b->count;EuRecord *r=record(b->records,&count,owner,row,0);if(!r)return 0;
 for(u32 i=0;i<16;i++){pads[i]=r->pads[i];pitch[i]=(u8)eu_record_pitch(r,i);}*mel=(u32)eu_record_melodic(r);
 if(!position(b,owner,row,step))*step=~0u;return 1;
}
static int position(EuBank *b,u32 owner,u32 row,u32 *step){
 for(u32 i=0;i<16;i++){
  volatile EuRuntime *r=b->runtime+i;
  u32 serial=r->reserved[3],epoch=r->epoch,rr=r->row;
  if(!serial||(serial&1)||epoch!=b->epoch||r->owner!=owner||rr!=row)continue;
  u32 value=r->reserved[1],valid=r->reserved[2];__asm__ volatile("dmb" ::: "memory");
  if(serial==r->reserved[3]&&valid){*step=value;return 1;}
 }
 return 0;
}

/* UI generation commits native notes before publishing the playback mode.
   On failure, the existing pattern/settings remain active. */
int live_generate(Euclid *e,u32 key,int value){
 EuRecord *r=selected(e,1);if(!r)return 0;EuPad p=live_value(e);
 if(key==5&&value==0)return live_edit(e,5,0);
 if(key==5&&eu_native(p)&&!eu_manual_cycle(p))return live_edit(e,5,1);
 Euclid next=*e;next.steps=eu_length(p);next.hits=eu_pulses(p);next.rotate=eu_rotation(p);next.velocity=100;
 if(key==1){next.steps=value<1?1:value>256?256:(u32)value;if(next.hits>next.steps)next.hits=next.steps;if(next.rotate>=next.steps)next.rotate%=next.steps;}
 if(key==2)next.hits=value<0?0:(u32)value>next.steps?next.steps:(u32)value;
 if(key==3)next.rotate=value<0?0:(u32)value>=next.steps?next.steps-1:(u32)value;
 if(key==4)next.velocity=value<1?1:value>127?127:(u32)value;
 int status=key==4&&eu_native(p)?eu_velocity(&next,MODEL):eu_apply(&next,MODEL);
 e->scratch=next.scratch;e->status=status;if(status!=EU_OK&&status!=EU_SAME)return 0;
 u32 serial=(r->serial+2)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 r->pads[e->pad]=eu_pack(next.steps,next.hits,next.rotate,next.velocity,1);r->pads[e->pad].pattern|=1u<<26;r->pads[e->pad].velocity=eu_dynamics_gate(next.velocity,eu_mode(p),eu_depth(p),eu_mel(e)?eu_mel_gate(e):eu_gate(p));
 if(eu_mel(e)){r->reserved[0]=(r->reserved[0]&~0xf00u)|EU_MELODIC|(((e->preview>>20)&15u)<<8);eu_record_set_pitch(r,e->pad,eu_mel_pitch(e));}
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();return 1;
}

int live_dynamic(Euclid *e,u32 key,int value){
 EuRecord *r=selected(e,1);if(!r)return 0;EuPad p=live_value(e);u32 mode=eu_mode(p),depth=eu_depth(p);
 if(key==4)mode=value<0?0:value>9?9:(u32)value;else if(key==6)depth=value<0?0:value>100?100:(u32)value;else return 0;
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");p.velocity=eu_dynamics_gate(100,mode,depth,eu_gate(p));r->pads[e->pad]=p;__asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();return 1;
}

/* CH3 accessors for melodic rows (pitched piano roll). */
int live_row_pitch(Euclid *e,u32 row,u32 *pitch){
 EuRecord *r=selected(e,0);if(!r||!eu_record_melodic(r)||row>=16)return 0;EuPad p=r->pads[row];if(!eu_pad_valid(p))return 0;*pitch=eu_record_pitch(r,row);return 1;
}
int live_pitch_owner(Euclid *e,u32 pitch,u32 except){
 EuRecord *r=selected(e,0);if(!r||!eu_record_melodic(r))return -1;
 for(u32 i=0;i<16;i++){EuPad p=r->pads[i];if(i!=except&&eu_pad_valid(p)&&eu_enabled(p)&&eu_record_pitch(r,i)==pitch)return (int)i;}return -1;
}
int live_assign_pitch(Euclid *e,u32 pitch){
 EuRecord *r=selected(e,1);if(!r||pitch>127)return 0;EuPad p=live_value(e);
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 r->reserved[0]=(r->reserved[0]&~0xf00u)|EU_MELODIC|(((e->preview>>20)&15u)<<8);eu_record_set_pitch(r,e->pad,pitch);r->pads[e->pad]=p;
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();return 1;
}
int live_set_gate(Euclid *e,u32 gate){
 EuRecord *r=selected(e,1);if(!r||gate<1||gate>64)return 0;EuPad p=live_value(e);
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 p.velocity=(p.velocity&~(63u<<24))|((gate&63u)<<24);r->pads[e->pad]=p;
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();return 1;
}
/* CH6 chord pad audition mailbox (see live_shared.h). M4 writes ChordMail only. */
__attribute__((used,retain)) int chord_audition_publish(int active,const u8 *count,const signed char *off,u32 velocity){
 EuBank *b=bank(active);if(!b)return 0;volatile ChordMail *m=&b->chord_mail;
 if(!active&&!m->active)return 1;
 u32 s=m->serial|1u;m->serial=s;__asm__ volatile("dmb" ::: "memory");
 m->active=active?1u:0u;m->velocity=velocity>127?127:velocity; /* CH8: pads scaled by the chord's Velocity */
 if(active)for(u32 pc=0;pc<12;pc++){u32 n=count[pc];m->count[pc]=(u8)(n>CA_VOICES?CA_VOICES:n);for(u32 i=0;i<CA_VOICES;i++)m->off[pc][i]=i<n?off[pc*CA_VOICES+i]:0;}
 __asm__ volatile("dmb" ::: "memory");m->serial=s+1u;return 1;
}
/* R5 (owner: in melodic Euclid a pad should only choose the row's pitch, not
   sound). EuControl.reserved[2] (previously unused) = 1 while the melodic
   Euclid view owns the pads. M7's pad press (perf_press already refreshes this
   line) publishes the pitch and drops the press. Releases stay native, so a
   note started earlier can never hang. */
__attribute__((section(".pad2"))) void chord_pad_silence(int on){
 u32 v=on?1u:0u;if(EC->reserved[2]!=v){EC->reserved[2]=v;__asm__ volatile("dsb" ::: "memory");}
}
u32 chord_mail_active(void){EuBank *b=bank(0);if(!b)return 0;volatile ChordMail *m=&b->chord_mail;return m->active&&!(m->serial&1u);}
u32 chord_pub_serial(void){EuBank *b=bank(0);return b?((volatile ChordPub*)&b->chord_pub)->serial:0;}
u32 chord_mail_serial(void){EuBank *b=bank(0);return b?((volatile ChordMail*)&b->chord_mail)->serial:0;}
__attribute__((used,retain)) int chord_pad_pitch(u32 pad){
 EuBank *b=bank(0);if(!b||pad>=16)return -1;u8 v=((volatile ChordPub*)&b->chord_pub)->pitch[pad];return v&0x80u?(int)(v&127u):-1;
}
/* M4 never reads or writes the audio core's ownership/refcount arrays. */
int chord_keys_snapshot(u32 owner,u32 *notes,u32 *held,u32 *root){
 EuBank *b=bank(0);for(u32 i=0;i<4;i++)notes[i]=0;*held=0;if(root)*root=128;if(!b)return 1;
 volatile ChordPub *p=&b->chord_pub;u32 serial=p->serial;
 if(serial&1u)return 0;
 u32 track=p->spare[0],epoch=p->spare[1],roots[4];
 volatile ChordKeys *keys=&b->chord_own.keys;
 for(u32 i=0;i<4;i++){roots[i]=keys->roots[i];notes[i]=keys->notes[i];}
 __asm__ volatile("dmb" ::: "memory");if(serial!=p->serial)return 0;
 if(track!=owner||epoch!=b->epoch){for(u32 i=0;i<4;i++)notes[i]=0;return 1;}
 for(u32 i=0;i<4;i++)for(u32 j=0;j<32;j++)if(roots[i]&(1u<<j)){if(root&&!*held)*root=32*i+j;(*held)++;}
 return 1;
}
/* CH7 (owner): recording takes over. Generated drum hits always sit exactly on
   their pattern steps. When notes are added (the project's next note ID at
   project+68 changes), a note on a generator pad of the current clip that is
   off the grid, past the lane length or not on a pattern step was recorded or
   drawn: that pad goes back to Manual (as Shift+Left). The generated notes stay
   in the clip as ordinary notes, so they and the recorded hits all play. The
   last seen ID is kept in EuControl.reserved[0] (UI-written, ignored by M7). */
__attribute__((used,retain)) u32 live_record_check(void){
 EuBank *b=bank(0);void *project=(void*)W(MODEL,0);if(!b||!project||(b->serial&1))return 0;
 u32 next=W(project,0x68);if(next==EC->reserved[0])return 0;EC->reserved[0]=next;
 u32 owner=0,seq=W(MODEL,0x144),row=16;void *node=0;
 if(!ui_owner(&owner)||ui_type(&owner)!=14)return 0;
 if(!ui_get(&seq,0x73,&row)||row>=16)return 0;
 u32 count=b->count;EuRecord *r=record(b->records,&count,owner,row,0);if(!r||eu_record_melodic(r))return 0;
 if(!NFN(0x0812dfe8,int(*)(void*,u32,void*))(project,seq,&node)||!node)return 0;
 void *c=(u8*)node+12;u32 n=W(c,0x3000),foreign=0,raw[6];if(n>2000)return 0;
 for(u32 i=0;i<n;i++){
  if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))(c,i,raw)||B(raw,0)!=1)continue;u32 pad=H(raw,2);if(pad>=16)continue;
  EuPad p=r->pads[pad];if(!eu_enabled(p))continue;
  u32 L=eu_length(p),k=eu_pulses(p),rot=eu_rotation(p),t=raw[1],at=t/960;
  if(!eu_native(p)||t%960||at>=L||((((at+L-rot)%L)*k)%L)>=k)foreign|=1u<<pad;
 }
 if(!foreign)return 0;
 u32 serial=(r->serial+2)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");
 for(u32 i=0;i<16;i++)if(foreign&(1u<<i))r->pads[i].pattern&=~(1u<<25);
 __asm__ volatile("dmb" ::: "memory");r->serial=serial;ui_commit();return foreign;
}
/* CH9: chord pads currently held (M7-published); recorded chords are only
   reshaped to the Rhythm once every chord pad is up. */
__attribute__((used,retain)) u32 chord_pads_held(void){EuBank *b=bank(0);return b?((volatile ChordPub*)&b->chord_pub)->held:0;}

#include "melodic_lock_shared.h"
#include "melodic_send_shared.h"
/* A separate checked allocation: no EuBank ABI or fixed RAM boundary changes. */
int mel_audio_prepare(u32 owner){
 EuBank *b=bank(1);if(!b)return 0;
 if(!b->reserved[0]){
  u32 p=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),n=sizeof(MelAudio)+sizeof(MelSends);
  if(!eu_memory(p,n)||end<p||end-p<n+32)return 0;
  if(NFN(0x08104c08,u32(*)(u32))(n)!=p)return 0;clear((void*)p,n);
  ((MelAudio*)p)->sends=p+sizeof(MelAudio);
  __asm__ volatile("dmb" ::: "memory");b->reserved[0]=p;
 }
 if(!owner)return 1;
 MelAudio *s=(MelAudio*)b->reserved[0];for(u32 i=0;i<8;i++)if(s->owners[i]==owner)return 1;
 s->serial|=1;__asm__ volatile("dmb" ::: "memory");s->owners[s->next++&7]=owner;
 __asm__ volatile("dmb" ::: "memory");s->serial=(s->serial+1)&~1u;if(!s->serial)s->serial=2;return 1;
}

/* P18: keep the published Step Len current (project load, Step Len changes). */
int live_mel_unit(Euclid *e){
 EuRecord *r=selected(e,0);if(!r||!eu_record_melodic(r))return 0;u32 want=(r->reserved[0]&~0xf00u)|(((e->preview>>20)&15u)<<8);if(r->reserved[0]==want)return 0;
 u32 serial=(r->serial+2u)&~1u;if(!serial)serial=2;r->serial=serial|1;__asm__ volatile("dmb" ::: "memory");r->reserved[0]=want;__asm__ volatile("dmb" ::: "memory");r->serial=serial;return 1;
}

/* P28 arpeggiator: the selected track's settings for the audio core
   (arp_shared.h). The block is allocated once, like MelAudio. */
#include "arp_shared.h"
int arp_publish(u32 on,u32 track,u32 mode,u32 rate,u32 octaves,u32 gate,u32 bpm,u32 background){
 EuBank *b=bank(on!=0);if(!b)return 0;
 if(!b->reserved[3]){
  if(!on)return 1;
  u32 p=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),n=(sizeof(ArpBlock)+31u)&~31u;
  if(!eu_memory(p,n)||end<p||end-p<n+32||(p&31))return 0;
  if(NFN(0x08104c08,u32(*)(u32))(n)!=p)return 0;clear((void*)p,n);
  __asm__ volatile("dmb" ::: "memory");b->reserved[3]=p;
 }
 volatile ArpMail *m=&((ArpBlock*)b->reserved[3])->mail;
 if(m->magic==ARP_MAGIC&&m->on==on&&m->track==track&&m->mode==mode&&m->rate==rate&&m->octaves==octaves&&m->gate==gate&&m->bpm==bpm&&m->spare[0]==background)return 1;
 u32 s=m->serial|1u;m->serial=s;__asm__ volatile("dmb" ::: "memory");
 m->magic=ARP_MAGIC;m->on=on;m->track=track;m->mode=mode;m->rate=rate;m->octaves=octaves;m->gate=gate;m->bpm=bpm;m->spare[0]=background;
 __asm__ volatile("dmb" ::: "memory");m->serial=s+1u;return 1;
}
/* R6.6 Berlin-school transpose (seqfx_shared.h). The block hangs off the arp
 * block (allocated here if no arp ran yet); M4 owns its first 96 bytes. */
#include "seqfx_shared.h"
__attribute__((noinline,section(".pad4"))) TrBlock *tr_block(int create){
 EuBank *b=bank(create);if(!b)return 0;
 if(!b->reserved[3]){if(!create)return 0;
  u32 p=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),n=(sizeof(ArpBlock)+31u)&~31u;
  if(!eu_memory(p,n)||end<p||end-p<n+32||(p&31))return 0;
  if(NFN(0x08104c08,u32(*)(u32))(n)!=p)return 0;clear((void*)p,n);__asm__ volatile("dmb" ::: "memory");b->reserved[3]=p;}
 volatile ArpMail *m=&((ArpBlock*)b->reserved[3])->mail;u32 t=m->spare[6];
 if(eu_memory(t,sizeof(TrBlock))&&((TrBlock*)t)->magic==TR_MAGIC)return (TrBlock*)t;if(!create)return 0;
 u32 p=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),n=(sizeof(TrBlock)+31u)&~31u;
 if(!eu_memory(p,n)||end<p||end-p<n+32||(p&31))return 0;
 if(NFN(0x08104c08,u32(*)(u32))(n)!=p)return 0;clear((void*)p,n);((TrBlock*)p)->magic=TR_MAGIC;
 __asm__ volatile("dmb" ::: "memory");m->spare[6]=p;return (TrBlock*)p;
}
static __attribute__((noinline,section(".pad4"))) int tr_slot(TrBlock *t,u32 owner,int create){
 for(u32 i=0;i<TR_TRACKS;i++)if(t->owner[i]==owner)return (int)i;if(!create)return -1;
 for(u32 i=0;i<TR_TRACKS;i++)if(!t->owner[i]||(!t->on[i]&&!t->off[i])){t->owner[i]=owner;t->on[i]=t->mode[i]=0;return (int)i;}return -1;
}
/* which: 0 Transpose on/off, 1 mode. Returns the offset text value. */
__attribute__((noinline,section(".pad4"))) int tr_get(u32 owner,u32 which){
 TrBlock *t=tr_block(0);int i=t?tr_slot(t,owner,0):-1;if(i<0)return which==2?0:0;
 return which==0?t->on[i]:which==1?t->mode[i]:t->off[i];
}
__attribute__((noinline,section(".pad4"))) void tr_set(u32 owner,u32 which,u32 value){
 TrBlock *t=tr_block(1);int i=t?tr_slot(t,owner,1):-1;if(i<0)return;
 if(which)t->mode[i]=value!=0;else t->on[i]=value!=0;
}
/* Every UI tick: arm the selected track's pads while its Transpose is on. */
__attribute__((noinline,section(".pad4"))) void tr_tick(void){
 TrBlock *t=tr_block(0);if(!t)return;u32 owner=0;int i=-1;
 if(ui_owner(&owner)&&owner)i=tr_slot(t,owner,0);
 u32 armed=i>=0&&t->on[i]?(u32)i+1:0;
 if(armed){extern unsigned chord_project_scale(unsigned char*);extern int chord_pad_pitch(unsigned);
  u8 rel[7];u32 root=chord_project_scale(rel);int base=-1;
  for(u32 p=0;p<16;p++){int q=chord_pad_pitch(p);if(q>=0&&(u32)q%12==root&&(base<0||q<base))base=q;}
  if(base<0)armed=0;else{t->root=(u8)root;t->base=(u8)base;for(u32 k=0;k<7;k++)t->rel[k]=rel[k];}}
 if(t->armed!=armed){__asm__ volatile("dmb" ::: "memory");t->armed=armed;}
 /* R6.8b (owner: pads/encoder 7 did not reliably show the transposition): the
    silent pad press redraws nothing natively; follow M7's offserial here. */
 volatile u32 *seen=(volatile u32*)(void*)t->m4_pad,now=*(volatile u32*)&t->offserial;
 if(*seen!=now||seen[1]!=armed){*seen=now;seen[1]=armed;extern void tr_changed(void) __attribute__((weak));
  NFN(0x081257f0,void(*)(void*))((u8*)MODEL+NOFF_MODEL_PADS);if(tr_changed)tr_changed();}
}
/* R6.6 (spec): while the selected track's pads set the transposition, root pads
 * light dim in the track colour and the pad of the active transposition brighter. */
__attribute__((noinline,section(".pad5"))) int tr_lights(void *pads){
 TrBlock *t=tr_block(0);if(!t||!t->armed||t->armed>TR_TRACKS)return 0;extern int chord_pad_pitch(unsigned);
 u32 i=t->armed-1,index=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)MODEL+4,0x131),dim=NFN(0x08140f50,u32(*)(u32))(index),bright=NFN(0x08140ef0,u32(*)(u32))(index);
 int active=tr_apply(t,(int)t->base,t->off[i],t->mode[i]);
 for(u32 p=0;p<16;p++){int q=chord_pad_pitch(p);u32 c=q==active?bright:q>=0&&(u32)q%12==t->root?dim:0;W(pads,p*16)=c;W(pads,p*16+4)=c;W(pads,p*16+8)=c;W(pads,p*16+12)=0;}
 return 1;
}
/* P29: what the audio core reports about the arp (diag line, see arp_shared.h). */
int arp_diag(u32 *out){
 EuBank *b=bank(0);if(!b||!b->reserved[3])return 0;volatile u32 *d=((ArpBlock*)b->reserved[3])->state.diag;
 for(u32 i=0;i<8;i++)out[i]=d[i];return 1;
}
