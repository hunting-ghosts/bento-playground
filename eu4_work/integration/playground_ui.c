#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
/* Bento Playground design: one-shot Step cells (owner's Playground mockup).
 *
 * The native cell class (vtable 0819E814) keeps all its data and behaviour:
 * number (+6F0), trigger (+6ED), track colour (+6EC), playhead (+EC == 0),
 * selection (0815B9C0), touches and hit testing are untouched. Only the cell's
 * two paint entries (slot 1, slot 2) are replaced, so the cell is drawn as:
 *   step number top left, playhead dot top centre, a 56 px square outlined in
 *   the track colour and filled by the selected pad's velocity, a white outline
 *   when selected, two lock rails under the square (lock 1, lock 2 values) and
 *   the probability under the step number (lower left).
 * Velocity, probability (note byte 1, 0 = always) and lock values come from the
 * selected pad's native note on that step (0810D2C0), once per frame.
 * GPL-3.0-or-later.
 */
#include "step_lock_shared.h"
#include "macro_display.h"
#include "velocity.h"
#ifdef BENTO_SYNCUSSION
#include "../drums/syncussion_controls.h"
#include "../drums/kick_knobs.h"
#include "../drums/drum_models.h"
#include "ui_native.h"
#endif
u32 seq_eu_dynamics(void*);
int perf_macro_targets(void);
unsigned perf_macro_focus(int);
typedef unsigned short u16;
#define MODEL ((void*)0x30024b00u)
#define TICK W((void*)0x3001fe2cu,0)
#define VIEW_VT 0x0819e854u
#define CELL_STRIDE 0x704u
#define PG_MAGIC 0x31475042u
#define LABEL_BYTES 0x80u
#define TRACK_ICON_CACHED (1u<<30)
#define TRACK_ICON_VERTICAL (1u<<31)

typedef struct {
 u32 handle,bitmap,flags,type;
 char name[32];
 u16 meter[2];
} TrackPaint;
typedef struct {
 u32 handle,flags;char name[32];int value[4];u16 meter[2];
} MixerPaint;
typedef struct {
 u32 clip,status,selected,colour;
 char name[16];
} LaunchCellPaint;
typedef struct {
 u32 colour;
 char name[32];
} LaunchHeaderPaint;
typedef struct {
 u32 magic,stamp,view,container,pad,base;
 u8 vel[32],prob[32],note[32],locked[32],cond[32];signed char off[32];
 unsigned short l1[32],l2[32];
 u8 label[LABEL_BYTES];   /* private native label (class 081B35C0) for text */
 u32 label_ready,font,ground; /* ground: background the text cell is drawn on (0 = BG) */
 u32 tracks_view,tracks_valid,outputs_valid,output_stamp;
 TrackPaint tracks[8];
 u32 outputs[4][2];
 u16 output_meter[8][2];
 char output_text[8][64];
 u32 launch_view,launch_cells_valid[2],launch_headers_valid;
 u32 launch_select,launch_project,launch_group[8],launch_track[8],launch_row[8];
 LaunchCellPaint launch_cells[64];
 LaunchHeaderPaint launch_headers[8];
 u32 down_col,down_id,down_tick,down_project,down_handle,down_zone,touches,cancelled;
 int down_x,down_y;
 u32 tap_col,tap_handle,tap_zone,tap_tick,tap_project;
 u32 mixer_view,mixer_valid,mixer_values,compressor,mixer_config,mixer_drag,mixer_overlay;
 MixerPaint mixer[8];
 int mix_value[8][4],drag_value,drag_sent;u32 drag_context;
 u32 perform_bar,perform_stamp,perform_valid,perform_hash[8],perform_controls;
 char perform_text[8][64],perform_name[12];
 u32 keys_owner,keys_notes[4],keys_held,keys_root,keys_valid,keys_hash,keys_stamp;
 char keys_name[16],keys_list[40];
 u32 fx_hash,fx_stamp,fx_valid,fx_touch;
 int fx_x,fx_y;
#ifdef BENTO_SYNCUSSION
 u32 sync_view,sync_valid,sync_hash[3]; /* drum panel paint cache (run 14: the Syncussion switch-tap state is gone) */
#endif
 u8 rt[32]; /* R6.14: ratchet hits per step (last, so earlier offsets stay) */
 u32 mix_up; /* run 18: the Mixer output row as last painted (1 = encoders on the outputs, framed) */
} PG;
void **playground_state_slot(void);
void **playground_existing_slot(void);
#define zero ui_zero
__attribute__((weak,noinline,section(".text.sls"))) void ui_zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static PG *state(void){
 void **slot=playground_state_slot();if(!slot)return 0;PG *s=*slot;
 if(s)return s->magic==PG_MAGIC?s:0;
 u32 bytes=(sizeof(PG)+31u)&~31u;s=(void*)ui_alloc(bytes,bytes+32);if(!s)return 0;zero(s,sizeof(*s));s->magic=PG_MAGIC;
 for(u32 i=0;i<4;i++)s->outputs[i][0]=s->outputs[i][1]=0xc2700000u;
 s->output_stamp=TICK-1u;*slot=s;return s;
}
static PG *existing(void){
 void **slot=playground_existing_slot();PG *s=slot?*slot:0;
 return s&&s->magic==PG_MAGIC?s:0;
}

/* Native fills/outlines take logical rects (x, y from the bottom, w, h). */
/* SURF: the paint surface of the current draw call (no writable globals in flash code). */
/* Space (1.6.8 port): coordinate pairs travel packed as two signed 16-bit halves
   (screen values are far inside +-32767), style as colour|font<<8|align<<16 (the
   callees only ever use the low byte of each), so most calls pass in registers. */
#define PK(a,b) ((u32)(u16)(int)(a)|(u32)(int)(b)<<16)
#define PLO(p) ((int)(short)(p))
#define PHI(p) ((int)(p)>>16)
#define STYLE(c,f,a) ((u32)(u8)(c)|(u32)(u8)(f)<<8|(u32)(u8)(a)<<16)
#define fill(x,top,w,h,c) fill_(SURF,PK(x,top),PK(w,h),c)
#define frame(x,top,w,h,t,c) frame_(SURF,PK(x,top),PK(w,h),t,c)
static void fill_(void *SURF,u32 at,u32 size,u32 c){int x=PLO(at),top=PHI(at),w=PLO(size),h=PHI(size);if(w<=0||h<=0)return;int r[4]={x,480-top-h,w,h};NFN(0x08166ef6,void(*)(void*,u32,void*))(r,c,SURF);}
static void frame_(void *SURF,u32 at,u32 size,int t,u32 c){int x=PLO(at),top=PHI(at),w=PLO(size),h=PHI(size);fill(x,top,w,t,c);fill(x,top+h-t,w,t,c);fill(x,top+t,t,h-2*t,c);fill(x+w-t,top+t,t,h-2*t,c);}
/* Font index 3 = Rajdhani Medium 14 (heights per index: 26 27 63 15 20 14). */
#define SMALL 3u
#define BIG 0u /* Rajdhani Medium 24 */
#define CENTRE 2u /* label +51: 0/1 left, 2 centred */
/* Run 13 (space): text size and style share one word, TSPEC: w 12 bits | h 7 | colour 8 | font 3 | align 2.
   Every caller's width is below 1,280 and its height below 64 (screen geometry; the launch cell rect is ours). */
#define TSPEC(w,h,c,f,a) (((u32)(w)&4095u)|((u32)(h)&127u)<<12|(u32)(u8)(c)<<19|((u32)(f)&7u)<<27|((u32)(a)&3u)<<30)
#define textf(s,ctx,x,top,w,h,str,colour,font,align) textf_(s,ctx,PK(x,top),TSPEC(w,h,colour,font,align),str)
static void textf_(PG *s,void *ctx,u32 at,u32 spec,const char *str){
 int x=PLO(at),top=PHI(at),w=(int)(spec&4095u),h=(int)(spec>>12&127u);u32 colour=spec>>19&255u,font=spec>>27&7u,align=spec>>30;
 void *l=s->label;
 if(!s->label_ready){NFN(0x0817e7c0,void(*)(void*))(l);s->label_ready=1;s->font=0xffu;}
 if(s->font!=font){NFN(0x0817e810,void(*)(void*,u32))(l,font);s->font=font;}
 B(l,0x53)=(u8)colour;B(l,0x54)=(u8)(s->ground?s->ground:0xf1u);B(l,0x56)=1;B(l,0x51)=(u8)align;
 NFN(0x0817e85e,void(*)(void*,const char*))(l,str);
 int r[4]={x,480-top-h,w,h};W(l,4)=r[0];W(l,8)=r[1];W(l,12)=r[2];W(l,16)=r[3];
 NFN(0x0817e448,void(*)(void*,void*,void*))(l,ctx,r);
}
static void text(PG *s,void *ctx,int x,int top,int w,int h,const char *str,u32 colour){textf(s,ctx,x,top,w,h,str,colour,SMALL,1);}

#define CACHED_LABELS 56u
void **playground_label_slot(void);
static void *cached_label(u32 index){
 if(index>=CACHED_LABELS||!W((void*)0x30035f40u,0))return 0;
 void **slot=playground_label_slot();if(!slot||*slot==(void*)1)return 0;
 if(!*slot){
  u32 bytes=CACHED_LABELS*LABEL_BYTES,cursor=ui_alloc(bytes,bytes+32u);
  if(!cursor){
   *slot=(void*)1;NFN(0x08104c00,void(*)(const char*))("Playground text cache: no memory");return 0;
  }
  zero((void*)cursor,bytes);*slot=(void*)cursor;
 }
 void *label=(u8*)*slot+index*LABEL_BYTES;
 if(!W(label,0))NFN(0x0817e7c0,void(*)(void*))(label);
 return label;
}
#define text_cached(s,ctx,index,x,top,w,h,str,colour,font,align) text_cached_(s,ctx,index,PK(x,top),TSPEC(w,h,colour,font,align),str)
static void text_cached_(PG *s,void *ctx,u32 index,u32 at,u32 spec,const char *str){
 void *l=cached_label(index);if(!l){textf_(s,ctx,at,spec,str);return;}
 int x=PLO(at),top=PHI(at),w=(int)(spec&4095u),h=(int)(spec>>12&127u);u32 colour=spec>>19&255u,font=spec>>27&7u,align=spec>>30;
 u32 ground=s->ground?s->ground:0xf1u;
 if(B(l,0x55)!=font)NFN(0x0817e810,void(*)(void*,u32))(l,font);
 if(B(l,0x53)!=(u8)colour||B(l,0x54)!=(u8)ground||B(l,0x51)!=(u8)align||
    W(l,12)!=(u32)w||W(l,16)!=(u32)h)B(l,0x5c)=1;
 B(l,0x53)=(u8)colour;B(l,0x54)=(u8)ground;B(l,0x56)=1;B(l,0x51)=(u8)align;
 NFN(0x0817e85e,void(*)(void*,const char*))(l,str);
 int r[4]={x,480-top-h,w,h};W(l,4)=r[0];W(l,8)=r[1];W(l,12)=r[2];W(l,16)=r[3];
 NFN(0x0817e448,void(*)(void*,void*,void*))(l,ctx,r);
}

static u32 frac1000(u32 w){u32 k=lock_kind(w);if(!k)return 0;u32 n=value_count(k);return n>1?(w&65535u)*1000u/(n-1):0;}
__attribute__((noinline,section(".pad2"))) static void refresh(PG *s,void *v){
 u32 container=W(v,0x113dc),pad=W(v,0x11400),base=W(v,0x113f4);
 if(s->stamp==TICK&&s->view==(u32)v&&s->container==container&&s->pad==pad&&s->base==base)return;
 s->stamp=TICK;s->view=(u32)v;s->container=container;s->pad=pad;s->base=base;
 for(u32 i=0;i<32;i++){s->vel[i]=s->prob[i]=s->note[i]=s->locked[i]=s->cond[i]=s->rt[i]=0;s->off[i]=0;s->l1[i]=s->l2[i]=0;}
 if(!container)return;
 u32 e[6],dyn=seq_eu_dynamics(v),n=dyn>>16,hits[8]={0};
 for(u32 j=0;j<511;j++){
  if(!NFN(0x0810d2c0,int(*)(void*,u32,void*))((void*)container,j,e))break;
  if(B(e,0)!=1||H(e,2)!=pad)continue;
  int t=(int)e[1],q=t%960;if(q>480)q-=960;int abs=(t-q)/960,at=abs-(int)base;
  if(dyn&&abs>=0&&(u32)abs<n)hits[abs/32]|=1u<<(abs%32);
  if(at<0||at>=32)continue;
  u32 vel=e[4]>>16;s->vel[at]=(u8)(vel>127?127:vel);s->prob[at]=B(e,1);s->note[at]=1;
  s->off[at]=(signed char)(q/40);s->cond[at]=(u8)lc_condition(e[5]); /* W14 HW3: offset nudge, ratio condition */
  {extern u32 locks_ratchet_get(u32);u32 r=locks_ratchet_get(e[5]);s->rt[at]=r?(u8)((r&7u)+1):0;} /* R6.14 */
  u32 a,b;lock_slots(e[5],&a,&b);
  if(a||b){s->locked[at]=1;s->l1[at]=(unsigned short)frac1000(a);s->l2[at]=(unsigned short)frac1000(b);}
 }
 /* W14 HW3 (owner): Vel Mode shapes the fill like playback (first loop; random modes use a fixed seed). */
 if(dyn){u32 total=0;for(u32 k=0;k<n;k++)total+=hits[k/32]>>(k%32)&1u;
  for(u32 i=0;i<32;i++){u32 a=base+i;if(!s->note[i]||a>=n)continue;u32 rank=0;for(u32 k=0;k<a;k++)rank+=hits[k/32]>>(k%32)&1u;
   s->vel[i]=(u8)velocity_value(s->vel[i]?s->vel[i]:100,dyn&255u,(dyn>>8)&255u,rank,total,a,vel_hash(pad*0x9e3779b9u));}}
}
static void *view_of(void *cell,u32 *index){
 for(u32 i=0;i<32;i++){u8 *v=(u8*)cell-0x34-i*CELL_STRIDE;if(W(v,0)==VIEW_VT){*index=i;return v;}}
 return 0;
}
static void number(char *out,u32 n){char t[6];u32 k=0;do{t[k++]=(char)('0'+n%10);n/=10;}while(n&&k<5);u32 j=0;if(k==1)out[j++]='0';while(k)out[j++]=t[--k];out[j]=0;}

#define BG 0xf1u
#define RULE 0xf3u
#define MUTED 0xf6u
#define TEXT 0xf2u
#define FAINT 0x62u  /* white at alpha 6 over the ground: #626c6c */
#define RAISED 0x22u /* white at alpha 2: rail ground */

static void draw(void *cell,void *ctx){
 u32 i=0;void *v=view_of(cell,&i);PG *s=v?state():0;if(!s)return;
 void *SURF=(void*)W(ctx,4);if(!SURF)return;
 s->ground=0;
 refresh(s,v);
 B(v,0xe0b4+0x30)=1; /* native 16-step frame: not part of the Playground grid */
 int x=(int)W(cell,4),w=(int)W(cell,12),h=(int)W(cell,16),top=480-(int)W(cell,8)-h;
 if(w<100||h<60)return;
 u32 colour=B(cell,0x6ec),on=B(cell,0x6ed)!=0,head=B(cell,0xec)==0;
 u32 step=s->base+i;int sel=NFN(0x0815b9c0,int(*)(void*,u32))(v,step);
 fill(x,top,w,h,BG);
 if((i&7)==0||(i&7)==4)fill(x+2,top+8,1,71,RULE);
 char num[8];number(num,W(cell,0x6f0));text(s,ctx,x+12,top+8,34,16,num,sel?TEXT:MUTED);
 /* playhead dot */
 int dx=x+74,dy=top+4;
 if(head){fill(dx+1,dy,3,5,TEXT);fill(dx,dy+1,5,3,TEXT);}
 else {fill(dx+1,dy,3,1,FAINT);fill(dx+1,dy+4,3,1,FAINT);fill(dx,dy+1,1,3,FAINT);fill(dx+4,dy+1,1,3,FAINT);}
 /* square, velocity fill */
 int bx=x+48,by=top+17,bw=56,bh=56;
 if(on){frame(bx,by,bw,bh,2,colour);u32 vel=s->note[i]?s->vel[i]:100;int fh=(int)((bh-8)*vel/127);if(fh<2)fh=2;int o=s->note[i]?s->off[i]:0;fill(bx+4+(o>0?o:0),by+bh-4-fh,bw-8-(o<0?-o:o),fh,colour);}
 else frame(bx,by,bw,bh,1,FAINT);
 /* rounded corners: knock the four corner pixels */
 for(u32 k=0;k<4;k++)fill(bx+(k&1u?bw-1:0),by+(k&2u?bh-1:0),1,1,BG); /* same order as before */
 if(sel){frame(bx-4,by-4,bw+8,bh+8,2,TEXT);}
 if(head)fill(bx,by-3,bw,2,TEXT);
 /* R6.14: ratchet ticks (one per hit) on the step's top row, track colour */
 if(on&&s->note[i]&&s->rt[i]>1)for(u32 k=0;k<s->rt[i];k++)fill(bx+(int)k*3,top+4,2,5,colour);
 /* lock rails: two bars under the square, filled to each lock's value */
 fill(bx,top+78,bw,2,RAISED);fill(bx,top+84,bw,2,RAISED);
 if(on&&s->locked[i]){int a=(int)(bw*s->l1[i]/1000),b=(int)(bw*s->l2[i]/1000);if(a<2)a=2;if(b<2)b=2;fill(bx,top+78,a,2,colour);fill(bx,top+84,b,2,colour);}
 /* probability, lower left under the step number */
 u32 p=s->prob[i];
 if(on&&s->note[i]&&s->cond[i]>=100&&s->cond[i]<RT_CONDITIONS)text(s,ctx,x+12,top+62,34,16,((const char**)0x081b6000u)[cond_pos(s->cond[i])],MUTED);
 else if(on&&s->note[i]&&p&&p<100){char t[6];u32 k=0;if(p>=10)t[k++]=(char)('0'+p/10);t[k++]=(char)('0'+p%10);t[k++]='%';t[k]=0;text(s,ctx,x+12,top+62,34,16,t,MUTED);}
}
/* slot 1 (paint pass) and slot 2 (clipped walk) both draw the whole cell and
   never recurse into the native children. */
