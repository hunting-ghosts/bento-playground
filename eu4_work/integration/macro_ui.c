/* P27/P28 performance macros (M4). Owner decisions: docs/releases/p27/PLAN.md
 * (P29 section: back to the P27 swipe left/right; armed indicator).
 *
 * Eight macros, each with up to three targets (any parameter that is on an
 * encoder somewhere). A macro sets its targets directly, like turning their
 * knobs, moving each target relatively from its current native value through
 * its configured Min/Max range.
 *
 * Native facts (stock 1.6.1, see docs/releases/p27/DESIGN.md):
 *  - Encoder strip = widget class vtable 081B2838 ("bar"); its eight slots are
 *    children at bar+38+468*i, parent pointer +2C, hidden flag +30. Its touch
 *    slots [4..6] are empty stubs and [7] ("takes touches") returns 0, so no
 *    native code reacts to touches on the strip. P27 makes [7] return 1 and
 *    handles down/move/up here.
 *  - Every encoder turn reaches 08171E44(slot, delta) through K15's
 *    kick_ui_increment (delta returned there). Delta 0 changes nothing.
 *  - Slot: +34 node handle, +9C key, +A0 last value, +450/+454 range,
 *    name label widget +3C8 (text +3F9, setter 0817E85E; +A8/+D9 is the value label), value text override
 *    08170656(bar, i, text) (0 = native text).
 *  - Hit test 0816FA10 style: vtable +28 (obj, point, &out); children +18,
 *    next sibling +20; vtable +10/+18 = touch down/up (obj, point, id). */
#include "fx_shared.h"
#include "macro_display.h"
int perf_macro_view(void);
#define BAR_VT 0x081b2838u
#define MACRO_MAGIC 0x4f52434du
#define NOW W((void*)0x3001fe2cu,0)
#define MACRO_TARGETS 3u
#define MACRO_HEX_BYTES (2u*(1u+8u*(15u+MACRO_TARGETS*33u))+1u)
#define MACRO_ROWS 2u
#define RANGE_STEP 160000 /* a full macro sweep; a full Min/Max sweep matches it */
#define SENS_STEP 10000   /* eight macro steps per Sensitivity step (feel unverified on hardware) */
/* G5 (owner): a target remembers the parameter name it was mapped from. The
 * name comes off the encoder slot at mapping time, because the page that owns
 * the parameter is usually not on screen when the target list is read back. */
typedef struct {u8 track,c1,c2,used;u16 key,pad;int lo,hi,min,max;u32 handle;char name[12];} Target;
/* Owner, 29 Oct (W14 HW4): a tap selects a macro and toggles map mode (a tap
 * on the armed macro ends it, PROJ too); a double tap clears all its mappings.
 * While armed a tap on a parameter maps it (full range), a double tap on it
 * unmaps it; encoders never map. A double tap on one binding on the Macro
 * page removes only that binding. On the Performance
 * page's Macro view, Up/Down switches between the amount overview and target
 * controls. The swipe that showed macros on other pages is gone. */
typedef struct {
 u32 magic,overlay,bar,live,live_tick,armed,bar_tick; /* armed = macro index + 1; bar = strip showing macros (kept), live = last visible strip ticked */
 u8 value[8],count[8];Target t[8][MACRO_TARGETS];
 char name[8][12];
 char backup[MACRO_ROWS][8][32];u32 backup_bar[MACRO_ROWS];
 u32 row_bar[MACRO_ROWS],row_seen[MACRO_ROWS]; /* the page's strips, topmost row first */
 int down,x0,y0,x,y,applying;u32 down_tick,routed_bar,under; /* one finger on a strip */
 char flash[16];u32 flash_until;
 u32 last_tap,last_tap_tick; /* macro index + 1 of the previous macro tap, for the arming double tap */
 signed char sens[8]; /* -2..2 = 1/4x..4x, 0 = Normal */
 u32 acc_slot;long long acc; /* Macro tab: partial turns of the edited slot */
 u32 project,loaded;long long frac[8];
 long long relative[8][MACRO_TARGETS];
 u32 hex_full; /* G5: a save that would not fit is dropped, never truncated */
 char *rejected; /* Unsupported data is preserved verbatim, never partly applied. */
 u32 rejected_active,rejected_bytes;
 char hex[MACRO_HEX_BYTES];
 u32 tap_handle,tap_key,tap_tick,bind_tap,bind_tick; /* W14 HW4: parameter / binding double taps */
} Macro;
void **macro_state_slot(void);
void **macro_existing_slot(void);
int macro_preservation_fault(int);
static void zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static Macro *state(int create){
 void **slot=create?macro_state_slot():macro_existing_slot();if(!slot)return 0;Macro *s=*slot;
 if(s)return s->magic==MACRO_MAGIC?s:0;if(!create)return 0;
 u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),bytes=(sizeof(Macro)+31u)&~31u;
 if(cursor<0xc0000000u||end>0xc8000000u||cursor>end||end-cursor<bytes+32)return 0;
 s=FN(0x08104c08,void*(*)(u32))(bytes);if((u32)s!=cursor)return 0;zero(s,sizeof(*s));s->magic=MACRO_MAGIC;
 if(macro_preservation_fault(-1)){s->rejected_active=3;s->loaded=1;}
 *slot=s;return s;
}
static int is_bar(u32 b){return b>=0x20000000u&&b<0xc8000000u&&W((void*)b,0)==BAR_VT;}
static void *slot_of(u32 bar,u32 i){return (u8*)bar+0x38+i*0x468;}
static int slot_index(void *slot,u32 *bar){
 u32 b=W(slot,0x2c);if(!is_bar(b))return -1;u32 off=(u32)slot-b-0x38;if(off%0x468||off/0x468>7)return -1;*bar=b;return (int)(off/0x468);
}
static int get(u32 h,u32 key,int *out){return h&&FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,key,out);}
static u32 settings(void){u32 h=0;return FN(0x08133e54,int(*)(void*,u32*))(MODEL,&h)?h:0;}
static u32 track_handle(u32 t){u32 h=0;return FN(0x08133960,int(*)(void*,u32,u32*))(MODEL,t,&h)?h:0;}
static u32 child_handle(u32 owner,u32 j){u32 c=0;return owner&&FN(0x0813391a,int(*)(void*,void*,u32,void*))(MODEL,&owner,j,&c)?c:0;}
static void post(Target *t,u32 h,int value){
 u32 code=0xcf;
 /* Native D0 (08131918) searches only direct children of synth tracks;
  * CF (0813BFB0) writes other nodes and addresses their own audio handle. */
 if(t->track<16&&t->c1!=0xff&&t->c2==0xff){
  u32 owner=track_handle(t->track);
  u32 type=owner?FN(0x08133f7c,u32(*)(void*,u32*))(MODEL,&owner):0;
  if(type==18||type==19)code=0xd0;
 }
 u32 ev[5]={code,h,t->key,(u32)value,0};
 FN(0x081403ec,int(*)(void*,void*))(MODEL,ev);
}
/* Targets are kept as a path that survives project reload: track, child,
 * grandchild (0xFF = none); track 0xFE = project settings node. */
