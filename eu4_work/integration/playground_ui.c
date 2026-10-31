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
} PG;
void **playground_state_slot(void);
void **playground_existing_slot(void);
static void zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static PG *state(void){
 void **slot=playground_state_slot();if(!slot)return 0;PG *s=*slot;
 if(s)return s->magic==PG_MAGIC?s:0;
 u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),bytes=(sizeof(PG)+31u)&~31u;
 if(cursor<0xc0000000u||end>0xc8000000u||cursor>end||end-cursor<bytes+32)return 0;
 s=FN(0x08104c08,void*(*)(u32))(bytes);if((u32)s!=cursor)return 0;zero(s,sizeof(*s));s->magic=PG_MAGIC;
 for(u32 i=0;i<4;i++)s->outputs[i][0]=s->outputs[i][1]=0xc2700000u;
 s->output_stamp=TICK-1u;*slot=s;return s;
}
static PG *existing(void){
 void **slot=playground_existing_slot();PG *s=slot?*slot:0;
 return s&&s->magic==PG_MAGIC?s:0;
}

/* Native fills/outlines take logical rects (x, y from the bottom, w, h). */
/* SURF: the paint surface of the current draw call (no writable globals in flash code). */
#define fill(x,top,w,h,c) fill_(SURF,x,top,w,h,c)
#define frame(x,top,w,h,t,c) frame_(SURF,x,top,w,h,t,c)
static void fill_(void *SURF,int x,int top,int w,int h,u32 c){if(w<=0||h<=0)return;int r[4]={x,480-top-h,w,h};FN(0x08166ef6,void(*)(void*,u32,void*))(r,c,SURF);}
static void frame_(void *SURF,int x,int top,int w,int h,int t,u32 c){fill(x,top,w,t,c);fill(x,top+h-t,w,t,c);fill(x,top+t,t,h-2*t,c);fill(x+w-t,top+t,t,h-2*t,c);}
/* Font index 3 = Rajdhani Medium 14 (heights per index: 26 27 63 15 20 14). */
#define SMALL 3u
#define BIG 0u /* Rajdhani Medium 24 */
#define CENTRE 2u /* label +51: 0/1 left, 2 centred */
static void textf(PG *s,void *ctx,int x,int top,int w,int h,const char *str,u32 colour,u32 font,u32 align){
 void *l=s->label;
 if(!s->label_ready){FN(0x0817e7c0,void(*)(void*))(l);s->label_ready=1;s->font=0xffu;}
 if(s->font!=font){FN(0x0817e810,void(*)(void*,u32))(l,font);s->font=font;}
 B(l,0x53)=(u8)colour;B(l,0x54)=(u8)(s->ground?s->ground:0xf1u);B(l,0x56)=1;B(l,0x51)=(u8)align;
 FN(0x0817e85e,void(*)(void*,const char*))(l,str);
 int r[4]={x,480-top-h,w,h};W(l,4)=r[0];W(l,8)=r[1];W(l,12)=r[2];W(l,16)=r[3];
 FN(0x0817e448,void(*)(void*,void*,void*))(l,ctx,r);
}
static void text(PG *s,void *ctx,int x,int top,int w,int h,const char *str,u32 colour){textf(s,ctx,x,top,w,h,str,colour,SMALL,1);}