__attribute__((used,retain)) void pg_cell_paint(void *cell,void *ctx){if(ctx&&(B(ctx,0)||B(ctx,1)))draw(cell,ctx);}
__attribute__((used,retain)) void pg_cell_walk(void *cell,void *ctx,void *clip){(void)clip;if(ctx&&(B(ctx,0)||B(ctx,1)))draw(cell,ctx);}


/* Tracks uses native children/model state; Mixer remains native. */
#define TRACKS_VT 0x0819eac8u
#define TRACKS_PAGE 2u
#define COLUMN_STRIDE 0x4c4u
#define SELECTED 0xa3u /* native scene-header grey at 10/15 intensity */
#define TRACK_FONT 0u
#define TRACK_BOLD 1u
#define COLUMN_END 431 /* upper edge of the native footer buttons */
#define MIX_METER_END 329
#define MIX_ROWS 362
#define MIX_ROW 23
#define MIX_METER_TOP 140
#define MIX_METER_INSET 4
static void *tracks_view(void *col,u32 *index){
 void *v=(void*)W(col,0x2c);
 if(!v||W(v,0)!=TRACKS_VT)return 0;
 u32 off=(u32)col-(u32)v-0x34u;
 if(off%COLUMN_STRIDE||off/COLUMN_STRIDE>=8)return 0;
 *index=off/COLUMN_STRIDE;return v;
}
static int equal(const void *a,const void *b,u32 n){
 for(u32 i=0;i<n;i++)if(((const u8*)a)[i]!=((const u8*)b)[i])return 0;
 return 1;
}
static void track_snapshot(void *col,void *v,u32 i,TrackPaint *next,const TrackPaint *old){
 zero(next,sizeof(*next));next->handle=W(col,0x2dc);
 next->bitmap=W(col,0x4b4);
 next->flags=(B(v,0x4aa4)==i)|((u32)B(col,0x2e0)<<1)|((u32)B(col,0x2e1)<<2)|((u32)B(col,0x2e2)<<3)|((u32)B(col,0x2d9)<<8);
 if(old->bitmap==next->bitmap)next->flags|=old->flags&(TRACK_ICON_CACHED|TRACK_ICON_VERTICAL);
#if BENTO_FW==168
 {extern u32 xy_state(void) __attribute__((weak));if(xy_state)next->flags|=(xy_state()>>i&1u)<<4;} /* P168 exp8: XY send off (bit 4) */
#endif
 for(u32 j=0;j<31;j++)next->name[j]=B(col,0xa1+j);
}
/* Native meter samples are dB, not linear amplitude: -60..0 maps to the rail.
 * Decode IEEE bits to Q8 without soft-float helpers on the M4. */
static u32 meter_width(u32 bits,u32 width){
 u32 exponent=(bits>>23)&255u;
 if(exponent==255u)return 0;
 if(!(bits>>31))return width;
 if(exponent>=133u)return 0;
 u32 shift=142u-exponent;
 u32 magnitude=shift>=32u?0:((bits&0x7fffffu)|0x800000u)>>shift;
 return magnitude>=15360u?0:width*(15360u-magnitude)/15360u;
}
static const char *track_type(u32 type){
 static const char *const names[]={"One-shot","Multisample","Slicer","Loop","Wavetable","Granular","Grain chop","Master","External"};
 return type==23?"Analog":type>=14&&type<=22?names[type-14]:"";
}
/* Track and mixer columns share this head: ground, colour rule, number, name; then M/S marks. */
static void column_head(PG *s,void *ctx,void *SURF,u32 i,int x,u32 ground,u32 colour,const char *name,int dim){
 s->ground=ground; /* only text reads it */
 fill(x,73,159,COLUMN_END-73,ground);fill(x+14,73,125,1,colour);
 char num[4];number(num,i+1);text_cached(s,ctx,i*5,x+14,77,40,28,num,colour,TRACK_FONT,1);
 if(name)text_cached(s,ctx,i*5+1,x+8,106,143,30,name,dim?FAINT:TEXT,TRACK_BOLD,CENTRE);
}
static void column_marks(PG *s,void *ctx,u32 i,int x,u32 flags){
 if(flags&2u)text_cached(s,ctx,i*5+3,x+110,77,22,28,"M",MUTED,TRACK_FONT,CENTRE);
 if(flags&4u)text_cached(s,ctx,i*5+4,x+135,77,22,28,"S",TEXT,TRACK_FONT,CENTRE);
}
static void track_column(void *col,void *ctx){
 u32 i;void *v=tracks_view(col,&i);if(!v||B(col,0x30)||!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 PG *s=state();if(!s)return;void *SURF=(void*)W(ctx,4);if(!SURF)return;
 if(s->tracks_view!=(u32)v){s->tracks_view=(u32)v;s->tracks_valid=0;s->outputs_valid=0;}
 TrackPaint *old=&s->tracks[i],next;track_snapshot(col,v,i,&next,old);
 void *icon=(u8*)col+0x480;
 int full=B(ctx,0)||!(s->tracks_valid&(1u<<i));
 if(full||old->handle!=next.handle||((old->flags^next.flags)&0xff00u)){
  next.type=next.handle?ui_type(&next.handle):0;
  extern int analog_track(u32);
  if(next.type==18&&analog_track(next.handle))next.type=23;
 }else next.type=old->type;
 int redraw=full||!equal(old,&next,__builtin_offsetof(TrackPaint,meter));
 int x=6+159*(int)i,selected=next.flags&1u,muted=next.flags&10u;
 u32 ground=selected?SELECTED:BG,colour=NFN(0x08140ebc,u32(*)(u32))(i);
 if(redraw){
  column_head(s,ctx,SURF,i,x,ground,colour,next.handle?next.name:0,muted);
  if(next.handle){
   u32 bw=H(icon,0x38),bh=H(icon,0x3a);
   if(next.type==23){
    for(int ramp=0;ramp<3;ramp++)for(int k=0;k<=13;k++)
     fill(x+58+13*ramp+k,223-2*k,2,2,muted?FAINT:colour);
    for(int ramp=1;ramp<3;ramp++)fill(x+58+13*ramp,197,2,28,muted?FAINT:colour);
   }else if(!B(icon,0x30)&&next.bitmap&&bw<=64&&bh<=64){
    const signed char *bitmap=(const signed char*)next.bitmap;
    if(!(next.flags&TRACK_ICON_CACHED)){
     u32 horizontal=0,vertical=0;
     for(u32 row=0;row<bh;row++)for(u32 at=0;at<bw;at++)if(bitmap[row*bw+at]<0){
      horizontal+=!at||bitmap[row*bw+at-1]>=0;vertical+=!row||bitmap[(row-1)*bw+at]>=0;
     }
     next.flags|=TRACK_ICON_CACHED;if(vertical<horizontal)next.flags|=TRACK_ICON_VERTICAL;
    }
    /* runs of set pixels, column by column (vertical) or row by row, in that order */
    int vertical=!!(next.flags&TRACK_ICON_VERTICAL);
    u32 outer=vertical?bw:bh,inner=vertical?bh:bw,so=vertical?1u:bw,si=vertical?bw:1u;
    for(u32 o=0;o<outer;o++)for(u32 at=0;at<inner;){
     if(bitmap[o*so+at*si]>=0){at++;continue;}
     u32 first=at++;while(at<inner&&bitmap[o*so+at*si]<0)at++;
     int a=(int)o,b=(int)first,run=(int)(at-first);
     fill(x+62+(vertical?a:b),197+(vertical?b:a),vertical?1:run,vertical?run:1,muted?FAINT:colour);
    }
   }
   text_cached(s,ctx,i*5+2,x+4,231,149,30,track_type(next.type),muted?FAINT:MUTED,TRACK_FONT,CENTRE);
#if BENTO_FW==168
   /* P168 exp8 (owner design C2): the square is the track's XY send. 2 px outline in the track colour;
      ON (default, through the XY effects) adds a fill inset 5 px at 80 % of the track colour (alpha 12/15). */
   frame(x+66,378,24,24,2,colour);
   if(!(next.flags&16u))fill(x+71,383,14,14,(colour&15u)|0xc0u);
#else
   frame(x+66,378,24,24,1,selected?FAINT:RULE);
#endif
  }else{
   fill(x+69,209,18,2,FAINT);fill(x+77,201,2,18,FAINT);
  }
  column_marks(s,ctx,i,x,next.flags);
 }
 for(u32 k=0;k<2;k++){
  u32 width=next.handle?meter_width(W(col,0x31c+k*0x4c),92):0;
  next.meter[k]=(u16)width;
  if(redraw||width!=old->meter[k]){
   fill(x+32,311+(int)k*7,92,2,selected?0x32u:RAISED);
   fill(x+32,311+(int)k*7,(int)width,2,colour);
  }
 }
 *old=next;s->tracks_valid|=1u<<i;s->ground=0;
}
__attribute__((used,retain)) void pg_column_paint(void *col,void *ctx){track_column(col,ctx);}
__attribute__((used,retain)) void pg_column_walk(void *col,void *ctx,void *clip){(void)clip;track_column(col,ctx);}

static void *output_view(void *bar){
 extern int macro_overlay(void);
 if(macro_overlay()){PG *s=existing();if(s)s->outputs_valid=0;return 0;}
 void *v=(void*)W(bar,0x2c);
 return v&&W(v,0)==TRACKS_VT&&(u32)bar==(u32)v+0x2658u?v:0;
}
static int output_cell(PG *s,void *ctx,u32 i,const char *lines,u32 left,u32 right,int audio){
 void *SURF=(void*)W(ctx,4);if(!SURF)return 0;
 s->ground=0;
 int x=6+159*(int)i;
 int full=B(ctx,0)||!(s->outputs_valid&(1u<<i))||!equal(lines,s->output_text[i],64);
 if(full){
  fill(x,0,159,73,BG);
  text_cached(s,ctx,40+2*i,x+4,4,149,28,lines,TEXT,TRACK_FONT,CENTRE);
  text_cached(s,ctx,41+2*i,x+4,32,149,28,lines+32,TEXT,BIG,CENTRE);
  for(u32 j=0;j<64;j++)s->output_text[i][j]=lines[j];
 }
 if(audio&&lines[0]){
  u32 width=meter_width(left,135),w2=meter_width(right,135);if(w2>width)width=w2;
  if(full||width!=s->output_meter[i][0]){
   fill(x+10,62,135,1,RAISED);fill(x+10,62,(int)width,1,MUTED);
  }
  s->output_meter[i][0]=s->output_meter[i][1]=(u16)width;
 }
 s->outputs_valid|=1u<<i;return full;
}
static void output_row(void *bar,void *ctx){
 PG *s=state();if(!s||!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 for(u32 i=0;i<8;i++){
  void *slot=(u8*)bar+0x38+i*0x468;
  char lines[64];zero(lines,sizeof(lines));
  if(H(slot,0x9c)&&!B(slot,0x30)){
   for(u32 j=0;j<31;j++){lines[j]=B(slot,0x3f9+j);lines[32+j]=B(slot,0xd9+j);}
  }
  u32 key=H(slot,0x9c);
  int audio=key>=0x135u&&key<=0x138u;u32 meter=audio?0x138u-key:0;
  output_cell(s,ctx,i,lines,s->outputs[meter][0],s->outputs[meter][1],audio);
 }
}
static u32 snapshot_hash(const void *p,u32 n){
 const u8 *b=p;u32 h=2166136261u;for(u32 i=0;i<n;i++)h=(h^b[i])*16777619u;return h;
}
static const signed char ring_points[37][2]={
 {-71,71},{-79,61},{-87,50},{-92,38},{-97,26},{-99,13},{-100,0},
 {-99,-13},{-97,-26},{-92,-38},{-87,-50},{-79,-61},{-71,-71},
 {-61,-79},{-50,-87},{-38,-92},{-26,-97},{-13,-99},{0,-100},
 {13,-99},{26,-97},{38,-92},{50,-87},{61,-79},{71,-71},
 {79,-61},{87,-50},{92,-38},{97,-26},{99,-13},{100,0},
 {99,13},{97,26},{92,38},{87,50},{79,61},{71,71}
};
static int ring_position(int v,int lo,int hi){
 if(hi<=lo)return -1;if(v<=lo)return 0;if(v>=hi)return 360;
 return (int)(((long long)v-lo)*360/((long long)hi-lo));
}
static void ring_point(int at,int r,int *x,int *y){
 int i=at/10,f=at%10,j=i<36?i+1:i;
 *x=(ring_points[i][0]*10+(ring_points[j][0]-ring_points[i][0])*f)*r/1000;
 *y=(ring_points[i][1]*10+(ring_points[j][1]-ring_points[i][1])*f)*r/1000;
}
static void ring_run(void *SURF,int vertical,int fixed,int first,int last,u32 colour){
 if(first>last){int t=first;first=last;last=t;}
 if(vertical)fill(fixed,first,2,last-first+2,colour);
 else fill(first,fixed,last-first+2,2,colour);
}
static __attribute__((used,noinline)) void ring(void *SURF,int cx,int cy,int r,int from,int to,u32 colour){
 if(from<0||to<0)return;if(from>to){int t=from;from=to;to=t;}
 while(from<to){
  int next=(from/10+1)*10;if(next>to)next=to;
  int x,y,endx,endy;ring_point(from,r,&x,&y);ring_point(next,r,&endx,&endy);
  x+=cx;y+=cy;endx+=cx;endy+=cy;
  int dx=endx-x,dy=endy-y,sx=dx<0?-1:1,sy=dy<0?-1:1;
  if(dx<0)dx=-dx;if(dy<0)dy=-dy;int err=dx-dy;
  int vertical=dy>dx,fixed=vertical?x:y,first=vertical?y:x,last=first;
  for(;;){
   int next_fixed=vertical?x:y,along=vertical?y:x;
   if(next_fixed!=fixed){ring_run(SURF,vertical,fixed,first,last,colour);fixed=next_fixed;first=along;}
   last=along;
   if(x==endx&&y==endy)break;int e=2*err;if(e>-dy){err-=dy;x+=sx;}if(e<dx){err+=dx;y+=sy;}
  }
  ring_run(SURF,vertical,fixed,first,last,colour);
  from=next;
 }
}
static void macro_ring(PG *s,void *ctx,int cx,int cy,int radius,const MacroDisplay *d,u32 label_slot){
 void *SURF=(void*)W(ctx,4);
 if(!d->count)ring(SURF,cx,cy,radius,0,360,RULE);
 for(u32 j=0;j<d->count;j++){
  const MacroTargetDisplay *t=&d->targets[j];int r=radius-(int)j*6;
  u32 colour=t->track<8?NFN(0x08140ebc,u32(*)(u32))(t->track):MUTED; /* R6.9: native track palette (follows the rotation; 6/8 were swapped) */
  ring(SURF,cx,cy,r,0,360,RULE);
  ring(SURF,cx,cy,r,ring_position(t->from,t->low,t->high),
       ring_position(t->to,t->low,t->high),colour);
  if(t->valid){int at=ring_position(t->current,t->low,t->high);if(at>=0){int px,py;ring_point(at,r,&px,&py);fill(cx+px-1,cy+py-1,4,4,TEXT);}}
 }
 char amount[8];
 if(d->rejected){amount[0]='!';amount[1]=0;}
 else{number(amount,d->value);if(d->value<10){amount[0]=(char)('0'+d->value);amount[1]=0;}}
 text_cached(s,ctx,label_slot,cx-24,cy-14,50,28,amount,d->count?TEXT:FAINT,BIG,CENTRE);
}
static int macro_percent(int value,int low,int high){
 if(high<=low)return 0;long long n=((long long)value-low)*100/(high-low);
 if(n<0)n=0;if(n>100)n=100;return (int)n;
}
static int macro_bar_x(int value,int low,int high,int x,int width){
 if(high<=low)return x;long long n=((long long)value-low)*width/(high-low);
 if(n<0)n=0;if(n>width)n=width;return x+(int)n;
}
static void macro_percent_label(char *out,const char *prefix,int value,int low,int high){
 u32 k=0;while(prefix[k]&&k<20){out[k]=prefix[k];k++;}
 number(out+k,(u32)macro_percent(value,low,high));while(out[k])k++;
 out[k++]='%';out[k]=0;
}
static void macro_editor(PG *s,void *bar,void *ctx){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 void *SURF=(void*)W(ctx,4);if(!s||!SURF)return;
 int selected=(int)perf_macro_focus(-1),controls=perf_macro_targets();
 static const char *const sensitivity[5]={"Fine","Slow","Default","Fast","Coarse"};
 MacroDisplay focused;if(controls)macro_snapshot((u32)selected,&focused);
 s->ground=BG;fill(0,8,1280,423,BG);
 for(u32 i=0;i<8;i++){
  int x=6+159*(int)i,cx=x+78;MacroDisplay d;
  macro_snapshot(i,&d);
  u32 ground=(int)i==selected?0xa3u:BG;
  fill(x,MACRO_BODY_TOP,159,428-MACRO_BODY_TOP,ground);s->ground=BG;
  char label[32]={'M',(char)('1'+i),0};
  char value[24];number(value,d.value);
  if(controls){
   if(i<6){
    const MacroTargetDisplay *t=&focused.targets[i/2];
    if(i/2<focused.count){
     u32 k=0;while(t->name[k]&&k<11){label[k]=t->name[k];k++;}label[k]=0;
     macro_percent_label(value,i&1?"Max ":"Min ",i&1?t->to:t->from,t->low,t->high);
    }else{label[0]='-';label[1]=0;value[0]=0;}
   }else if(i==6){
    const char *name="Sensitivity";u32 k=0;do{label[k]=name[k];}while(name[k++]);
    name=sensitivity[focused.sensitivity<5?focused.sensitivity:2];k=0;do{value[k]=name[k];}while(name[k++]);
   }else{label[0]='M';label[1]=(char)('1'+selected);label[2]=0;number(value,focused.value);}
  }
  textf(s,ctx,x+4,10,151,28,label,TEXT,BIG,CENTRE);
  if(controls)textf(s,ctx,x+4,40,151,28,value,TEXT,BIG,CENTRE);
  else macro_ring(s,ctx,cx,78,MACRO_RING_RADIUS,&d,CACHED_LABELS);
  s->ground=ground;
  if(d.armed)textf(s,ctx,x+99,394,54,28,"MAP",TEXT,BIG,CENTRE);
  for(u32 j=0;j<3;j++){
   const MacroTargetDisplay *t=&d.targets[j];int top=MACRO_TARGET_TOP+(int)j*MACRO_TARGET_PITCH;
   if(j>=d.count||!t->name[0]){
    textf(s,ctx,x+8,top+10,143,28,"--",FAINT,BIG,CENTRE);continue;
   }
   u32 colour=t->track<8?NFN(0x08140ebc,u32(*)(u32))(t->track):MUTED; /* R6.9: native track palette (follows the rotation; 6/8 were swapped) */
   u32 k=0;
   if(t->track<8){label[k++]=(char)('1'+t->track);label[k++]=' ';label[k++]='/';label[k++]=' ';}
   else{label[k++]='P';label[k++]='R';label[k++]='J';label[k++]=' ';}
   for(u32 n=0;t->name[n]&&n<11&&k<31;n++)label[k++]=t->name[n];label[k]=0;
   textf(s,ctx,x+4,top,151,28,label,colour,BIG,CENTRE);
   macro_percent_label(label,"",t->from,t->low,t->high);
   textf(s,ctx,x+4,top+28,72,28,label,TEXT,BIG,CENTRE);
   macro_percent_label(label,"",t->to,t->low,t->high);
   textf(s,ctx,x+80,top+28,72,28,label,TEXT,BIG,CENTRE);
   int bx=x+12,bw=135,by=top+60;
   fill(bx,by,bw,3,RULE);
   if(t->high>t->low){
    int from=macro_bar_x(t->from,t->low,t->high,bx,bw);
    int to=macro_bar_x(t->to,t->low,t->high,bx,bw);
    int current=macro_bar_x(t->current,t->low,t->high,bx,bw);
    int left=from<to?from:to,right=from>to?from:to;
    if(right==left)right++;
    fill(left,by,right-left,3,MUTED);
    if(t->valid){
     if(current<left)current=left;if(current>right)current=right;
     int a=current<from?current:from,b=current>from?current:from;
     if(a==b)b++;
     fill(a,by,b-a,3,colour);
     fill(current-1,by-3,2,9,TEXT);
    }
   }
  }
 }
 s->ground=0;(void)bar;
}
int fx_screen_active(void);
u32 fx_screen_bar(void);
int fx_screen_snapshot(u32*,u32*,int*);
int fx_screen_meter_snapshot(float*);
int fx_screen_select(void*,int,int);
static void segment(void *SURF,int x,int y,int ex,int ey,u32 colour){
 int dx=ex-x,dy=ey-y,sx=dx<0?-1:1,sy=dy<0?-1:1;
 if(dx<0)dx=-dx;if(dy<0)dy=-dy;int err=dx-dy;
 for(;;){fill(x,y,2,2,colour);if(x==ex&&y==ey)break;int e=2*err;if(e>-dy){err-=dy;x+=sx;}if(e<dx){err+=dx;y+=sy;}}
}
#if BENTO_FW!=168
static void fx_decimal(char *out,int value){
 char digits[12];u32 n=0,k=0;unsigned v;
 if(value<0){out[k++]='-';v=(unsigned)(-(value+1))+1u;}else v=(unsigned)value;
 do{digits[n++]=(char)('0'+v%10u);v/=10u;}while(v&&n<sizeof(digits));
 while(n)out[k++]=digits[--n];out[k]=0;
}
static void fx_db(char *out,int value){
 u32 k=0;if(value>0)out[k++]='+';fx_decimal(out+k,value);while(out[k])k++;out[k++]=' ';out[k++]='d';out[k++]='B';out[k]=0;
}
static void fx_value(char *out,int value,const char *suffix){
 fx_decimal(out,value);u32 k=0;while(out[k])k++;
 while(*suffix&&k<23)out[k++]=*suffix++;out[k]=0;
}
#endif
static __attribute__((noinline,section(".text.bank1b"))) u32 fx_gr_tenths(u32 bits){ /* R6.14: moved from .pad2 (bank-1 cave) */
 u32 exponent=(bits>>23)&255u;
 if((bits>>31)||!exponent||exponent>=134u)return exponent>=134u?1000u:0u;
 if(exponent<123u)return 0;
 u32 shift=150u-exponent;
 return ((((bits&0x7fffffu)|0x800000u)*10u+(1u<<(shift-1)))>>shift);
}
#if BENTO_FW!=168
static __attribute__((noinline,section(".stepstrings"))) void fx_gr_text(char *out,u32 bits){
 u32 exponent=(bits>>23)&255u;
 if(exponent>=134u){out[0]='>';out[1]='9';out[2]='9';out[3]=' ';out[4]='d';out[5]='B';out[6]=0;return;}
 u32 value=fx_gr_tenths(bits),k=0;fx_decimal(out,value/10u);while(out[k])k++;
 out[k++]='.';out[k++]=(char)('0'+value%10u);out[k++]=' ';out[k++]='d';out[k++]='B';out[k]=0;
}
static void fx_knobs(PG *s,void *bar,void *ctx){
 void *SURF=(void*)W(ctx,4);
 for(u32 i=0;i<8;i++){
  int x=6+159*(int)i;void *slot=(u8*)bar+0x38+i*0x468;
  char name[32],value[32];for(u32 j=0;j<31;j++){name[j]=B(slot,0x3f9+j);value[j]=B(slot,0xd9+j);}name[31]=value[31]=0;
  fill(x,8,159,68,BG);
  textf(s,ctx,x+4,8,151,28,name,TEXT,BIG,CENTRE);
  textf(s,ctx,x+4,34,151,30,value,TEXT,BIG,CENTRE);
 }
}
static void fx_section(PG *s,void *ctx,int x,int width,const char *name,int enabled,int active){
 void *SURF=(void*)W(ctx,4);
 u32 colour=enabled?TEXT:FAINT;
 textf(s,ctx,x+10,92,width-86,27,name,active?TEXT:MUTED,1,1);
 textf(s,ctx,x+width-72,92,62,28,enabled?"ON":"OFF",colour,BIG,2);
}
static int fx_eq_y(int top,int height,int db){
 if(db>12)db=12;if(db<-12)db=-12;
 return top+height/2-db*(height/2-8)/12;
}
static void fx_eq(PG *s,void *ctx,const int *v,u32 colour){
 void *SURF=(void*)W(ctx,4);int x=42,top=145,width=560,height=144,base=top+height/2;
 for(int i=-12;i<=12;i+=6){int y=fx_eq_y(top,height,i);fill(x,y,width,1,i?RULE:FAINT);}
 static const int offsets[7]={0,144,315,362,459,482,560};
 static const char *const freq[]={"20","120","1k","1.8k","6k","8k","20k"};
 int db[7]={v[2],v[2],0,v[4],0,v[7],v[7]};
 for(u32 i=0,qx=0,qy=0;i<7;i++){ /* q: the previous point */
  int px=x+offsets[i],py=fx_eq_y(top,height,db[i]);fill(px,top,1,height,RULE);
  if(i!=3&&i!=5)textf(s,ctx,px-30,296,60,28,freq[i],TEXT,BIG,CENTRE);
  if(i)segment(SURF,(int)qx,(int)qy,px,py,colour);
  qx=(u32)px;qy=(u32)py;
 }
 textf(s,ctx,14,top,24,28,"+",TEXT,BIG,CENTRE);
 textf(s,ctx,14,base-14,24,28,"0",TEXT,BIG,CENTRE);
 textf(s,ctx,14,top+height-28,24,28,"-",TEXT,BIG,CENTRE);
 static const int starts[3]={34,226,418},indices[3]={1,3,6},gains[3]={2,4,7};
 static const char *const bands[3]={"LOW SHELF","MID PEAK","HIGH SHELF"};
 for(u32 i=0;i<3;i++){
  char value[24];fx_value(value,v[indices[i]]," Hz");
  textf(s,ctx,starts[i],332,184,28,bands[i],TEXT,BIG,CENTRE);
  textf(s,ctx,starts[i],362,184,28,value,TEXT,BIG,CENTRE);
  fx_db(value,v[gains[i]]);textf(s,ctx,starts[i],392,184,28,value,colour,BIG,CENTRE);
 }
}
static void fx_compressor(PG *s,void *ctx,const int *v,u32 colour,int meter_valid,u32 meter_bits){
 void *SURF=(void*)W(ctx,4); int x=664,top=148,width=210,height=132,ratio=v[10]<1?1:v[10];
 for(int db=-60;db<=0;db+=20){int y=top+height-(db+60)*height/60;fill(x,y,width,1,db?RULE:FAINT);}
 for(int db=-60;db<=0;db+=20){int px=x+(db+60)*width/60;fill(px,top,1,height,RULE);}
 for(int i=0,qx=0,qy=0;i<=48;i++){ /* q: the previous point (same formula at i-1) */
  int input=-60+i*60/48,output=input<=v[9]?input:v[9]+(input-v[9])/ratio;
  int px=x+i*width/48,py=top+height-(output+60)*height/60;
  if(i)segment(SURF,qx,qy,px,py,colour);
  qx=px;qy=py;
 }
 textf(s,ctx,884,146,140,28,"GR (dB)",TEXT,BIG,CENTRE);
 fill(942,174,12,100,RAISED);
 if(meter_valid){
  u32 amount=fx_gr_tenths(meter_bits);if(amount>240u)amount=240u;
  u32 height=(amount*100u+120u)/240u;
  if(height)fill(942,274-(int)height,12,(int)height,colour);
  char reduction[24];fx_gr_text(reduction,meter_bits);
  textf(s,ctx,878,280,152,28,reduction,TEXT,BIG,CENTRE);
 }else textf(s,ctx,878,280,152,28,"Unavailable",FAINT,0,CENTRE);
 textf(s,ctx,662,332,172,28,"Threshold",TEXT,BIG,CENTRE);
 textf(s,ctx,844,332,172,28,"Ratio",TEXT,BIG,CENTRE);
 char value[24];fx_db(value,v[9]);textf(s,ctx,662,362,172,28,value,TEXT,BIG,CENTRE);
 fx_value(value,v[10],":1");textf(s,ctx,844,362,172,28,value,TEXT,BIG,CENTRE);
}
static void fx_clip(PG *s,void *ctx,const int *v,u32 colour){
 void *SURF=(void*)W(ctx,4);int x=1070,top=148,width=176,height=122;
 for(int i=0,qx=0,qy=0;i<=60;i++){ /* q: the previous point (same formula at i-1) */
  int input=-300+i*10,abs=input<0?-input:input,output;
  if(abs>30)output=input<0?-10:10;
  else output=input*(2700+input*input)/(2700+9*input*input);
  int px=x+i*width/60,py=top+height/2-output*height/26;
  if(i)segment(SURF,qx,qy,px,py,colour);
  qx=px;qy=py;
 }
 fill(x,top+height/2,width,1,RULE);fill(x+width/2,top,1,height,RULE);
 textf(s,ctx,x,332,width,28,"Ceiling",TEXT,BIG,CENTRE);
 char value[24];fx_db(value,v[17]);textf(s,ctx,x,362,width,28,value,TEXT,BIG,CENTRE);
}
static void track_fx_paint(PG *s,void *bar,void *ctx){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1))||!s)return;
 void *SURF=(void*)W(ctx,4);if(!SURF)return;
 u32 bank=0,track=0;int v[18];if(!fx_screen_snapshot(&bank,&track,v))return;
 s->ground=BG;fill(0,8,1280,423,BG);fx_knobs(s,bar,ctx);
 fx_section(s,ctx,16,610,"EQ",v[0],bank==0);
 fx_section(s,ctx,646,386,"Compressor",v[8],bank==1);
 fx_section(s,ctx,1052,212,"Soft Clip",v[16],bank==2);
 u32 colour=NFN(0x08140ebc,u32(*)(u32))(track); /* R6.9: native track palette */
 union {float value;u32 bits;} reduction={0};
 int meter_valid=fx_screen_meter_snapshot(&reduction.value);
 fx_eq(s,ctx,v,colour);fx_compressor(s,ctx,v,colour,meter_valid,reduction.bits);fx_clip(s,ctx,v,colour);
 s->ground=0;
}
#else
/* Run 17: Track FX v5 (owner, 13 Nov; reference design/native/native_trackfx.png, mk34.py = the drawing maths).
   Encoder row on top in the thin frame (dim labels, white values, section On/Off and Auto Makeup as switch A);
   three sections side by side, the selected one (Left/Right, tap) in the thin frame, nothing dimmed; graphs in the
   selected track's colour with dim native-size (24 px) scales and no value text under them:
     EQ          response of the three bands (log 20 Hz..20 kHz, +-12 dB) with a marker on each band,
     Compressor  static transfer curve, input and output on the same -60..0 dB scale, 1:1 reference, knee exactly at
                 Threshold, slope 1/Ratio above it, threshold marker, gain-reduction meter,
     Saturator   a 0 dBFS sine in (dim) and the signal out (track colour) through the real curve: Drive into Soft
                 (DaisySP SoftClip) or Hard (clamp), the automatic compensation (1/Drive) and Level; dim lines at the
                 clip level Drive and Level imply. */
