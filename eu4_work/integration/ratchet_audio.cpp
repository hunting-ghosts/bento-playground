/* R6.13 ratchet playback (M7). Spec: ratchet_shared.h.
 * rt_note runs in the native sequencer's note-on adapter (08060B9A), after the
 * lock condition filter and before the native note-on 0805F8E0: it rolls the
 * ratchet once per note (chord notes starting together share the roll), makes
 * the native first hit 1/count long with the shaped velocity, and arms an
 * entry. rt_block runs after the native renderer for every played segment
 * (wrapper at its only caller, 080601E8): it plays the later hits on their
 * exact frames through the same note path as native notes (locks, transpose,
 * de-click), and drops entries on rewind, clip/track change or expiry, so a
 * stop/rewind never bursts or leaves notes hanging. No allocation; bounded.
 * Code in the checked stock-zero cave 080CF4C0..080CFFF0. */
#define _Static_assert static_assert
#include "live_shared.h"
#define LOCK_M7
#include "step_lock_shared.h"
#include "lock_api.h"
#include "melodic_lock_api.h"
#include "ratchet_shared.h"
#define RT2 __attribute__((noinline,section(".rt2code"))) /* R6.16c: second cave 080DA640..080DABF0 */
static void invalidate(u32 a,u32 n){__asm__ volatile("dsb" ::: "memory");if(W((void*)0xe000ed14u,0)&(1u<<16))for(u32 end=a+n;a<end;a+=32)W((void*)0xe000ef5cu,0)=a;__asm__ volatile("dsb" ::: "memory");}
static RtBlock *block(){
 invalidate(0x24041fc0u,32);u32 p=*RT_EC_POINTER;if(!eu_memory(p,sizeof(RtBlock)))return 0;
 invalidate(p,sizeof(RtConfig));RtBlock *b=(RtBlock*)p;if(b->cfg.magic!=RT_BLOCK_MAGIC)return 0;
 if(b->m7_magic!=RT_M7_MAGIC){u32 *w=(u32*)&b->m7_magic;for(u32 i=0;i<(sizeof(RtBlock)-sizeof(RtConfig))/4;i++)w[i]=0;b->m7_magic=RT_M7_MAGIC;
  b->epoch=((u32)FN(0x080a40b8,int(*)())()^p^0x52544237u)|1u;} /* R6.16c: requests of an earlier init can never validate */
 return b;
}
/* R6.16c: read-only lookup for the sampler voice start: no M7-area init, no write. */
static RtBlock *block_ro(){u32 p=*RT_EC_POINTER;if(!eu_memory(p,sizeof(RtBlock)))return 0;RtBlock *b=(RtBlock*)p;return b->cfg.magic==RT_BLOCK_MAGIC&&b->m7_magic==RT_M7_MAGIC&&b->epoch?b:0;}
static i64 time_at(void *clock,u32 frame){i64 t=0;FN(0x080a21c0,void(*)(void*,void*,int))(&t,clock,(int)frame);return t;}
static int frame_of(void *clock,i64 t){return FN(0x080a2200,int(*)(void*,void*))(clock,&t);}
static u32 roll100(){return (u32)FN(0x080a40b8,int(*)())()%100u;}
/* Native active-note table: count s+238, entry i at s+i*16: +38 on, +3A pad, +3C pitch, +40 end. */
static u8 *table_entry(void *s,u32 pitch,u32 pad){
 u32 n=W(s,0x238);if(n>32)return 0;
 for(u32 i=0;i<n;i++){u8 *e=(u8*)s+i*16;if(e[0x38]&&W(e,0x3c)==pitch&&H(e,0x3a)==pad)return e;}return 0;
}
static u32 amount(RtBlock *b,u32 owner){
 for(u32 i=0;i<RT_TRACKS;i++)if(owner&&b->cfg.owner[i]==owner)return b->cfg.amount[i]>100?100:b->cfg.amount[i];
 return 100;
}
/* Condition-counter loop of this sequence (24048A60, as locks_native_filter). */
static u32 loop_count(void *s){
 for(u32 i=0;i<16;i++){void *c=(void*)(0x24048a60u+i*32);if(W(c,0)==(u32)s&&W(c,4)==W(s,12)&&W(c,8)==W(s,0x86c0))return W(c,12);}return 0;
}
/* R6.17 trigger conditions (owner; semantics as Elektron and romanjeff's
 * bento_enhanced v3.40, GPL-3.0, used as reference only): codes >= 100.
 * loop = passes of this sequence (or Euclid pad cycle) since launch/restart.
 * A:B plays on pass A of every B; 1ST on the first pass only, !1ST on every
 * later pass. PRE plays if the most recent A:B / 1ST / !1ST decision on the
 * same sequence passed (false until there is one); PRE steps leave that
 * state alone; % never counts. State: the sequence's T2 condition counter
 * (24048A60, 16 x 32 B: seq, owner, row, loop, boundaries, reserved[3]),
 * reserved[0] = 2 | passed, reserved[1] = owner/row stamp, so a counter that
 * the T2 code re-binds to another owner or row forgets it. */