static u32 frac1000(u32 w){u32 k=lock_kind(w);if(!k)return 0;u32 n=value_count(k);return n>1?(w&65535u)*1000u/(n-1):0;}
__attribute__((noinline,section(".pad2"))) static void refresh(PG *s,void *v){
 u32 container=W(v,0x113dc),pad=W(v,0x11400),base=W(v,0x113f4);
 if(s->stamp==TICK&&s->view==(u32)v&&s->container==container&&s->pad==pad&&s->base==base)return;
 s->stamp=TICK;s->view=(u32)v;s->container=container;s->pad=pad;s->base=base;
 for(u32 i=0;i<32;i++){s->vel[i]=s->prob[i]=s->note[i]=s->locked[i]=s->cond[i]=0;s->off[i]=0;s->l1[i]=s->l2[i]=0;}
 if(!container)return;
 u32 e[6],dyn=seq_eu_dynamics(v),n=dyn>>16,hits[8]={0};
 for(u32 j=0;j<511;j++){
  if(!FN(0x0810d2c0,int(*)(void*,u32,void*))((void*)container,j,e))break;
  if(B(e,0)!=1||H(e,2)!=pad)continue;
  int t=(int)e[1],q=t%960;if(q>480)q-=960;int abs=(t-q)/960,at=abs-(int)base;
  if(dyn&&abs>=0&&(u32)abs<n)hits[abs/32]|=1u<<(abs%32);
  if(at<0||at>=32)continue;
  u32 vel=e[4]>>16;s->vel[at]=(u8)(vel>127?127:vel);s->prob[at]=B(e,1);s->note[at]=1;
  s->off[at]=(signed char)(q/40);s->cond[at]=(u8)lc_condition(e[5]); /* W14 HW3: offset nudge, ratio condition */
  u32 a=lock_slot(e[5],0),b=lock_slot(e[5],1);
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
 u32 step=s->base+i;int sel=FN(0x0815b9c0,int(*)(void*,u32))(v,step);
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
 fill(bx,by,1,1,BG);fill(bx+bw-1,by,1,1,BG);fill(bx,by+bh-1,1,1,BG);fill(bx+bw-1,by+bh-1,1,1,BG);
 if(sel){frame(bx-4,by-4,bw+8,bh+8,2,TEXT);}
 if(head)fill(bx,by-3,bw,2,TEXT);
 /* lock rails: two bars under the square, filled to each lock's value */
 fill(bx,top+78,bw,2,RAISED);fill(bx,top+84,bw,2,RAISED);
 if(on&&s->locked[i]){int a=(int)(bw*s->l1[i]/1000),b=(int)(bw*s->l2[i]/1000);if(a<2)a=2;if(b<2)b=2;fill(bx,top+78,a,2,colour);fill(bx,top+84,b,2,colour);}
 /* probability, lower left under the step number */
 u32 p=s->prob[i];
 if(on&&s->note[i]&&s->cond[i]>=100&&s->cond[i]<135)text(s,ctx,x+12,top+62,34,16,((const char**)0x081b6000u)[s->cond[i]],MUTED);
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
static void track_snapshot(void *col,void *v,u32 i,TrackPaint *next){
 zero(next,sizeof(*next));next->handle=W(col,0x2dc);
 next->bitmap=W(col,0x4b4);
 next->flags=(B(v,0x4aa4)==i)|((u32)B(col,0x2e0)<<1)|((u32)B(col,0x2e1)<<2)|((u32)B(col,0x2e2)<<3)|((u32)B(col,0x2d9)<<8);
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
static void track_column(void *col,void *ctx){
 u32 i;void *v=tracks_view(col,&i);if(!v||B(col,0x30)||!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 PG *s=state();if(!s)return;void *SURF=(void*)W(ctx,4);if(!SURF)return;
 if(s->tracks_view!=(u32)v){s->tracks_view=(u32)v;s->tracks_valid=0;s->outputs_valid=0;}
 TrackPaint next;track_snapshot(col,v,i,&next);
 void *icon=(u8*)col+0x480;
 TrackPaint *old=&s->tracks[i];
 int full=B(ctx,0)||!(s->tracks_valid&(1u<<i));
 if(full||old->handle!=next.handle||((old->flags^next.flags)&0xff00u)){
  next.type=next.handle?FN(0x08133f7c,u32(*)(void*,void*))(MODEL,&next.handle):0;
  extern int analog_track(u32);
  if(next.type==18&&analog_track(next.handle))next.type=23;
 }else next.type=old->type;
 int redraw=full||!equal(old,&next,__builtin_offsetof(TrackPaint,meter));
 int x=6+159*(int)i,selected=next.flags&1u,muted=next.flags&10u;
 u32 ground=selected?SELECTED:BG,colour=FN(0x08140ebc,u32(*)(u32))(i);
 if(redraw){
  fill(x,73,159,COLUMN_END-73,ground);
  s->ground=ground;
  fill(x+14,73,125,1,colour);
  char num[4];number(num,i+1);
  textf(s,ctx,x+14,77,40,28,num,colour,TRACK_FONT,1);
  if(next.handle)textf(s,ctx,x+8,106,143,30,next.name,muted?FAINT:TEXT,TRACK_BOLD,CENTRE);
  if(next.handle){
   u32 bw=H(icon,0x38),bh=H(icon,0x3a);
   if(next.type==23){
    for(int ramp=0;ramp<3;ramp++)for(int k=0;k<=13;k++)
     fill(x+58+13*ramp+k,223-2*k,2,2,muted?FAINT:colour);
    for(int ramp=1;ramp<3;ramp++)fill(x+58+13*ramp,197,2,28,muted?FAINT:colour);
   }else if(!B(icon,0x30)&&next.bitmap&&bw<=64&&bh<=64){
    const signed char *bitmap=(const signed char*)next.bitmap;
    for(u32 row=0;row<bh;row++)for(u32 at=0;at<bw;){
     if(bitmap[row*bw+at]>=0){at++;continue;}
     u32 first=at++;while(at<bw&&bitmap[row*bw+at]<0)at++;
     fill(x+62+(int)first,197+(int)row,(int)(at-first),1,muted?FAINT:colour);
    }
   }
   textf(s,ctx,x+4,231,149,30,track_type(next.type),muted?FAINT:MUTED,TRACK_FONT,CENTRE);
   frame(x+66,378,24,24,1,selected?FAINT:RULE);
  }else{
   fill(x+69,209,18,2,FAINT);fill(x+77,201,2,18,FAINT);
  }
  if(next.flags&2u)textf(s,ctx,x+110,77,22,28,"M",MUTED,TRACK_FONT,CENTRE);
  if(next.flags&4u)textf(s,ctx,x+135,77,22,28,"S",TEXT,TRACK_FONT,CENTRE);
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
static void output_cell(PG *s,void *ctx,u32 i,const char *lines,u32 left,u32 right,int audio){
 void *SURF=(void*)W(ctx,4);if(!SURF)return;
 s->ground=0;
 int x=6+159*(int)i;
 int full=B(ctx,0)||!(s->outputs_valid&(1u<<i))||!equal(lines,s->output_text[i],64);
 if(full){
  fill(x,0,159,73,BG);
  textf(s,ctx,x+4,4,149,28,lines,TEXT,TRACK_FONT,CENTRE);
  textf(s,ctx,x+4,32,149,28,lines+32,TEXT,BIG,CENTRE);
  for(u32 j=0;j<64;j++)s->output_text[i][j]=lines[j];
 }
 if(audio&&lines[0]){
  u32 width=meter_width(left,135),w2=meter_width(right,135);if(w2>width)width=w2;
  if(full||width!=s->output_meter[i][0]){
   fill(x+10,62,135,1,RAISED);fill(x+10,62,(int)width,1,MUTED);
  }
  s->output_meter[i][0]=s->output_meter[i][1]=(u16)width;
 }
 s->outputs_valid|=1u<<i;
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
static u32 macro_focus_hash(u32 mode,u32 i){return (mode&1u)?0x40000000u:((mode>>1)&7u)==i?0x80000000u:0;}
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
static void ring(void *SURF,int cx,int cy,int r,int from,int to,u32 colour){
 if(from<0||to<0)return;if(from>to){int t=from;from=to;to=t;}
 while(from<to){
  int next=(from/10+1)*10;if(next>to)next=to;
  int x,y,endx,endy;ring_point(from,r,&x,&y);ring_point(next,r,&endx,&endy);
  x+=cx;y+=cy;endx+=cx;endy+=cy;
  int dx=endx-x,dy=endy-y,sx=dx<0?-1:1,sy=dy<0?-1:1;
  if(dx<0)dx=-dx;if(dy<0)dy=-dy;int err=dx-dy;
  for(;;){fill(x,y,2,2,colour);if(x==endx&&y==endy)break;int e=2*err;if(e>-dy){err-=dy;x+=sx;}if(e<dx){err+=dx;y+=sy;}}
  from=next;
 }
}
static void macro_ring(PG *s,void *ctx,int cx,int cy,int radius,const MacroDisplay *d){
 void *SURF=(void*)W(ctx,4);
 if(!d->count)ring(SURF,cx,cy,radius,0,360,RULE);
 for(u32 j=0;j<d->count;j++){
  const MacroTargetDisplay *t=&d->targets[j];int r=radius-(int)j*6;
  u32 colour=t->track<8?0xf7u+t->track:MUTED;
  ring(SURF,cx,cy,r,0,360,RULE);
  ring(SURF,cx,cy,r,ring_position(t->from,t->low,t->high),
       ring_position(t->to,t->low,t->high),colour);
  if(t->valid){int at=ring_position(t->current,t->low,t->high);if(at>=0){int px,py;ring_point(at,r,&px,&py);fill(cx+px-1,cy+py-1,4,4,TEXT);}}
 }
 char amount[8];
 if(d->rejected){amount[0]='!';amount[1]=0;}
 else{number(amount,d->value);if(d->value<10){amount[0]=(char)('0'+d->value);amount[1]=0;}}
 textf(s,ctx,cx-24,cy-14,50,28,amount,d->count?TEXT:FAINT,BIG,CENTRE);
}
static void perform_macro(PG *s,void *ctx,u32 i,const MacroDisplay *d,u32 mode){
 void *SURF=(void*)W(ctx,4);int x=6+159*(int)i,cx=x+78;
 fill(x,8,159,194,BG);char label[32]={'M',(char)('1'+i),0};
 textf(s,ctx,x+4,12,149,28,label,TEXT,BIG,CENTRE);
 macro_ring(s,ctx,cx,78,37,d);
 for(u32 j=0;j<d->count;j++){
  const MacroTargetDisplay *t=&d->targets[j];u32 colour=t->track<8?0xf7u+t->track:MUTED;
  u32 k=0;
  if(t->track<8){label[k++]='1'+(char)t->track;label[k++]=' ';label[k++]='/';label[k++]=' ';}
  else{label[k++]='P';label[k++]='R';label[k++]='J';label[k++]=' ';}
  for(u32 n=0;t->name[n]&&n<11&&k<31;n++)label[k++]=t->name[n];label[k]=0;
  textf(s,ctx,x+2,114+(int)j*26,153,26,label,colour,BIG,CENTRE);
 }
 if(d->armed)textf(s,ctx,x+95,8,58,28,"MAP",TEXT,BIG,CENTRE);
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
 s->ground=BG;fill(0,8,1280,423,BG);
 for(u32 i=0;i<8;i++){
  int x=6+159*(int)i,cx=x+78;MacroDisplay d;
  macro_snapshot(i,&d);
  u32 ground=(int)i==selected?0xa3u:BG;
  fill(x,88,159,340,ground);s->ground=BG;
  char label[32]={'M',(char)('1'+i),0};
  char value[24];number(value,d.value);
  if(controls){
   MacroDisplay focused;macro_snapshot((u32)selected,&focused);
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
  else macro_ring(s,ctx,cx,62,23,&d);
  s->ground=ground;
  if(d.armed)textf(s,ctx,x+99,394,54,28,"MAP",TEXT,BIG,CENTRE);
  for(u32 j=0;j<3;j++){
   const MacroTargetDisplay *t=&d.targets[j];int top=104+(int)j*104;
   if(j>=d.count||!t->name[0]){
    textf(s,ctx,x+8,top+10,143,28,"--",FAINT,BIG,CENTRE);continue;
   }
   u32 colour=t->track<8?0xf7u+t->track:MUTED;
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
int fx_screen_select(void*,int,int);
static void segment(void *SURF,int x,int y,int ex,int ey,u32 colour){
 int dx=ex-x,dy=ey-y,sx=dx<0?-1:1,sy=dy<0?-1:1;
 if(dx<0)dx=-dx;if(dy<0)dy=-dy;int err=dx-dy;
 for(;;){fill_(SURF,x,y,2,2,colour);if(x==ex&&y==ey)break;int e=2*err;if(e>-dy){err-=dy;x+=sx;}if(e<dx){err+=dx;y+=sy;}}
}
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
 for(u32 i=0;i<7;i++){
  int px=x+offsets[i];fill(px,top,1,height,RULE);
  if(i!=3&&i!=5)textf(s,ctx,px-30,296,60,28,freq[i],TEXT,BIG,CENTRE);
  if(i)segment(SURF,x+offsets[i-1],fx_eq_y(top,height,db[i-1]),px,fx_eq_y(top,height,db[i]),colour);
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
static void fx_compressor(PG *s,void *ctx,const int *v,u32 colour){
 void *SURF=(void*)W(ctx,4); int x=664,top=148,width=210,height=132,ratio=v[10]<1?1:v[10];
 for(int db=-60;db<=0;db+=20){int y=top+height-(db+60)*height/60;fill(x,y,width,1,db?RULE:FAINT);}
 for(int db=-60;db<=0;db+=20){int px=x+(db+60)*width/60;fill(px,top,1,height,RULE);}
 for(int i=0;i<=48;i++){
  int input=-60+i*60/48,output=input<=v[9]?input:v[9]+(input-v[9])/ratio;
  int px=x+i*width/48,py=top+height-(output+60)*height/60;
  if(i){int prev=-60+(i-1)*60/48,prevout=prev<=v[9]?prev:v[9]+(prev-v[9])/ratio;
   segment(SURF,x+(i-1)*width/48,top+height-(prevout+60)*height/60,px,py,colour);}
 }
 textf(s,ctx,884,146,140,28,"Reduction",TEXT,BIG,CENTRE);
 fill(942,174,12,100,RAISED);
 textf(s,ctx,906,280,104,28,"-- dB",FAINT,BIG,CENTRE);
 textf(s,ctx,662,332,172,28,"Threshold",TEXT,BIG,CENTRE);
 textf(s,ctx,844,332,172,28,"Ratio",TEXT,BIG,CENTRE);
 char value[24];fx_db(value,v[9]);textf(s,ctx,662,362,172,28,value,TEXT,BIG,CENTRE);
 fx_value(value,v[10],":1");textf(s,ctx,844,362,172,28,value,TEXT,BIG,CENTRE);
}
static void fx_clip(PG *s,void *ctx,const int *v,u32 colour){
 void *SURF=(void*)W(ctx,4);int x=1070,top=148,width=176,height=122;
 for(int i=0;i<=60;i++){
  int input=-300+i*10,abs=input<0?-input:input,output;
  if(abs>30)output=input<0?-10:10;
  else output=input*(2700+input*input)/(2700+9*input*input);
  int px=x+i*width/60,py=top+height/2-output*height/26;
  if(i){int prev=-300+(i-1)*10,pabs=prev<0?-prev:prev,pout;
   if(pabs>30)pout=prev<0?-10:10;else pout=prev*(2700+prev*prev)/(2700+9*prev*prev);
   segment(SURF,x+(i-1)*width/60,top+height/2-pout*height/26,px,py,colour);}
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
 u32 colour=0xf7u+track;
 fx_eq(s,ctx,v,colour);fx_compressor(s,ctx,v,colour);fx_clip(s,ctx,v,colour);
 s->ground=0;
}
static void track_fx_tick(void *bar,void *ctx){
 PG *s=state();if(!s||!ctx||!fx_screen_active()||(u32)bar!=fx_screen_bar())return;
 if(TICK-s->fx_stamp<100u)return;s->fx_stamp=TICK;
 u32 bank=0,track=0;int v[18];if(!fx_screen_snapshot(&bank,&track,v))return;
 u32 words[20];words[0]=bank;words[1]=track;for(u32 i=0;i<18;i++)words[i+2]=(u32)v[i];
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
int chord_keys_snapshot(u32,u32*,u32*,u32*);
int perf_notes_name(u32,const u32*,char*);
static int key_on(const u32 *notes,u32 pitch){return (notes[pitch>>5]>>(pitch&31u))&1u;}
static u32 keys_poll(PG *s){
 u32 owner=0,notes[4],held=0,root=128;
 FN(0x08133cfc,int(*)(void*,u32*))(MODEL,&owner);
 if(s->keys_owner!=owner){
  s->keys_owner=owner;s->keys_held=s->keys_valid=0;zero(s->keys_notes,sizeof(s->keys_notes));
  s->keys_name[0]=s->keys_list[0]=0;
 }
 if(chord_keys_snapshot(owner,notes,&held,&root)){
  for(u32 i=0;i<4;i++)s->keys_notes[i]=notes[i];s->keys_held=held;s->keys_root=root;s->keys_valid=1;
 }
 return snapshot_hash(s->keys_notes,sizeof(s->keys_notes))^s->keys_owner^(s->keys_held*31u)^(s->keys_root<<16)^s->keys_valid;
}
static void pitch_text(char *out,u32 pitch){
 static const char *const names[12]={"C","C#","D","D#","E","F","F#","G","G#","A","A#","B"};
 const char *p=names[pitch%12];u32 n=0;while(*p)out[n++]=*p++;
 int octave=(int)(pitch/12)-1;if(octave<0){out[n++]='-';octave=-octave;}
 out[n++]=(char)('0'+octave);out[n]=0;
}
static void perform_keys(PG *s,void *ctx,u32 mode){
 void *SURF=(void*)W(ctx,4);u32 colour=0xf7u+((mode>>8)&7u);
 fill(0,312,1280,112,BG);fill(20,312,1240,1,RULE);
 if(s->keys_held){
  u32 k=0,first=128,total=0;
  for(u32 p=0;p<128;p++)if(key_on(s->keys_notes,p)){
   if(first==128)first=p;total++;char note[6];pitch_text(note,p);
   u32 n=0;while(note[n])n++;
   if(k+n+2<sizeof(s->keys_list)-4){if(k)s->keys_list[k++]=' ';for(u32 j=0;j<n;j++)s->keys_list[k++]=note[j];}
   else{if(k+4<sizeof(s->keys_list)){s->keys_list[k++]=' ';s->keys_list[k++]='.';s->keys_list[k++]='.';s->keys_list[k++]='.';}break;}
  }
  s->keys_list[k]=0;zero(s->keys_name,sizeof(s->keys_name));
  if(total==1)pitch_text(s->keys_name,first);
  else{const char *p="Notes";for(u32 i=0;p[i];i++)s->keys_name[i]=p[i];
   if(s->keys_held==1)perf_notes_name(s->keys_root,s->keys_notes,s->keys_name);}
 }
 int remembered=s->keys_name[0]!=0;
 textf(s,ctx,20,320,410,26,s->keys_held?"Held notes":remembered?"Released":"Held notes",MUTED,BIG,1);
 textf(s,ctx,20,348,410,38,remembered?s->keys_name:"--",s->keys_held?TEXT:FAINT,BIG,1);
 textf(s,ctx,20,394,410,26,s->keys_list,s->keys_held?MUTED:FAINT,BIG,1);
 /* Two octaves, C3..B4: actual MIDI pitches, never folded modulo 12. */
 static const u8 white[7]={0,2,4,5,7,9,11},black[5]={1,3,6,8,10},after[5]={0,1,3,4,5};
 for(u32 octave=0;octave<2;octave++)for(u32 i=0;i<7;i++){
  u32 pitch=48+12*octave+white[i];int x=448+(int)(octave*7+i)*58;
  fill(x,326,56,94,key_on(s->keys_notes,pitch)?colour:BG);frame(x,326,56,94,1,RULE);
  if(!i){char label[6];pitch_text(label,pitch);s->ground=key_on(s->keys_notes,pitch)?colour:BG;textf(s,ctx,x+4,397,48,20,label,key_on(s->keys_notes,pitch)?BG:MUTED,BIG,CENTRE);s->ground=0;}
 }
 for(u32 octave=0;octave<2;octave++)for(u32 i=0;i<5;i++){
  u32 pitch=48+12*octave+black[i];int x=448+(int)(octave*7+after[i]+1)*58-16;
  fill(x,326,32,57,key_on(s->keys_notes,pitch)?colour:BG);frame(x,326,32,57,1,RULE);
 }
}
static void perform_row(void *bar,void *ctx,int kind){
 if(!ctx||(!B(ctx,0)&&!B(ctx,1)))return;
 PG *s=state();void *SURF=(void*)W(ctx,4);if(!s||!SURF)return;s->ground=0;
 char name[12];zero(name,sizeof(name));u32 mode=perf_display_state(name);
 int full=B(ctx,0)||s->perform_bar!=W(bar,0x2c);
 if(s->perform_bar!=W(bar,0x2c)){s->perform_bar=W(bar,0x2c);s->perform_valid=0;}
 if(kind==1){
  int dirty=0;
  for(u32 i=0;i<8;i++){
   MacroDisplay d;macro_snapshot(i,&d);u32 h=snapshot_hash(&d,sizeof(d))^macro_focus_hash(mode,i);
   if(full||!(s->perform_valid&(1u<<i))||h!=s->perform_hash[i]){perform_macro(s,ctx,i,&d,mode);dirty=1;}
   s->perform_hash[i]=h;s->perform_valid|=1u<<i;
  }
  if(dirty)frame(6,8,1268,194,2,mode&1u?BG:TEXT);
  return;
 }
 static const char *const labels[8]={"Type","Voicing","Inversion","Mode","Rate","Octaves","Gate","Arp"};
 int headers=full||!(s->perform_valid&256u)||mode!=s->perform_controls;
 int dirty=headers;
 if(headers){
  fill(0,202,1280,38,BG);fill(20,207,1240,1,RULE);
  u32 track=(mode>>8)&7u,colour=0xf7u+track;char title[16]="Track ";
  title[6]=(char)('1'+track);title[7]=0;
  textf(s,ctx,20,212,90,28,"Chord",mode&16u?TEXT:FAINT,BIG,1);
  textf(s,ctx,110,212,65,28,mode&16u?"ON":"OFF",mode&16u?colour:FAINT,BIG,1);
  textf(s,ctx,497,212,72,28,"Arp",mode&96u?TEXT:FAINT,BIG,1);
  textf(s,ctx,575,212,85,28,(mode&96u)==64u?"LATCH":mode&96u?"ON":"OFF",mode&96u?colour:FAINT,BIG,1);
  textf(s,ctx,1000,212,255,28,title,colour,BIG,2);
 }
 for(u32 i=0;i<8;i++){
  void *slot=(u8*)bar+0x38+i*0x468;char lines[64];zero(lines,sizeof(lines));
  for(u32 j=0;j<31;j++)lines[j]=B(slot,0xd9+j);
  if(full||!(s->perform_valid&256u)||!equal(lines,s->perform_text[i],64)){
   dirty=1;
   int x=6+159*(int)i;fill(x,242,159,60,BG);
   textf(s,ctx,x+8,242,145,26,labels[i],MUTED,BIG,1);
   textf(s,ctx,x+8,270,145,28,lines,TEXT,BIG,1);
   for(u32 j=0;j<64;j++)s->perform_text[i][j]=lines[j];
  }
 }
 u32 keys=keys_poll(s);
 if(full||!(s->perform_valid&256u)||keys!=s->keys_hash||mode!=s->perform_controls||!equal(name,s->perform_name,sizeof(name))){
  perform_keys(s,ctx,mode);s->keys_hash=keys;
  for(u32 i=0;i<sizeof(name);i++)s->perform_name[i]=name[i];
 }
 s->perform_controls=mode;s->perform_valid|=256u;
 if(dirty)frame(6,208,1268,96,2,mode&1u?TEXT:BG);
}
void pg_perform_tick(void *bar,void *ctx){
 if(!ctx)return;
 if(fx_screen_active()&&(u32)bar==fx_screen_bar()){track_fx_tick(bar,ctx);return;}
 if(!perf_bar_kind(bar))return;
 if(perf_bar_kind(bar)==3){macro_editor_tick(bar,ctx);return;}
 PG *s=existing();if(!s){B(ctx,1)=1;return;}
 if(perf_bar_kind(bar)!=1)return;
 if(TICK-s->keys_stamp>=33u){s->keys_stamp=TICK;if(keys_poll(s)!=s->keys_hash)B(ctx,1)=1;}
 if(TICK-s->perform_stamp<100u)return;s->perform_stamp=TICK;
 u32 mode=perf_display_state(0);
 for(u32 i=0;i<8;i++){
  MacroDisplay d;macro_snapshot(i,&d);
  if(!(s->perform_valid&(1u<<i))||s->perform_hash[i]!=(snapshot_hash(&d,sizeof(d))^macro_focus_hash(mode,i))){B(ctx,1)=1;break;}
 }
 if(s->perform_controls!=mode)B(ctx,1)=1;
}
__attribute__((used,retain)) void pg_bar_paint(void *bar,void *ctx){
 if(fx_screen_active()&&(u32)bar==fx_screen_bar()){track_fx_paint(state(),bar,ctx);return;}
 int kind=perf_bar_kind(bar);if(kind==3){macro_editor(state(),bar,ctx);return;}if(kind){perform_row(bar,ctx,kind);return;}
 if(output_view(bar))output_row(bar,ctx);
 else FN(0x0816faec,void(*)(void*,void*))(bar,ctx);
}
__attribute__((used,retain)) void pg_bar_walk(void *bar,void *ctx,void *clip){
 if(fx_screen_active()&&(u32)bar==fx_screen_bar())return;
 if(perf_bar_kind(bar))return;
 if(output_view(bar))output_row(bar,ctx);
 else FN(0x0816f9e8,void(*)(void*,void*,void*))(bar,ctx,clip);
}
__attribute__((used,retain)) void pg_tracks_tick(void *view,void *ctx){
 FN(0x08160a20,void(*)(void*,void*))(view,ctx);
 PG *s=existing();if(!s)return;
 if(ctx)for(u32 i=0;i<8;i++){
  void *col=(u8*)view+0x34+i*COLUMN_STRIDE;TrackPaint next;
  track_snapshot(col,view,i,&next);next.type=s->tracks[i].type;
  int changed=s->tracks_view!=(u32)view||!(s->tracks_valid&(1u<<i))||
   !equal(&next,&s->tracks[i],__builtin_offsetof(TrackPaint,meter));
  for(u32 k=0;k<2;k++)if((next.handle?meter_width(W(col,0x31c+k*0x4c),92):0)!=s->tracks[i].meter[k])changed=1;
  if(changed)B(ctx,1)=1;
 }
 if(s->output_stamp==TICK)return;s->output_stamp=TICK;
 for(u32 i=0;i<4;i++){
  u16 channel=(u16)(8+i);u32 left=0xc2700000u,right=left; /* -60 dB */
  if(!FN(0x08138164,int(*)(void*,u16*,u32*,u32*))(MODEL,&channel,&left,&right))left=right=0xc2700000u;
  if(s->outputs[i][0]!=left||s->outputs[i][1]!=right){s->outputs[i][0]=left;s->outputs[i][1]=right;if(ctx)B(ctx,1)=1;}
 }
}
void pg_tracks_nav(void){
 PG *s=existing();if(!s)return;
 s->tracks_valid=s->outputs_valid=s->tracks_view=0;
 s->touches=s->down_col=s->tap_col=0;
 s->mixer_valid=s->mixer_values=s->mixer_view=s->compressor=s->mixer_config=s->mixer_drag=0;
}
__attribute__((used,retain)) void pg_tracks_event(void *view,void *event){
 FN(0x08160fb4,void(*)(void*,void*))(view,event);
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
 int twice=s->tap_col==(u32)col&&s->tap_handle==handle&&s->tap_zone==z&&s->tap_project==project&&TICK-s->tap_tick<450u;
 s->tap_col=0;
 if(z==1){
  if(handle){u32 muted=0;
   if(!FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&handle,0x13d,&muted)){
    FN(0x08104c00,void(*)(const char*))("Tracks: cannot read mute");return;
   }
   u32 event[5]={0xd3,handle,0x13d,!muted,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,event);
   u32 current=muted;
   if(FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&handle,0x13d,&current))
    FN(0x08180b94,void(*)(void*,u32))(col,current!=0);
   else FN(0x08104c00,void(*)(const char*))("Tracks: cannot refresh mute");
  }
  return;
 }
 u32 event[5]={twice&&z==2?0x7bu:0x7au,0,i,0,0};
 FN(0x0816085c,int(*)(void*,void*))(v,event);
 if(twice){
  if(z==4&&handle){u32 button[5]={0x73,0,11,0,0};FN(0x08142afc,void(*)(void*,void*))(MODEL,button);}
  return;
 }
 if(z==2||z==4){s->tap_col=(u32)col;s->tap_handle=handle;s->tap_zone=z;s->tap_tick=TICK;s->tap_project=project;}
}


#define MIXER_VT 0x0819dd20u
#define MIXER_PAGE 0x1fu
#define MIXER_COLUMN 0x750u
#define MIXER_COMP 0x1076u
static const u16 mix_keys[4]={0x134,0x13f,0x140,0x141};
static const u16 comp_keys[8]={0x9c,0x123,0x124,0x125,0x126,0x12e,0x127,0x130};
static void *mix_col(void *v,u32 i){return (u8*)v+0x34+i*MIXER_COLUMN;}
static void *mix_bar(void *v){return (u8*)v+0x7610;}
static int mix_get(u32 h,u32 key,int *value){
 return FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,key,value);
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
  else FN(0x08104c00,void(*)(const char*))("Mixer: cannot read controls");
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
 u32 ground=selected?SELECTED:BG,colour=FN(0x08140ebc,u32(*)(u32))(i);
 s->ground=ground;
 if(identity){
  fill(x,73,159,COLUMN_END-73,ground);fill(x+14,73,125,1,colour);
  char num[4];number(num,i+1);textf(s,ctx,x+14,77,40,28,num,colour,TRACK_FONT,1);
  if(n.handle)textf(s,ctx,x+8,106,143,30,n.name,dim?FAINT:TEXT,TRACK_BOLD,CENTRE);
  if(n.flags&2u)textf(s,ctx,x+110,77,22,28,"M",MUTED,TRACK_FONT,CENTRE);
  if(n.flags&4u)textf(s,ctx,x+135,77,22,28,"S",TEXT,TRACK_FONT,CENTRE);
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
   textf(s,ctx,x+4,MIX_METER_END+4,149,28,value,dim?FAINT:TEXT,TRACK_FONT,CENTRE);
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
static int mix_comp_key(u32 key){for(u32 i=0;i<8;i++)if(comp_keys[i]==key)return 1;return 0;}
/* Compressor keys are Project Settings: native binds them (like the Main
   output strip) to the project node from 08133E54, not global FFFFFFFE. */
static u32 mix_comp_handle(void){u32 h=0;return FN(0x08133e54,int(*)(void*,u32*))(MODEL,&h)?h:0;}
static void mix_comp_config(PG *s,void *v){
 struct {u32 handles[8];u16 keys[8];int values[8];} config;
 u32 h=mix_comp_handle();
 if(!h){FN(0x08104c00,void(*)(const char*))("Mixer: no project for compressor");return;}
 for(u32 i=0;i<8;i++){
  config.handles[i]=h;config.keys[i]=comp_keys[i];
  if(!mix_get(h,comp_keys[i],&config.values[i])){
   FN(0x08104c00,void(*)(const char*))("Mixer: cannot read compressor");return;
  }
 }
 FN(0x08170394,void(*)(void*,void*))(mix_bar(v),&config);s->mixer_config=1;
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
  s->outputs_valid=0;FN(0x0816faec,void(*)(void*,void*))(mix_bar(v),ctx);
  B(ctx,0)=full;
 }
 else for(u32 i=0;i<8;i++){
  void *c=mix_col(v,8+i);char lines[64];zero(lines,sizeof(lines));
  /* The encoder binding buffer follows focus; output identity does not. */
  mix_output(v,i,lines);
  output_cell(s,ctx,i,lines,W(c,0x498),W(c,0x4e4),i<4||i==7);
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
  FN(0x0816f9e8,void(*)(void*,void*,void*))(mix_bar(v),ctx,clip);
 mix_foreign(v,ctx,clip,2);
}
static void mix_layout(void *v){
 int r[4]={6,407,1268,73};void *bar=mix_bar(v);
 FN(W((void*)W(bar,0),0x20),void(*)(void*,void*))(bar,r);
}
__attribute__((used,retain)) void pg_mixer_tick(void *v,void *ctx){
 FN(0x081b5000,void(*)(void*,void*))(v,ctx);
 PG *s=existing();if(!s||s->mixer_view!=(u32)v||!ctx)return;
 extern int macro_overlay(void);
 int overlay=macro_overlay();
 if(s->compressor&&!overlay){
  void *slot=(u8*)mix_bar(v)+0x38;
  if(H(slot,0x9c)!=comp_keys[0]||W(slot,0x34)!=mix_comp_handle())s->mixer_config=0;
  if(!s->mixer_config)mix_comp_config(s,v);
 }
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
 FN(0x0814b98c,void(*)(void*,void*))(v,event);
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
 if(B(MODEL,0x12c)!=MIXER_PAGE)return FN(0x0814baea,int(*)(void*,void*))(v,event);
 PG *s=mix_state(v);if(!s)return 1;u32 code=H(event,0);
 if(code==MIXER_COMP){
  s->compressor=1;s->mixer_config=s->outputs_valid=0;mix_comp_config(s,v);
  return 0;
 }
 if(s->compressor&&code==0xcf&&mix_comp_key(W(event,8))){
  u32 h=mix_comp_handle();if(!h)return 0;
  u32 e[5]={0xcf,h,W(event,8),W(event,12),0};
  FN(0x081403ec,int(*)(void*,void*))(MODEL,e);s->mixer_config=0;return 0;
 }
 if(code>=0x108&&code<=0x10b){s->compressor=0;s->outputs_valid=0;}
 int result=FN(0x0814baea,int(*)(void*,void*))(v,event);
 if(s->compressor)s->mixer_config=0;
 return result;
}
int pg_mixer_toolbar(void *model,void *out){
 if(B(model,0x12c)!=MIXER_PAGE)return 0;PG *s=existing();
 extern int header_fixed_tab(void*,unsigned,unsigned,const char*,int);
 for(u32 i=0;i<6;i++){
  void *record=(u8*)out+0x74+i*48;u32 id=H(record,44);
  if(id<0x108||id>0x10c||B(record,0x20))continue;
  if(s&&s->compressor){if(id<=0x10b)B(record,0x21)=0;continue;}
  /* Native 0x68 lights these widgets after the snapshot was taken; a stale
     record would make header_sync re-arm a relayout forever (W7 black footer). */
  if(W(0x30034d48u,0)==0x081b3680u)
   B(record,0x21)=B(0x30034d48u+(B(record,0x22)?0xa2cu:0x54cu)+i*0xd0u,0xac)?1:0;
 }
 void *removed=(u8*)out+0x74+4*48;
 if(H(removed,44)==MIXER_COMP){zero(removed,48);B(removed,0x20)=1;return 1;}
 return 0;
}
int pg_mixer_compressor(void){PG *s=existing();return B(MODEL,0x12c)==MIXER_PAGE&&s&&s->compressor;}
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
  FN(0x0816fa10,int(*)(void*,void*,void**))(v,point,out):0;
 PG *s=existing();*out=z==6&&s&&s->compressor?mix_bar(v):v;return 1;
}
static u32 mix_target(void *v,u32 i,u32 z,u32 *key){
 static const u16 output_keys[8]={0x138,0x137,0x136,0x135,0,0,0x18,0xa9};
 *key=z==6?output_keys[i]:z==1?0x13du:z>=2&&z<=5?mix_keys[z-2]:0;
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
 if(z>=2&&z<=6){
  if(!mix_get(h,key,&s->drag_value)){
   s->cancelled=1;FN(0x08104c00,void(*)(const char*))("Mixer: cannot start drag");return;
  }
  s->drag_sent=s->drag_value;
 }
 if(z!=1){
  W(v,0x75b4)=z==6?1u:0u;
  FN(0x0814b814,void(*)(void*))(v);
  if(z!=6){u32 e[5]={0x37,h,i,0,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,e);}
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
 if(!h||s->down_zone==9)return;
 u32 registry=W((void*)0x30031484u,0);void *d=(void*)(registry+key*32u);
 if(!registry||H(d,0)!=key){s->cancelled=1;FN(0x08104c00,void(*)(const char*))("Mixer: missing parameter bounds");return;}
 int fader=s->down_zone==2?MIX_METER_END-MIX_METER_TOP-2*MIX_METER_INSET:113;
 int delta=s->down_zone==2||s->down_zone==6?mix_bound(dy,-fader,fader)*66000/fader:
  s->down_zone==3?mix_bound(dx,-100,100)*2000/100:mix_bound(dx,-129,129)*1000/129;
 int value=mix_bound(s->drag_value+delta,(int)W(d,16),(int)W(d,20));
 if(value==s->drag_sent)return;
 u32 e[5]={s->down_zone==6?0xcfu:0xd3u,h,key,(u32)value,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,e);
 if(!mix_get(h,key,&value)){s->cancelled=1;FN(0x08104c00,void(*)(const char*))("Mixer: cannot refresh drag");return;}
 s->drag_sent=value;
 if(s->down_zone>=2&&s->down_zone<=5)s->mix_value[initial][s->down_zone-2]=value;
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
 if(!mix_get(h,key,&value)){FN(0x08104c00,void(*)(const char*))("Mixer: cannot read mute/solo");return;}
 u32 e[5]={0xd3,h,key,!value,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,e);
 if(!mix_get(h,key,&value)){FN(0x08104c00,void(*)(const char*))("Mixer: cannot refresh mute/solo");return;}
 FN(0x08173a68,void(*)(void*,u32))(mix_col(v,i),value!=0);
 FN(0x0814a828,void(*)(void*))(v);
}
int pg_mixer_bar_drag(void *bar,void *point,u32 id,int phase){
 void *v=(void*)W(bar,0x2c);PG *s=existing();
 if(!v||W(v,0)!=MIXER_VT||!s||s->compressor)return 0;
 extern int macro_overlay(void);
 if(phase==0){
  s->mixer_drag=0;if(macro_overlay())return 0;
  pg_mixer_down(v,point,id);s->mixer_drag=s->touches&&!s->cancelled?1u:0u;return 0;
 }
 if(!s->mixer_drag)return 0;
 if(phase==1){
  int dx=(int)W(point,0)-s->down_x,dy=(int)W(point,4)-s->down_y;
  if(dx<0)dx=-dx;if(dy<0)dy=-dy;
  if(s->mixer_drag==1&&dy>dx+5)s->mixer_drag=2;
  if(s->mixer_drag==1&&dx>dy+5){s->touches=0;s->mixer_drag=3;}
  if(s->mixer_drag==2){pg_mixer_move(v,point,id);return 1;}return 0;
 }
 int active=s->mixer_drag==2;
 if(active)pg_mixer_up(v,point,id);else s->touches=0;
 s->mixer_drag=0;return active;
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
 if(!FN(0x08133cfc,int(*)(void*,void*))(MODEL_,&h)||!h)return;
 FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL_,&h,0x73,&idx);
 if(idx>7)return;
 u8 c=(u8)FN(0x08140ebc,u32(*)(u32))(idx);
 u8 *g=(u8*)grid;
 if(g[0x5274]!=c){g[0x5274]=c;FN(0x0817527e,void(*)(void*))(grid);g[0x4f0]=1;}
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
  int pos=FN(0x081322ac,int(*)(void*,u32,void*,void*))(MODEL,t,&row,&queued);
  if(play){
   if(queued==(int)s->launch_row[t]||(pos!=-1&&row==(int)s->launch_row[t]&&queued<0))continue;
   FN(0x0810b5c8,void(*)(void*,u32,u32,u32))(engine,s->launch_track[t],0x64,1);
   FN(0x0810b5c8,void(*)(void*,u32,u32,u32))(engine,s->launch_track[t],0x63,s->launch_row[t]);
  }else if(pos!=-1||queued>=0)
   FN(0x0810b5c8,void(*)(void*,u32,u32,u32))(engine,s->launch_track[t],0x64,0);
 }
}
__attribute__((used,retain)) int pg_launch_event(void *view,void *event){
 u32 code=H(event,0);
 if(code<LAUNCH_SELECT||code>LAUNCH_STOP)
  return FN(0x0814a0d0,int(*)(void*,void*))(view,event);
 PG *s=state();if(!s)return 0;
 launch_group_check(s,view);
 if(code==LAUNCH_SELECT){
  s->launch_select=!s->launch_select;
  FN(0x0813130c,void(*)(void*))(MODEL);
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
 return FN(0x08172a08,int(*)(void*,void*))(column,event);
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
 FN(0x0814a7a4,void(*)(void*,void*))(view,ctx);
 PG *s=state();if(s){
  launch_group_check(s,view);
  for(u32 i=0;i<64;i++){
   LaunchCellPaint *c=&s->launch_cells[i];
   if((s->launch_cells_valid[i>>5]&(1u<<(i&31u)))&&c->clip&&
      (c->status==LAUNCH_QUEUED||c->status==LAUNCH_WAITING)&&
      ((c->selected>>1)&1u)!=((TICK/250u)&1u)){
    B(view,0x39)=1;if(ctx)B(ctx,1)=1;break;
   }
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
  FN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;
 }
 PG *s=state();if(!s){FN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;}
 launch_prepare_state(s,view);
 void *SURF=(void*)W(ctx,4);
 if(!SURF){s->launch_view=0;FN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;}
 u32 track=W(W(cell,0x2c),0x14),row=W(cell,0x14),index=track*8+row;
 if(track>=8||row>=8){FN(0x0816faec,void(*)(void*,void*))(cell,ctx);return;}
 void *status=(u8*)cell+0x34;LaunchCellPaint next;zero(&next,sizeof(next));
 next.clip=W(cell,0x278);next.status=W(status,0xa8);
 next.selected=s->launch_select||launch_has_group(s)?
  s->launch_group[track]&&s->launch_group[track]==next.clip:B(cell,0x288)!=0;
 next.colour=FN(0x08140ebc,u32(*)(u32))(track);
 int queued=next.status==LAUNCH_QUEUED||next.status==LAUNCH_WAITING;
 if(queued)next.selected|=((TICK/250u)&1u)<<1;
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
 *old=next;s->launch_cells_valid[bank]|=mask;
}
__attribute__((used,retain)) void pg_launch_cell_walk(void *cell,void *ctx,void *clip){
 (void)clip;
 void *view=launch_view_for_cell(cell);PG *s=existing();
 if(view&&s&&s->launch_view==(u32)view)return;
 FN(0x0816f9e8,void(*)(void*,void*,void*))(cell,ctx,0);
}
__attribute__((used,retain)) void pg_launch_header_paint(void *label,void *ctx){
 if(W(label,0)!=LAUNCH_LABEL_VT){
  FN(0x0817e780,void(*)(void*,void*))(label,ctx);return;
 }
 void *column=(void*)W(label,0x2c);
 void *view=column&&W(column,0)==LAUNCH_COLUMN_VT?(void*)W(column,0x2c):0;
 if(!view||W(view,0)!=LAUNCH_VT||label!=(u8*)column+0x78){
  FN(0x0817e780,void(*)(void*,void*))(label,ctx);return;
 }
 if(!launch_should_paint(ctx))return;
 PG *s=state();if(!s)return;launch_prepare_state(s,view);
 void *SURF=(void*)W(ctx,4);if(!SURF)return;
 u32 track=W(column,0x14);if(track>=8)return;
 u32 colour=FN(0x08140ebc,u32(*)(u32))(track);
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