void pg_switch(void*,int,int,int);
#define FX_FRAME 0xa6u /* thin frame A, owner's (110,118,120) */
#define FX_SCALE 0xa6u /* dim scale text and labels */
#define FX_MARK 0xb3u  /* threshold marker, darker than the grid */
/* Shared curve helper (run 17; also the FX views' pictures): y[i] at x+i*step, 2 px wide, gaps closed vertically. */
__attribute__((used,retain,noinline)) void pg_curve(void *SURF,int x,int n,int step,const short *y,u32 colour){
 for(int i=0;i<n;i++){int a=y[i],b=i?y[i-1]:a,lo=a<b?a:b,hi=a>b?a:b;fill(x+i*step,lo,step>2?step:2,hi-lo+2,colour);}
}
/* 10^(-d/20) in Q12 for d = 0..24 dB (Drive's compensation, Level). */
static const u16 db_q12[25]={4096,3651,3254,2900,2584,2303,2053,1830,1631,1453,1295,1154,1029,917,817,728,649,579,516,460,410,365,325,290,259};
static int fx_gain_q12(int db){return db>=0?(db>24?16777216/259:16777216/db_q12[db]):db_q12[-db>24?24:-db];}
static void fx_knobs(PG *s,void *bar,void *ctx){
 void *SURF=(void*)W(ctx,4);
 fill(0,0,1280,76,BG); /* run 19 (owner rule): no frame A around the encoder row - it is the only row of this view */
 for(u32 i=0;i<8;i++){
  int x=160*(int)i;u8 *slot=(u8*)bar+0x38+i*0x468;if(B(slot,0x30))continue;
  char name[32],value[32];for(u32 j=0;j<31;j++){name[j]=B(slot,0x3f9+j);value[j]=B(slot,0xd9+j);}name[31]=value[31]=0;
  textf(s,ctx,x+4,8,152,28,name,FX_SCALE,BIG,CENTRE);
  if(B(slot,0x9e)==6)pg_switch(SURF,x+58,40,value[0]=='O'&&value[1]=='n');
  else textf(s,ctx,x+4,36,152,28,value,TEXT,BIG,CENTRE);
 }
}
static void fx_scale(PG *s,void *ctx,int x,int top,int w,const char *t,u32 align){textf(s,ctx,x,top,w,28,t,FX_SCALE,BIG,align);}
/* EQ: x 56..610, y 132..380 (mk34). Response from the band settings (integer: f steps by 10^(3/554) per pixel). */
#define EQ_X 56
#define EQ_W 554
#define EQ_TOP 132
#define EQ_H 248
static void fx_eq(PG *s,void *ctx,const int *v,u32 colour){
 void *SURF=(void*)W(ctx,4);int mid=EQ_TOP+EQ_H/2;
 frame(EQ_X,EQ_TOP,EQ_W+1,EQ_H+1,1,RULE);fill(EQ_X,mid,EQ_W,1,RULE);
 static const short gx[3]={185,370,554};static const char *const gl[3]={"100","1k","10k"},*const dl[3]={"+12","0","-12"};
 for(u32 i=0;i<3;i++){fill(gx[i],EQ_TOP,1,EQ_H,RULE);fx_scale(s,ctx,gx[i]-40,386,80,gl[i],CENTRE);fx_scale(s,ctx,0,EQ_TOP-14+(int)i*EQ_H/2,EQ_X-8,dl[i],2u);}
 /* 1/(1+x^2) in Q16 from x in Q16: low shelf x = f/fl, high shelf 1 - that with x = f/fh, middle peak x = Q(f/fm - fm/f)
    (mk34 shapes); f steps by 10^(3/554) per pixel in Q16, so every ratio is one integer division. */
 short y[EQ_W];u32 f16=20u<<16;int mark[3]={-1,-1,-1};const int fc[3]={v[1],v[3],v[6]};
 for(int i=0;i<EQ_W;i++){
  unsigned long long w[3];
  for(u32 b=0;b<3;b++){
   unsigned long long r=f16/(u32)fc[b],x=r;if(r>(1u<<24))r=x=1u<<24;
   if(b==1){x=r>65536u?(r*r-(1ull<<32))/r:((1ull<<32)-r*r)/(r?r:1);if(x>(64u<<16))x=64u<<16;x=x*x/10000u*(unsigned)(v[5]*v[5]);}
   else x=x*x;
   w[b]=(1ull<<48)/((1ull<<32)+x);if(b==2)w[b]=65536u-w[b];
   if(mark[b]<0&&f16>>16>=(u32)fc[b])mark[b]=i;
  }
  int db=(int)(((long long)v[2]*(long long)w[0]+(long long)v[4]*(long long)w[1]+(long long)v[7]*(long long)w[2])>>16); /* tenths of a dB */
  y[i]=(short)(mid-db*EQ_H/240);
  f16=(u32)((unsigned long long)f16*66358u>>16);
 }
 pg_curve(SURF,EQ_X,EQ_W,1,y,colour);
 static const u8 ring[7]={6,6,6,5,5,4,2}; /* band marker: a 13 px ring (half widths per row) */
 for(u32 b=0;b<3;b++)if(mark[b]>=0){int mx=EQ_X+mark[b],my=y[mark[b]];
  for(int j=-6;j<=6;j++){int h=ring[j<0?-j:j],in=(j<0?-j:j)>=5?0:h-2;fill(mx-h,my+j,h-in,1,colour);fill(mx+in+1,my+j,h-in,1,colour);if(in>0)fill(mx-in,my+j,2*in+1,1,BG);}}
}
/* Compressor: transfer box x 660..880, y 132..380, both axes -60..0 dB; GR meter 892..912 (0..24 dB from the top). */
static void fx_compressor(PG *s,void *ctx,const int *v,u32 colour,int meter_valid,u32 meter_bits){
 void *SURF=(void*)W(ctx,4);int x=660,w=220,top=132,h=248,thr=v[9],ratio=v[10]<1?1:v[10];
 frame(x,top,w+1,h+1,1,RULE);
 {int tx=x+(thr+60)*w/60;fill(tx,top,1,h,FX_MARK);}
 for(int i=0;i<w;i++)fill(x+i,top+h-i*h/w,1,1,RULE); /* 1:1 reference */
 /* exact corners: two straight runs through the knee at (Threshold, Threshold) */
 {int kx=x+(thr+60)*w/60,ky=top+h-(thr+60)*h/60,ey=top+h-(thr+60+(0-thr)/ratio)*h/60;segment(SURF,x,top+h,kx,ky,colour);segment(SURF,kx,ky,x+w,ey,colour);}
 fx_scale(s,ctx,x+4,386,60,"-60",0u);fx_scale(s,ctx,x+w-80,386,80,"0 dB",2u);fx_scale(s,ctx,886,386,40,"GR",0u);
 frame(892,top,21,h+1,1,RULE);
 if(meter_valid){u32 amount=fx_gr_tenths(meter_bits);if(amount>240u)amount=240u;int gh=(int)(amount*246u/240u);if(gh)fill(894,top+2,17,gh,(colour&15u)|0x90u);}
}
/* Saturator: x 968..1262, y 132..380; two periods of a 0 dBFS sine. Out = Level*k*curve(sin/k), k = 10^(-Drive/20):
   Soft = DaisySP SoftClip (u(27+u^2)/(27+9u^2), +-1 beyond |u| 3), Hard = clamp at +-1. */