extern "C" __attribute__((used,retain,section(".rt2code"))) u32 rt_cond(void *s,u32 c,u32 loop){
 u32 *k=0;for(u32 i=0;i<16;i++){u32 *q=(u32*)(0x24048a60u+i*32u);if(q[0]==(u32)s&&q[1]==W(s,12)&&q[2]==W(s,0x86c0)){k=q;break;}}
 u32 stamp=k?(k[1]*31u)^k[2]^0x50524531u:0;
 if(c>=137)return (u32)(k&&k[6]==stamp&&(k[5]&3u)==3u)^(u32)(c==138);
 u32 pass;
 if(c>=135)pass=(loop==0)^(c==136);
 else{u32 i=c-100,b=2;while(i>=b){i-=b;b++;}pass=loop%b==i;}
 if(k){k[5]=2u|pass;k[6]=stamp;}
 return pass;
}
static int roll(RtBlock *b,void *s,u32 r,i64 t0){
 for(u32 i=0;i<RT_ROLLS;i++){RtRoll *q=b->rolls+i;if(q->seq==(u32)s&&q->word==r&&q->t0==t0)return (int)q->pass;}
 u32 a=amount(b,W(s,12)),c=rt_prob(r);int pass;
 if(c<100&&!a)pass=0;
 else if(c>=100)pass=(int)rt_cond(s,c,loop_count(s)); /* A:B and R6.17 1ST/PRE; owner: amount scales % only */
 else{u32 p=c?c*a/100u:a;pass=p&&(p>=100||roll100()<=p);} /* <= p as the lock filter */
 RtRoll *q=b->rolls;for(u32 i=1;i<RT_ROLLS;i++)if(b->rolls[i].t0<q->t0||!b->rolls[i].seq){q=b->rolls+i;if(!q->seq)break;}
 q->seq=(u32)s;q->word=r;q->t0=t0;q->pass=(u32)pass;return pass;
}
static u32 step_of(RtBlock *b,u32 owner){
 for(u32 i=0;i<RT_TRACKS;i++)if(owner&&b->cfg.owner[i]==owner&&b->cfg.step[i])return b->cfg.step[i];
 return 240u; /* 1/16 until the M4 publishes this track's Step Len */
}
static u32 step_ticks(void *clip){
 u32 grid=W(clip,0);if(grid>=15)return 0;
 float scale=((const float*)0x080bdbecu)[grid];u32 period=(u32)(scale*960.0f+0.5f);return period<=30720?period:0;
}
/* R6.16: the track handle a note of (s, pad) goes to (as native 0805F8E0). */
static RT2 u32 handle_of(void *s,u32 pad){u32 h=pad<=15?W(s,(0x21b6u+pad)*4u+4u):0xffffff00u;return h!=0xffffff00u?h:H(s,0x10);}
/* R6.16: the next sampler voice start of this handle belongs to entry e (cut:
 * release e's previous voice first). Oldest request first; bounded. */
