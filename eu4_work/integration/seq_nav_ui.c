#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
/* P16: native-style melodic tabs, selection, global Undo/settings access. */
#include "fx_shared.h"
#include "kit_seq.h"
#include "../../chord_work/device.h"
int chord_view_visible(void);void chord_view_set(int);
void piano_mode_set(void*,int);int piano_select_toggle(void*);int piano_selecting(void*);
#define PROJECTS 0x1062u
#define SETTINGS 0x1063u
#define DATETIME 0x1064u
/* R6 burger actions, routed once from the model to the visible editor:
   1086 Clear (piano: the former footer Clear 4D; one-shot: Clear 102C, which
   clears only selected steps when there are any), 1085 Select None. */
void *piano_current_view(void);void *step_current_view(void);
static int nav_menu_action(u32 code){
 if(code!=0x1085u&&code!=0x1086u)return 0;
 u32 page=B(MODEL,0x12c);
 if(page==0x17){void *v=piano_current_view();if(!v)return 1;
  if(code==0x1085u){extern int piano_select_none(void*);piano_select_none(v);return 1;}
  u32 e[5]={0x4d,W(MODEL,0x144),0,0,0};NFN(0x0815a598,int(*)(void*,void*))(v,e);return 1;}
 if(page==0x27){void *v=step_current_view();if(!v)return 1;
  u32 e[5]={code==0x1085u?0x1085u:NUI(0x102cu),0,0,0,0};NFN(0x0815d600,int(*)(void*,void*))(v,e);return 1;}
 return 1;
}
__attribute__((section(".steptext"))) int seq_nav_global(void *model,void *event){
 if(kit_seq_event(0,event))return 1;
#ifdef BENTO_SYNCUSSION
 extern int drum_panel_navigation(void*,void*);if(drum_panel_navigation(model,event))return 1;
#endif
 extern int native_fx_event(void*,void*);if(native_fx_event(model,event))return 1;
 extern int oneshot_event(void*);if(oneshot_event(event))return 1; /* run 18: one-shot Pad -> Kit */
 extern int perf_navigation(void*);if(perf_navigation(event))return 1;
 extern int nav_event(void*);if(nav_event(event))return 1;
 if(nav_menu_action(H(event,0)))return 1;
 u32 code=H(event,0),page=code==PROJECTS?0x13:code==SETTINGS?0x1a:code==DATETIME?0x19:0;
 if(!page)return 0;
 NFN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(model,page,0,0,1);return 1;
}
__attribute__((section(".pad3"))) int seq_nav_event(void *v,void *event){
 if(seq_nav_global(MODEL,event))return 1;
 u32 code=H(event,0);
 /* P22 (owner: no way out of the automation view). Chord/Euclid draw over
    the Step editor, so leave the native Automation tab (2) first. */
#ifdef BENTO_NO_CHORD_EDITOR
 if(code==0x1061&&B(v,0x125dac)==2){u32 e[5]={0x49,0,0,0,0};NFN(0x0815a598,int(*)(void*,void*))(v,e);}
#else
 if((code==0x1060||code==0x1061)&&B(v,0x125dac)==2){u32 e[5]={0x49,0,0,0,0};NFN(0x0815a598,int(*)(void*,void*))(v,e);}
#endif
#ifndef BENTO_NO_CHORD_EDITOR /* exp8 build switch: no Chord view */
 if(code==0x1060){if(!chord_view_visible()){piano_mode_set(v,0);chord_view_set(1);NFN(0x081599bc,void(*)(void*))(v);}return 1;}
#endif
 if(code==0x1061){chord_view_set(0);piano_mode_set(v,1);return 1;}
 {extern int chord_clear_current(void);if(code==0x4d&&chord_view_visible()&&chord_clear_current())return 1;} /* P24 (owner): Clear in chord mode = the whole selected chord */
 if(code==0x1051)return piano_select_toggle(v);
 {extern int piano_select_all(void*);if(code==0x1065)return piano_select_all(v);} /* W14 HW3 Select All */
 if(code==0x49||code==0x4a||code==0x4b){chord_view_set(0);piano_mode_set(v,0);return 0;}
 return 0;
}
/* Rebuild F9 on every header apply. mode 0: native sequence actions;
 * 1: pitched SEQ (sequence actions, Automation, Chord Bank on the chord view);
 * 2 (P17, owner plan): the Performance page burger holds Projects, Settings and
 * Date / Time, and nothing else does. At most 9 cells. */