static int locate(u32 h,Target *t){
 if(h==settings()){t->track=0xfe;t->c1=t->c2=0xff;return 1;}
 for(u32 i=0;i<16;i++){u32 tr=track_handle(i);if(!tr)continue;
  if(tr==h){t->track=(u8)i;t->c1=t->c2=0xff;return 1;}
  for(u32 j=0;j<64;j++){u32 c=child_handle(tr,j);if(!c)break;
   if(c==h){t->track=(u8)i;t->c1=(u8)j;t->c2=0xff;return 1;}
   for(u32 k=0;k<64;k++){u32 g=child_handle(c,k);if(!g)break;if(g==h){t->track=(u8)i;t->c1=(u8)j;t->c2=(u8)k;return 1;}}
  }
 }
 return 0;
}
static u32 resolve(Target *t){
 u32 h=t->track==0xfe?settings():t->track<16?track_handle(t->track):0;
 if(h&&t->c1!=0xff)h=child_handle(h,t->c1);if(h&&t->c2!=0xff)h=child_handle(h,t->c2);
 return h;
}
int macro_snapshot(u32 m,MacroDisplay *out){
 if(m>=8||!out)return 0;zero(out,sizeof(*out));
 out->sensitivity=2;
 Macro *s=state(0);if(!s){out->rejected=macro_preservation_fault(-1)?3:0;return 1;}
 out->value=s->value[m];out->count=s->rejected_active?0:s->count[m];out->armed=s->armed==m+1;out->rejected=s->rejected_active;out->sensitivity=(unsigned)(s->sens[m]+2);
 for(u32 i=0;i<out->count;i++){
  Target *t=&s->t[m][i];MacroTargetDisplay *d=&out->targets[i];
  d->track=t->track;d->low=t->lo;d->high=t->hi;d->from=t->min;d->to=t->max;
  for(u32 j=0;j<12;j++)d->name[j]=t->name[j];
  d->valid=get(resolve(t),t->key,&d->current);
 }
 return 1;
}
static void relative_turn(Macro *s,u32 m,int delta){
 if(s->rejected_active)return;
 int any=0;s->applying=1;
 for(u32 i=0;i<s->count[m];i++){Target *t=&s->t[m][i];u32 h=resolve(t);if(!h){
  FN(0x08104c00,void(*)(const char*))("Macro: target is unavailable");continue;
 }
  int current;if(!get(h,t->key,&current)){
   FN(0x08104c00,void(*)(const char*))("Macro: cannot read current target");continue;
  }
  long long scale=(long long)RANGE_STEP*4;
  s->relative[m][i]+=(long long)delta*((long long)t->max-t->min)*(1<<(s->sens[m]+2));
  long long step=s->relative[m][i]/scale;s->relative[m][i]-=step*scale;
  int low=t->min<t->max?t->min:t->max,high=t->min>t->max?t->min:t->max;
  long long v=(long long)current+step;
  if(current<low){if(step>0&&v<low)low=current;else if(step<=0)v=current;}
  if(current>high){if(step<0&&v>high)high=current;else if(step>=0)v=current;}
  if(v<low&&current>=low){v=low;s->relative[m][i]=0;}
  if(v>high&&current<=high){v=high;s->relative[m][i]=0;}
  if(v<t->lo)v=t->lo;if(v>t->hi)v=t->hi;
  if(v!=current){post(t,h,(int)v);any=1;}
  if(i==0&&t->max!=t->min){long long amount=(v-t->min)*127/((long long)t->max-t->min);
   if(amount<0)amount=0;if(amount>127)amount=127;s->value[m]=(u8)amount;}
 }
 if(!s->count[m]){
  s->frac[m]+=(long long)delta*127*(1<<(s->sens[m]+2))/4;
  int step=s->frac[m]/RANGE_STEP;s->frac[m]-=step*RANGE_STEP;
  int v=(int)s->value[m]+step;if(v<0)v=0;if(v>127)v=127;s->value[m]=(u8)v;
 }
 if(any)FN(0x0813130c,void(*)(void*))(MODEL);
 s->applying=0;
}
static void flash_name(Macro *s,char sign,const char *n){
 u32 k=0;s->flash[k++]=sign;s->flash[k++]=' ';for(u32 i=0;n[i]&&k<15;i++)s->flash[k++]=n[i];s->flash[k]=0;s->flash_until=NOW+2500u;
}
static int find_target(Macro *s,u32 m,u32 h,u32 key){
 for(u32 i=0;i<s->count[m];i++){Target *x=&s->t[m][i];if(x->key==key&&resolve(x)==h)return (int)i;}return -1;
}
static void remove_target(Macro *s,u32 m,u32 at){
 for(u32 j=at;j+1<s->count[m];j++){s->t[m][j]=s->t[m][j+1];s->relative[m][j]=s->relative[m][j+1];}
 s->relative[m][s->count[m]-1]=0;
 s->count[m]--;if(!s->count[m])s->name[m][0]=0;
}
/* While armed, a tap on a parameter slot maps it at full range; a second tap
 * on the same parameter within the double-tap window unmaps it. The slot carries its
 * own node handle at +34; locate() checks the handle is in the model. Every
 * refusal says why in the lower-left readout. */