#define RT_REQUEST_LIFE 128u /* rt_block calls: a request is consumed in the same audio cycle */
static RT2 void request(RtBlock *b,RtEntry *e,void *s,u32 cut){
 RtCut *q=0;for(u32 i=0;i<RT_CUTS;i++){RtCut *c=b->cuts+i;if(!c->handle){q=c;break;}}
 if(!q)return;
 u32 idx=(u32)(e-b->entries);q->handle=handle_of(s,e->pad);q->entry=idx;q->gen=b->voices[idx].gen;q->tick=b->tick;q->cut=cut;q->order=++b->order;
 q->check=rt_cut_check(b->epoch,q->handle,idx,q->gen,q->tick,cut,q->order);b->pending++;b->cut_diag[0]++;
}
/* Arm an entry for ratchet word r of a note at absolute time t0 (shared by the
 * native note-on adapter and the live scheduler). Returns the first hit's
 * velocity (shaped) or vel unchanged when nothing is armed. */
static __attribute__((noinline)) u32 arm(void *s,u32 r,i64 t0,u32 len,void *clock,u32 frame,u32 pitch,u32 vel,u32 pad,u32 word){
 if(!r||(r&0xff0080e0u)!=RT_TAG||rt_shape(r)>2||!s)return vel;
 RtBlock *b=block();if(!b)return vel;
 void *clip=(void*)W(s,0x86c0);u32 n=rt_count(r);
 if(!clock||!clip||n<2||frame>1024)return vel;
 if(!roll(b,s,r,t0)){b->diag[1]++;return vel;}
 RtEntry *e=0;for(u32 i=0;i<RT_ENTRIES;i++)if(!b->entries[i].seq){e=b->entries+i;break;}
 if(!e){b->diag[4]++;return vel;}
 u32 melodic=!B(clip,0x38),step=melodic?step_of(b,W(s,12)):step_ticks(clip);
 if(!step)return vel;
 /* span = max(note length, one step); one hit = span / count (owner, R6.14). */
 u32 length=melodic?len:(u32)(((u64)len*step)/960u),span=length>step?length:step;
 for(u32 i=0;i<sizeof(*e)/4;i++)((u32*)e)[i]=0;
 e->seq=(u32)s;e->owner=W(s,12);e->clip=(u32)clip;e->t0=t0;e->now0=time_at(clock,frame);
 /* Step clips count the event length 960 per step; the native rounds sounding
    lengths down to whole steps, ratchet hits keep their real span / count. */
 u32 hit_ticks=span/n;
 e->span=span;e->len=len;e->hit=hit_ticks?hit_ticks:1;e->word=word;e->pad=(u16)pad;e->pitch=(u8)pitch;e->vel=(u8)(vel>127?127:vel);
 e->count=(u8)n;e->next=1;e->shape=(u8)rt_shape(r);e->depth=(u8)rt_depth(r);e->melodic=(u8)melodic;
 RtVoice *v=b->voices+(e-b->entries);v->voice=0;v->root=0;v->age=0;v->gen++;request(b,e,s,0); /* R6.16: record the first hit's voice */
 b->active++;b->diag[0]++;
 return rt_velocity(e->vel,0,n,e->shape,e->depth);
}
extern "C" __attribute__((used,retain)) void rt_note(void *s,u32 token,u32 *regs){
 u8 *osp=(u8*)(regs+14);
 /* The native first hit: shaped velocity (r2 restored by the adapter); its
    end time is set to one hit length by the first rt_block (same segment,
    before the native release loop). */
 if(!s)return;regs[2]=arm(s,lc_ratchet(token),*(i64*)(osp+0x20),W(osp,0x30),(void*)regs[6],regs[3],regs[1],regs[2],W(osp,0),W(osp,0x3c));
}
/* R6.16: drum pads the live scheduler plays itself (Euclid, velocity modes,
 * own Step Count) arm here: token = the note's own lock word, vel = its
 * effective velocity (after velocity modes), word = the filtered locks. */