#define SAT_X 968
#define SAT_W 294
#define SAT_TOP 132
#define SAT_H 248
static int sat_sine(int i){u32 p=(u32)i*512u/SAT_W&255u;int t=(int)(p&127u),y=t*(128-t);return p&128u?-y:y;} /* parabolic sine +-4096, period SAT_W/2 */
static void fx_saturator(PG *s,void *ctx,const int *v,u32 colour){
 void *SURF=(void*)W(ctx,4);int mid=SAT_TOP+SAT_H/2,amp=SAT_H/2-8,packed=v[16],hard=packed>>1&1,level=(signed char)(packed>>8);
 int k=fx_gain_q12(-v[17]),g=fx_gain_q12(level),peak=k*g>>12; /* Q12 */
 frame(SAT_X,SAT_TOP,SAT_W+1,SAT_H+1,1,RULE);fill(SAT_X,mid,SAT_W,1,RULE);
 if(peak<4096)for(int sgn=-1;sgn<=1;sgn+=2)fill(SAT_X,mid-sgn*amp*peak/4096,SAT_W,1,0x63u);
 short yin[SAT_W/2],yout[SAT_W/2];
 for(int i=0;i<SAT_W/2;i++){
  int x=sat_sine(2*i),u=(int)((long long)x*4096/k),c; /* Q12 */
  if(hard)c=u>4096?4096:u<-4096?-4096:u;
  else if(u>3*4096||u<-3*4096)c=u<0?-4096:4096;
  else{long long u2=(long long)u*u>>12;c=(int)((long long)u*(27*4096+u2)/(27*4096+9*u2));}
  int o=(int)((long long)c*k>>12)*g>>12;if(o>4096)o=4096;if(o<-4096)o=-4096;
  yin[i]=(short)(mid-x*amp/4096);yout[i]=(short)(mid-o*amp/4096);
 }
 pg_curve(SURF,SAT_X,SAT_W/2,2,yin,0x52u);pg_curve(SURF,SAT_X,SAT_W/2,2,yout,colour);
}
static void track_fx_paint(PG *s,void *bar,void *ctx){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1))||!s)return;
 void *SURF=(void*)W(ctx,4);if(!SURF)return;
 u32 bank=0,track=0;int v[18];if(!fx_screen_snapshot(&bank,&track,v))return;
 s->ground=BG;fill(0,0,1280,431,BG);fx_knobs(s,bar,ctx);
 static const short bx[4]={4,636,944,1276};static const char *const title[3]={"EQ","Compressor","Saturator"};
 for(u32 i=0;i<3;i++)textf(s,ctx,bx[i]+14,82,240,28,title[i],TEXT,BIG,0u);
 if(bank<3)frame(bx[bank],76,bx[bank+1]-bx[bank]-(bank<2?7:0),349,1,FX_FRAME);
 u32 colour=NFN(0x08140ebc,u32(*)(u32))(track); /* R6.9: native track palette */
 union {float value;u32 bits;} reduction={0};
 int meter_valid=fx_screen_meter_snapshot(&reduction.value);
 fx_eq(s,ctx,v,colour);fx_compressor(s,ctx,v,colour,meter_valid,reduction.bits);fx_saturator(s,ctx,v,colour);
 s->ground=0;
}
#endif
static void track_fx_tick(void *bar,void *ctx){
 PG *s=state();if(!s||!ctx||!fx_screen_active()||(u32)bar!=fx_screen_bar())return;
 if(s->fx_valid&&TICK-s->fx_stamp<33u)return;s->fx_stamp=TICK;
 u32 bank=0,track=0;int v[18];if(!fx_screen_snapshot(&bank,&track,v))return;
 union {float value;u32 bits;} reduction={0};
 u32 meter_valid=(u32)fx_screen_meter_snapshot(&reduction.value);
 u32 words[22];words[0]=bank;words[1]=track;for(u32 i=0;i<18;i++)words[i+2]=(u32)v[i];
 words[20]=meter_valid;words[21]=meter_valid?reduction.bits:0;
 u32 hash=snapshot_hash(words,sizeof(words));
 if(!s->fx_valid||s->fx_hash!=hash){s->fx_hash=hash;s->fx_valid=1;B(ctx,1)=1;}
}
void pg_fx_touch_down(void *bar,void *point){
 PG *s=state();if(!s||!point||(u32)bar!=fx_screen_bar())return;
 s->fx_touch=1;s->fx_x=(int)W(point,0);s->fx_y=480-(int)W(point,4);
}
void pg_fx_touch_up(void *bar,void *point){
 PG *s=existing();if(!s||!s->fx_touch)return;s->fx_touch=0;
 if(!point||(u32)bar!=fx_screen_bar())return;
 int x=(int)W(point,0),top=480-(int)W(point,4);
 int dx=x-s->fx_x,dy=top-s->fx_y;if(dx<0)dx=-dx;if(dy<0)dy=-dy;
 if(dx<=30&&dy<=30)fx_screen_select(bar,x,top);
}
static void macro_editor_tick(void *bar,void *ctx){
 if(!ctx||perf_bar_kind(bar)!=3)return;PG *s=existing();if(!s){B(ctx,1)=1;return;}
 if(TICK-s->perform_stamp<100u)return;s->perform_stamp=TICK;
 u32 selected=perf_macro_focus(-1),edit=(u32)perf_macro_targets();
 if(s->perform_controls!=edit){B(ctx,1)=1;s->perform_controls=edit;}
 for(u32 i=0;i<8;i++){
  MacroDisplay d;macro_snapshot(i,&d);
  u32 h=snapshot_hash(&d,sizeof(d))^(selected==i?0x80000000u:0);
  if(!(s->perform_valid&(1u<<i))||s->perform_hash[i]!=h){B(ctx,1)=1;s->perform_hash[i]=h;s->perform_valid|=1u<<i;}
 }
}
/* Run 18 (owner, 13 Nov; reference design/native/native_perform.png, perform/mk29.py): Perform without the macro
   row. Row 0 (no encoders, our drawing): the 8 track names in their colours (selected: bold, full colour, a bar
   under it; tap or Left/Right select, perf_ui.c), the project key, the played chord's name (big, track colour;
   dimmed after release) and its notes, and a two-octave piano at its full height (130 px, held notes in the track
   colour, window follows the played notes; the piano/chord naming of 7b8b128, piano keys from a 12-note pattern).
   Rows 1/2 (Chord, Arp): 8 cells at the native 24 px, dim labels, white values; true two-state cells (and Arp
   Off/On) as switch style A without text; the active row in the thin frame A, the other dimmed. */
void pg_switch(void*,int,int,int);
int chord_keys_snapshot(u32,u32*,u32*,u32*);
int perf_notes_name(u32,const u32*,char*);
#define PERF_FRAME 0xa6u /* thin frame A (owner's ~(110,118,120)) */
static int key_on(const u32 *notes,u32 pitch){return pitch<128&&(notes[pitch>>5]>>(pitch&31u))&1u;}
static void pitch_text(char *out,u32 pitch){
 static const char *const names[12]={"C","C#","D","D#","E","F","F#","G","G#","A","A#","B"};
 const char *p=names[pitch%12];u32 n=0;while(*p)out[n++]=*p++;
 int octave=(int)(pitch/12)-1;if(octave<0){out[n++]='-';octave=-octave;}
 out[n++]=(char)('0'+octave);out[n]=0;
}
static const char *desc_name(u32 key,u32 value){ /* a value's name from the native registry descriptor */
 u32 r=W((void*)0x30031484u,0);if(!r)return "";const char *const *t=(const char *const*)W((void*)(r+key*32),8);
 return t&&value<W((void*)(r+key*32),12)?t[value]:"";
}
static u32 perf_project(u32 *root,u32 *scale){
 u32 h=0;*root=*scale=0;if(!NFN(0x08133e54,int(*)(void*,u32*))(MODEL,&h)||!h)return 0;
 NFN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,0x8eu,root);NFN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,0x8du,scale);
 return *root|*scale<<8|1u<<16;
}
/* Last held notes stay (dimmed) after the release; a new track forgets them. */
static u32 keys_poll(PG *s){
 u32 owner=0,notes[4],held=0,root=128,any=0;
 NFN(0x08133cfc,int(*)(void*,u32*))(MODEL,&owner);
 if(s->keys_owner!=owner){s->keys_owner=owner;s->keys_held=s->keys_valid=0;zero(s->keys_notes,sizeof(s->keys_notes));s->keys_name[0]=s->keys_list[0]=0;}
 if(chord_keys_snapshot(owner,notes,&held,&root)){
  for(u32 i=0;i<4;i++)any|=notes[i];
  if(any)for(u32 i=0;i<4;i++)s->keys_notes[i]=notes[i];
  s->keys_held=held&&any?held:0;s->keys_root=root;s->keys_valid=1;
 }
 u32 r,sc;return snapshot_hash(s->keys_notes,sizeof(s->keys_notes))^s->keys_owner^(s->keys_held*31u)^(s->keys_root<<16)^s->keys_valid^perf_project(&r,&sc)*977u^perf_display_state(0)*7919u;
}
static void perform_top(PG *s,void *ctx){
 void *SURF=(void*)W(ctx,4);u32 sel=(perf_display_state(0)>>8)&7u,colour=NFN(0x08140ebc,u32(*)(u32))(sel);
 fill(0,0,1280,200,BG);
 for(u32 i=0;i<8;i++){
  u32 h=0;char name[32];
  if(!NFN(0x08133960,int(*)(void*,u32,u32*))(MODEL,i,&h)||!h)continue;
  ui_name(&h,name); /* run 19: never the raw getter into a short buffer (it writes 256 bytes) */
  u32 c=NFN(0x08140ebc,u32(*)(u32))(i);
  textf(s,ctx,160*(int)i,2,160,28,name,i==sel?c:(c&15u)|0x90u,i==sel?1u:BIG,CENTRE);
  if(i==sel)fill(160*(int)i+14,30,133,3,c);
 }
 /* Key, chord name, notes (left, centred on x 190) */
 u32 root,scale;char line[48];u32 k=0;
 if(perf_project(&root,&scale)){const char *p="Key ";while(*p)line[k++]=*p++;p=desc_name(0x8eu,root);while(*p&&k<20)line[k++]=*p++;line[k++]=' ';p=desc_name(0x8du,scale);while(*p&&k<46)line[k++]=*p++;}
 line[k]=0;textf(s,ctx,20,44,340,28,line,MUTED,BIG,CENTRE);
 u32 first=128,last=0,total=0;
 for(u32 p=0;p<128;p++)if(key_on(s->keys_notes,p)){if(first==128)first=p;last=p;total++;}
 if(total){
  if(s->keys_held){
   u32 n=0;
   for(u32 p=first;p<=last;p++)if(key_on(s->keys_notes,p)){char note[6];pitch_text(note,p);u32 j=0;while(note[j])j++;
    if(n+j+5>=sizeof(s->keys_list)){s->keys_list[n++]=' ';s->keys_list[n++]='.';s->keys_list[n++]='.';break;}
    if(n)s->keys_list[n++]=' ';for(u32 q=0;q<j;q++)s->keys_list[n++]=note[q];}
   s->keys_list[n]=0;zero(s->keys_name,sizeof(s->keys_name));
   if(total==1)pitch_text(s->keys_name,first);
   else if(!(s->keys_held==1&&perf_notes_name(s->keys_root,s->keys_notes,s->keys_name))){const char *p="Notes";for(u32 i=0;p[i];i++)s->keys_name[i]=p[i];}
  }
 }
 u32 live=s->keys_held!=0,c=live?colour:(colour&15u)|0x70u;
 textf(s,ctx,20,70,340,64,s->keys_name[0]?s->keys_name:"--",s->keys_name[0]?c:FAINT,2u,CENTRE);
 textf(s,ctx,20,136,340,28,s->keys_list,live?MUTED:FAINT,BIG,CENTRE);
 /* Piano: 14 white keys of 58 px from x 400, top 46, 130 px high; the window starts at the lowest held C. */
 if(total){s->keys_stamp=first/12*12;if(s->keys_stamp>104)s->keys_stamp=104;}else if(!s->keys_stamp)s->keys_stamp=60;
 u32 lo=s->keys_stamp;
 static const u8 white[7]={0,2,4,5,7,9,11},black[5]={1,3,6,8,10},after[5]={0,1,3,4,5};
 for(u32 i=0;i<14;i++){
  u32 pitch=lo+12*(i/7)+white[i%7],on=key_on(s->keys_notes,pitch);int x=400+(int)i*58;
  fill(x,46,55,131,on?c:RULE);
  if(i%7==0){char label[6];pitch_text(label,pitch);s->ground=on?c:RULE;textf(s,ctx,x+2,154,51,20,label,on?BG:MUTED,SMALL,CENTRE);s->ground=0;}
 }
 for(u32 i=0;i<10;i++){
  u32 pitch=lo+12*(i/5)+black[i%5],on=key_on(s->keys_notes,pitch);int x=400+(int)((i/5)*7+after[i%5]+1)*58-17;
  fill(x-1,46,37,80,BG);fill(x+1,46,33,78,on?c:0x12u);
 }
}
static void perform_row(void *bar,void *ctx){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 PG *s=state();if(!s||!W(ctx,4))return;s->ground=0;
 u32 h=keys_poll(s); /* a settled partial paint repeats nothing */
 if(!B(ctx,0)&&(s->perform_valid&256u)&&h==s->keys_hash&&s->perform_bar==W(bar,0x2c))return;
 s->perform_bar=W(bar,0x2c);s->keys_hash=h;perform_top(s,ctx);s->perform_valid|=256u;
}
static void perform_controls(void *bar,void *ctx,int kind){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 PG *s=state();void *SURF=(void*)W(ctx,4);if(!s||!SURF)return;
 int top=kind==4?206:314,active=((perf_display_state(0)>>16)&3u)==(u32)kind-3u;
 u32 h=snapshot_hash((u8*)bar+0x38,4)^(u32)active;
 for(u32 i=0;i<8;i++)h=h*31u^snapshot_hash((u8*)bar+0x38+i*0x468+0xd9,24)^H((u8*)bar+0x38+i*0x468,0x9c)^B((u8*)bar+0x38+i*0x468,0x30);
 if(!B(ctx,0)&&(s->perform_valid&(1u<<kind))&&s->perform_hash[kind-4]==h)return;
 s->perform_valid|=1u<<kind;s->perform_hash[kind-4]=h;
 s->ground=BG;fill(0,top,1280,89,BG);
 for(u32 i=0;i<8;i++){
  u8 *slot=(u8*)bar+0x38+i*0x468;if(B(slot,0x30)||!H(slot,0x9c))continue;
  char name[32],value[32];
  for(u32 j=0;j<31;j++){name[j]=B(slot,0x3f9+j);value[j]=B(slot,0xd9+j);}name[31]=value[31]=0;
  const char *label=name;if(name[0]=='A'&&name[1]=='r'&&name[2]=='p'&&name[3]==' ')label+=4; /* "Arp Mode" -> "Mode" */
  int x=160*(int)i;
  textf(s,ctx,x,top+6,160,28,label,active?MUTED:0xa6u,BIG,CENTRE);
  if(B(slot,0x9e)==6||(H(slot,0x9c)==0xa6u&&value[0]=='O'))pg_switch(SURF,x+58,top+40,value[0]=='O'&&value[1]=='n');
  else textf(s,ctx,x,top+36,160,28,value,active?TEXT:0xb2u,BIG,CENTRE);
 }
 if(active)frame(4,top,1272,89,1,PERF_FRAME);
 s->ground=0;
}
void pg_perform_tick(void *bar,void *ctx){
 if(!ctx)return;
 if(fx_screen_active()&&(u32)bar==fx_screen_bar()){track_fx_tick(bar,ctx);return;}
 if(!perf_bar_kind(bar))return;
 if(perf_bar_kind(bar)==3){macro_editor_tick(bar,ctx);return;}
 PG *s=existing();if(!s){B(ctx,1)=1;return;}
 if(perf_bar_kind(bar)!=1)return;
 if(TICK-s->perform_stamp<33u)return;s->perform_stamp=TICK;
 if(!(s->perform_valid&256u)||keys_poll(s)!=s->keys_hash)B(ctx,1)=1;
}
#include "kit_seq.h"
#ifdef BENTO_SYNCUSSION
int drum_panel(void*,u32*);
const char *drum_panel_label(u32,u32);
void drum_panel_cancel_touch(void){
 PG *s=existing();if(s)s->sync_valid=0;
}
/* The six engine symbols of the engine row (R6.3/R6.4; display only since R6.5). */
static STEP_DRAW void panel_button(void *bar,u32 n,int *r){
 int x=(int)W(bar,4),top=480-(int)W(bar,8)-(int)W(bar,16);
 r[0]=x+10+(int)n*159;r[1]=top+30;r[2]=157;r[3]=40;
}
/* R6.4 (owner: engine taps ignored until the page is re-entered; a touch at the
 * very top lights a white rectangle): the whole engine row belongs to us. Taps
 * off a button are swallowed (fader focus stays pinned), so the native focus
 * never takes the row. */