static int tap_map(Macro *s,void *slot){
 if(s->rejected_active)return 1;
 u32 m=s->armed-1,h=W(slot,0x34),key=H(slot,0x9c);
 int lo=(int)W(slot,0x450),hi=(int)W(slot,0x454);
 const char *l=(const char*)slot+0x3f9;
 if(!h){flash_name(s,'!',"NO NODE");return 0;}
 if(!key){flash_name(s,'!',"NO KEY");return 0;}
 if(hi<=lo){flash_name(s,'!',"NO RANGE");return 0;}
 int at=find_target(s,m,h,key);
 int twice=s->tap_handle==h&&s->tap_key==key&&NOW-s->tap_tick<400u;
 s->tap_handle=twice?0:h;s->tap_key=key;s->tap_tick=NOW;
 if(at>=0){if(twice){remove_target(s,m,(u32)at);flash_name(s,'-',l);}else flash_name(s,'=',l);return 1;}
 if(s->count[m]>=MACRO_TARGETS){flash_name(s,'!',"FULL 3/3");return 1;}
 Target n;zero(&n,sizeof n);if(!locate(h,&n)){flash_name(s,'!',"NOT FOUND");return 0;}
 n.key=(u16)key;n.lo=lo;n.hi=hi;n.min=lo;n.max=hi;
 {u32 k=0;while(l[k]&&k<11){n.name[k]=l[k];k++;}n.name[k]=0;}
 if(!s->count[m]){u32 k=0;while(l[k]&&k<11){s->name[m][k]=l[k];k++;}s->name[m][k]=0;}
 s->relative[m][s->count[m]]=0;s->t[m][s->count[m]++]=n;flash_name(s,'+',l);
 return 1;
}
/* Outside map mode a double tap on a mapped parameter removes it from every
 * macro that maps it (owner, 29 Oct). The single tap stays native. */
static void tap_unmap(Macro *s,void *slot){
 u32 h=W(slot,0x34),key=H(slot,0x9c);if(!h||!key||s->rejected_active)return;
 int twice=s->tap_handle==h&&s->tap_key==key&&NOW-s->tap_tick<400u;
 s->tap_handle=twice?0:h;s->tap_key=key;s->tap_tick=NOW;if(!twice)return;
 u32 gone=0;for(u32 m=0;m<8;m++){int at=find_target(s,m,h,key);if(at>=0){remove_target(s,m,(u32)at);gone++;}}
 if(gone)flash_name(s,'-',(const char*)slot+0x3f9);
}
/* ---- strip display (P27, confirmed on hardware: swipe in/out, names) ---- */
static void number(char *p,u32 v){u32 n=0;if(v>=100)p[n++]=(char)('0'+v/100);if(v>=10)p[n++]=(char)('0'+v/10%10);p[n++]=(char)('0'+v%10);p[n]=0;}
static void label(Macro *s,u32 m,char *out){
 if(s->count[m]&&s->name[m][0]){u32 k=0;while(s->name[m][k]){out[k]=s->name[m][k];k++;}out[k]=0;return;}
 const char *d="MACRO ";u32 k=0;while(d[k]){out[k]=d[k];k++;}out[k++]=(char)('1'+m);out[k]=0;
}
static int same(const char *a,const char *b){u32 i=0;while(a[i]&&a[i]==b[i])i++;return a[i]==b[i];}
u32 perf_macro_focus(int set);
int perf_macro_targets(void);
static const char *const SENS[5]={"Fine","Slow","Normal","Fast","Coarse"};
static void put(char *d,u32 *k,const char *a,u32 cap){while(*a&&*k<cap)d[(*k)++]=*a++;d[*k]=0;}
static void pct(char *d,u32 *k,const Target *t,int v){
 u32 p=(u32)(((long long)(v-t->lo)*100+(t->hi-t->lo)/2)/(t->hi-t->lo));
 char n[4];number(n,p);put(d,k,n,11);put(d,k,"%",11);
}
/* Macro tab, top row (owner, 28 Oct): the focused macro's ranges. Encoders
 * 1-2 = Min/Max of target 1, 3-4 target 2, 5-6 target 3 (Min above Max plays
 * it backwards), 7 = Sensitivity. Values are % of the parameter's range: the
 * native unit formatter is not reachable for a remembered target. */
