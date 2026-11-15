#include "fx_shared.h"
#include "kit_seq.h"
#include "ui_native.h"

#define NOW W((void*)0x3001fe2cu,0)
typedef struct {
 u32 pending,stamp,page,seq,owner,context;
 void *kit_seq;
 /* R6 navigation (owner spec 6 Nov): last view per melodic track and per
    one-shot pad, and a view to apply once the target page exists. */
 u32 nav_project,nav_want,nav_stamp,nav_seq_press;
 u8 nav_track[8+128+8];
 unsigned short inst_tab[10]; /* R6.3: [9] = INST home page of this visit. R6.2: last INST footer tab per track; [8] = MIXER/INST press page. Follows nav_track: reset together. */ /* [0..7] per track, [8..135] per track x pad, [136..143] last pad */
#define NAV_PAD(s,t,p) (s)->nav_track[8+(t)*16+(p)]
#define NAV_LAST(s,t) (s)->nav_track[136+(t)]
} Workflow;
void **workflow_state_slot(int);
int locks_touch_supported(void*);
int locks_touch(void*,int);
u32 locks_touch_context(void*);
static Workflow *state(int create){
 void **slot=workflow_state_slot(create);if(!slot)return 0;
 if(*slot)return *slot;if(!create)return 0;
 u32 n=(sizeof(Workflow)+31u)&~31u;Workflow *s=(void*)ui_alloc(n,n+32);if(!s)return 0;
 for(u32 i=0;i<sizeof(*s)/4;i++)((u32*)s)[i]=0;*slot=s;return s;
}
void **kit_seq_state_slot(int create){Workflow *s=state(create);return s?&s->kit_seq:0;}
static u32 touch_context(void *slot){u32 c=kit_seq_touch_context(slot);return c?c:locks_touch_context(slot);}
static int touch(void *slot,int twice){return kit_seq_touch(slot,twice)||locks_touch(slot,twice);}
void nav_tick(void);
/* R6.11 bank-1 proof: runs on every UI header tick from boot, so an M4 that
   cannot execute flash bank 1 faults at once (owner hardware check). */
__attribute__((section(".text.bank1a"))) void workflow_periodic(void){
 kit_seq_periodic();nav_tick();
 {extern void chord_track_tick(void) __attribute__((weak));extern void tr_tick(void) __attribute__((weak));if(chord_track_tick)chord_track_tick();if(tr_tick)tr_tick();} /* weak: partial test builds */ /* R6.6 (owner: chord pads stayed): page changes are seen here, not only on button messages */
 Workflow *s=state(0);if(!s)return;
 if(!s->pending)return;
 if(s->page!=B(MODEL,0x12c)||s->seq!=W(MODEL,0x144)||s->owner!=W(MODEL,0x13c)||s->context!=touch_context((void*)s->pending)){s->pending=0;return;}
 if(NOW-s->stamp>=300u){void *slot=(void*)s->pending;s->pending=0;touch(slot,0);}
}
int workflow_lock_tap(void *slot){
 if(!touch_context(slot))return 0;
 Workflow *s=state(1);if(!s)return 1;
 if(s->pending&&(s->page!=B(MODEL,0x12c)||s->seq!=W(MODEL,0x144)||s->owner!=W(MODEL,0x13c)||s->context!=touch_context((void*)s->pending)))s->pending=0;
 if(s->pending==(u32)slot&&NOW-s->stamp<300u){
  s->pending=0;return touch(slot,1);
 }
 if(s->pending){void *prior=(void*)s->pending;s->pending=0;touch(prior,0);}
 s->pending=(u32)slot;s->stamp=NOW;s->page=B(MODEL,0x12c);s->seq=W(MODEL,0x144);s->owner=W(MODEL,0x13c);s->context=touch_context(slot);return 1;
}
__attribute__((section(".bankstate"))) void workflow_nav(void){kit_seq_nav();extern void pg_tracks_nav(void);pg_tracks_nav();Workflow *s=state(0);if(s)s->pending=0;}