extern "C" __attribute__((used,retain,section(".rt2code"))) u32 rt_live(void *s,u32 token,u32 pad,u32 vel,u32 frame,void *clock,u32 len,u32 word){
 if(!s||!clock)return vel;return arm(s,lc_ratchet(token),time_at(clock,frame),len,clock,frame,0,vel,pad,word);
}
/* R6.16: native sampler voice start (both note paths, before kick_voice):
 * if a ratchet hit posted for this handle, release that note's previous hit. */
/* R6.16c: a request that an armed note of this init made (stale or reused
 * memory never passes); read-only. */
static RT2 int valid_cut(RtBlock *b,RtCut *c){
 return c->handle&&c->entry<RT_ENTRIES&&b->voices[c->entry].gen==c->gen&&c->check==rt_cut_check(b->epoch,c->handle,c->entry,c->gen,c->tick,c->cut,c->order);
}
static RT2 int ram(u32 p){return !(p&3)&&((p>=0x20000000u&&p<0x20020000u)||(p>=0x24000000u&&p<0x24080000u)||(p>=0x30000000u&&p<0x30048000u)||(p>=0xc0000000u&&p<0xc8000000u));}
/* R6.16c: the root's live voice list holds v (checked before any read of v). */
static RT2 int live_voice(void *root,u32 v){u32 n=W(root,0x60);if(!v||n>16)return 0;for(u32 i=0;i<n;i++)if(W(root,0x20+i*4)==v)return 1;return 0;}
/* R6.16c: native sampler voice start (both note paths, before kick_voice).
 * A no-op without side effects unless a valid request of an armed ratchet
 * note is pending for this track: its check word (per-init epoch, handle,
 * entry, generation, tick, order) must match and it must be recent. Then the
 * note's previous hit is released, only if it is still in the root's live
 * voice list, sounding, not released and still the same voice (native age). */
extern "C" __attribute__((used,retain,section(".rt2code"))) void rt_voice(void *voice,void *root){
 if(!voice||!root||W(root,0)!=0x080ac66cu)return;
 RtBlock *b=block_ro();if(!b||!b->pending)return;
 u32 h=W(root,12);RtCut *q=0;
 for(u32 i=0;i<RT_CUTS;i++){RtCut *c=b->cuts+i;
  if(c->handle!=h||b->tick-c->tick>RT_REQUEST_LIFE||!valid_cut(b,c))continue;
  if(!q||c->order<q->order)q=c;}
 if(!q)return;
 RtVoice *v=b->voices+q->entry;u32 prev=v->voice;
 q->handle=0;q->check=0;if(b->pending)b->pending--;b->cut_diag[1]++;
 if(q->cut&&prev&&prev!=(u32)voice&&v->root==(u32)root&&v->age&&live_voice(root,prev)&&B((void*)prev,0)&&!B((void*)prev,0x58+0x18)&&W((void*)prev,8)+1u==v->age){
  FN(0x08063960,void(*)(void*))((u8*)prev+0x58);b->cut_count++;}
 v->voice=(u32)voice;v->root=(u32)root;v->age=0;
}
/* R6.16c: rt_block's bookkeeping. Inert (as R6.15) unless a ratchet is armed
 * or a valid request of one is outstanding; garbage is never written. Returns
 * whether entries are armed. */