static void range_slot(Macro *s,u32 i,char *name,char *text){
 u32 m=perf_macro_focus(-1)&7u,k=0;name[0]=text[0]=0;
 if(i==6){put(name,&k,"Sensitivity",15);k=0;put(text,&k,SENS[s->sens[m]+2],11);return;}
 if(i>6)return;
 if(i/2>=s->count[m]){put(name,&k,i&1?"":"-",15);return;}
 Target *t=&s->t[m][i/2];
 put(name,&k,t->name[0]?t->name:"PARAM",15);
 k=0;put(text,&k,i&1?"Max ":"Min ",11);pct(text,&k,t,i&1?t->max:t->min);
}
/* Selector row (and the Perform strip's own texts): name and amount. */
static void macro_slot(Macro *s,u32 i,char *name,char *text){
 label(s,i,name);
 if(s->armed==i+1){u32 k=0;put(text,&k,"MAP",11);}else number(text,s->value[i]);
}
static void restore_row(Macro *s,u32 k){
 u32 b=s->backup_bar[k];s->backup_bar[k]=0;if(!is_bar(b))return;
 for(u32 i=0;i<8;i++){void *slot=slot_of(b,i);FN(0x0817e85e,void(*)(void*,const char*))((u8*)slot+0x3c8,s->backup[k][i]);FN(0x08170656,void(*)(void*,u32,const char*))((void*)b,i,0);}
}
static void restore(Macro *s){for(u32 k=0;k<MACRO_ROWS;k++)restore_row(s,k);}
static void paint_row(Macro *s,u32 k,u32 b,int ranges){
 if(!is_bar(b))return;
 if(s->backup_bar[k]!=b){restore_row(s,k);for(u32 i=0;i<8;i++){const char *l=(const char*)slot_of(b,i)+0x3f9;u32 j=0;while(l[j]&&j<31){s->backup[k][i][j]=l[j];j++;}s->backup[k][i][j]=0;}s->backup_bar[k]=b;}
 for(u32 i=0;i<8;i++){
  void *slot=slot_of(b,i);char name[16],text[12];
  if(ranges)range_slot(s,i,name,text);else macro_slot(s,i,name,text);
  const char *now=(const char*)slot+0x3f9;
  if(!same(now,name)){u32 j=0;while(now[j]&&j<31){s->backup[k][i][j]=now[j];j++;}s->backup[k][i][j]=0; /* native relabelled it meanwhile */
   FN(0x0817e85e,void(*)(void*,const char*))((u8*)slot+0x3c8,name);}
  if(!same((const char*)slot+0x2c8,text))FN(0x08170656,void(*)(void*,u32,const char*))((void*)b,i,text);
 }
}
/* Perform: the macro strip. Macro tab: ranges on top, the macros underneath. */
static void paint(Macro *s,u32 b){
 int tab=perf_macro_targets();u32 r=s->row_bar[1];
 paint_row(s,0,b,tab);
 if(tab&&r&&r!=b)paint_row(s,1,r,0);else restore_row(s,1);
}
/* The visible strip is the one whose tick ran last (strip vtable +0 wrapped):
 * P27 looked it up through the header's widget tree, which never reaches the
 * page, so after a page change the macros stayed on a strip that was gone. */
/* P30 (owner on P29: macros switch back at once, and the knobs then change
 * macros while the native names show). Strips under a hidden parent still
 * tick, so "last ticked" alternated between strips. A strip counts only when
 * neither it nor any parent is hidden, and the strip showing the macros is
 * kept as long as it stays visible. */
static int visible(u32 w){for(u32 i=0;i<24&&w;i++){if(w<0x20000000u||w>=0xc8000000u||B((void*)w,0x30))return 0;w=W((void*)w,0x2c);}return 1;}
/* G8: the page's visible strips, topmost first (widget rect +8 is y from the
 * bottom). P27-P30 used "the strip whose tick ran last", which is ambiguous as
 * soon as a page has more than one strip — and the Macros page now has three. */
static void note_bar(Macro *s,u32 b){
 u32 y=W((void*)b,8);
 for(u32 k=0;k<MACRO_ROWS;k++)if(s->row_bar[k]&&(NOW-s->row_seen[k]>500u||(s->row_bar[k]!=b&&!visible(s->row_bar[k]))))s->row_bar[k]=0;
 for(u32 k=0;k<MACRO_ROWS;k++)if(s->row_bar[k]==b){s->row_seen[k]=NOW;return;}
 for(u32 k=0;k<MACRO_ROWS;k++){
  if(!s->row_bar[k]){s->row_bar[k]=b;s->row_seen[k]=NOW;return;}
  if(W((void*)s->row_bar[k],8)<y){
   for(u32 j=MACRO_ROWS-1;j>k;j--){s->row_bar[j]=s->row_bar[j-1];s->row_seen[j]=s->row_seen[j-1];}
   s->row_bar[k]=b;s->row_seen[k]=NOW;return;}
 }
}
static u32 live_bar(Macro *s){
 u32 b=s->row_bar[0];
 if(b&&NOW-s->row_seen[0]<500u&&visible(b))return b;
 return is_bar(s->live)&&NOW-s->live_tick<500u&&visible(s->live)?s->live:0;
}
static void open(Macro *s,u32 b){if(!is_bar(b))b=live_bar(s);if(!b)return;s->overlay=1;s->bar=b;s->bar_tick=NOW;paint(s,b);}
static int shown(Macro *s){return is_bar(s->bar)&&visible(s->bar)&&NOW-s->bar_tick<=300u;}
static void close(Macro *s){s->overlay=0;restore(s);s->bar=0;s->acc_slot=0;}
void macro_project_reset(void);
int macro_overlay(void){Macro *s=state(0);return s&&s->overlay;}
__attribute__((used,retain)) void macro_bar_tick(void *bar,void *frame){
 FN(0x081703cd,void(*)(void*,void*))(bar,frame);
 extern void pg_perform_tick(void*,void*);pg_perform_tick(bar,frame);
 Macro *s=state(1);if(!s||!W(bar,0x2c))return;if((u32)bar==s->bar)s->bar_tick=NOW;
 int shown=visible((u32)bar);
 if(shown)note_bar(s,(u32)bar);
 if((u32)bar==s->live||shown){s->live=(u32)bar;s->live_tick=NOW;}
}
/* Detail mode changes focus without arming; overview taps also support double-tap. */
void macro_select(u32 i){
 Macro *s=state(1);if(!s||i>7)return;
 s->last_tap=0;
 if(perf_macro_focus(-1)!=i)s->acc_slot=0;
 perf_macro_focus((int)i);
 if(s->overlay&&is_bar(s->bar))paint(s,s->bar);
}
void macro_touch(u32 i){
 Macro *s=state(1);if(!s||i>7)return;
 u32 last=s->last_tap,tick=s->last_tap_tick;
 macro_select(i);
 if(last==i+1&&NOW-tick<400u){
  s->last_tap=0;s->armed=0;
  if(!s->rejected_active&&s->count[i]){while(s->count[i])remove_target(s,i,s->count[i]-1);flash_name(s,'-',"ALL");}
 }else{s->last_tap=i+1;s->last_tap_tick=NOW;if(!s->rejected_active)s->armed=s->armed==i+1?0:i+1;}
 if(s->overlay&&is_bar(s->bar))paint(s,s->bar);
}
/* Macro page: a double tap on binding j of macro i removes only that binding. */
void macro_binding_tap(u32 i,u32 j){
 Macro *s=state(1);if(!s||i>7||j>=MACRO_TARGETS)return;
 u32 id=i*MACRO_TARGETS+j+1;
 if(s->bind_tap==id&&NOW-s->bind_tick<400u){s->bind_tap=0;if(!s->rejected_active&&j<s->count[i]){char n[12];for(u32 k=0;k<12;k++)n[k]=s->t[i][j].name[k];remove_target(s,i,j);flash_name(s,'-',n);}}
 else{s->bind_tap=id;s->bind_tick=NOW;}
 if(s->overlay&&is_bar(s->bar))paint(s,s->bar);
}
void macro_disarm(void){Macro *s=state(0);if(s){s->armed=0;s->last_tap=0;}}
/* Header tick (every UI tick). Macros are shown only on Perform and the Macro
 * tab (owner, 28 Oct: the swipe that showed them elsewhere is gone); the armed
 * macro stays in sight on every page through the lower-left readout. */
