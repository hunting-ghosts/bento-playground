/* P28 arpeggiator, audio core (M7). Owner decisions: docs/releases/p27/PLAN.md
 * (P28 section) and docs/releases/p28/DESIGN.md.
 *
 * Keyboard pad presses reach chord_press/chord_release (CH6 hooks on the pad
 * module's note posts 08084918/0808494E/0808414A/08084180). While the selected
 * track's arp is on, those presses are kept here instead of being posted, and
 * arp_block (once before native graph traversal) plays one note of the
 * held set per step through the same native post 0809ECA0 with the same record
 * layout the pad module uses: {type 2 on / 3 off, 0, target handle, pitch,
 * velocity, 0}.
 *
 * Timing: positions are native clock ticks (960 per quarter) in Q8 fixed
 * point. While transport runs, the pre-graph adapter reports the song position
 * (arp_clock) and steps fall on the rate grid; when nothing plays the arp runs
 * free from the first press at the project tempo (BPM from M4, 48 kHz).
 * No allocation, no UI calls, bounded work per block. */
#define _Static_assert static_assert
#include "arp_shared.h"
typedef void (*Post)(void*,void*);
#define POST ((Post)(0x0809eca0u|1u))
#define LDIV(a,b) FN(0x080a34f4,i64(*)(i64,i64))((a),(b)) /* native i64 division (live_audio uses it) */
static void invalidate(u32 a,u32 n){__asm__ volatile("dsb" ::: "memory");if(W((void*)0xe000ed14u,0)&(1u<<16))for(u32 end=a+n;a<end;a+=32)W((void*)0xe000ef5cu,0)=a;__asm__ volatile("dsb" ::: "memory");}
static EuBank *bank(){
 invalidate(EU_CONTROL_ADDR,32);if(EC->magic!=EU_MAGIC||EC->bytes!=sizeof(EuBank)||!eu_memory(EC->pointer,sizeof(EuBank)))return 0;
 EuBank *b=(EuBank*)EC->pointer;invalidate((u32)b,32);if(!b->serial||(b->serial&1))return 0;return b;
}
static ArpBlock *block(){
 EuBank *b=bank();if(!b)return 0;u32 p=b->reserved[3];if(!eu_memory(p,sizeof(ArpBlock)))return 0;
 ArpBlock *a=(ArpBlock*)p;invalidate(p,sizeof(ArpMail));
 u32 s=a->mail.serial;if(s&&!(s&1)&&a->mail.magic==ARP_MAGIC){u32 m[16];volatile u32 *src=(volatile u32*)&a->mail;for(u32 i=0;i<16;i++)m[i]=src[i];__asm__ volatile("dmb" ::: "memory");invalidate(p,32);
  if(a->mail.serial==s){u32 *dst=(u32*)&a->state.cfg;for(u32 i=0;i<16;i++)dst[i]=m[i];a->state.seen_serial=s;}}
 return a;
}
static void send(ArpState *s,u32 type,u32 pitch,u32 vel){
 s->diag[type==2?2:3]++;
 for(u32 k=0;k<2;k++){if(!s->router[k]||!s->handle[k])continue;
  volatile u32 r[6];r[0]=type;r[1]=0;r[2]=s->handle[k];r[3]=pitch;r[4]=type==2?vel:0;r[5]=0;POST((void*)s->router[k],(void*)r);}
}
static void stop(ArpState *s){if(s->sounding){send(s,3,s->sounding&127u,0);s->sounding=0;}s->running=0;}
static void clear(ArpState *s){stop(s);s->nroots=0;s->wait=0;s->step=0;}
static int find(ArpState *s,u32 root){for(u32 i=0;i<s->nroots;i++)if(s->roots[i].root==root)return (int)i;return -1;}
static int chord_tones(EuBank *b,u32 root,u8 *tone){
 ChordMail *m=&b->chord_mail;invalidate((u32)m,sizeof(*m));u32 serial=m->serial;
 if(serial&&!(serial&1)&&m->active){u32 n=m->count[root%12];if(n&&n<=CA_VOICES){u32 k=0;
  for(u32 i=0;i<n;i++){int p=(int)root+m->off[root%12][i];if(p>=0&&p<=127)tone[k++]=(u8)p;}
  __asm__ volatile("dmb" ::: "memory");invalidate((u32)m,32);if(m->serial==serial&&k)return (int)k;}}
 tone[0]=(u8)root;return 1;
}
/* From chord_press, before anything is posted. Returns 1 when the arp keeps it. */
extern "C" __attribute__((used,retain)) int arp_press(void *router,u32 *rec,u32 slot){
 ArpBlock *a=block();if(!a||!rec)return 0;ArpState *s=&a->state;u32 root=rec[3];if(root>127)return 0;
 if(slot){int i=find(s,root);if(i<0||!s->roots[i].down)return 0;s->router[1]=(u32)router;s->handle[1]=rec[2];return 1;}
 if(!s->cfg.on||s->cfg.magic!=ARP_MAGIC)return 0;
 if(s->wait){clear(s);} /* latch: a new press after letting go replaces the held notes */
 if(s->track!=s->cfg.track){clear(s);s->track=s->cfg.track;} /* the selected track's arp */
 if(!s->nroots){s->router[1]=s->handle[1]=0;}
 s->router[0]=(u32)router;s->handle[0]=rec[2];
 int i=find(s,root);
 if(i<0){if(s->nroots>=16)return 1;ArpRoot *r=&s->roots[s->nroots++];r->root=(u8)root;EuBank *b=bank();r->n=(u8)(b?chord_tones(b,root,r->tone):(r->tone[0]=(u8)root,1));i=(int)s->nroots-1;}
 u32 v=rec[4];s->roots[i].vel=(u8)(v>127?127:v?v:1);s->roots[i].down=1;s->diag[1]++;return 1;
}
extern "C" __attribute__((used,retain)) int arp_release(void *router,u32 *rec,u32 slot){
 (void)router;ArpBlock *a=block();if(!a||!rec)return 0;ArpState *s=&a->state;int i=find(s,rec[3]);
 if(i<0||!s->roots[i].down)return 0;if(slot)return 1;
 s->roots[i].down=0;
 if(s->cfg.on!=2){for(u32 j=(u32)i;j+1<s->nroots;j++)s->roots[j]=s->roots[j+1];s->nroots--;}
 u32 held=0;for(u32 j=0;j<s->nroots;j++)held+=s->roots[j].down;
 if(!held&&s->cfg.on==2)s->wait=1;
 return 1;
}
/* From the pre-graph adapter: song position at frame 0 of this block. */
extern "C" __attribute__((used,retain)) void arp_clock(void *clock){
 ArpBlock *a=block();if(!a||!clock)return;ArpState *s=&a->state;if(s->clock_block==s->block+1)return;
 i64 t=0;FN(0x080a21c0,void(*)(void*,void*,int))(&t,clock,0);s->clock_pos=t<<8;s->clock_block=s->block+1;
}
/* One note of the held set per step. */
static u32 pick(ArpState *s,u32 *vel){
 u8 tone[32],tv[32];u32 k=0; /* no memset: filled below */
 for(u32 i=0;i<s->nroots;i++)for(u32 j=0;j<s->roots[i].n&&k<32;j++){u8 p=s->roots[i].tone[j];u32 dup=0;for(u32 q=0;q<k;q++)dup|=tone[q]==p;if(!dup){tone[k]=p;tv[k]=s->roots[i].vel;k++;}}
 if(!k)return 0;
 u32 mode=s->cfg.mode;
 if(mode!=3)for(u32 i=1;i<k;i++)for(u32 j=i;j>0&&tone[j]<tone[j-1];j--){u8 x=tone[j];tone[j]=tone[j-1];tone[j-1]=x;x=tv[j];tv[j]=tv[j-1];tv[j-1]=x;}
 u32 oct=s->cfg.octaves;if(oct<1)oct=1;if(oct>4)oct=4;u32 m=k*oct,i;
 if(mode==4){s->rnd=s->rnd*1664525u+1013904223u;i=(s->rnd>>8)%m;}
 else if(mode==2&&m>1){u32 p=2*m-2,j=s->step%p;i=j<m?j:p-j;}
 else{i=s->step%m;if(mode==1)i=m-1-i;}
 s->step++;
 u32 p=tone[i%k]+12u*(i/k);while(p>127)p-=12;*vel=tv[i%k];return p|0x100u;
}
/* Once per audio block, n frames at 48 kHz; adapter passes legacy track 0. */
extern "C" __attribute__((used,retain)) void arp_block(u32 n,u32 track){
 ArpBlock *a=block();if(!a||!n||n>1024)return;ArpState *s=&a->state;
 u32 first=track<=s->last_track;s->last_track=track;if(!first)return; /* the first track the mixer processes in a block */
 s->block++;
 s->diag[0]=s->block;s->diag[4]=s->nroots;s->diag[5]=s->running;s->diag[6]=s->clock_block&&s->block-s->clock_block<=2;
 if(!(s->block&63u)){__asm__ volatile("dsb" ::: "memory");W((void*)0xe000ef68u,0)=(u32)s->diag;__asm__ volatile("dsb" ::: "memory");} /* M4 shows these */
 ArpMail *c=&s->cfg;
 if(c->magic!=ARP_MAGIC||!c->on){if(s->nroots||s->sounding)clear(s);s->track=c->track;return;}
 if(c->track!=s->track){clear(s);s->track=c->track;}
 u32 bpm=c->bpm>=20&&c->bpm<=300?c->bpm:120;
 /* ticks per frame = bpm*960/(60*48000) = bpm/3000; Q8 with remainder */
 u32 num=n*bpm*256u+(u32)s->frac,adv32=num/3000u;s->frac=num-adv32*3000u;i64 adv=adv32;
 int synced=s->clock_block&&s->block>=s->clock_block&&s->block-s->clock_block<=2;
 if(synced)s->pos=s->clock_pos+(i64)(s->block-s->clock_block)*adv;
 i64 grid=(i64)arp_rate_ticks[c->rate<ARP_RATES?c->rate:4]<<8,end=s->pos+adv;
 if(!s->nroots){stop(s);s->pos=end;return;}
 if(!s->running){s->running=1;s->step=0;s->next=synced?LDIV(s->pos+grid-1,grid)*grid:s->pos;}
 else if(synced&&(s->next<s->pos-grid||s->next>s->pos+2*grid))s->next=LDIV(s->pos+grid-1,grid)*grid; /* transport jump */
 for(u32 work=0;work<8;work++){
  if(s->sounding&&s->off_at<=s->next&&s->off_at<end){send(s,3,s->sounding&127u,0);s->sounding=0;}
  if(s->next>=end)break;
  if(s->sounding){send(s,3,s->sounding&127u,0);s->sounding=0;}
  u32 vel=100,p=pick(s,&vel);if(!p)break;send(s,2,p&127u,vel);s->sounding=p;
  u32 gate=c->gate<10?10:c->gate>100?100:c->gate;s->off_at=s->next+(i64)((u32)grid/100u*gate)-(gate==100?1:0);s->next+=grid;
 }
 if(s->sounding&&s->off_at<end){send(s,3,s->sounding&127u,0);s->sounding=0;}
 s->pos=end;
}