__attribute__((used,retain)) int drum_panel_point(void *widget,void *point,void **out){
 if(!point||drum_panel(widget,0)!=2)return 0;
 int x=(int)W(point,0),y=(int)W(point,4),rx=(int)W(widget,4),ry=(int)W(widget,8),rw=(int)W(widget,12),rh=(int)W(widget,16);
 if(x<rx||x>=rx+rw||y<ry||y>=ry+rh)return 0;*out=widget;return 1;
}
void drum_panel_focus_fix(void);
__attribute__((used,retain)) int drum_panel_touch(void *bar,void *point,u32 id,int phase){
 if(kit_seq_holding())return kit_seq_strip_touch(bar,point,id,phase);
 u32 values[11];int row=drum_panel(bar,values);if(row==1&&phase==2)drum_panel_focus_fix(); /* R6.5 */
 if(row!=2)return 0;
 /* R6.5 (owner): engine switching on this screen is unreliable on hardware; the row stays visible but
  * untouchable (switch by loading a drum synth from the one-shot INST page). Every touch on the row is
  * swallowed; the press keeps the fader focus pinned. Run 14: the unreachable tap code is gone. */
 (void)id;if(!point)return 0;
 if(!phase)drum_panel_focus_fix();
 return 1;
}
static void drum_symbol(void *SURF,int x,int top,u32 engine,u32 colour){
 static const u32 masks[6][24]={ /* R6.3: [5] Metal (cymbal) */
  {0,0x0007e000,0x001ff800,0x00381c00,0x00600600,0x00c3c300,0x018c3180,0x01900980,0x031008c0,0x032004c0,0x032004c0,0x032004c0,0x032004c0,0x031008c0,0x01900980,0x018c3180,0x00c3c300,0x0160c600,0x03b8dc40,0x071ff8e0,0x0607e070,0x0e00c030,0x1c00c038,0x0800fc1c},
  {0x010001e0,0x01c00380,0x00700f00,0x001c3c00,0x003ffc00,0x03ffffc0,0x07c7e3e0,0x1c023838,0x18000e18,0x1c0003b8,0x1fc003f8,0x1bffffd8,0x183ffc18,0x19010118,0x18808098,0x18808098,0x18404058,0x18404058,0x18202038,0x1c202078,0x070000e0,0x01ffffc0,0x007fff00,0},
  {0,0x0000c000,0x0000c000,0x0000c000,0x0001c000,0x0007c000,0x001c7000,0x00f03e00,0x3ffffffc,0x3ffffffc,0x20000004,0x0003e000,0x007fff00,0x1f8001f8,0x1000c008,0x0000c000,0x0000c000,0x0000c000,0x0000c000,0x0000c000,0x0000c000,0x0003e000,0x000ef800,0x00380e00},
  {0x00000020,0x000000c0,0x00000100,0x000c0000,0x00fc0003,0x00c6600c,0x03c7efc0,0x07c63fc0,0x0ec63cc0,0x0cc73c60,0x0ce31c67,0x06631c60,0x06631c60,0x2e638c60,0x7e738c30,0xef700c30,0xc7000630,0x63800630,0x61000660,0x30000c60,0x30000c60,0x18000cc0,0x180018c0,0x00001800},
  {0,0x001ff800,0x00ffff00,0x01e00780,0x030000c0,0x06000060,0x06000060,0x070000e0,0x07e007e0,0x06ffff60,0x031ff860,0x03300360,0x03300360,0x03300360,0x03180360,0x03180360,0x01980660,0x01980660,0x018c0660,0x018c06e0,0x01cc07c0,0x00f00380,0x003fff00,0x001ffe00}
  ,{0x80000,0x80000,0x80000,0xc0000,0x1e0000,0x1e0003,0x3f000f,0x3f000f,0x73803c,0xe3803c,0xe1c0f0,0x1c1c0f0,0x1c0e000,0x380e000,0x3807000,0x7003000,0xe003800,0xe001c00,0x1c001c00,0x1c000e00,0x18000e00,0x3ffff00,0x3ffff00,0x0} /* R6.4: Metal = percussion triangle + beater */
 };
 for(u32 row=0;row<24;row++)for(u32 at=0;at<32;){
  if(!(masks[engine][row]&(0x80000000u>>at))){at++;continue;}
  u32 first=at++;while(at<32&&(masks[engine][row]&(0x80000000u>>at)))at++;
  fill(x+(int)first,top+(int)row,(int)(at-first),1,colour);
 }
}
/* A bounded, illustrative shape: no audio sampling or DSP work on the UI core. */
static void drum_shape(void *SURF,int x,int cy,u32 model,const u32 *v,u32 colour){
 int length=28+(int)v[1]*96/100,phase=0,previous=0;
 int tune=drum_family(model)==1?((int)v[0]-25)*100/155:(int)v[0];
 fill(x,cy,248,1,RULE);
 for(int i=0;i<124;i++){
  int envelope=i<length?(length-i)*16/length:0;
  int rate=3+tune/10;
  if(model==1||model==9){
   int sweep=8+(int)v[5];if(i<sweep)rate+=(int)v[4]*(sweep-i)/sweep/5;
  }
  phase+=rate;int triangle=(phase&63)<32?(phase&63)-16:48-(phase&63);
  int noise=(int)(((u32)phase*1103515245u+12345u)>>16&31u)-16;
  int body=triangle+((triangle<0?-16:16)-triangle)*(int)v[2]/200;
  if(model==3)body=(body*(100-(int)v[4])+noise*(int)v[4])/100;
  if(model==5)body=(body*(100-(int)v[4])+noise*(70+(int)v[4]))/170;
  if(model==7){int gap=4+(int)v[4]/5;body=(noise*(100+(int)v[2])+triangle*(100-(int)v[2]))/200;if(i<3*gap)envelope=envelope*(gap-i%gap)/gap;}
  if(model==9)body=(body*(100-(int)v[6])+noise*(int)v[6])/100;
  if(model==1&&i<5)body+=noise*(int)v[7]/100;
  if(model==1&&i<8)envelope+=((int)v[6]*(8-i))/50;
  int y=body*envelope*(60+(int)v[3])/1600;
  if(y>17)y=17;if(y<-17)y=-17;
  int lo=y<previous?y:previous,hi=y>previous?y:previous;
  fill(x+i*2,cy+lo,2,hi-lo+2,colour);previous=y;
 }
}
static STEP_DRAW void step_strip_paint(PG *s,void *ctx,void *bar,u32 model,u32 colour,const KitStep *step){
 (void)s;(void)model;(void)colour;(void)step;
 for(u32 i=0;i<8;i++){
  void *slot=(u8*)bar+0x38+i*0x468;
  if(B(slot,0x30))continue;
  FN(W((void*)W(slot,0),8),void(*)(void*,void*,void*))(slot,ctx,(u8*)bar+4);
 }
}
extern unsigned kit_seq_signature(void);extern int kit_seq_value(unsigned,int,int*);
/* Fader readout: number, unit (1 " Hz", 2 "%"), then the lock-state prefix. */
static int panel_value(char *value,u32 n,u32 unit,u32 key,int raw){
 number(value,n);u32 at=0;while(value[at])at++;
 if(unit==1){value[at++]=' ';value[at++]='H';value[at++]='z';}else if(unit==2)value[at++]='%';
 value[at]=0;
 int status=0;kit_seq_value(key,raw,&status);
 if(status==1||status==2){for(u32 j=at+1;j;j--)value[j]=value[j-1];value[0]=status==2?'*':'=';}
 return status;
}
static void panel_paint(void *bar,void *ctx){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1))||!W(ctx,4))return;
 PG *s=state();if(!s)return;u32 values[11];int row=drum_panel(bar,values);if(!row)return;
 drum_panel_focus_fix(); /* R6.5: focus box stays on the selected row */
 u32 model=values[10];
 /* 0x131 is the native selected-track property key, not a model byte offset. */
 u32 track=NFN(0x0812dc74,u32(*)(void*,u32))((u8*)MODEL+4,0x131);
 u32 colour=track<8?NFN(0x08140ebc,u32(*)(u32))(track):TEXT;
 u32 hash=snapshot_hash(values,sizeof(values))^(u32)bar^(colour<<24)^kit_seq_signature();
 if(s->sync_view!=W(bar,0x2c)){s->sync_view=W(bar,0x2c);s->sync_valid=0;}
 u32 bit=1u<<(row-1);
 if(!B(ctx,0)&&(s->sync_valid&bit)&&s->sync_hash[row-1]==hash)return;
 void *SURF=(void*)W(ctx,4);int x=(int)W(bar,4),top=480-(int)W(bar,8)-(int)W(bar,16);
 const int mix=0; /* the switch row is hidden under Mix */
 fill(x,top,W(bar,12),W(bar,16),BG);s->ground=0;
 if(row==2&&top>0)fill(x,0,W(bar,12),top,BG); /* R6.5: the Mix strip (top, 73 px) leaves nothing above the engine row */
 KitStep step;if(row==2&&kit_seq_strip_snapshot(bar,&step)){step_strip_paint(s,ctx,bar,model,colour,&step);goto painted;}
 if(row==2)for(u32 i=0;i<6u;i++){ /* Run 15 Clean: the engine shown gets the thin frame A, the others are dimmed */
  int r[4];panel_button(bar,i,r);
  int on=model==(i==5?15u:1+2*i);
  if(on)frame(r[0],r[1],r[2],r[3],1,0xa6u); /* run 18: frame A in the lighter A6 (owner ~(110,118,120)) */
  drum_symbol(SURF,r[0]+r[2]/2-16,r[1]+8,i,on?colour:MUTED);
 }
 if(row==1){
  /* Run 15 (owner: drum synth screen in the Clean look, table-driven): one layout for every engine incl. Metal.
     Section headings = name index<<4 | span in columns, consecutive from column 0. Run 16 (OWNER RULE, no normal
     text below the native 24 px; design/native/native_settings_drum.png): titles in the track colour, labels dim,
     values white, all Rajdhani 24 (font 0); no lines; the fader picture is unchanged. */
  static const char *const heads[]={"Body","Sweep","Transient","Snares","Noise","Spread","Drive","Tune","Envelope / Filter","Pitch Sweep","Pitch LFO + S&H"};
  static const u8 groups[6][4]={{0x04,0x12,0x22},{0x04,0x31},{0x04,0x41},{0x04,0x51},{0x04,0x12,0x61},{0x71,0x83,0x92,0xa2}};
  const u8 *g=groups[model==15?5:(model-1)>>1] /* panel models 1,3,5,7,9,15 */;
  for(u32 i=0,at=0;i<4&&g[i];at+=g[i]&15u,i++)
   text_cached(s,ctx,50+i,x+(int)at*159+14,top+5,(int)(g[i]&15u)*159-28,26,heads[g[i]>>4],colour,BIG,1);
  int metal=model==15;u32 count=model==1||metal?8:drum_count(model);
  for(u32 i=0;i<count;i++){
   int col=x+159*(int)i;u32 index=metal&&i?(i==1?8:i-1):i; /* Metal: Tune, Attack, then its six controls */
   int amount=(int)values[index];
   if(!i&&drum_family(model)==1)amount=(amount-25)*100/155;
   text_cached(s,ctx,i*2,col+4,top+41,150,26,drum_panel_label(model,index),MUTED,BIG,CENTRE);
   int handle=top+82+(100-amount)*158/100;
   fill(col+68,top+78,22,178,BG);
   fill(col+77,top+82,4,168,RULE);
   fill(col+75,handle+5,8,top+250-handle-5,(colour&15u)|0x80u);
   for(u32 tick=0;tick<9;tick++){
    int y=top+82+(int)tick*20;
    fill(col+56,y,6,1,RULE);fill(col+96,y,6,1,RULE);
   }
   fill(col+60,handle+2,38,10,BG);
   fill(col+60,handle,38,10,TEXT);
   fill(col+64,handle+4,30,2,colour);
   char value[24];int status=panel_value(value,i?values[index]:drum_tune_hz(model,values[0]),i?(metal?0:2):1,(metal?i==1:i==7)?NKEY(0x1b0u):kick_keys[index],(int)values[index]);
   text_cached(s,ctx,i*2+1,col+6,top+260,146,26,status==3?"Mixed":status==5?"Empty":status==4&&metal?"No lock":value,TEXT,BIG,CENTRE);
  }
  s->ground=0;
 }
 if(row==2){ /* R6.3: Metal (15) shows its name and ENGINE like the other drums */
  if(!mix){
   text_cached(s,ctx,54,x+1000,top-2,248,26,drum_name(model),colour,BIG,1); /* Run 16: native size, no "ENGINE" title (reference) */
  }
  if(model!=15)drum_shape(SURF,x+1000,top+49,model,values,colour);
 }
painted:
 s->sync_hash[row-1]=hash;s->sync_valid|=bit;
}
/* R6.4 (owner): the drum Mix strip is painted natively, like every other header strip. */
#endif
__attribute__((used,retain)) void pg_bar_paint(void *bar,void *ctx){
#ifdef BENTO_SYNCUSSION
 int sync=drum_panel(bar,0);
 if(sync==1||sync==2){panel_paint(bar,ctx);return;}
#endif
 if(fx_screen_active()&&(u32)bar==fx_screen_bar()){track_fx_paint(state(),bar,ctx);return;}
 int kind=perf_bar_kind(bar);if(kind==3){macro_editor(state(),bar,ctx);return;}if(kind==1){perform_row(bar,ctx);return;}
 if(kind>=4){perform_controls(bar,ctx,kind);return;}
 if(output_view(bar))output_row(bar,ctx);
 else NFN(0x0816faec,void(*)(void*,void*))(bar,ctx);
}
__attribute__((used,retain)) void pg_bar_walk(void *bar,void *ctx,void *clip){
#ifdef BENTO_SYNCUSSION
 int sync=drum_panel(bar,0);if(sync==1||sync==2)return;
#endif
 if(fx_screen_active()&&(u32)bar==fx_screen_bar())return;
 int kind=perf_bar_kind(bar);if(kind)return;
 if(output_view(bar))output_row(bar,ctx);
 else NFN(0x0816f9e8,void(*)(void*,void*,void*))(bar,ctx,clip);
}
/* Run 15 item C step 2 (owner, 13 Nov): the shared native SectionGroup (vtable slots 0 and 2, port/clean_blocks.py)
   in the Clean look. Run 16 (OWNER RULE: no normal text below the native 24 px; design/native/native_settings_drum.png):
   tick (before the native tick, so the labels re-render before the first paint): section titles and cell names keep
   the native 24 px font and their native text, drawn dim (F6); values stay native (white, selection brightness);
   native value sliders keep their visibility (not touched). Walk: two-state cells (type +9E == 6, On/Off) show switch
   style A (design/switch_styles.png: 1 px outline pill 45x21, 13 px knob; On = white, knob right; Off = grey, knob
   left; no fill) instead of the text; the value label is hidden for the native walk only (restored after it).
   Groups whose bars we draw (drum panel, Perform/Macro, Track FX, outputs) stay native. No lines (title bars and the
   bottom separator are off by the step 1 constants). */