int perf_macro_view(void);
void macro_periodic(void *out){
 extern void workflow_periodic(void);workflow_periodic();
 int want=perf_macro_view();
 Macro *s=state(want?1:0);if(!s)return;
 u32 project=settings(); /* a new project: its macros come from its file, else none */
 if(project!=s->project){if(s->project&&!s->loaded)macro_project_reset();s->project=project;s->loaded=0;}
 if(!want){if(s->overlay)close(s);}
 else{
  if(!s->overlay)open(s,0); /* the strip may not have ticked yet, so retry every tick */
  if(s->overlay&&!shown(s)){u32 b=live_bar(s);restore(s);s->bar=b;s->bar_tick=NOW;if(!b)s->overlay=0;}
  if(s->overlay)paint(s,s->bar);
 }
 if(s->down&&NOW-s->down_tick>3000u)s->down=0; /* an up that never came must not block the strip */
 (void)out;
}
/* G11: reuse the native lower-left instrument/track labels. Leave the battery
 * readout alone and let the next native snapshot restore names when idle. */
void macro_readout(void *out){
 if(!out)return;Macro *s=state(0);u32 rejected=macro_preservation_fault(-1)?3:s?s->rejected_active:0;
 extern int motion_active(int);
 if(motion_active(0)){char *p=(char*)out;const char *w="MOTION ON";u32 k=0;while(w[k]){p[k]=w[k];k++;}p[k]=0;B(out,0x60)=0;return;}
 if(rejected){char *p=(char*)out;const char *w=rejected==3?"! MACRO NO MEM":rejected==2?"! MACROS MAX 3":"! MACRO DATA";u32 k=0;while(w[k]){p[k]=w[k];k++;}p[k]=0;B(out,0x60)=0;return;}
 if(!s)return;
 int flash=s->flash_until&&(int)(s->flash_until-NOW)>0;
 if(!flash&&!s->armed)return;
 char *p=(char*)out;B(out,0x60)=0;u32 k=0;
 if(flash){while(s->flash[k]&&k<31){p[k]=s->flash[k];k++;}p[k]=0;return;}
 /* Owner, 28 Oct: steady, with how many of the three targets are taken. */
 const char *w="MAP M";while(w[k]){p[k]=w[k];k++;}
 p[k++]=(char)('0'+s->armed);p[k++]=' ';p[k++]=(char)('0'+s->count[s->armed-1]);p[k++]='/';p[k++]=(char)('0'+MACRO_TARGETS);p[k]=0;
}
int macro_model_event(void *event){
 extern int macro_save_blocked(void);
 if(event&&H(event,0)==0x101d&&macro_save_blocked()){
  FN(0x08104c00,void(*)(const char*))("Macro data not preserved: save/SD-card mode cancelled");
  return 1;
 }
 return 0; /* owner, 28 Oct: turning a knob never maps; only a tap does */
}
/* Macro tab: one turn edits the focused macro's ranges or its Sensitivity. */
static void range_turn(Macro *s,u32 i,int delta){
 u32 m=perf_macro_focus(-1)&7u,id=m*8u+i+1u;
 if(s->acc_slot!=id){s->acc_slot=id;s->acc=0;}
 if(i==7){
  relative_turn(s,m,delta);
  return;
 }
 if(i==6){
  s->acc+=delta;long long step=s->acc/SENS_STEP;s->acc-=step*SENS_STEP;
  int v=s->sens[m]+(int)step;if(v<-2)v=-2;if(v>2)v=2;s->sens[m]=(signed char)v;return;
 }
 if(i>6||i/2>=s->count[m])return;
 Target *t=&s->t[m][i/2];
 s->acc+=(long long)delta*(t->hi-t->lo);long long step=s->acc/RANGE_STEP;s->acc-=step*RANGE_STEP;
 if(!step)return;
 int *x=i&1?&t->max:&t->min;long long v=*x+step;if(v<t->lo)v=t->lo;if(v>t->hi)v=t->hi;
 if(v!=*x){*x=(int)v;s->relative[m][i/2]=0;}
}
/* From kick_ui_increment: returns 1 when the turn belongs to a macro. */
int macro_increment(void *slot,int delta){
 Macro *s=state(0);if(!s||!slot||!s->overlay)return 0;
 u32 bar=0;int i=slot_index(slot,&bar);if(i<0)return 0;
 if(s->rejected_active)return 1;
 if(perf_macro_targets()){
  if(bar!=s->row_bar[0]&&bar!=s->row_bar[1]&&bar!=s->bar)return 0;
  range_turn(s,(u32)i,delta);paint(s,s->bar);return 1;
 }
 if(bar!=s->bar){if(shown(s))return 0; /* a strip that does not show the macros stays native */
  restore(s);s->bar=bar;s->bar_tick=NOW;}
 /* Sensitivity: Fine 1/4x .. Coarse 4x of the original feel. */
 relative_turn(s,(u32)i,delta);paint(s,bar);return 1;
}
/* ---- touches (P27 gesture) ----
 * Strip vtable +10/+14/+18 (down/move/up) and +1C (takes touches) as in P27.
 * The app hit test redirects strip-area touches to the real strip. G12 must
 * keep its native identity in the widget tree: the hardware dispatcher stores
 * +28 on down and looks that identity up again for move/up. P29's detached,
 * zero-initialized catcher could receive down but could never receive up. */