int chord_bank(void);
static __attribute__((noinline,section(".steptext"))) void cells(u8 *menu,const u32 *keys,const char *const *names,u32 n){ /* R6.10: .text full */
 for(u32 i=0;i<n;i++){void *c=menu+4+i*20;for(u32 j=0;j<5;j++)W(c,j*4)=0;W(c,0)=keys[i];W(c,4)=(u32)names[i];W(c,16)=1;}B(menu,0xcc)=(u8)n;
}
void seq_nav_menus(int mode){
 /* R6 (owner spec): one burger for every sequencer, F9 (page 17) and FA
    (page 27): Double, Halve, Cut, Copy, Paste, Clear, Clear Auto,
    Select All / Select None, Undo. Chord view: Chord Bank replaces Clear Auto. */
 static const char *const seq_names[]={"Double Seq","Halve Seq","Cut Seq","Copy Seq","Paste Seq","Clear","Clear Auto","Select All","Undo"};
 static const u32 seq_keys[]={NUI(0x1041),NUI(0x1042),NUI(0x102f),NUI(0x102e),NUI(0x1030),0x1086,NUI(0x102d),0x1065,NUI(0x1032)};
 static const char *const perf_names[]={"Projects","Settings","SD-card mode"};
 static const u32 perf_keys[]={PROJECTS,SETTINGS,NUI(0x101d)}; /* R6.7: native SD-card menu key (stock menus 0814FC68/08150026/08150542); 100A was unhandled */
 u32 page=B(MODEL,0x12c),id=page==0x27?0xfau:0xf9u;int any=0;
 if(mode==1){
  if(page==0x17){void *v=piano_current_view();any=v&&(int)W((u8*)v+0x38,0x1254)>0;} /* native selected-note count */
  else{extern int seq_any_selected(void);any=seq_any_selected();}
 }
 for(u32 m=0;m<20;m++){
  u8 *menu=(u8*)0x30030168u+m*0xe0;u32 n=B(menu,0xcc);if(n>10)continue;u32 mid=W(menu,0);
  if(mode==1&&mid==id){
   cells(menu,seq_keys,seq_names,9);
   if(any){W(menu,4+7*20)=0x1085;W(menu,8+7*20)=(u32)"Select None";}
   if(page==0x17&&chord_view_visible()){W(menu,4+6*20)=0x1052;W(menu,8+6*20)=(u32)(chord_bank()?"Chord Bank 1":"Chord Bank 2");}
   continue;
  }
  if(mid==0xf4u&&n>2&&!W(menu,4+2*20)){W(menu,4+2*20)=0x3f;W(menu,8+2*20)=(u32)"Load";W(menu,20+2*20)=1;continue;} /* run 18: bank burger Load (native 3F, the empty cell) */
  if(mid==0xf5u&&mode==2){
   static const u32 keys[]={NUI(0x1014),NUI(0x1013),NUI(0x1018),PROJECTS,SETTINGS,NUI(0x101d)};
   static const char *const names[]={"Save As","New","Delete","Projects","Settings","SD-card mode"};
   cells(menu,keys,names,6);continue;
  }
  /* R6.10 (owner: Seq burger on the Proj page): F9 is the stock burger of the
     Proj/Settings/Perform pages too; outside the sequencers it gets its stock
     entries back (Projects, Settings, SD-card mode). */
  if(mid==0xf9u&&mode!=1&&!(B(menu,0xcc)==3&&W(menu,4)==PROJECTS&&W(menu,24)==SETTINGS&&W(menu,44)==NUI(0x101du)))cells(menu,perf_keys,perf_names,3);
 }
}
/* R5 (owner: the piano-roll burger showed Projects/Settings/SD-card mode on
 * the device). F9 is one native menu shared by the piano roll and the
 * Performance page; the header-apply rewrite evidently does not run on every
 * device path. Re-assert the page's contents on every UI message as well. */
__attribute__((section(".stepnote"))) int burger_mode(void){
 extern int perf_page_active(void);u32 page=B(MODEL,0x12c);
 return (page==0x1a||page==0x13)&&perf_page_active()?2:page==0x17||page==0x27?1:0;
}
/* P168 exp3 (owner: the SEQ burger showed the PROJ burger): the native header binds a
 * menu's cells to the popup only when the menu INDEX differs from the one it bound last
 * (root +FE0, 0817FFF8: ldrsh [root,#FE0]; cmp; bne bind -> 0817818C copies the cells).
 * F9 is shared by the Perform page and the sequencers and is rewritten per page, so a
 * second opening of F9 showed the cells of the first. Forget the bound index whenever
 * the menus are (re)written: the next opening binds the current cells. Native code in
 * both firmware versions; nothing happens while a popup is open (binding runs on open). */
__attribute__((section(".stepstrings"))) void seq_nav_menus_tick(void){
 seq_nav_menus(burger_mode());
 if(W((void*)0x30034d48u,0)==0x081b3680u)H((void*)0x30034d48u,NOFF_ROOT(0xfe0u))=0xffffu;
}
void seq_nav_undo(void *model){
 extern void *piano_current_view(void);extern void *step_current_view(void);
 u32 e[5]={NUI(0x1032),W(model,0x144),0,0,0};void *v=0;
 if(B(model,0x12c)==0x17&&(v=piano_current_view()))NFN(0x0815a598,int(*)(void*,void*))(v,e);
 else if(B(model,0x12c)==0x27&&(v=step_current_view()))NFN(0x0815d600,int(*)(void*,void*))(v,e);
 else NFN(0x081403ec,int(*)(void*,void*))(model,e);
}
