#include "fx_shared.h"

#define NOW W((void*)0x3001fe2cu,0)
typedef struct {
 u32 pending,stamp,page,seq,owner,context;
} Workflow;
void **workflow_state_slot(int);
int locks_touch_supported(void*);
int locks_touch(void*,int);
u32 locks_touch_context(void*);
static Workflow *state(int create){
 void **slot=workflow_state_slot(create);if(!slot)return 0;
 if(*slot)return *slot;if(!create)return 0;
 u32 p=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),n=(sizeof(Workflow)+31u)&~31u;
 if(p<0xc0000000u||end>0xc8000000u||p>end||end-p<n+32)return 0;
 Workflow *s=FN(0x08104c08,void*(*)(u32))(n);if((u32)s!=p)return 0;
 for(u32 i=0;i<sizeof(*s)/4;i++)((u32*)s)[i]=0;*slot=s;return s;
}
void workflow_periodic(void){
 Workflow *s=state(0);if(!s)return;
 if(!s->pending)return;
 if(s->page!=B(MODEL,0x12c)||s->seq!=W(MODEL,0x144)||s->owner!=W(MODEL,0x13c)||s->context!=locks_touch_context((void*)s->pending)){s->pending=0;return;}
 if(NOW-s->stamp>=300u){void *slot=(void*)s->pending;s->pending=0;locks_touch(slot,0);}
}
int workflow_lock_tap(void *slot){
 if(!locks_touch_supported(slot))return 0;
 Workflow *s=state(1);if(!s)return 1;
 if(s->pending&&(s->page!=B(MODEL,0x12c)||s->seq!=W(MODEL,0x144)||s->owner!=W(MODEL,0x13c)||s->context!=locks_touch_context((void*)s->pending)))s->pending=0;
 if(s->pending==(u32)slot&&NOW-s->stamp<300u){
  s->pending=0;return locks_touch(slot,1);
 }
 if(s->pending){void *prior=(void*)s->pending;s->pending=0;locks_touch(prior,0);}
 s->pending=(u32)slot;s->stamp=NOW;s->page=B(MODEL,0x12c);s->seq=W(MODEL,0x144);s->owner=W(MODEL,0x13c);s->context=locks_touch_context(slot);return 1;
}
void workflow_nav(void){extern void pg_tracks_nav(void);pg_tracks_nav();Workflow *s=state(0);if(s)s->pending=0;}