static void rect(u32 b,int *r){void *a=slot_of(b,0),*z=slot_of(b,7);r[0]=(int)W(a,4);r[1]=(int)W(a,8);r[2]=(int)W(z,4)+(int)W(z,12)-r[0];r[3]=(int)W(a,16);}
int perf_macro_view(void);
int fx_screen_active(void);
int fx_screen_hit(void*,void**);
void pg_fx_touch_down(void*,void*);
void pg_fx_touch_up(void*,void*);
int perf_point_hit(void*,void*,void**);
/* Owner, 29 Oct: a tap on the header readout ("MAP M1 1/3") ends map mode.
 * The readout is the header root's title label (x from root+240, width +248,
 * set by the native apply 0817FAF8, which stops it before the first tab); the
 * header root spans y 0..+10 (emulator: 0,0,1280,42). Unverified on hardware. */
static int readout_tap(void *point){
 extern int motion_active(int);
 Macro *s=state(0);if((!s||!s->armed)&&!motion_active(0))return 0;
 if(!point||W((void*)0x30034d48u,0)!=0x081b3680u)return 0;
 int x=(int)W(point,0),y=(int)W(point,4),x0=(int)W((void*)0x30034d48u,0x240),w=(int)W((void*)0x30034d48u,0x248);
 if(y<0||y>=(int)W((void*)0x30034d48u,0x10)||x<x0||x>=x0+w)return 0;
 if(motion_active(1))return 1;
 s->armed=0;s->last_tap=0;flash_name(s,'-',"MAP OFF");return 1;
}
__attribute__((used,retain)) int macro_app_hit(void *app,void *point,void **out){
 if(readout_tap(point)){if(out)*out=0;return 0;}
 if(perf_point_hit(app,point,out))return 1;
 if(fx_screen_hit(point,out))return 1;
 int ok=FN(0x0816e0fc,int(*)(void*,void*,void**))(app,point,out);
 if(ok&&out&&*out){
  void *w=*out;
  for(u32 n=0;w&&n<5;n++){
   if(perf_bar_kind(w)){*out=w;return 1;}
   w=(void*)W(w,0x2c);
  }
 }
 Macro *s=state(1);if(!s||!point||!out)return ok;
 s->routed_bar=0;s->under=0;
 if(ok&&*out&&W(*out,0)==BAR_VT)return ok;
 /* G6: ...except on our own Macros tab, which the app presents as a popup and
  * which would otherwise swallow every tap before the strip ever sees it. */
 if(!perf_macro_view()&&((W(app,0x48)&&!B((void*)W(app,0x48),0x30))||(W(app,0x44)&&!B((void*)W(app,0x44),0x30))))return ok; /* menus and popups first */
 int x=(int)W(point,0),y=(int)W(point,4);
 /* Macro tab: the range row or the macro selector underneath it. */
 u32 rows[MACRO_ROWS]={s->overlay&&is_bar(s->bar)?s->bar:live_bar(s),perf_macro_targets()&&s->overlay?s->row_bar[1]:0};
 for(u32 k=0;k<MACRO_ROWS;k++){u32 b=rows[k];if(!is_bar(b))continue;
  int r[4];rect(b,r);
  if(r[2]<=0||x<r[0]||x>=r[0]+r[2]||y<r[1]||y>=r[1]+r[3])continue;
  s->under=ok?(u32)*out:0;s->routed_bar=b;*out=(void*)b;return 1;}
 return ok;
}
__attribute__((used,retain)) int macro_bar_takes(void *bar){(void)bar;return 1;}
int pg_mixer_bar_drag(void*,void*,u32,int);
__attribute__((used,retain)) void macro_bar_down(void *bar,void *point,u32 id){
 if(perf_bar_down(bar,point))return;
 if(fx_screen_active()){
  pg_fx_touch_down(bar,point);return;
 }
 (void)bar;(void)id;Macro *s=state(1);if(!s||!point)return;
 s->down=1;s->down_tick=NOW;s->x0=s->x=(int)W(point,0);s->y0=s->y=(int)W(point,4); /* every down starts fresh */
 pg_mixer_bar_drag(bar,point,id,0);
}
/* Owner, 28 Oct: no swipe opens or closes macros any more; a move only tracks. */
__attribute__((used,retain)) void macro_bar_move(void *bar,void *point,u32 id){
 if(fx_screen_active())return;
 Macro *s=state(0);if(!s||!s->down||!point)return;s->x=(int)W(point,0);s->y=(int)W(point,4);
 pg_mixer_bar_drag(bar,point,id,1);
}
static int column(u32 b,int x){
 if(is_bar(b))for(u32 k=0;k<8;k++){void *sl=slot_of(b,k);int sx=(int)W(sl,4),sw=(int)W(sl,12);if(x>=sx&&x<sx+sw)return (int)k;}
 return -1;
}
/* Macro tab: a tap on the selector row focuses / double tap arms. Elsewhere,
 * while armed, a tap on a parameter maps or unmaps it and still reaches the
 * page underneath, so it selects that lane natively (G10). */