/* ---- R6 navigation -------------------------------------------------------
 * Views: 1 Euclid, 2 Steps, 3 Piano, 4 Auto, 5 Chord, 6 melodic Euclid.
 * One-shot: Euclid/Steps/Piano are the native SEQ page 27 (Euclid tab, drum
 * Step/Sequence flag +113E0); Auto is the native piano page 17 Automation tab.
 * Melodic (page 17): tabs 49/4A/4B, Chord 1060, Euclid 1061.
 * SEQ: first press opens the remembered view (default Euclid / Steps); further
 * presses cycle Euclid->Steps->Piano (one-shot) or Steps->Piano->Auto
 * (melodic); off-cycle views re-enter at the first cycle view. */
enum{V_EU=1,V_STEPS,V_PIANO,V_AUTO,V_CHORD,V_MEU,V_REMEMBER};
void *step_current_view(void);void *piano_current_view(void);int piano_one_shot(void*);
int seq_eu_mode(void*);int seq_eu_tab(void*);int chord_view_visible(void);int piano_custom_view(void);int seq_nav_event(void*,void*);
__attribute__((noinline,section(".pad"))) u32 nav_track_index(void){u32 t=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)MODEL+4,0x131);return t<8?t:0;}
__attribute__((noinline)) int nav_one_shot(void){ /* the page decides: 27 is one-shot only; on 17 the view knows its owner */
 u32 page=B(MODEL,0x12c);if(page==0x27)return 1;if(page==0x17){void *v=piano_current_view();if(v)return piano_one_shot(v);} /* R6.4: unknown view: the track decides */
 u32 o=0;return ui_owner(&o)&&o&&ui_type(&o)==14;}