static RT2 u32 maintain(RtBlock *b){
 u32 live=0;if(b->pending&&!b->active)for(u32 i=0;i<RT_CUTS;i++)live|=(u32)valid_cut(b,b->cuts+i);
 if(!b->active&&!live)return 0;
 b->tick++;
 for(u32 i=0;i<RT_CUTS;i++){RtCut *c=b->cuts+i;if(b->tick-c->tick>RT_REQUEST_LIFE&&valid_cut(b,c)){c->handle=0;c->check=0;if(b->pending)b->pending--;b->cut_diag[2]++;}}
 /* the native age of armed entries' voices once set (live list checked first) */
 for(u32 i=0;i<RT_ENTRIES;i++){RtVoice *v=b->voices+i;if(b->entries[i].seq&&v->voice&&!v->age&&ram(v->root)&&W((void*)v->root,0)==0x080ac66cu&&live_voice((void*)v->root,v->voice))v->age=W((void*)v->voice,8)+1u;} /* +1: native ages start at 0 */
 return b->active;
}
static void drop(RtBlock *b,RtEntry *e,u32 why){e->seq=0;if(b->active)b->active--;b->diag[3]+=why;}
static void hit(RtEntry *e,void *s,void *clock,void *router,int frame,u32 k){
 u32 vel=rt_velocity(e->vel,k,e->count,e->shape,e->depth),pitch=e->pitch,pad=e->pad,w=e->word;
 FN(MEL_PENDING,void(*)(void*,void*,u32,u32))(s,router,pad,w);
 FN(LIVE_LOCK_PENDING,void(*)(u32))(w);FN(LIVE_LOCK_ROUTE,void(*)(void*,void*,u32))(s,router,pad);
 u8 *t=table_entry(s,pitch,pad);
 {RtBlock *b=block();if(b)request(b,e,s,1);} /* R6.16 mono roll: this hit's voice start cuts the previous hit */
 /* Melodic: a still-sounding previous hit is released first (as the Euclid
    player does); drum steps retrigger like the native sequencer. */
 if(t&&e->melodic)FN(0x0805fe00,void(*)(void*,u32,u32,u32,void*))(s,pitch,(u32)frame,pad,router);
 FN(0x0805f8e0,void(*)(void*,u32,u32,u32,u32,void*))(s,pitch,vel,(u32)frame,pad,router);
 FN(LIVE_LOCK_PENDING,void(*)(u32))(0);FN(MEL_PENDING_CLEAR,void(*)())();
 i64 end=time_at(clock,(u32)frame)+(i64)e->hit;
 if(!t){u32 n=W(s,0x238);if(n>=32)return;t=(u8*)s+n*16;W(t,0x3c)=pitch;H(t,0x3a)=(u16)pad;W(s,0x238)=n+1;}
 t[0x38]=1;*(i64*)(t+0x40)=end;
}
extern "C" __attribute__((used,retain)) void rt_block(void *s,void *clock,u32 offset,u32 frames,void *router){
 if(!s||!clock||frames>1024||offset>1024||offset+frames>1024)return;
 RtBlock *b=block();if(!b||!maintain(b))return; /* R6.16c: inert unless armed or a valid request is outstanding */
 i64 start=time_at(clock,offset);
 for(u32 i=0;i<RT_ENTRIES;i++){
  RtEntry *e=b->entries+i;if(e->seq!=(u32)s)continue;
  if(e->owner!=W(s,12)||e->clip!=W(s,0x86c0)||!B(s,0x20)||start<e->last){drop(b,e,1);continue;}
  e->last=start;
  if(!e->spare[0]){ /* first call: the native first hit lasts one hit too */
   e->spare[0]=1;u8 *t=table_entry(s,e->pitch,e->pad);if(t){*(i64*)(t+0x40)=e->now0+(i64)e->hit;b->diag[5]++;}
  }
  if(start>e->t0+2*(i64)e->span){drop(b,e,1);continue;}
  while(e->next<e->count){
   i64 t=e->t0+(i64)(((u64)e->span*e->next)/e->count);
   int f=frame_of(clock,t);
   if(f>=(int)(offset+frames))break;
   if(f>=(int)offset){hit(e,s,clock,router,f,e->next);b->diag[2]++;}
   e->next++;
  }
  if(e->next>=e->count)drop(b,e,0);
 }
}
