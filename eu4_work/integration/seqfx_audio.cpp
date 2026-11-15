/* R6.6 Berlin-school transpose, audio core (M7). Owner decisions:
 * project doc claude/Bento_R6_6_Plan_2026-11-07.md.
 *
 * - tr_press/tr_release sit between the CH6 pad-module post sites and
 *   chord_press/chord_release. While the selected track's Transpose is On
 *   (TrBlock.armed), a keyboard pad press only sets that track's offset (from
 *   the pad's pitch to the lowest root pad, chromatic or diatonic) and is not
 *   posted; its release is swallowed too.
 * - tr_note_pitch runs at the entry of the native "sequence plays a note"
 *   0805F8E0 (sequencer and Euclid). A note of a transposing track plays at the
 *   shifted pitch; the pair is remembered so the native note-off 0805FE00
 *   (tr_off_pitch) releases the pitch that actually sounds, even if the
 *   offset changed while the note was held.
 * Lives in the checked zero cave 080D08B0..080D1000. No allocation, bounded. */
#define _Static_assert static_assert
#include "arp_shared.h"
#include "seqfx_shared.h"
static void invalidate(u32 a,u32 n){__asm__ volatile("dsb" ::: "memory");if(W((void*)0xe000ed14u,0)&(1u<<16))for(u32 end=a+n;a<end;a+=32)W((void*)0xe000ef5cu,0)=a;__asm__ volatile("dsb" ::: "memory");}
static void clean(u32 a,u32 n){__asm__ volatile("dsb" ::: "memory");if(W((void*)0xe000ed14u,0)&(1u<<16))for(u32 end=a+n;a<end;a+=32)W((void*)0xe000ef68u,0)=a;__asm__ volatile("dsb" ::: "memory");}
static TrBlock *block(){
 invalidate(EU_CONTROL_ADDR,32);if(EC->magic!=EU_MAGIC||EC->bytes!=sizeof(EuBank)||!eu_memory(EC->pointer,sizeof(EuBank)))return 0;
 EuBank *b=(EuBank*)EC->pointer;invalidate((u32)b,32);if(!b->serial||(b->serial&1))return 0;
 u32 a=b->reserved[3];if(!eu_memory(a,sizeof(ArpBlock)))return 0;invalidate(a,64);
 u32 p=((ArpBlock*)a)->mail.spare[6];if(!eu_memory(p,sizeof(TrBlock)))return 0;
 invalidate(p,96);TrBlock *t=(TrBlock*)p;return t->magic==TR_MAGIC?t:0;
}
#define TR_DATA(t) ((u32)&(t)->off)
#define TR_DATA_BYTES (sizeof(TrBlock)-(u32)((u8*)&((TrBlock*)0)->off-(u8*)0))
extern "C" __attribute__((used,retain)) int tr_press(void *router,u32 *rec,u32 pad,u32 slot){
 TrBlock *t=block();u32 p=rec?rec[3]:128;(void)router;
 if(!t||!t->armed||t->armed>TR_TRACKS||p>127)return 0;
 u32 i=t->armed-1;int off;
 if(t->mode[i]){off=tr_degree(t,(int)p,0)-tr_degree(t,(int)t->base,0);}
 else off=(int)p-(int)t->base;
 if(off<-48)off=-48;if(off>48)off=48;
 /* R6.10 (owner: transposed but the pad did not light): the swallowed press
    never reached chord_start's P21 publish, so the M4 knew no pitch for that
    pad. Publish it the same way, before offserial tells the M4 to redraw. */
 if(!slot&&pad<16){EuBank *b=(EuBank*)EC->pointer;ChordPub *pp=&b->chord_pub;pp->pitch[pad]=(u8)(0x80|p);pp->serial+=2;clean((u32)pp,32);}
 if(!slot){t->off[i]=(signed char)off;t->offserial++;}
 t->held[p>>5]|=1u<<(p&31);clean(TR_DATA(t),TR_DATA_BYTES);return 1;
}
extern "C" __attribute__((used,retain)) int tr_release(void *router,u32 *rec,u32 slot){
 TrBlock *t=block();u32 p=rec?rec[3]:128;(void)router;(void)slot;
 if(!t||p>127||!(t->held[p>>5]&(1u<<(p&31))))return 0;
 if(!slot)t->held[p>>5]&=~(1u<<(p&31));clean(TR_DATA(t),TR_DATA_BYTES);return 1;
}
extern "C" __attribute__((used,retain)) u32 tr_note_pitch(void *s,u32 pitch){
 if(!s||!pitch||pitch>127)return pitch;TrBlock *t=block();if(!t)return pitch;
 u32 owner=W(s,12);for(u32 i=0;i<TR_TRACKS;i++)if(t->owner[i]==owner&&owner){
  if(!t->on[i]&&!t->off[i])return pitch;
  int q=tr_apply(t,(int)pitch,t->on[i]?t->off[i]:0,t->mode[i]);if(q<1)q=1;if(q>127)q=127;
  if((u32)q!=pitch){TrMap *free_=0;for(u32 k=0;k<TR_MAP;k++){TrMap *m=&t->map[k];if(m->used&&m->seq==(u32)s&&m->from==pitch){free_=m;break;}if(!m->used&&!free_)free_=m;}
   if(free_){free_->seq=(u32)s;free_->from=(u8)pitch;free_->to=(u8)q;free_->used=1;clean((u32)free_&~31u,64);}}
  return (u32)q;
 }
 return pitch;
}
extern "C" __attribute__((used,retain)) u32 tr_off_pitch(void *s,u32 pitch){
 if(!s||!pitch||pitch>127)return pitch;TrBlock *t=block();if(!t)return pitch;
 for(u32 k=0;k<TR_MAP;k++){TrMap *m=&t->map[k];if(m->used&&m->seq==(u32)s&&m->from==pitch){u32 q=m->to;m->used=0;clean((u32)m&~31u,64);return q;}}
 return pitch;
}