static u32 nav_current(void){
 u32 page=B(MODEL,0x12c);
 if(page==0x27){void *v=step_current_view();if(!v)return 0;return seq_eu_mode(v)?V_EU:B(v,0x113e0)?V_PIANO:V_STEPS;}
 if(page==0x17){void *v=piano_current_view();
  /* R6.4 (owner: one-shot Auto <-> Seq loop, Auto not lit): a one-shot track's
     only view on page 17 is Auto, whether or not its view is known yet. */
  if(!v)return nav_one_shot()?V_AUTO:0;u32 tab=B(v,0x125dac);
  if(piano_one_shot(v))return V_AUTO; /* R6.5 (owner: Auto stripes flicker): a one-shot's only view on page 17 */
  if(chord_view_visible())return V_CHORD;if(piano_custom_view())return V_MEU;return tab==0?V_STEPS:tab==1?V_PIANO:V_AUTO;}
 return 0;
}
static __attribute__((noinline,section(".cycleundo"))) void nav_go(Workflow *s,u32 page,u32 want){s->nav_want=want;s->nav_stamp=NOW;NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(MODEL,page,0,0,0);}
static void nav_show(Workflow *s,u32 want){
 u32 page=B(MODEL,0x12c);
 if(nav_one_shot()){
  if(want==V_AUTO){
   if(page!=0x17){nav_go(s,0x17,V_AUTO);return;}
   void *v=piano_current_view();if(!v){s->nav_want=V_AUTO;s->nav_stamp=NOW;return;}
   u32 e[5]={0x4b,0,0,0,0};NFN(0x0815a598,int(*)(void*,void*))(v,e);return;
  }
  if(page!=0x27){nav_go(s,0x27,want);return;}
  void *v=step_current_view();if(!v){s->nav_want=want;s->nav_stamp=NOW;return;}
  if(want==V_EU){if(!seq_eu_mode(v))seq_eu_tab(v);return;}
  u32 e[5]={want==V_PIANO?0x4au:0x49u,0,0,0,0};NFN(0x0815d600,int(*)(void*,void*))(v,e);return;
 }
 if(page!=0x17)return;
 void *v=piano_current_view();if(!v){s->nav_want=want;s->nav_stamp=NOW;return;}
 static const u16 codes[]={0x49,0x4a,0x4b,0x1060,0x1061};
 u32 e[5]={want>=V_STEPS&&want<=V_MEU?codes[want-V_STEPS]:0x49u,0,0,0,0};
 if(!seq_nav_event(v,e))NFN(0x0815a598,int(*)(void*,void*))(v,e);
}
static u32 nav_remembered(Workflow *s){
 u32 t=nav_track_index();
 if(nav_one_shot()){void *v=step_current_view();u32 pad=v&&W(v,0x11400)<16?W(v,0x11400):NAV_LAST(s,t)&15u;u32 w=NAV_PAD(s,t,pad);return w?w:V_STEPS;} /* P168 exp3 (owner): a pad opens on Steps until another view was chosen for it (was Euclid) */
 return s->nav_track[t]?s->nav_track[t]:V_STEPS;
}
void nav_tick(void){
 Workflow *s=state(0);if(!s)return;
 if(s->nav_project!=W(MODEL,0)){s->nav_project=W(MODEL,0);for(u32 i=0;i<8+128+8+20;i++)s->nav_track[i]=0;} /* all view memory incl. inst_tab */
 u32 page=B(MODEL,0x12c);if(page!=0x27&&page!=0x17)return; /* no work off the sequencer pages */
 if(s->nav_want){ /* a pending restore wins over recording the native default view */
  if(NOW-s->nav_stamp>1500u){s->nav_want=0;return;}
  if(page==0x27?!step_current_view():!piano_current_view())return;
  u32 want=s->nav_want;if(want==V_REMEMBER){want=nav_remembered(s);s->nav_want=want;}
  /* R6.4: keep restoring until the view is really shown (a page change can
     rebuild the view after the first attempt); never navigate again here. */
  u32 cur=nav_current();
  if(want==V_AUTO&&page==0x17){void *pv=piano_current_view();if(pv&&B(pv,0x125dac)!=2)cur=0;} /* Auto counts as reached only on the real tab */
  if(want==cur){s->nav_want=0;return;}
  if(!nav_one_shot()){s->nav_want=0;nav_show(s,want);return;} /* melodic: once, as before (Chord toggles) */
  /* Retry only shortly after the page change, so a later user choice wins. */
  if(NOW-s->nav_stamp<400u&&(want==V_AUTO)==(page==0x17)){nav_show(s,want);if(want!=V_AUTO&&nav_current()==want)s->nav_want=0;}
  return;
 }
 u32 cur=nav_current();
 if(cur){u32 t=nav_track_index();
  if(nav_one_shot()){void *v=step_current_view();u32 pad=page==0x27&&v&&W(v,0x11400)<16?W(v,0x11400):NAV_LAST(s,t)&15u;NAV_LAST(s,t)=(u8)pad;NAV_PAD(s,t,pad)=(u8)cur;}
  else s->nav_track[t]=(u8)cur;
 }
}
/* SEQ button (index 11). Returns 1 when the press is consumed. */
int nav_seq_button(u32 code){
 Workflow *s=state(1);if(!s)return 0;
 if(code==0xb0){u32 c=s->nav_seq_press;s->nav_seq_press=0;return (int)c;}
 if(W((void*)0x24048d60u,8))return 0;
 u32 cur=nav_current();
 if(!cur){s->nav_want=V_REMEMBER;s->nav_stamp=NOW;s->nav_seq_press=0;return 0;} /* native opens the sequencer */
 u32 next;
 /* R6.3 (owner): the button cycles through every view. */
 if(nav_one_shot())next=cur==V_EU?V_STEPS:cur==V_STEPS?V_PIANO:cur==V_PIANO?V_AUTO:V_EU;
#ifdef BENTO_NO_CHORD_EDITOR
 else next=cur==V_STEPS?V_PIANO:cur==V_PIANO?V_AUTO:cur==V_AUTO?V_MEU:V_STEPS; /* exp8 switch: no Chord view */
#else
 else next=cur==V_STEPS?V_PIANO:cur==V_PIANO?V_AUTO:cur==V_AUTO?V_CHORD:cur==V_CHORD?V_MEU:V_STEPS;
#endif
 s->nav_seq_press=1;s->nav_want=0;nav_show(s,next);return 1; /* R6.4: a press cancels a pending restore */
}
unsigned nav_view(void){return nav_current();}
unsigned short *nav_inst_tabs(void){Workflow *s=state(1);return s?s->inst_tab:0;}
/* Footer buttons that cross between the one-shot pages (1081..1084). */
int nav_event(void *event){
 u32 code=H(event,0);if(code<0x1081u||code>0x1084u)return 0;
 Workflow *s=state(1);if(s){s->nav_want=0;nav_show(s,code-0x1080u);}return 1;
}
