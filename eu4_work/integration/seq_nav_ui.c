/* P16: native-style melodic tabs, selection, global Undo/settings access. */
#include "fx_shared.h"
#include "../../chord_work/device.h"
int chord_view_visible(void);void chord_view_set(int);
void piano_mode_set(void*,int);int piano_select_toggle(void*);int piano_selecting(void*);
#define PROJECTS 0x1062u
#define SETTINGS 0x1063u
#define DATETIME 0x1064u
int seq_nav_global(void *model,void *event){
 extern int perf_navigation(void*);if(perf_navigation(event))return 1;
 u32 code=H(event,0),page=code==PROJECTS?0x13:code==SETTINGS?0x1a:code==DATETIME?0x19:0;
 if(!page)return 0;
 FN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(model,page,0,0,1);return 1;
}
__attribute__((section(".pad3"))) int seq_nav_event(void *v,void *event){
 if(seq_nav_global(MODEL,event))return 1;
 u32 code=H(event,0);
 /* P22 (owner: no way out of the automation view). Chord/Euclid draw over
    the Step editor, so leave the native Automation tab (2) first. */
 if((code==0x1060||code==0x1061)&&B(v,0x125dac)==2){u32 e[5]={0x49,0,0,0,0};FN(0x0815a598,int(*)(void*,void*))(v,e);}
 if(code==0x1060){if(!chord_view_visible()){piano_mode_set(v,0);chord_view_set(1);FN(0x081599bc,void(*)(void*))(v);}return 1;}
 if(code==0x1061){chord_view_set(0);piano_mode_set(v,1);return 1;}
 {extern int chord_clear_current(void);if(code==0x4d&&chord_view_visible()&&chord_clear_current())return 1;} /* P24 (owner): Clear in chord mode = the whole selected chord */
 if(code==0x1051)return piano_select_toggle(v);
 {extern int piano_select_all(void*);if(code==0x1065)return piano_select_all(v);} /* W14 HW3 Select All */
 if(code==0x49||code==0x4a||code==0x4b){chord_view_set(0);piano_mode_set(v,0);return 0;}
 if(code==0x1059||code==0x107d){
  extern int piano_custom_view(void);
  u32 tab=B(v,0x125dac),next=code==0x1059?(tab==2?0x49u:0x4bu):(tab==0&&!piano_custom_view()?0x4au:0x49u);
  u32 e[5]={next,0,0,0,0};chord_view_set(0);piano_mode_set(v,0);FN(0x0815a598,int(*)(void*,void*))(v,e);return 1;
 }
 return 0;
}
__attribute__((section(".pad3"))) int piano_cycle_step(void){
 extern void *piano_current_view(void);void *v=piano_current_view();
 if(B(MODEL,0x12c)!=0x17||!v)return 0;
 u32 e[5]={0x107d,0,0,0,0};return seq_nav_event(v,e);
}
/* Rebuild F9 on every header apply. mode 0: native sequence actions;
 * 1: pitched SEQ (sequence actions, Automation, Chord Bank on the chord view);
 * 2 (P17, owner plan): the Performance page burger holds Projects, Settings and
 * Date / Time, and nothing else does. At most 9 cells. */
int chord_bank(void);
static void cells(u8 *menu,const u32 *keys,const char *const *names,u32 n){
 for(u32 i=0;i<n;i++){void *c=menu+4+i*20;for(u32 j=0;j<5;j++)W(c,j*4)=0;W(c,0)=keys[i];W(c,4)=(u32)names[i];W(c,16)=1;}B(menu,0xcc)=(u8)n;
}
static int ours(const u8 *menu,u32 n){
 if(!n)return 0;u32 first=W(menu,4),last=W(menu,4+(n-1)*20);
 return first==PROJECTS||first==0x100au||(first==0x1041u&&(last==0x1059u||last==0x1052u||last==0x1032u||last==DATETIME));
}
void seq_nav_menus(int mode){
 /* W14 HW3 (owner): Select All in every sequencer burger. */
 static const char *const seq_names[]={"Double Seq","Halve Seq","Cut Seq","Select All","Copy Seq","Paste Seq","Automation","Undo","Chord Bank 2","Chord Bank 1"};
 static const u32 seq_keys[]={0x1041,0x1042,0x102f,0x1065,0x102e,0x1030,0x1059,0x1032,0x1052,0x1052};
 static const char *const perf_names[]={"SD-card mode"};
 static const u32 perf_keys[]={0x100a};
 for(u32 m=0;m<20;m++){
  u8 *menu=(u8*)0x30030168u+m*0xe0;u32 n=B(menu,0xcc);if(n>9)continue;int f9=W(menu,0)==0xf9u;
  if(f9&&mode==1){
   cells(menu,seq_keys,seq_names,8);
   {extern void *piano_current_view(void);void *pv=piano_current_view();if(pv&&B(pv,0x125dac)==2)W(menu,4+6*20+4)=(u32)"Close Automation";} /* P22 */
   if(chord_view_visible()){u32 b=chord_bank()?9:8;void *c=menu+4+8*20;for(u32 j=0;j<5;j++)W(c,j*4)=0;W(c,0)=seq_keys[b];W(c,4)=(u32)seq_names[b];W(c,16)=1;B(menu,0xcc)=9;}
   continue;
  }
  if(W(menu,0)==0xf5u&&mode==2){
   static const u32 keys[]={0x1014,0x1013,0x1018,0x100a};
   static const char *const names[]={"Save As","New","Delete","SD-card mode"};
   cells(menu,keys,names,4);continue;
  }
  if(f9&&mode==2){cells(menu,perf_keys,perf_names,1);continue;}
  if(f9&&ours(menu,n)){
   static const u32 old[]={0x1041,0x1042,0x102f,0x1051,0x102e,0x1030,0x102c,0x102d,0x1032};
   static const char *const labels[]={"Double Seq","Halve Seq","Cut Seq","Select","Copy Seq","Paste Seq","Clear Seq","Clear Auto","Undo"};
   cells(menu,old,labels,9);
  }
  if(f9&&mode==0){
   n=B(menu,0xcc);int found=0;for(u32 i=0;i<n;i++)if(W(menu,4+i*20)==0x1032u)found=1;
   if(!found&&n<9){void *c=menu+4+n*20;for(u32 j=0;j<5;j++)W(c,j*4)=0;W(c,0)=0x1032;W(c,4)=(u32)"Undo";W(c,16)=1;B(menu,0xcc)=(u8)(n+1);}
   /* W14 HW3 (owner): the one-shot header keeps Select; its burger cell becomes Select All. */
   if(B(MODEL,0x12c)==0x27){n=B(menu,0xcc);for(u32 i=0;i<n&&i<9;i++)if(W(menu,4+i*20)==0x1051u){W(menu,4+i*20)=0x1065;W(menu,4+i*20+4)=(u32)"Select All";}}
  }
 }
}
void seq_nav_undo(void *model){
 extern void *piano_current_view(void);extern void *step_current_view(void);
 u32 e[5]={0x1032,W(model,0x144),0,0,0};void *v=0;
 if(B(model,0x12c)==0x17&&(v=piano_current_view()))FN(0x0815a598,int(*)(void*,void*))(v,e);
 else if(B(model,0x12c)==0x27&&(v=step_current_view()))FN(0x0815d600,int(*)(void*,void*))(v,e);
 else FN(0x081403ec,int(*)(void*,void*))(model,e);
}