#include "port/clean_native.h"
static int sg_own(void *g){
 u32 n=W(g,0x204);if(n>4||B(g,0x30))return 1;
 for(u32 i=0;i<n;i++){void *bar=(void*)W(g,0x34+4*i);if(bar&&(perf_bar_kind(bar)||drum_panel(bar,0)||output_view(bar)||(fx_screen_active()&&(u32)bar==fx_screen_bar())))return 1;}
 return 0;
}
static void sg_dim(u8 *l){if(!B(l,0x30)&&(B(l,0x55)!=BIG||B(l,0x53)!=MUTED)){NFN(0x0817e810,void(*)(void*,u32))(l,BIG);B(l,0x53)=MUTED;B(l,0x5c)=1;}} /* +5C: re-render */
__attribute__((used,retain)) void pg_sg_tick(void *g,void *ctx){
 if(!sg_own(g))for(u32 i=0,n=W(g,0x204);i<n;i++){
  u8 *bar=(u8*)W(g,0x34+4*i);sg_dim((u8*)g+0x44+i*0x70);
  for(u32 k=0;bar&&k<8;k++){u8 *c=bar+0x38+k*0x468;if(!B(c,0x30))sg_dim(c+0x3c8);}
 }
 ((void(*)(void*,void*))(SG_NATIVE_TICK|1u))(g,ctx); /* not translated: the address comes from port/clean_native.h */
 /* Run 19 (owner rule, exp8 hardware): the row frame only shows when there are several rows to choose from. With
    fewer than two visible sections the native selection frame (+208) is hidden (+30 = 2: hidden by this rule, so
    it comes back when a second row appears, e.g. Mod FX -> Send FX). */
 {u32 shown=0;for(u32 i=0,n=W(g,0x204);i<n&&i<8u;i++){u8 *bar=(u8*)W(g,0x34+4*i);if(bar&&!B(bar,0x30))shown++;}
  u8 *f=(u8*)g+0x208;if(shown<2u)B(f,0x30)=2;else if(B(f,0x30)==2)B(f,0x30)=0;}
}
/* Switch style A at (x,top), 45x21: rounded outline (radius 10, row insets) and a 13 px knob. */
__attribute__((used,retain,noinline)) void pg_switch(void *SURF,int x,int top,int on){
 static const u8 ins[11]={7,5,3,2,2,1,1,0,0,0,0},kn[7]={6,6,6,5,5,4,2};
 u32 c=on?TEXT:0xa6u; /* Off grey (106,113,112) ~ owner's (110,116,118) */
 for(int r=0;r<21;r++){
  int d=r<=10?r:20-r,a=ins[d],b=d?(ins[d-1]>a+1?ins[d-1]-1:a):44-a;
  fill(x+a,top+r,b-a+1,1,c);if(d)fill(x+44-b,top+r,b-a+1,1,c);
 }
 for(int j=-6;j<=6;j++){int h=kn[j<0?-j:j];fill((on?x+33:x+11)-h,top+10+j,2*h+1,1,c);}
}
__attribute__((used,retain)) void pg_sg_walk(void *g,void *ctx,void *clip){
 u8 *pills[32];u32 count=0;
 if(!sg_own(g))for(u32 i=0,n=W(g,0x204);i<n;i++){
  u8 *bar=(u8*)W(g,0x34+4*i);if(bar&&B(bar,0x30))continue; /* Run 16: hidden rows (FX views) draw no switch */
  for(u32 k=0;bar&&k<8;k++){
   u8 *c=bar+0x38+k*0x468,*value=c+0xa8;
   if(!B(c,0x30)&&B(c,0x9e)==6&&!B(value,0x30)&&count<32){B(value,0x30)=1;pills[count++]=value;}
  }
 }
 NFN(0x0816f9e8,void(*)(void*,void*,void*))(g,ctx,clip);
 void *SURF=ctx?(void*)W(ctx,4):0;
 for(u32 i=0;i<count;i++){
  u8 *v=pills[i];B(v,0x30)=0;if(!SURF)continue;
  int lx=(int)W(v,4),lw=(int)W(v,12),lh=(int)W(v,16),ly=480-(int)W(v,8)-lh;
  fill(lx,ly,lw,lh,BG); /* the value text area (no On/Off text next to the switch) */
  pg_switch(SURF,lx+lw/2-22,ly+lh/2-10,B(v,0x31)=='O'&&B(v,0x32)=='n');
 }
}
/* Run 16: native-size (24 px) centred text for the FX views (port/fxv_ui.c), through the cached labels. */
__attribute__((used,retain,noinline)) void pg_text(void *ctx,u32 index,int x,int top,int w,const char *str,u32 colour){
 PG *s=state();if(s&&ctx)text_cached(s,ctx,index,x,top,w,26,str,colour,BIG,CENTRE);
}
__attribute__((used,retain)) void pg_tracks_tick(void *view,void *ctx){
 NFN(0x08160a20,void(*)(void*,void*))(view,ctx);
 PG *s=existing();if(!s)return;
 if(ctx)for(u32 i=0;i<8;i++){
  void *col=(u8*)view+0x34+i*COLUMN_STRIDE;TrackPaint next;
  track_snapshot(col,view,i,&next,&s->tracks[i]);next.type=s->tracks[i].type;
  int changed=s->tracks_view!=(u32)view||!(s->tracks_valid&(1u<<i))||
   !equal(&next,&s->tracks[i],__builtin_offsetof(TrackPaint,meter));
  for(u32 k=0;k<2;k++)if((next.handle?meter_width(W(col,0x31c+k*0x4c),92):0)!=s->tracks[i].meter[k])changed=1;
  if(changed)B(ctx,1)=1;
 }
 if(s->output_stamp==TICK)return;s->output_stamp=TICK;
 for(u32 i=0;i<4;i++){
  u16 channel=(u16)(8+i);u32 left=0xc2700000u,right=left; /* -60 dB */
  if(!NFN(0x08138164,int(*)(void*,u16*,u32*,u32*))(MODEL,&channel,&left,&right))left=right=0xc2700000u;
  if(s->outputs[i][0]!=left||s->outputs[i][1]!=right){s->outputs[i][0]=left;s->outputs[i][1]=right;if(ctx)B(ctx,1)=1;}
 }
}
void pg_tracks_nav(void){
 PG *s=existing();if(!s)return;
 /* P168 exp3 (owner: Level flashes while MIXER is held down on the Track view). The native press of MIXER
    navigates to the Mixer page even from itself (08142E58), and every navigation ended the Track overlay,
    so Level showed until the release. While the hold controls have MIXER down (K16 state: button 5) and
    we are on the Mixer page, the overlay survives that navigation; its encoder row is bound again. */
 u32 keep=s->compressor&&B(MODEL,0x12c)==0x1fu&&W((void*)0x24048cc0u,0)==0x354d5442u&&W((void*)0x24048cc0u,4)==5;
 s->tracks_valid=s->outputs_valid=s->tracks_view=0;
 s->touches=s->down_col=s->tap_col=0;
 s->mixer_valid=s->mixer_values=s->mixer_view=s->compressor=s->mixer_config=s->mixer_drag=0;
 s->compressor=keep;
}
__attribute__((used,retain)) void pg_tracks_event(void *view,void *event){
#if BENTO_FW==168
 {u32 c=H(event,0);if(c==0x1078u){extern int fx_open(void*);fx_open(MODEL);return;}if(c==0x1077u)return;} /* run 17: footer Tracks | Track FX */
#endif
 NFN(0x08160fb4,void(*)(void*,void*))(view,event);
}
static u32 zone(void *col,void *point){
 u32 i;void *v=tracks_view(col,&i);
 if(!v||!point||B(col,0x30)||B(v,0x30)||B(MODEL,0x12c)!=TRACKS_PAGE)return 0;
 int x=(int)W(point,0),top=480-(int)W(point,4),left=10+159*(int)i;
 if(x<left||x>=left+149||top<73||top>=COLUMN_END-7)return 0;
 return top<161?1u:top<268?2u:top<351?3u:4u;
}
__attribute__((used,retain)) int pg_column_hit(void *col,void *point,void **out){
 if(!out||!zone(col,point))return 0;*out=col;return 1;
}
__attribute__((used,retain)) void pg_column_down(void *col,void *point,u32 id){
 u32 z=zone(col,point);if(!z)return;PG *s=state();if(!s)return;
 if(s->touches&&TICK-s->down_tick>1500u)s->touches=0;
 if(s->touches){s->cancelled=1;s->tap_col=0;s->touches++;return;}
 s->touches=1;s->cancelled=0;s->down_col=(u32)col;s->down_id=id;s->down_tick=TICK;
 s->down_x=(int)W(point,0);s->down_y=(int)W(point,4);s->down_zone=z;s->down_project=W(MODEL,0);s->down_handle=W(col,0x2dc);
}
__attribute__((used,retain)) void pg_column_move(void *col,void *point,u32 id){
 PG *s=existing();if(!s||!s->touches||!point)return;
 int dx=(int)W(point,0)-s->down_x,dy=(int)W(point,4)-s->down_y;
 if(s->down_col!=(u32)col||s->down_id!=id||dx>20||dx<-20||dy>20||dy<-20){s->cancelled=1;s->tap_col=0;}
}
__attribute__((used,retain)) void pg_column_up(void *col,void *point,u32 id){
 PG *s=existing();if(!s||!s->touches)return;
 pg_column_move(col,point,id);
 if(--s->touches)return;
 u32 z=zone(col,point),i;void *v=tracks_view(col,&i);
 if(s->cancelled||!z||z!=s->down_zone||TICK-s->down_tick>600u||s->down_project!=W(MODEL,0)||s->down_handle!=W(col,0x2dc)){s->tap_col=0;return;}
 u32 handle=W(col,0x2dc),project=W(MODEL,0);
#if BENTO_FW==168
 /* P168 exp8: a tap on the square (24 px at x+66, top 378, with a 10 px margin) toggles the track's XY send;
    no selection and no double tap into the sequencer there (the rest of the lower zone keeps both). */
 if(z==4&&handle&&i<8){int px=(int)W(point,0)-(6+159*(int)i),py=480-(int)W(point,4);
  if(px>=56&&px<100&&py>=368&&py<412){extern void xy_toggle_track(u32) __attribute__((weak));if(xy_toggle_track){xy_toggle_track(i);s->tap_col=0;return;}}}
#endif
 int twice=s->tap_col==(u32)col&&s->tap_handle==handle&&s->tap_zone==z&&s->tap_project==project&&TICK-s->tap_tick<450u;
 s->tap_col=0;
 if(z==1){
  if(handle){u32 muted=0;
   if(!ui_get(&handle,NKEY(0x13d),&muted)){
    NFN(0x08104c00,void(*)(const char*))("PG: mute read");return;
   }
   ui_post((u32)(0xd3),(u32)(handle),(u32)(NKEY(0x13d)),(u32)(!muted));
   u32 current=muted;
   if(ui_get(&handle,NKEY(0x13d),&current))
    NFN(0x08180b94,void(*)(void*,u32))(col,current!=0);
   else NFN(0x08104c00,void(*)(const char*))("PG: mute refresh");
  }
  return;
 }
 u32 event[5]={twice&&z==2?0x7bu:0x7au,0,i,0,0};
 NFN(0x0816085c,int(*)(void*,void*))(v,event);
 if(twice){
  if(z==4&&handle){u32 button[5]={0x73,0,11,0,0};NFN(0x08142afc,void(*)(void*,void*))(MODEL,button);}
  return;
 }
 if(z==2||z==4){s->tap_col=(u32)col;s->tap_handle=handle;s->tap_zone=z;s->tap_tick=TICK;s->tap_project=project;}
}


#define MIXER_VT 0x0819dd20u
#define MIXER_PAGE 0x1fu
#define MIXER_COLUMN 0x750u
#define MIXER_COMP 0x1076u
static const u16 mix_keys[4]={0x134,NKEY(0x13f),NKEY(0x140),NKEY(0x141)};
/* R6.4 (owner): Mixer > Track reuses the former compressor overlay: the mixer
   page stays, only the header strip shows the selected track's Level, Pan,
   Delay and Reverb sends (keys 134/13F/140/141 on the real track handle). */
static const u16 comp_keys[8]={0x134,NKEY(0x13f),NKEY(0x140),NKEY(0x141),0,0,0,0};
static void *mix_col(void *v,u32 i){return (u8*)v+0x34+i*MIXER_COLUMN;}
static void *mix_bar(void *v){return (u8*)v+0x7610;}
static int mix_get(u32 h,u32 key,int *value){
 return ui_get(&h,key,value);
}
static PG *mix_state(void *v){
 PG *s=state();if(!s)return 0;
 if(s->mixer_view!=(u32)v){
  s->mixer_view=(u32)v;s->mixer_valid=s->mixer_values=s->outputs_valid=0;
  s->mixer_config=0;s->mixer_overlay=~0u;
 }
 return s;
}
static void mix_values(PG *s,void *v){
 for(u32 i=0;i<8;i++){
  if(s->mixer_values&(1u<<i))continue;
  u32 h=W(mix_col(v,i),0x34);int good=1;
  for(u32 k=0;k<4;k++){
   int value=0;
   if(h&&!mix_get(h,mix_keys[k],&value))good=0;
   s->mix_value[i][k]=value;
  }
  if(good)s->mixer_values|=1u<<i;
  else NFN(0x08104c00,void(*)(const char*))("PG: mixer read");
 }
}
static void mix_snapshot(PG *s,void *v,u32 i,MixerPaint *n){
 void *c=mix_col(v,i);zero(n,sizeof(*n));n->handle=W(c,0x34);
 n->flags=B(c,0x3dd)|((u32)B(c,0x3e0)<<1)|((u32)B(c,0x3df)<<2)|
  ((u32)B(c,0x3e1)<<3)|((u32)B(v,0x9a08)<<4);
 for(u32 j=0;j<31;j++)n->name[j]=B(c,0x2a4+j);
 for(u32 k=0;k<4;k++)n->value[k]=s->mix_value[i][k];
 for(u32 k=0;k<2;k++)n->meter[k]=(u16)(n->handle?meter_width(W(c,0x498+k*0x4c),113):0);
}
static u32 digits(char *out,u32 n){
 char rev[12];u32 count=0;do{rev[count++]=(char)('0'+n%10);n/=10;}while(n);
 for(u32 i=0;i<count;i++)out[i]=rev[count-i-1];return count;
}
static void mix_db(char *out,int value){
 u32 at=0;if(value<0){out[at++]='-';value=-value;}
 at+=digits(out+at,(u32)value/1000);out[at++]='.';out[at++]=(char)('0'+(u32)value/100%10);
 out[at++]=' ';out[at++]='d';out[at++]='B';out[at]=0;
}
static int mix_bound(int value,int lo,int hi){return value<lo?lo:value>hi?hi:value;}
static void mix_strip(PG *s,void *v,void *ctx,u32 i){
 void *SURF=(void*)W(ctx,4);MixerPaint n;mix_snapshot(s,v,i,&n);MixerPaint *old=&s->mixer[i];
 int full=B(ctx,0)||!(s->mixer_valid&(1u<<i));
 int identity=full||n.handle!=old->handle||n.flags!=old->flags||!equal(n.name,old->name,32);
 int x=6+159*(int)i,selected=n.flags&1u,dim=n.flags&10u;
 u32 ground=selected?SELECTED:BG,colour=NFN(0x08140ebc,u32(*)(u32))(i);
 s->ground=ground;
 if(identity){
  column_head(s,ctx,SURF,i,x,ground,colour,n.handle?n.name:0,dim);
  column_marks(s,ctx,i,x,n.flags);
 }
 if(n.handle){
  int meter_top=MIX_METER_TOP+MIX_METER_INSET;
  int meter_end=MIX_METER_END-MIX_METER_INSET;
  int span=meter_end-meter_top;
  for(u32 k=0;k<2;k++)if(identity||n.meter[k]!=old->meter[k]){
   u32 height=(u32)n.meter[k]*(u32)span/113u;
   fill(x+40+(int)k*12,meter_top,8,span,RAISED);
   fill(x+40+(int)k*12,meter_end-(int)height,6,(int)height,colour);
  }
  if(identity||n.value[0]!=old->value[0]){
   fill(x+76,meter_top-2,33,span+4,ground);fill(x+91,meter_top,2,span,RULE);
   int pos=mix_bound(n.value[0],-60000,6000);
   int fy=meter_end-(pos+60000)*span/66000-1;fill(x+78,fy,29,3,TEXT);
   char value[20];mix_db(value,n.value[0]);
   text_cached(s,ctx,i*5+2,x+4,MIX_METER_END+4,149,28,value,dim?FAINT:TEXT,TRACK_FONT,CENTRE);
  }
  for(u32 k=1;k<4;k++)if(identity||n.value[k]!=old->value[k]){
   int top=MIX_ROWS+MIX_ROW*((int)k-1);
   fill(x+4,top,149,MIX_ROW,ground);
   if(k==1){
    fill(x+28,top+11,100,1,RULE);fill(x+78,top+9,1,5,FAINT);
    fill(x+78+mix_bound(n.value[k],-1000,1000)/20,top+8,2,7,colour);
   }else{
    fill(x+14,top+11,129,2,RAISED);
    fill(x+14,top+11,mix_bound(n.value[k],0,1000)*129/1000,2,colour);
   }
  }
 }
 *old=n;s->mixer_valid|=1u<<i;s->ground=0;
}
static int mix_comp_key(u32 key){for(u32 i=0;i<4;i++)if(comp_keys[i]==key)return 1;return 0;}
/* Compressor keys are Project Settings: native binds them (like the Main
   output strip) to the project node from 08133E54, not global FFFFFFFE. */
extern u32 nav_track_index(void);
static __attribute__((noinline)) u32 mix_comp_handle(void){u32 h=0;return NFN(0x08133960,int(*)(void*,u32,u32*))(MODEL,nav_track_index(),&h)?h:0;}
static void mix_comp_config(PG *s,void *v){
 struct {u32 handles[8];u16 keys[8];int values[8];} config;
 u32 h=mix_comp_handle();
 if(!h){return;}
 for(u32 i=0;i<8;i++){
  config.handles[i]=h;config.keys[i]=comp_keys[i];config.values[i]=0;
  if(comp_keys[i]&&!mix_get(h,comp_keys[i],&config.values[i])){
   NFN(0x08104c00,void(*)(const char*))("PG: comp read");return;
  }
 }
 NFN(0x08170394,void(*)(void*,void*))(mix_bar(v),&config);s->mixer_config=1;
}
static void mix_output(void *v,u32 i,char *lines){
 void *c=mix_col(v,8+i);zero(lines,64);
 if(i==4||i==5)return;
 for(u32 j=0;j<31;j++){lines[j]=B(c,0x2a4+j);lines[32+j]=B(c,0x1f5+j);}
}
/* Native setPage (0816E2A0) re-parents the footer root, popups and overlays
   under the active page; generic page paint/walk reach them as children. */