__attribute__((used,retain)) void macro_bar_up(void *bar,void *point,u32 id){
 if(perf_bar_up(bar,point))return;
 if(fx_screen_active()){pg_fx_touch_up(bar,point);return;}
 Macro *s=state(0);if(!s||!s->down)return;s->down=0;if(!point)return;
 if(pg_mixer_bar_drag(bar,point,id,2))return;
 int x=(int)W(point,0),dx=x-s->x0,dy=(int)W(point,4)-s->y0;if(dx<0)dx=-dx;if(dy<0)dy=-dy;if(dx>30||dy>30)return;
 u32 b=(u32)bar;
 if(s->overlay&&is_bar(s->bar)){
  if(perf_macro_targets()?b!=s->row_bar[1]:b!=s->bar)return; /* the range row takes knobs, not taps */
  int i=column(b,x);if(i>=0)macro_touch((u32)i);
  return;
 }
 {extern int workflow_lock_tap(void*);int i=column(b,x);
  if(i>=0&&workflow_lock_tap(slot_of(b,(u32)i)))return;}
 void *hit=0;
 if(s->armed){
  if(is_bar(b)){int i=column(b,x);if(i>=0)tap_map(s,slot_of(b,(u32)i));else flash_name(s,'!',"NO SLOT");}
  else flash_name(s,'!',"NO STRIP");
 }else if(is_bar(b)){int i=column(b,x);if(i>=0)tap_unmap(s,slot_of(b,(u32)i));}
 if((u32)bar==s->routed_bar)hit=(void*)s->under;
 else{u32 parent=W(bar,0x2c);if(!parent)return;B(bar,0x30)=1;FN(0x0816fa10,int(*)(void*,void*,void**))((void*)parent,point,&hit);B(bar,0x30)=0;}
 if(hit&&hit!=bar&&W(hit,0)!=BAR_VT){FN(W((void*)W(hit,0),0x10),void(*)(void*,void*,u32))(hit,point,id);FN(W((void*)W(hit,0),0x18),void(*)(void*,void*,u32))(hit,point,id);}
}
/* ---- project file: one versioned attribute on project settings' params ---- */
static const char hexd[]="0123456789ABCDEF";
static void put8(Macro *s,u32 *n,u32 v){if(*n+2<sizeof(s->hex)){s->hex[*n]=hexd[(v>>4)&15];s->hex[*n+1]=hexd[v&15];*n+=2;}else s->hex_full=1;}
static void put32(Macro *s,u32 *n,u32 v){for(u32 i=0;i<4;i++)put8(s,n,v>>(i*8)&255);}
void macro_save(void *object,void *params){
 Macro *s=state(0);if(!s||!object||!params||B(object,4)!=21)return;
 if(s->rejected_active){
  if(s->rejected_active==3)return;
  void *a=FN(0x08109cdc,void*(*)(void*,const char*))(params,"playground_macros_v1");
  if(a)FN(0x08109582,void(*)(void*,const char*))(a,s->rejected);
  return;
 }
 u32 n=0,any=0,v3=0;s->hex_full=0;
 for(u32 m=0;m<8;m++)v3|=s->sens[m]!=0;
 put8(s,&n,v3?3:2); /* G5: version 2 adds a name per target; 3 a Sensitivity per macro */
 for(u32 m=0;m<8;m++){put8(s,&n,s->value[m]);put8(s,&n,s->count[m]);any|=s->count[m];
  if(v3)put8(s,&n,(u8)(s->sens[m]+2));
  for(u32 k=0;k<12;k++)put8(s,&n,(u8)s->name[m][k]);
  for(u32 i=0;i<s->count[m];i++){Target *t=&s->t[m][i];put8(s,&n,t->track);put8(s,&n,t->c1);put8(s,&n,t->c2);put8(s,&n,t->key&255);put8(s,&n,t->key>>8);
   put32(s,&n,(u32)t->lo);put32(s,&n,(u32)t->hi);put32(s,&n,(u32)t->min);put32(s,&n,(u32)t->max);
   for(u32 k=0;k<12;k++)put8(s,&n,(u8)t->name[k]);}}
 s->hex[n]=0;if(!any||s->hex_full)return;
 void *a=FN(0x08109cdc,void*(*)(void*,const char*))(params,"playground_macros_v1");if(a)FN(0x08109582,void(*)(void*,const char*))(a,s->hex);
}
static int nib(char c){return c>='0'&&c<='9'?c-'0':c>='A'&&c<='F'?c-'A'+10:-1;}
static int get8(const char **p){int h=nib((*p)[0]),l=h<0?-1:nib((*p)[1]);if(l<0)return -1;*p+=2;return h*16+l;}
static int get32(const char **p,u32 *v){*v=0;for(u32 i=0;i<4;i++){int b=get8(p);if(b<0)return 0;*v|=(u32)b<<(i*8);}return 1;}
static int parse(const char *p,Macro *out){
 int ver=get8(&p),over=0;if(ver<1||ver>3)return 0;
 for(u32 m=0;m<8;m++){
  int v=get8(&p),c=get8(&p),e=ver>=3?get8(&p):2;if(v<0||v>127||c<0||c>8||e<0||e>4)return 0;
  if(c>(int)MACRO_TARGETS)over=1;
  if(out){out->value[m]=(u8)v;out->count[m]=0;out->sens[m]=(signed char)(e-2);}
  for(u32 k=0;k<12;k++){int ch=get8(&p);if(ch<0)return 0;if(out)out->name[m][k]=(char)ch;}
  if(out)out->name[m][11]=0;
  for(int i=0;i<c;i++){
   Target x;zero(&x,sizeof x);
   int a1=get8(&p),a2=get8(&p),a3=get8(&p),k1=get8(&p),k2=get8(&p);u32 lo,hi,mn,mx;
   if(a1<0||a2<0||a3<0||k1<0||k2<0||!get32(&p,&lo)||!get32(&p,&hi)||!get32(&p,&mn)||!get32(&p,&mx))return 0;
   x.track=(u8)a1;x.c1=(u8)a2;x.c2=(u8)a3;x.key=(u16)(k1|k2<<8);x.lo=(int)lo;x.hi=(int)hi;x.min=(int)mn;x.max=(int)mx;
   if((x.track>=16&&x.track!=0xfe)||(x.c1>=64&&x.c1!=0xff)||(x.c2>=64&&x.c2!=0xff)||(x.c1==0xff&&x.c2!=0xff)||!x.key||x.hi<=x.lo||x.min<x.lo||x.min>x.hi||x.max<x.lo||x.max>x.hi)return 0;
   if(ver>=2){for(u32 k=0;k<12;k++){int ch=get8(&p);if(ch<0)return 0;x.name[k]=(char)ch;}x.name[11]=0;}
   if(out&&i<(int)MACRO_TARGETS)out->t[m][out->count[m]++]=x;
  }
 }
 return *p?0:over?2:1;
}
static void reject_no_memory(Macro *s){
 macro_preservation_fault(1);s->rejected_active=3;s->loaded=1;s->armed=s->last_tap=0;
}
int macro_save_blocked(void){
 return macro_preservation_fault(-1);
}
int macro_save_request(void *worker){
 u32 command=B(worker,0x14);
 if((command!=0x2d&&command!=0x2e)||!macro_save_blocked())return 0;
 /* Native Save failure (4C), before either worker can touch paths/files. */
 u32 index=W(worker,0x300)&15u;void *event=(u8*)worker+0x160+24u*index;
 zero(event,20);B(event,0)=0x4c;
 FN(0x08100590,void(*)(void*))((u8*)worker+0x300);
 FN(0x08104c00,void(*)(const char*))("Macro data not preserved: project Save cancelled");
 return 1;
}
void macro_load(void *node,void *object){
 if(!node||!object)return;void *params=FN(0x08109268,void*(*)(void*,const char*))(node,"params");if(!params)return;
 void *a=FN(0x08109c64,void*(*)(void*,const char*))(params,"playground_macros_v1");if(!a)return;
 const char *p=FN(0x081094c2,const char*(*)(void*))(a);if(!p)return;
 Macro *s=state(1);if(!s){macro_preservation_fault(1);FN(0x08104c00,void(*)(const char*))("Macro state unavailable: project Save disabled");return;}
 int parsed=parse(p,0);
 if(parsed!=1){
  u32 n=0;while(p[n])n++;
  u32 bytes=(n+1u+31u)&~31u;
  if(bytes<n){reject_no_memory(s);return;}
  if(bytes>s->rejected_bytes){
   u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0);
   if(cursor<0xc0000000u||end>0xc8000000u||cursor>end||end-cursor<bytes+32u){reject_no_memory(s);return;}
   char *copy=FN(0x08104c08,char*(*)(u32))(bytes);
   if((u32)copy!=cursor){reject_no_memory(s);return;}
   s->rejected=copy;s->rejected_bytes=bytes;
  }
  char *copy=s->rejected;
  for(u32 i=0;i<=n;i++)copy[i]=p[i];
  s->rejected_active=parsed==2?2:1;s->loaded=1;s->armed=s->last_tap=0;macro_preservation_fault(0);return;
 }
 zero(s->relative,sizeof(s->relative));zero(s->frac,sizeof(s->frac));s->acc=0;s->acc_slot=0;
 parse(p,s);s->rejected_active=0;s->loaded=1;macro_preservation_fault(0);
}
/* A new project: no macros until its file says otherwise (load runs later). */
void macro_project_reset(void){macro_preservation_fault(0);Macro *s=state(0);if(!s)return;if(s->overlay)close(s);s->armed=s->last_tap=0;s->rejected_active=0;zero(s->relative,sizeof(s->relative));for(u32 m=0;m<8;m++){s->count[m]=0;s->value[m]=0;s->name[m][0]=0;s->sens[m]=0;s->frac[m]=0;}}
/* ---- the Performance page Macro tab holds the strip open ---- */
void macro_view_set(int on){
 Macro *s=state(on?1:0);if(!s)return;
 if(on){if(!s->overlay)open(s,0);}
 else if(s->overlay)close(s);
}
int macro_armed(void){Macro *s=state(0);return s?(int)s->armed:0;}
/* Macro tab title, e.g. "M3 Cutoff". */
void macro_title(char *out){
 Macro *s=state(0);u32 m=perf_macro_focus(-1)&7u,k=0;out[k++]='M';out[k++]=(char)('1'+m);out[k]=0;
 if(s&&s->count[m]&&s->name[m][0]){put(out,&k," ",30);put(out,&k,s->name[m],30);}
 put(out,&k,perf_macro_targets()?" Controls":" Overview",30);
}