static void mix_foreign(void *v,void *ctx,void *clip,u32 slot){
 for(u32 c=W(v,0x1c);c;c=W((void*)c,0x24)){
  if(c-(u32)v<0x10000u||W((void*)c,0x2c)!=(u32)v||B((void*)c,0x30))continue;
  u32 f=W((void*)W((void*)c,0),slot*4);
  if(slot==2)FN(f,void(*)(void*,void*,void*))((void*)c,ctx,clip);
  else FN(f,void(*)(void*,void*))((void*)c,ctx);
 }
}
static void mix_paint_own(void *v,void *ctx){
 if((!B(ctx,0)&&!B(ctx,1))||!W(ctx,4))return;
 PG *s=mix_state(v);if(!s)return;mix_values(s,v);
 extern int macro_overlay(void);
 u32 overlay=macro_overlay()?2u:s->compressor?1u:0u;
 if(overlay){
  u8 full=B(ctx,0);int reset=full||s->mixer_overlay!=overlay;
  if(reset){void *SURF=(void*)W(ctx,4);fill(6,0,1272,73,BG);B(ctx,0)=1;}
  s->outputs_valid=0;NFN(0x0816faec,void(*)(void*,void*))(mix_bar(v),ctx);
  B(ctx,0)=full;
 }
 else{int drawn=s->mix_up!=(W(v,0x75b4)!=0);
  for(u32 i=0;i<8;i++){
  void *c=mix_col(v,8+i);char lines[64];zero(lines,sizeof(lines));
  /* The encoder binding buffer follows focus; output identity does not. */
  mix_output(v,i,lines);
  drawn|=output_cell(s,ctx,i,lines,W(c,0x498),W(c,0x4e4),i<4||i==7);
  }
  /* run 18: thin frame A on the active output row, after the cells (they fill their own ground) */
  u32 up=W(v,0x75b4)!=0;if(drawn&&(up||s->mix_up)){void *SURF=(void*)W(ctx,4);frame(4,2,1272,69,1,up?0xa6u:BG);}s->mix_up=up;
 }
 s->mixer_overlay=overlay;
 for(u32 i=0;i<8;i++)mix_strip(s,v,ctx,i);
}
__attribute__((used,retain)) void pg_mixer_paint(void *v,void *ctx){
 if(!ctx)return;
 mix_paint_own(v,ctx);mix_foreign(v,ctx,0,1);
}
__attribute__((used,retain)) void pg_mixer_walk(void *v,void *ctx,void *clip){
 PG *s=existing();extern int macro_overlay(void);
 if(s&&s->mixer_view==(u32)v&&(s->compressor||macro_overlay()))
  NFN(0x0816f9e8,void(*)(void*,void*,void*))(mix_bar(v),ctx,clip);
 mix_foreign(v,ctx,clip,2);
}
static void mix_layout(void *v){
 int r[4]={6,407,1268,73};void *bar=mix_bar(v);
 FN(W((void*)W(bar,0),0x20),void(*)(void*,void*))(bar,r);
}
__attribute__((used,retain)) void pg_mixer_tick(void *v,void *ctx){
 NFN(0x081b5000,void(*)(void*,void*))(v,ctx);
 PG *s=existing();if(!s||s->mixer_view!=(u32)v||!ctx)return;
 extern int macro_overlay(void);
 int overlay=macro_overlay();
 if(s->compressor&&!overlay){
  void *slot=(u8*)mix_bar(v)+0x38;
  if(H(slot,0x9c)!=comp_keys[0]||W(slot,0x34)!=mix_comp_handle())s->mixer_config=0;
  if(!s->mixer_config)mix_comp_config(s,v);
 }
 if(!overlay&&(W(v,0x75b4)!=0)!=s->mix_up){s->outputs_valid=0;B(ctx,1)=1;} /* run 18: Up/Down or an output/strip tap moved the encoders */
 for(u32 i=0;i<8;i++){
  if(W(mix_col(v,i),0x34)!=s->mixer[i].handle)s->mixer_values&=~(1u<<i);
  if(!(s->mixer_values&(1u<<i)))B(ctx,1)=1;
  MixerPaint n;mix_snapshot(s,v,i,&n);
  if(!(s->mixer_valid&(1u<<i))||!equal(&n,&s->mixer[i],sizeof(n)))B(ctx,1)=1;
  if(!s->compressor&&!overlay){
   char lines[64];mix_output(v,i,lines);void *c=mix_col(v,8+i);
   if(!(s->outputs_valid&(1u<<i))||!equal(lines,s->output_text[i],64)||
      ((i<4||i==7)&&(meter_width(W(c,0x498),135)!=s->output_meter[i][0]||
                        meter_width(W(c,0x4e4),135)!=s->output_meter[i][1])))B(ctx,1)=1;
  }
 }
}
__attribute__((used,retain)) void pg_mixer_event(void *v,void *event){
 NFN(0x0814b98c,void(*)(void*,void*))(v,event);
 u32 code=H(event,0);if(B(MODEL,0x12c)!=MIXER_PAGE)return;
 PG *s=mix_state(v);if(!s)return;
 if(code==0x78){mix_layout(v);s->mixer_values=s->mixer_valid=s->outputs_valid=0;s->mixer_overlay=~0u;}
 if(code==0xa8||code==0xaa)s->mixer_values=0;
 if(code==0xc3){
  u32 h=W(event,4),key=W(event,8);
  for(u32 i=0;i<8;i++)if(W(mix_col(v,i),0x34)==h)
   for(u32 k=0;k<4;k++)if(mix_keys[k]==key)s->mix_value[i][k]=(int)W(event,12);
  if(mix_comp_key(key))s->mixer_config=0;
 }
}
__attribute__((used,retain)) int pg_mixer_receive(void *v,void *event){
 if(B(MODEL,0x12c)!=MIXER_PAGE)return NFN(0x0814baea,int(*)(void*,void*))(v,event);
 PG *s=mix_state(v);if(!s)return 1;u32 code=H(event,0);
 if(code==0x1087||code==MIXER_COMP){ /* R6.4: Track = overlay on the Mixer page */
  extern void mix_track_lights(int);
  s->compressor=1;s->mixer_config=s->outputs_valid=0;mix_comp_config(s,v);
  mix_track_lights(1);
  return 0;
 }
 if(s->compressor&&code==0xcf&&mix_comp_key(W(event,8))){
  u32 h=mix_comp_handle();if(!h)return 0;
  /* P168 exp3 (owner, old bug: the Track view encoders change the display but not the sound). The native
     Mixer view turns a slot's CF into D3 before it goes to the model (0814BB86), and the model's D3
     handler 08131AE0 updates the mixer strip of that track in the audio engine (0810B650 with the track
     index); CF (0813BFB0) only stores the value and addresses the engine by node handle. Send D3. */
  u32 e[5]={0xd3,h,W(event,8),W(event,12),0};
  NFN(0x081403ec,int(*)(void*,void*))(MODEL,e);s->mixer_config=0;return 0;
 }
 if(code>=NHID(0x108)&&code<=NHID(0x10b)&&s->compressor){extern void mix_track_lights(int);s->compressor=0;s->outputs_valid=0;mix_track_lights(0);}
 int result=NFN(0x0814baea,int(*)(void*,void*))(v,event);
 if(s->compressor)s->mixer_config=0;
 return result;
}
int pg_mixer_toolbar(void *model,void *out){
 if(B(model,0x12c)!=MIXER_PAGE)return 0;PG *s=existing();
 extern int header_fixed_tab(void*,unsigned,unsigned,const char*,int);
 for(u32 i=0;i<6;i++){
  void *record=(u8*)out+NOFF_HDR(0x74)+i*48;u32 id=H(record,44);
  if(id<NHID(0x108)||id>NHID(0x10c)||B(record,0x20))continue;
  if(s&&s->compressor){if(id<=NHID(0x10b))B(record,0x21)=0;continue;}
  /* Native 0x68 lights these widgets after the snapshot was taken; a stale
     record would make header_sync re-arm a relayout forever (W7 black footer). */
  if(W(0x30034d48u,0)==0x081b3680u)
   B(record,0x21)=B(0x30034d48u+(B(record,0x22)?NOFF_ROOT_TABS:NOFF_ROOT_SLOTS)+i*0xd0u,0xac)?1:0;
 }
 void *removed=(u8*)out+NOFF_HDR(0x74)+4*48;int changed=0;
 if(H(removed,44)==MIXER_COMP){zero(removed,48);B(removed,0x20)=1;changed=1;}
 /* R6.2 (owner spec): Level, Track, Pan, Delay, Reverb, Solo / Mute. Track is
    the selected track's mix on one page (Mixer > Track, fx_ui MIX_VIEW). */
 u8 *r=(u8*)out+NOFF_HDR(0x74);
 if(H(r+48,44)==NHID(0x109)&&H(r+2*48,44)==NHID(0x10a)&&H(r+3*48,44)==NHID(0x10b)){
  for(u32 i=4;i>=2;i--)for(u32 j=0;j<48;j++)r[i*48+j]=r[(i-1)*48+j];
  header_fixed_tab(out,1,0x1087,"Track",0);changed=1;
 }
 if(H(r+48,44)==0x1087)changed|=header_fixed_tab(out,1,0x1087,"Track",s&&s->compressor);
 return changed;
}
/* R6.5 (owner: Track lit briefly, Level relit, cycle broken): the footer
 * snapshot the MIXER cycle reads is rebuilt and applied at once, and the native
 * tab lights follow (68 off for the native tabs / on for Track, and back). */
__attribute__((noinline,section(".mixstrip"))) void mix_track_lights(int on){
 void *root=(void*)0x30034d48u;if(W(root,0)!=0x081b3680u)return;
 u32 e[5]={0x68,0,0x1087,(u32)on,0};FN(0x0817ffb9&~1u,void(*)(void*,void*))(root,e);
 if(on)for(u32 id=NHID(0x108);id<=NHID(0x10b);id++){e[2]=id;e[3]=0;FN(0x0817ffb9&~1u,void(*)(void*,void*))(root,e);}
 u8 snap[NSIZE_HDR];u8 *cur=(u8*)root+0x34;if(cur[NOFF_HDR(0x1c2)]!=MIXER_PAGE)return;
 for(u32 i=0;i<sizeof(snap);i++)snap[i]=cur[i];
 pg_mixer_toolbar(MODEL,snap);
 int changed=0;for(u32 i=0;i<sizeof(snap);i++)if(snap[i]!=cur[i]){changed=1;break;}
 if(!changed)return;B(root,NOFF_ROOT_LAYOUT)=1;NFN(0x0817faf8,void(*)(void*,void*))(root,snap);
}
int pg_mixer_compressor(void){PG *s=existing();return B(MODEL,0x12c)==MIXER_PAGE&&s&&s->compressor;}
/* Run 18 (owner, approved design/mixer_updown.png, native_mixer_up.png): on the Mixer page Up puts the encoders on the
   output row, Down back on the strips (the footer mode, as a tap on an output / a strip does natively: view +75B4,
   rebind 0814B814); Left/Right select the previous/next track as a strip tap does (model event 37), no wrap. Natively
   the Mixer view ignores the arrow message (0814B98C handles A8/AD/C0/C3/C4 only). Track overlay: Up/Down stay with
   it (its strip is the selected track); Left/Right still pick the track. Press and release are consumed. */
int pg_mixer_arrow(u32 code,u32 index){
 PG *s=existing();void *v=s?(void*)s->mixer_view:0;
 if(!v||W(v,0)!=MIXER_VT||B(MODEL,0x12c)!=MIXER_PAGE||B(v,0x30))return 0;
 if(code!=0xaf)return 1;
 if(index==1||index==8){if(!s->compressor){W(v,0x75b4)=index==1;NFN(0x0814b814,void(*)(void*))(v);ui_commit();}return 1;}
 u32 cur=0;while(cur<8&&W(mix_col(v,cur),0x34)!=W(MODEL,0x13c))cur++;if(cur>7)cur=0; /* the selected track (MODEL+13C) among the strips */
 int t=(int)cur+(index==9?1:-1);
 if(t>=0&&t<8){u32 h=W(mix_col(v,(u32)t),0x34);if(h){ui_post(0x37,h,(u32)t,0);if(s->compressor)mix_comp_config(s,v);ui_commit();}}
 return 1;
}
/* P168 exp5 (owner: the MIXER cycle skips Delay). The cycle read the lit footer record, which the native
   header rebuild refreshes on its own schedule (stale between a tap and the next rebuild). The native
   Mixer view keeps its own mode (the shown property key at view+75BC); 1..4 = Level, Pan, Delay, Reverb. */
u32 pg_mixer_mode(void){PG *s=existing();void *v=s?(void*)s->mixer_view:0;
 if(!v||W(v,0)!=MIXER_VT||B(MODEL,0x12c)!=MIXER_PAGE)return 0;
 u32 k=H(v,0x75bc);for(u32 i=0;i<4;i++)if(mix_keys[i]==k)return i+1;return 0;}
static u32 mix_context(PG *s,void *v){return H(v,0x75bc)|((u32)B(v,0x9a08)<<16)|(s->compressor<<24);}
static u32 mix_zone(void *v,void *point,u32 *index){
 if(!point||B(v,0x30)||B(MODEL,0x12c)!=MIXER_PAGE)return 0;
 int x=(int)W(point,0)-6,top=480-(int)W(point,4);
 if(x<0||x>=1272)return 0;*index=(u32)x/159u;
 if(top>=0&&top<73)return 6;
 if(top>=COLUMN_END)return 0;
 if(top<MIX_METER_TOP-8)return 1;
 return top<MIX_ROWS?2u:top<MIX_ROWS+MIX_ROW?3u:top<MIX_ROWS+2*MIX_ROW?4u:top<MIX_ROWS+3*MIX_ROW?5u:9u;
}
__attribute__((used,retain)) int pg_mixer_hit(void *v,void *point,void **out){
 u32 i,z=mix_zone(v,point,&i);if(!out)return 0;
 /* Footer root is a native-parented child below the columns (see mix_foreign);
    the generic child hit-test that ends native 0814A7BC routes it. */
 if(!z)return point&&B(MODEL,0x12c)==MIXER_PAGE&&480-(int)W(point,4)>=COLUMN_END?
  NFN(0x0816fa10,int(*)(void*,void*,void**))(v,point,out):0;
 PG *s=existing();*out=z==6&&s&&s->compressor?mix_bar(v):v;return 1;
}
static u32 mix_target(void *v,u32 i,u32 z,u32 *key){
 static const u16 output_keys[8]={0x138,0x137,0x136,0x135,0,0,0x18,0xa9};
 *key=z==6?output_keys[i]:z==1?NKEY(0x13du):z>=2&&z<=5?mix_keys[z-2]:0;
 return z==6?(*key?W(mix_col(v,8+i),0x34):0):W(mix_col(v,i),0x34);
}
__attribute__((used,retain)) void pg_mixer_down(void *v,void *point,u32 id){
 u32 i,z=mix_zone(v,point,&i);if(!z)return;PG *s=mix_state(v);if(!s)return;
 if(s->touches&&TICK-s->down_tick>1500u)s->touches=0;
 if(s->touches){s->cancelled=1;s->touches++;return;}
 s->touches=1;s->cancelled=0;s->down_col=(u32)v;s->down_id=id;s->down_tick=TICK;
 s->down_x=(int)W(point,0);s->down_y=(int)W(point,4);s->down_zone=z;
 s->down_project=W(MODEL,0);u32 key;u32 h=mix_target(v,i,z,&key);s->down_handle=h;
 if(!h)return;
 if(z>=3&&z<=5){
  if(!mix_get(h,key,&s->drag_value)){
   s->cancelled=1;NFN(0x08104c00,void(*)(const char*))("PG: drag start");return;
  }
  s->drag_sent=s->drag_value;
 }
 if(z!=1){
  W(v,0x75b4)=z==6?1u:0u;
  NFN(0x0814b814,void(*)(void*))(v);
  if(z!=6){ui_post((u32)(0x37),(u32)(h),(u32)(i),(u32)(0));}
  if(s->compressor)mix_comp_config(s,v);
 }
 s->drag_context=mix_context(s,v);
}
__attribute__((used,retain)) void pg_mixer_move(void *v,void *point,u32 id){
 PG *s=existing();if(!s||!s->touches||!point||s->cancelled)return;
 u32 initial=(u32)(s->down_x-6)/159u,key=0;
 u32 h=mix_target(v,initial,s->down_zone,&key);
 if(s->down_col!=(u32)v||s->down_id!=id||W(MODEL,0)!=s->down_project||h!=s->down_handle||
    B(MODEL,0x12c)!=MIXER_PAGE||s->drag_context!=mix_context(s,v)){s->cancelled=1;return;}
 int dx=(int)W(point,0)-s->down_x,dy=(int)W(point,4)-s->down_y;
 if(s->down_zone==1){
  if(dx>20||dx<-20||dy>20||dy<-20)s->cancelled=1;return;
 }
 if(!h||s->down_zone==2||s->down_zone==6||s->down_zone==9)return;
 u32 registry=W((void*)0x30031484u,0);void *d=(void*)(registry+key*32u);
 if(!registry||H(d,0)!=key){s->cancelled=1;NFN(0x08104c00,void(*)(const char*))("PG: no bounds");return;}
 int delta=s->down_zone==3?mix_bound(dx,-100,100)*2000/100:mix_bound(dx,-129,129)*1000/129;
 int value=mix_bound(s->drag_value+delta,(int)W(d,16),(int)W(d,20));
 if(value==s->drag_sent)return;
 ui_post((u32)(0xd3u),(u32)(h),(u32)(key),(u32)((u32)value));
 if(!mix_get(h,key,&value)){s->cancelled=1;NFN(0x08104c00,void(*)(const char*))("PG: drag refresh");return;}
 s->drag_sent=value;
 s->mix_value[initial][s->down_zone-2]=value;
}
__attribute__((used,retain)) void pg_mixer_up(void *v,void *point,u32 id){
 PG *s=existing();if(!s||!s->touches)return;pg_mixer_move(v,point,id);
 if(--s->touches)return;
 u32 i,z=mix_zone(v,point,&i);
 if(s->cancelled||!z||z!=s->down_zone||TICK-s->down_tick>600u||
    i!=(u32)(s->down_x-6)/159u)return;
 if(z!=1)return;
 u32 key,h=mix_target(v,i,z,&key);int value=0;
 if(!h)return;
 if(!mix_get(h,key,&value)){NFN(0x08104c00,void(*)(const char*))("PG: m/s read");return;}
 ui_post((u32)(0xd3),(u32)(h),(u32)(key),(u32)(!value));
 if(!mix_get(h,key,&value)){NFN(0x08104c00,void(*)(const char*))("PG: m/s refresh");return;}
 NFN(0x08173a68,void(*)(void*,u32))(mix_col(v,i),value!=0);
 NFN(0x0814a828,void(*)(void*))(v);
}
int pg_mixer_bar_drag(void *bar,void *point,u32 id,int phase){
 void *v=(void*)W(bar,0x2c);PG *s=existing();
 if(!v||W(v,0)!=MIXER_VT||!s||s->compressor)return 0;
 extern int macro_overlay(void);
 if(phase==0){
  s->mixer_drag=0;if(macro_overlay())return 0;
  pg_mixer_down(v,point,id);return 0;
 }
 if(phase==2)s->touches=0;
 return 0;
}

/* ---------------------------------------------------------------------------
 * Piano grid (class 081B2BCC; Chord, Melodic Step, Sequence, Melodic Euclid and
 * the one-shot piano view). Native notes take their colour from grid+5274
 * (0817524E; muted one-shot rows use F6). Playground: notes in the current
 * track's colour (native 08140EBC(track number), as the Step view does).
 * Bar lines are made faint in build_fx.py (08176EE2 F6 -> 62).
 * ------------------------------------------------------------------------- */
#define MODEL_ ((void*)0x30024b00u)
void pg_grid_prepare(void *grid){
 u32 h=0,idx=0;
 if(!NFN(0x08133cfc,int(*)(void*,void*))(MODEL_,&h)||!h)return;
 NFN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL_,&h,0x73,&idx);
 if(idx>7)return;
 u8 c=(u8)NFN(0x08140ebc,u32(*)(u32))(idx);
 u8 *g=(u8*)grid;
 if(g[0x5274]!=c){g[0x5274]=c;NFN(0x0817527e,void(*)(void*))(grid);g[0x4f0]=1;}
}

#define LAUNCH_VT 0x0819dce0u
#define LAUNCH_COLUMN_VT 0x081b298cu
#define LAUNCH_CELL_VT 0x081b2944u
#define LAUNCH_LABEL_VT 0x081b35c0u
#define LAUNCH_COLUMN_STRIDE 0x15c0u
#define LAUNCH_CELL_STRIDE 0x28cu
#define LAUNCH_SELECTED 0xa3u
#define LAUNCH_OUTLINE 0x22u
#define LAUNCH_MUTED 0x62u
#define LAUNCH_QUEUED 0x44cu
#define LAUNCH_WAITING 0xffffff38u
#define LAUNCH_SELECT 0x107au
#define LAUNCH_PLAY 0x107bu
#define LAUNCH_STOP 0x107cu

static void *launch_column(void *view,u32 track){
 return (u8*)view+0x34+track*LAUNCH_COLUMN_STRIDE;
}
static void *launch_cell(void *view,u32 track,u32 row){
 return (u8*)launch_column(view,track)+0x12c+row*LAUNCH_CELL_STRIDE;
}
static int launch_has_group(PG *s){
 for(u32 t=0;t<8;t++)if(s->launch_group[t])return 1;return 0;
}
static void launch_group_check(PG *s,void *view){
 u32 project=W(MODEL,0);
 if(s->launch_project!=project){
  s->launch_project=project;s->launch_select=0;
  zero(s->launch_group,sizeof(s->launch_group));
  s->launch_cells_valid[0]=s->launch_cells_valid[1]=0;B(view,0x39)=1;
 }
 for(u32 t=0;t<8;t++)if(s->launch_group[t]){
  void *col=launch_column(view,t);
  if(s->launch_row[t]>=8||W(col,0x124)!=s->launch_track[t]||
     W(launch_cell(view,t,s->launch_row[t]),0x278)!=s->launch_group[t])
   {s->launch_group[t]=0;s->launch_cells_valid[0]=s->launch_cells_valid[1]=0;B(view,0x39)=1;}
 }
}
int pg_launch_toolbar(void *model,void *out){
 if(B(model,0x12c)!=0x1e)return 0;
 extern int header_fixed_action(void*,unsigned,unsigned,const char*,int);
 PG *s=existing();int lit=s&&s->launch_project==W(model,0)&&s->launch_select;
 int change=header_fixed_action(out,2,LAUNCH_SELECT,"Select",lit);
 change|=header_fixed_action(out,3,LAUNCH_PLAY,"Play",0);
 change|=header_fixed_action(out,4,LAUNCH_STOP,"Stop",0);return change;
}
/* Stock 08137F30..48 uses this exact native queue pair; 0813D02C uses
   64=0. The audio core retains ownership of launch/stop quantization. */
static void launch_group_action(PG *s,void *view,int play){
 launch_group_check(s,view);
 void *engine=(void*)W((void*)0x3000f650u,0);if(!engine)return;
 for(u32 t=0;t<8;t++)if(s->launch_group[t]){
  int row=-1,queued=-1;
  int pos=NFN(0x081322ac,int(*)(void*,u32,void*,void*))(MODEL,t,&row,&queued);
  if(play){
   if(queued==(int)s->launch_row[t]||(pos!=-1&&row==(int)s->launch_row[t]&&queued<0))continue;
   NFN(0x0810b5c8,void(*)(void*,u32,u32,u32))(engine,s->launch_track[t],0x64,1);
   NFN(0x0810b5c8,void(*)(void*,u32,u32,u32))(engine,s->launch_track[t],0x63,s->launch_row[t]);
  }else if(pos!=-1||queued>=0)
   NFN(0x0810b5c8,void(*)(void*,u32,u32,u32))(engine,s->launch_track[t],0x64,0);
 }
}
/* P168 exp3 (owner: the pad area marker is gone). Native 1.6.8 lights the pads from two clip rows:
 * row MODEL+2540 on pads 1-8 and the row below on pads 9-16 (08136AD6: ldr [model+2540]; row+1 -> pad
 * bit +8; set by the native pad handler 0813B4E8). Our cell painter replaces the native cell drawing,
 * so the cells of those two rows get a white outline here. 1.6.1 has no such rows. */
#if BENTO_FW==168
static u32 launch_pad_row(u32 row){u32 top=W(MODEL,0x2540);return row==top?1u:row==top+1u?2u:0;}
#else
#define launch_pad_row(row) 0u
#endif
__attribute__((used,retain)) int pg_launch_event(void *view,void *event){
 u32 code=H(event,0);
 if(code<LAUNCH_SELECT||code>LAUNCH_STOP)
  return NFN(0x0814a0d0,int(*)(void*,void*))(view,event);
 PG *s=state();if(!s)return 0;
 launch_group_check(s,view);
 if(code==LAUNCH_SELECT){
  s->launch_select=!s->launch_select;
  ui_commit();
 }
 else launch_group_action(s,view,code==LAUNCH_PLAY);
 s->launch_cells_valid[0]=s->launch_cells_valid[1]=0;
 B(view,0x39)=1;return 0;
}
__attribute__((used,retain)) int pg_launch_column_event(void *column,void *event){
 void *view=(void*)W(column,0x2c);PG *s=existing();
 u32 code=H(event,0),row=W(event,8),track=W(column,0x14);
 if(view&&W(view,0)==LAUNCH_VT&&s&&s->launch_select&&track<8&&row<8&&
    (code==0x79||code==0x7b)){
  launch_group_check(s,view);
  if(s->launch_select&&code==0x79){
   void *cell=launch_cell(view,track,row);
   if(W(cell,0x278)&&W(column,0x124)){
    s->launch_group[track]=W(cell,0x278);s->launch_track[track]=W(column,0x124);
    s->launch_row[track]=row;s->launch_cells_valid[0]=s->launch_cells_valid[1]=0;
    B(view,0x39)=1;
   }
  }
  return 0; /* Do not forward the native double-tap navigation while selecting. */
 }
 return NFN(0x08172a08,int(*)(void*,void*))(column,event);
}

static void launch_rect(void *widget,int x,int y,int w,int h){
 W(widget,4)=(u32)x;W(widget,8)=(u32)y;W(widget,12)=(u32)w;W(widget,16)=(u32)h;
}
static void *launch_view_for_cell(void *cell){
 if(W(cell,0)!=LAUNCH_CELL_VT)return 0;
 void *column=(void*)W(cell,0x2c);
 if(!column||W(column,0)!=LAUNCH_COLUMN_VT)return 0;
 void *view=(void*)W(column,0x2c);
 return view&&W(view,0)==LAUNCH_VT?view:0;
}
static void launch_prepare_state(PG *s,void *view){
 if(s->launch_view==(u32)view)return;
 s->launch_view=(u32)view;
 s->launch_cells_valid[0]=s->launch_cells_valid[1]=0;
 s->launch_headers_valid=0;
}
static int launch_set_rect(void *widget,int x,int y,int w,int h){
 if((int)W(widget,4)==x&&(int)W(widget,8)==y&&(int)W(widget,12)==w&&(int)W(widget,16)==h)return 0;
 launch_rect(widget,x,y,w,h);return 1;
}
/* P168 exp3 (owner: the footer Play/Stop do nothing on 1.6.8; why they did not arrive at the view's
 * handler there is not established). The three footer actions are also taken at the model event
 * entry, where every header action passes before it is routed to a view, and consumed there, so they
 * run exactly once whichever way the native header delivers them. */
__attribute__((used,retain,noinline)) int pg_launch_action(void *event){
 u32 code=H(event,0);PG *s=existing();
 if(code<LAUNCH_SELECT||code>LAUNCH_STOP||B(MODEL,0x12c)!=0x1e||!s||!s->launch_view||W((void*)s->launch_view,0)!=LAUNCH_VT)return 0;
 pg_launch_event((void*)s->launch_view,event);return 1;
}
/* Same grid as Tracks/Mixer: 159 px columns from x6, header directly under the
   native top row (y73), eight 36 px clip rows ending above the footer. Every
   widget is checked each tick because native relayouts touch single columns. */
#define LAUNCH_HEAD 68
#define LAUNCH_ROW 36
static int launch_apply_layout(void *view){
 void *first=(u8*)view+0x34;
 if(W(view,0)!=LAUNCH_VT||W(first,0)!=LAUNCH_COLUMN_VT)return 0;
 int changed=0,cells=73+LAUNCH_HEAD+1;
 for(u32 track=0;track<8;track++){
  void *column=(u8*)view+0x34+track*LAUNCH_COLUMN_STRIDE;
  if(W(column,0)!=LAUNCH_COLUMN_VT)continue;
  int x=6+159*(int)track,head=480-73-LAUNCH_HEAD;
  changed|=launch_set_rect(column,x,480-COLUMN_END,159,COLUMN_END-73);
  changed|=launch_set_rect((u8*)column+0x34,x,head,0,0); /* native colour tile: paint only */
  changed|=launch_set_rect((u8*)column+0x78,x,head,159,LAUNCH_HEAD);
  changed|=launch_set_rect((u8*)column+0xe8,x,head,159,LAUNCH_HEAD);
  for(u32 row=0;row<8;row++){
   void *cell=(u8*)column+0x12c+row*LAUNCH_CELL_STRIDE;
   int y=480-cells-LAUNCH_ROW*((int)row+1);
   changed|=launch_set_rect(cell,x,y,159,LAUNCH_ROW);
   changed|=launch_set_rect((u8*)cell+0x34,x+2,y+2,155,LAUNCH_ROW-4);
   changed|=launch_set_rect((u8*)cell+0x68,x+2,y+2,155,LAUNCH_ROW-4);
   changed|=launch_set_rect((u8*)cell+0x1fc,x,y,159,LAUNCH_ROW);
   changed|=launch_set_rect((u8*)cell+0x238,x+2,y+2,155,LAUNCH_ROW-4);
  }
 }
 if(changed){PG *s=existing();if(s&&s->launch_view==(u32)view)s->launch_cells_valid[0]=s->launch_cells_valid[1]=s->launch_headers_valid=0;}
 return changed;
}
__attribute__((used,retain)) void pg_launch_tick(void *view,void *ctx){
 NFN(0x0814a7a4,void(*)(void*,void*))(view,ctx);
 PG *s=state();if(s){
  launch_group_check(s,view);
  for(u32 i=0;i<64;i++){
   LaunchCellPaint *c=&s->launch_cells[i];
   if((s->launch_cells_valid[i>>5]&(1u<<(i&31u)))&&c->clip&&
      (c->status==LAUNCH_QUEUED||c->status==LAUNCH_WAITING)&&
      ((c->selected>>1)&1u)!=((TICK/250u)&1u)){
    B(view,0x39)=1;if(ctx)B(ctx,1)=1;break;
   }
   if((s->launch_cells_valid[i>>5]&(1u<<(i&31u)))&&(c->selected>>2)!=launch_pad_row(i&7u)){B(view,0x39)=1;if(ctx)B(ctx,1)=1;break;} /* exp3: the pad rows moved */
  }
 }
 if(launch_apply_layout(view)&&ctx)B(ctx,1)=1;
}
static int launch_should_paint(void *ctx){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1)))return 0;
 return 1;
}
__attribute__((used,retain)) void pg_launch_cell_paint(void *cell,void *ctx){
 void *view=launch_view_for_cell(cell);
 if(!view||!launch_should_paint(ctx)){
  NFN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;
 }
 PG *s=state();if(!s){NFN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;}
 launch_prepare_state(s,view);
 void *SURF=(void*)W(ctx,4);
 if(!SURF){s->launch_view=0;NFN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;}
 u32 track=W(W(cell,0x2c),0x14),row=W(cell,0x14),index=track*8+row;
 if(track>=8||row>=8){NFN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;}
 void *status=(u8*)cell+0x34;LaunchCellPaint next;zero(&next,sizeof(next));
 next.clip=W(cell,0x278);next.status=W(status,0xa8);
 next.selected=s->launch_select||launch_has_group(s)?
  s->launch_group[track]&&s->launch_group[track]==next.clip:B(cell,0x288)!=0;
 next.colour=NFN(0x08140ebc,u32(*)(u32))(track);
 int queued=next.status==LAUNCH_QUEUED||next.status==LAUNCH_WAITING;
 if(queued)next.selected|=((TICK/250u)&1u)<<1;
 next.selected|=launch_pad_row(row)<<2;
 for(u32 i=0;i<sizeof(next.name)-1&&B(cell,0xe5+i);i++)next.name[i]=(char)B(cell,0xe5+i);
 u32 mask=1u<<(index&31u),bank=index>>5;
 LaunchCellPaint *old=&s->launch_cells[index];
 int full=B(ctx,0)!=0;
 if(!full&&(s->launch_cells_valid[bank]&mask)&&equal(old,&next,sizeof(next)))return;
 int x=(int)W(cell,4),top=480-(int)W(cell,8)-(int)W(cell,16);
 int w=(int)W(cell,12),h=(int)W(cell,16),selected=(next.selected&1u)!=0;
 u32 ground=selected?LAUNCH_SELECTED:BG;
 fill(x,top,w,h,BG);fill(x+3,top+1,w-6,h-2,ground);frame(x+3,top+1,w-6,h-2,1,LAUNCH_OUTLINE);
 if(next.clip)fill(x+4,top+8,2,h-16,next.colour);
 if(next.clip&&next.status<=1000u){
  int mx=x+11,my=top+10;
  for(int line=0;line<7;line++){
   fill(mx,my+line,2+line,1,TEXT);
   fill(mx,my+13-line,2+line,1,TEXT);
  }
  int progress=(int)(141u*next.status/1000u);
  if(progress)fill(x+9,top+h-4,progress,1,TEXT);
 }else if(next.clip&&queued){
  int mx=x+11,my=top+10;u32 colour=(next.selected&2u)?TEXT:next.colour;
  fill(mx,my,2,14,colour);
  for(int line=0;line<7;line++){
   fill(mx+line,my+line,2,1,colour);
   fill(mx+line,my+13-line,2,1,colour);
  }
 }
 if(next.clip&&next.name[0]){
  s->ground=ground;
  textf(s,ctx,x+23,top+4,w-43,h-8,next.name,
        next.status<=1000u||queued?TEXT:LAUNCH_MUTED,TRACK_FONT,CENTRE);
  s->ground=0;
 }
 if(next.selected>>2){ /* exp3: white outline around the two rows the pads launch */
  fill(x,(next.selected>>2)==1?top:top+h-2,w,2,TEXT);
  if(track==0)fill(x,top,2,h,TEXT);
  if(track==7)fill(x+w-2,top,2,h,TEXT);
 }
 *old=next;s->launch_cells_valid[bank]|=mask;
}
__attribute__((used,retain)) void pg_launch_cell_walk(void *cell,void *ctx,void *clip){
 (void)clip;
 void *view=launch_view_for_cell(cell);PG *s=existing();
 if(view&&s&&s->launch_view==(u32)view)return;
 NFN(0x0816f9e8,void(*)(void*,void*,void*))(cell,ctx,0);
}
__attribute__((used,retain)) void pg_launch_header_paint(void *label,void *ctx){
 if(W(label,0)!=LAUNCH_LABEL_VT){
  NFN(0x0817e780,void(*)(void*,void*))(label,ctx);return;
 }
 void *column=(void*)W(label,0x2c);
 void *view=column&&W(column,0)==LAUNCH_COLUMN_VT?(void*)W(column,0x2c):0;
 if(!view||W(view,0)!=LAUNCH_VT||label!=(u8*)column+0x78){
  NFN(0x0817e780,void(*)(void*,void*))(label,ctx);return;
 }
 if(!launch_should_paint(ctx))return;
 PG *s=state();if(!s)return;launch_prepare_state(s,view);
 void *SURF=(void*)W(ctx,4);if(!SURF)return;
 u32 track=W(column,0x14);if(track>=8)return;
 u32 colour=NFN(0x08140ebc,u32(*)(u32))(track);
 const char *name=(const char*)label+0x31;LaunchHeaderPaint next;zero(&next,sizeof(next));
 next.colour=colour;for(u32 i=0;i<sizeof(next.name)-1&&name[i];i++)next.name[i]=name[i];
 u32 mask=1u<<track;int full=B(ctx,0)!=0;
 if(!full&&(s->launch_headers_valid&mask)&&equal(&s->launch_headers[track],&next,sizeof(next)))return;
 int x=(int)W(label,4),top=480-(int)W(label,8)-(int)W(label,16),h=(int)W(label,16);
 fill(x,top,159,h,BG);fill(x+14,top,125,1,colour);
 char num[8];number(num,track+1);s->ground=BG;
 textf(s,ctx,x+14,top+4,40,28,num,colour,TRACK_FONT,1);
 if(next.name[0])textf(s,ctx,x+8,top+33,143,30,next.name,TEXT,TRACK_BOLD,CENTRE);
 s->ground=0;
 s->launch_headers[track]=next;s->launch_headers_valid|=mask;
}
