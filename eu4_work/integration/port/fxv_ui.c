/* P168 exp8 (FX views; run 16 rework to design/native/native_modfx.png and native_sendfx.png): the FX button views
 * "Mod FX | Send FX | XY Pads". 1.6.8 only.
 *
 * This directory is not translated by tools/port/make_tree.py: every native address here is a 1.6.8 address
 * (docs/port-1.6.8/FXVIEWS_PROGRESS.md has the evidence). The 1.6.1 build compiles an empty unit.
 *
 * The native FX Settings page (model page 0B, view ctor 08149014, vtable 081A0A20) is one SectionGroup
 * (view+9180) with the sections Mod FX (0), Delay (1), Reverb (2) and, in Shimmer mode, Shimmer (3); native Up/Down
 * move the active section (+39C). The views are projections of that one native page, no new parameters:
 *   Mod FX view  = the Mod FX section only: its native encoder row at the top in the thin frame, NO effect list
 *                  (owner correction 13 Nov: Left/Right switch the type, shown only in encoder 1 and the picture),
 *                  a full-width picture computed live from the native values (type, amount, rate, feedback,
 *                  distortion; see modfx_picture), 8 track toggles just above the footer that switch the native
 *                  track output "1" <-> "1 w/ Mod FX" (key 2D), with the track names at the native 24 px;
 *   Send FX view = Delay row at the top, Reverb row just above the footer (Shimmer, when present, between them),
 *                  "Delay"/"Reverb" titles over the picture area; the native active-section frame and Up/Down
 *                  (the v3 delay/reverb pictures are a later run);
 *   XY Pads      = the native XY page 0C.
 * The rows are moved after every native layout (tick): the bar subtree is shifted, the frame follows the active row.
 * State: 240416BC = 'FV' << 16 | pending section + 1 (bits 8-9) | shown view (bit 0: 0 Mod FX, 1 Send FX);
 *        240416B8 = hash of the values the Mod FX picture/toggles show (a change asks for a full repaint). Both in
 *        the unused tail of the Track FX mailbox line (FxMail ends at +26C, XY uses +26C..+277). M4 only; absent
 *        tag = Mod FX view.
 * GPL-3.0-or-later. */
#include "../native_ids.h"
#include "../fx_shared.h"
#include "../ui_native.h"
#if BENTO_FW==168
#define FV W((void*)0x240416bcu,0)
#define FV_SEEN W((void*)0x240416b8u,0)  /* hash of the picture values + track outputs last shown */
#define FV_TAG 0x46560000u
#define SG(v) ((u8*)(v)+0x9180u)
#define BAR(g,i) ((u8*)W(g,0x34u+4u*(i)))
#define TITLE(g,i) ((u8*)(g)+0x44u+(i)*0x70u)
#define CELL(bar,c) (int)W(bar,0x38u+(c)*0x468u+0xa0u)
#define HIDE(w,h) B((w),0x30)=(u8)(h)
#define TABS ((u8*)0x300366e8u+0xa44u+0xceu) /* root tab widgets, +CE: left divider (fx_nav sets it back) */
#define TRACK_HANDLE(t,h) NFN(0x08134dbc,u32(*)(void*,u32,u32*))(MODEL,t,h)
#define PIC_X 60
#define PIC_W 1160
#define PIC_TOP 92
#define PIC_H 216
#define PIC_MID (PIC_TOP+PIC_H/2)
#define SQ_TOP 334
int header_fixed_tab(void*,unsigned,unsigned,const char*,int);
u32 *native_fx_view_slot(int);
void pg_text(void*,u32,int,int,int,const char*,u32);
void pg_curve(void*,int,int,int,const short*,u32);
static u32 fv(void){u32 w=FV;return (w&0xffff0000u)==FV_TAG?w:FV_TAG;}
static u32 modview(void *g){return !(W(g,0x39c)&3u);} /* native active section 0 = Mod FX */
static u32 type_sel(void *g){return ((u32)CELL(BAR(g,0),0)+2u)%3u;} /* native type 1/2/0 -> Chorus/Phaser/Flanger 0/1/2 */
static const char *const tab_name[3]={"Mod FX","Send FX","XY Pads"};
/* Footer (owner: mixing-desk order, right-aligned, no dividers): Mod FX | Send FX | XY Pads (ids 1066..1068). */
int fxv_toolbar(void *out,u32 page){
 u32 sel=page==0x0cu?2u:fv()&1u,c=0;
 for(u32 i=0;i<3;i++){c|=(u32)header_fixed_tab(out,3+i,0x1066u+i,tab_name[i],sel==i);B(TABS,(3+i)*0xd0u)=0;}
 W(out,0)=0x5846u;return (int)c;
}
/* c = 0 Mod FX, 1 Send FX, 2 XY Pads (footer taps 1066..1068 via native_fx_event), 3 = FX button (the next view). */
int fxv_go(void *m,u32 c){
 u32 page=B(m,0x12c);if(c>3||(page!=0x0bu&&page!=0x0cu))return 0;
 if(c==3)c=page==0x0cu?0:(fv()&1u)?2:1;
 u32 *last=native_fx_view_slot(1),to=c==2?0x0cu:0x0bu;if(last)*last=to;
 if(c<2)FV=(fv()&~0x301u)|(c+1u)<<8|c; /* pending section: Mod FX = 0, Send FX = Delay (1) */
 NFN(0x08143d44,void(*)(void*,u32,u32,u32,u32))(m,to,0,0,0);return 1;
}
static void setrect(void *w,int x,int top,int width,int h){int r[4]={x,480-top-h,width,h};((void(*)(void*,int*))W(W(w,0),0x20))(w,r);}
/* Move a widget subtree down by 'down' screen pixels (rects are bottom-up; children +18, siblings +20). */
static void shift(u8 *w,int down){W(w,8)-=(u32)down;for(u8 *c=(u8*)W(w,0x18);c;c=(u8*)W(c,0x20))shift(c,down);}
static int row_top(u32 i,u32 mod){return mod||i==1?8:i==2?354:272;} /* first cell top: Delay top, Reverb above the footer */
static u32 outputs(void){u32 bits=0;for(u32 t=0;t<8;t++){u32 h=0,v=9;TRACK_HANDLE(t,&h);if(h)ui_get(&h,0x2du,&v);bits|=(v>1?2u:v)<<2*t;}return bits;}
static u32 seen(void *g,u32 n){u32 h=outputs()*31u+n;for(u32 i=0;i<n;i++){u8 *b=BAR(g,i);for(u32 c=0;c<8;c++)h=h*31u+(u32)CELL(b,c);}return h;} /* run 17: every row (Send FX pictures) */
/* View tick (slot 0): native tick, then the pending section; per view the rows are shown/hidden and moved, the
   frame follows the active row; the Mod FX view asks for a full repaint when a picture value or an output changes. */
__attribute__((used)) void fxv_tick(void *v,void *ctx){
 NFN(0x08149426,void(*)(void*,void*))(v,ctx);
 u8 *g=SG(v);u32 w=fv(),n=W(g,0x204);if(n<3||n>4)return;
 if(w&0x300u)NFN(0x08172de6,void(*)(void*,u32))(g,(w>>8&3u)-1u);
 u32 mod=modview(g),a=W(g,0x39c)&3u;FV=(w&~0x301u)|!mod;
 HIDE(g+0x358,1); /* bottom separator box */
 for(u32 i=0;i<n;i++){
  u8 *bar=BAR(g,i),*title=TITLE(g,i);
  HIDE(bar,mod?i!=0:i==0);HIDE(g+0x248u+i*0x44u,1); /* no grey section title boxes */
  HIDE(title,mod||i==0||i==3); /* Send FX: "Delay" / "Reverb" over the picture area */
  if(!mod&&(i==1||i==2)&&(int)W(title,4)!=(i==1?24:664))setrect(title,i==1?24:664,80,200,26);
  u8 *c0=bar+0x38;int down=row_top(i,mod)-(480-(int)W(c0,8)-(int)W(c0,16));if((mod?!i:i)&&down)shift(bar,down);
 }
 u8 *f=g+0x208;W(f,4)=6;W(f,8)=(u32)(480-(row_top(a,mod)-4)-70);W(f,12)=1272;W(f,16)=70; /* thin frame A, active row */
 if(mod)HIDE(f,2);else if(B(f,0x30)==2)HIDE(f,0); /* run 19 (owner rule): no frame in the Mod FX view - one row, nothing to choose (2 = hidden by the rule, see pg_sg_tick) */
 {u32 h=seen(g,n)^mod;if(mod&&type_sel(g))h^=W((void*)0x3001fe2cu,0)/50u*0x9e3779b9u; /* run 17: Flanger/Phaser animate (<= 20 fps) */
  if(h!=FV_SEEN){FV_SEEN=h;if(ctx)B(ctx,1)=1;}} /* run 17: both views' pictures are live */
}
static void box(void *surf,int x,int top,int w,int h,u32 c){if(w>0&&h>0){int r[4]={x,480-top-h,w,h};NFN(0x08168d62,void(*)(void*,u32,void*))(r,c,surf);}}
static void outline(void *surf,int x,int top,int w,int h,int t,u32 c){box(surf,x,top,w,t,c);box(surf,x,top+h-t,w,t,c);box(surf,x,top,t,h,c);box(surf,x+w-t,top,t,h,c);}
static int sn(u32 p){int t=(int)(p&127u),y=t*(128-t)>>4;return p&128u?-y:y;} /* parabolic sine, period 256, +-256 */
/* The Mod FX picture, live from the native Mod FX values (0..1000 each), white/grey (owner: neutral).
     Chorus       = three voices (white, grey, dim): amount -> height (8..104 px) and phase spread, rate -> cycles
                    across the width (1..8).
   Run 17 (owner go-ahead 13 Nov; design/native/flanger_pages_v2.png mk37.py, phaser_pages.png mk38.py): Flanger+Dist
   and Phaser are LIVE, ANIMATED frequency-response curves: the white curve is where the sweep is now, the two dim
   curves mark the sweep range (Amount/Depth); it moves between them at the Rate (a triangle sweep of 4 s .. 0.5 s,
   repainted at most every 50 ms while the view is open).
     Flanger+Dist = a feedback comb |1/(1 - g e^-jwT)| on a log-ish axis, many narrow even peaks/notches; Feedback g
                    sharpens them; Distortion = a separate small waveform strip below that gets squarer at constant
                    height (tanh(g sin)/tanh g, g = 1 + 12 Dist).
     Phaser       = six first-order allpass stages mixed with the dry signal on 20 Hz..20 kHz: only a few BROAD dips
                    (never a dense comb); Feedback adds modest resonance next to them.
   Integer maths: parabolic sine/cosine (4096 per turn), atan(10^v) and log2 mantissa tables. */
static int sn12(u32 p){int t=(int)(p&2047u),y=t*(2048-t)>>8;return p&2048u?-y:y;} /* parabolic sine, 4096 per turn, +-4096 */
static const u8 lg2_m[32]={0,11,22,33,44,54,63,73,82,92,100,109,118,126,134,142,150,157,165,172,179,186,193,200,207,213,220,226,232,238,244,250};
static int lg2(u32 x){if(!x)return 0;int n=31-__builtin_clz(x);u32 m=n>=5?x>>(n-5)&31u:x<<(5-n)&31u;return n*256+lg2_m[m];} /* log2 in Q8 */
static const u16 atan_t[97]={1,1,1,1,1,1,2,2,2,2,3,3,4,4,5,6,7,8,9,10,12,13,15,18,21,24,27,32,37,42,49,56,65,75,86,100,115,132,152,174,200,228,260,295,334,375,419,465,512,559,605,649,690,729,764,796,824,850,872,892,909,924,938,949,959,968,975,982,987,992,997,1000,1003,1006,1009,1011,1012,1014,1015,1016,1017,1018,1019,1020,1020,1021,1021,1022,1022,1022,1022,1023,1023,1023,1023,1023,1023}; /* atan(10^v) in 1/4096 turns, v = -3..3 step 1/16 */
static int sweep(int rate){u32 period=4000u-(u32)rate*7u/2u,t=W((void*)0x3001fe2cu,0)%period;return (int)(t<period/2?t*2000u/period:(period-t)*2000u/period);} /* 0..1000 */
static void flanger_curve(short *ys,int top,int h,int delay,int g){ /* delay in 1/256 teeth, g Q12 */
 int lo=lg2(4096+g),span=lo-lg2(4096-g);
 for(int i=0;i<PIC_W/2;i++){
  int t=i*4096/(PIC_W/2),f=t*(1638+2458*t/4096)/4096; /* t^1.6 ~ t(0.4+0.6t), Q12 */
  int c=sn12((u32)(f*delay/256)+1024u),d=4096+g*g/4096-2*g*c/4096; /* 1+g^2-2g cos, Q12 */
  int v=(lo-lg2((u32)(d<1?1:d)*4096u)/2)*1000/span; /* normalised 0..1000: lo..hi magnitude (log) */
  if(v<0)v=0;if(v>1000)v=1000;ys[i]=(short)(top+h-h*v/1000);
 }
}
static void phaser_curve(short *ys,int top,int h,int fc_log,int amt,int g){ /* fc_log: log10 fc in Q8, amt/g Q12 */
 for(int i=0;i<PIC_W/2;i++){
  int v=(333+768*i/(PIC_W/2))-fc_log; /* log10(f/fc) Q8 over 20 Hz..20 kHz (log10 20 = 1.30) */
  int q=v*16+48*256;if(q<0)q=0;if(q>96*256-1)q=96*256-1;int k=q>>8,a=atan_t[k]+((atan_t[k+1]-atan_t[k])*(q&255)>>8); /* interpolated */
  u32 ph=(u32)(6*(2048-2*a)); /* six stages: phase 6(pi - 2 atan w) */
  int c=sn12(ph+1024u),s=sn12(ph),den=4096+g*g/4096-2*g*c/4096;if(den<64)den=64;
  int ar=(c-g)*4096/den,ai=s*4096/den,hr=4096-amt/2+amt/2*ar/4096,hi=amt/2*ai/4096;
  u32 m=(u32)(hr*hr/4096+hi*hi/4096);int db=(lg2(m?m:1)-12*256)*3; /* 10 log10 |h|^2 ~ 3.01 log2, dB in Q8 */
  if(db<-14*256)db=-14*256;if(db>10*256)db=10*256;ys[i]=(short)(top+h*(10*256-db)/(24*256));
 }
}
static void modfx_picture(void *surf,u32 type,int amount,int rate,int fb,int dist){
 static const u8 grey[4]={0xf2,0x92,0x52,0x42};
 short ys[PIC_W/2];
 box(surf,PIC_X,PIC_TOP,PIC_W,PIC_H,0xf1u);
 if(type==2){ /* Flanger+Dist: comb 96..236, line at 250, distortion strip 262..312 */
  int dmin=6*256*(1000-8*amount/10)/1000,dmax=6*256*(1000+8*amount/10)/1000,g=(300+650*fb/1000)*4096/1000,ph=sweep(rate);
  flanger_curve(ys,96,140,dmin,g);pg_curve(surf,PIC_X,PIC_W/2,2,ys,0x52u);
  flanger_curve(ys,96,140,dmax,g);pg_curve(surf,PIC_X,PIC_W/2,2,ys,0x52u);
  flanger_curve(ys,96,140,dmin+(dmax-dmin)*ph/1000,g);pg_curve(surf,PIC_X,PIC_W/2,2,ys,0xf2u);
  box(surf,PIC_X,250,PIC_W,1,0xf3u);
  int gd=4096+12*4096*dist/1000; /* tanh(g sin)/tanh g with tanh ~ x(27+x^2)/(27+9x^2), +-1 beyond 3 */
  for(int i=0;i<PIC_W/2;i++){
   int y[2];for(int j=0;j<2;j++){int x=j?gd:(int)((long long)gd*sn12((u32)(i*4*4096/(PIC_W/2)))/4096);
    if(x>3*4096)x=3*4096;if(x<-3*4096)x=-3*4096;long long x2=(long long)x*x/4096;y[j]=(int)((long long)x*(27*4096+x2)/(27*4096+9*x2));}
   ys[i]=(short)(287-25*y[0]/(y[1]?y[1]:1));
  }
  pg_curve(surf,PIC_X,PIC_W/2,2,ys,0xf2u);return;
 }
 if(type==1){ /* Phaser: 96..312, sweep 300 Hz..4 kHz (log10: 2.477..3.602) */
  int amt=amount*4096/1000,g=850*fb/1000*4096/1000,lo=634,hi=922,ph=sweep(rate);
  phaser_curve(ys,96,216,lo,amt,g);pg_curve(surf,PIC_X,PIC_W/2,2,ys,0x52u);
  phaser_curve(ys,96,216,hi,amt,g);pg_curve(surf,PIC_X,PIC_W/2,2,ys,0x52u);
  phaser_curve(ys,96,216,lo+(hi-lo)*ph/1000,amt,g);pg_curve(surf,PIC_X,PIC_W/2,2,ys,0xf2u);return;
 }
 box(surf,PIC_X,PIC_MID,PIC_W,1,0xf3u);
 int amp=8+amount*96/1000;
 for(u32 k=3;k--;){ /* Chorus, back to front: the white voice last */
  u32 off=k*(8u+(u32)amount/40u);
  for(int x=0;x<PIC_W;x+=2){u32 p=(u32)x*(u32)(1000+7*rate)/1000u*256u/PIC_W+off;ys[x/2]=(short)(PIC_MID-sn(p)*amp/256);}
  pg_curve(surf,PIC_X,PIC_W/2,2,ys,grey[k]); /* run 17: the shared curve helper (playground_ui.c) */
 }
 (void)fb;(void)dist;
}
/* Mod FX view extras: the live picture and the 8 track toggles with their names (native 24 px). */
static void modfx(u8 *g,void *ctx){
 void *surf=(void*)W(ctx,4);u8 *b=BAR(g,0);u32 bits=outputs(),type=type_sel(g);
 modfx_picture(surf,type,CELL(b,1),CELL(b,2),type?CELL(b,3):0,type==2?CELL(b,4):0);
 for(u32 t=0;t<8;t++){
  u32 c=NFN(0x08142a04,u32(*)(u32))(t),o=bits>>2*t&3u;int x=56+160*(int)t;char name[32];name[0]=0;u32 h=0;
  box(surf,x,SQ_TOP,48,48,0xf1u);outline(surf,x,SQ_TOP,48,48,2,o>1?(c&15u)|0x60u:c);if(o==1)box(surf,x+8,SQ_TOP+8,32,32,(c&15u)|0xb0u);
  TRACK_HANDLE(t,&h);if(h)ui_name(&h,name); /* run 19: ui_name (the raw getter writes 256 bytes) */
  pg_text(ctx,t,160*(int)t,SQ_TOP+60,160,name,o==1?c:(c&15u)|0x80u);
 }
}

/* ---- Run 17: Send FX v3 pictures (owner FINAL 13 Nov; design/native/native_sendfx.png, design/native/mk10.py =
 * the reference maths), live from the native cell values; integer only, tables instead of libm.
 * DELAY = rings, one per echo: Time = spacing, Feedback = how slowly they fade (stop below 6 %), Ping Pong = rings
 *   alternate left/right, Filter on = darker rings (Cutoff: the lower, the darker), Width = horizontal stretch,
 *   Beat Sync = grid ticks under the rings.
 * REVERB = tail: early reflections (a few lines) after the Pre Delay gap, then a dense wash every 2nd column; the
 *   Style picks length/shape/reflection count from a 15-row table (exp, slap, notchy, resonant, dark, gated, bloom,
 *   heavy, grain); Time = tail length, Level = height and brightness, Hi Cut = darker towards the end, Low Cut =
 *   thinner towards the end, Freeze = runs to the edge with an end mark; Shimmer mode = rising sparks (Shift = height,
 *   Feedback = how many). Balanced brightness: the tail is drawn sparser and dimmer than the rings (mk10).
 * Colours: the native track palette's blue (Delay) and violet (Reverb) entries (mockup DEL/REV), brightness by alpha,
 * never below 3/15 (MINB 0.2). Bars: 1 Delay, 2 Reverb, 3 Shimmer (only in Shimmer mode). */
#define NORM(b,c) norm((u8*)(b)+0x38u+(c)*0x468u)
/* A cell's value as 0..1000 of its native range, from its registry descriptor (registry pointer 30032DE4 on 1.6.8):
   choices (type 7: Style, Mode, the synced Delay division) by their count, everything else by min/max. */
static int norm(u8 *cell){
 u8 *d=(u8*)W((void*)0x30032de4u,0);if(!d)return 0;d+=H(cell,0x9c)*32u;int v=(int)W(cell,0xa0);
 int lo=B(d,2)==7?0:(int)W(d,16),hi=B(d,2)==7?(int)W(d,12)-1:(int)W(d,20);if(hi<=lo)return 0;if(v<lo)v=lo;if(v>hi)v=hi;return (v-lo)*1000/(hi-lo);
}
static u32 shade(u32 c,int a){if(a<3)a=3;if(a>15)a=15;return (c&15u)|(u32)a<<4;} /* alpha 3..15 */
static u32 isq(u32 v){u32 r=0,b=1u<<30;while(b>v)b>>=2;while(b){if(v>=r+b){v-=r+b;r=(r>>1)+b;}else r>>=1;b>>=2;}return r;}
/* An ellipse outline (rx, ry) through the shared curve helper: upper and lower halves, 2 px steps. */
static void ellipse(void *surf,int cx,int cy,int rx,int ry,u32 c){
 short up[200],dn[200];int n=0;if(rx>398)rx=398;
 for(int dx=-rx;dx<=rx&&n<200;dx+=2,n++){int h=(int)((u32)ry*isq((u32)(65536-(dx*dx*65536)/(rx*rx)))>>8);up[n]=(short)(cy-h);dn[n]=(short)(cy+h-1);}
 pg_curve(surf,cx-rx,n,2,up,c);pg_curve(surf,cx-rx,n,2,dn,c);
}
static void rings(void *surf,int cx,int cy,int rmax,u8 *b){
 int fb=NORM(b,0),filt=CELL(b,1),cut=NORM(b,2),width=NORM(b,3),pp=CELL(b,4),sync=CELL(b,5),tm=NORM(b,6);
 u32 base=NFN(0x08142a04,u32(*)(u32))(0);int step=8+22*tm/1000,a=1000;
 for(int k=0;;k++){
  int r=8+k*step;if(r>rmax||a<60)break;
  int alpha=a*15/1000;if(filt)alpha=alpha*(450+55*cut/100)/1000; /* filter on: darker, the lower the cutoff */
  int ox=pp&&k?(k&1?-12:12):0;ellipse(surf,cx+ox,cy,r*(13+6*width/1000)/10,r*8/10,shade(base,alpha));
  a=a*(150+800*fb/1000)/1000;
 }
 if(sync)for(int j=1;j<8;j++)box(surf,cx-rmax*16/10+j*rmax*4/10,cy+rmax*85/100,1,5,0xf3u);
}
/* Reverb styles: tail length (% of the area), kind, early reflections, tone (0 plain, 1 bright, 2 dark). */
enum{K_EXP,K_SLAP,K_NOTCH,K_RESO,K_GATE,K_BLOOM,K_HEAVY,K_GRAIN};
static const u8 styles[15][4]={{22,K_EXP,3,0},{40,K_EXP,4,1},{60,K_EXP,5,0},{35,K_SLAP,2,0},{40,K_NOTCH,3,0},{50,K_RESO,4,0},{85,K_EXP,6,1},
 {50,K_EXP,6,0},{85,K_EXP,5,2},{55,K_EXP,5,0}, /* Small Hall 55 (mk10: same as Large Room; owner: a shape per style) */{60,K_GATE,4,0},{100,K_EXP,7,0},{100,K_BLOOM,4,1},{100,K_HEAVY,5,0},{85,K_GRAIN,0,0}};
/* envelopes over the tail (33 points, /255): exp(-3.2x); bloom 0.25+0.75 sin(pi x)^1.2 (1-0.4x); slap exp(-5(x-0.15)) */
static const u8 env_exp[33]={255,231,209,189,171,155,140,127,115,104,94,85,77,69,63,57,51,47,42,38,35,31,28,26,23,21,19,17,16,14,13,11,10};
static const u8 env_bloom[33]={64,75,90,105,121,136,151,165,177,188,198,206,212,216,218,218,217,213,209,202,194,185,175,164,152,140,128,115,103,91,81,71,64};
static const u8 env_slap[33]={0,0,0,0,0,247,211,181,155,132,113,97,83,71,61,52,44,38,32,28,24,20,17,15,13,11,9,8,7,6,5,4,4};
static int env(u32 kind,int f){ /* f 0..1000 */
 int i=f*32/1000;
 switch(kind){case K_GATE:return f<800?217:0;case K_BLOOM:return env_bloom[i];case K_HEAVY:return 255-153*f/1000;case K_SLAP:return env_slap[i];default:return env_exp[i];}
}
static u32 rnd(u32 *r){*r=*r*1103515245u+12345u;return *r>>16&0x7fffu;} /* deterministic: the picture is stable */
static void tail(void *surf,int x0,int y0,int w,int h,u8 *b,u8 *shim){
 int mode=CELL(b,0),style=CELL(b,1),tm=NORM(b,2),level=NORM(b,3),hicut=NORM(b,4),lowcut=NORM(b,5),pre=NORM(b,6),freeze=CELL(b,7);
 if(style<0||style>14)style=2;const u8 *st=styles[style];u32 kind=st[1],r=4,base=NFN(0x08142a04,u32(*)(u32))(1);
 int cy=y0+h/2,lv=450+550*level/1000,tone=st[3]==1?2:st[3]==2?-3:0,xs=x0+4+pre*w*18/100000;
 for(int i=0;i<st[2];i++){int x=xs+i*7+(int)(rnd(&r)%5)-2,a=(950-100*i)*lv/1000,hh=h*42*a/100000;box(surf,x,cy-hh,2,2*hh,shade(base,a*15/1000+tone));}
 xs+=st[2]*7+4;int room=w-(xs-x0)-6,tl=freeze?room:room*st[0]/100*(400+900*tm/1000)/1000;if(tl>room)tl=room;
 for(int j=0;j<tl;j++){
  int f=j*1000/(tl>1?tl:1),e=freeze?179:env(kind,f),x=xs+j;u32 q=rnd(&r);
  if(kind==K_GRAIN){if(q%10<6){int yy=cy+(int)((int)(q>>4&255)-128)*h*4*(400+600*(1000-f)/1000)/1280000;box(surf,x-1,yy-1,3,3,shade(base,(850-600*f/1000)*lv*15/1000000+tone));}continue;}
  if(kind==K_NOTCH&&(j/6)%3==2)e=e*35/100;
  if(kind==K_RESO)e=e*(1000+sn((u32)j*256u/19u)*250/256)/1000;
  int dark=1000-(1000-hicut)*f*8/10000,thin=1000-lowcut*f/2000;
  int amp=(int)((long long)h*42*e*thin/1000*(750+250*(int)(q%1000)/1000)/1000*lv/1000/100/255);
  if(amp<1||(j&1))continue; /* balance: every 2nd column, dimmer than the rings */
  box(surf,x,cy-amp,1,2*amp,shade(base,(180+420*e/255)*dark/1000*15/1000+tone));
 }
 if(freeze)box(surf,x0+w-8,cy-h*42/100,2,h*84/100,0xf2u);
 if(mode&&shim){ /* Shimmer: Shift = how high the sparks rise, Feedback = how many */
  int shift=NORM(shim,0),sfb=NORM(shim,1),n=10+40*sfb/1000;r=3;
  for(int i=0;i<n;i++){int x=xs+(int)(rnd(&r)%(u32)(tl>10?tl:10)),y=cy-h/10-(int)(rnd(&r)%1000)*h*35/100*(400+600*shift/1000)/1000000;box(surf,x,y-5,1,5,shade(0xf2u,6+(int)(rnd(&r)%10)));}
 }
}
static void sendfx(u8 *g,void *ctx){
 void *surf=(void*)W(ctx,4);u32 n=W(g,0x204);int shimmer=n>3,h=shimmer?150:224;
 rings(surf,320,112+h/2,shimmer?78:118,BAR(g,1));
 tail(surf,680,112,570,h,BAR(g,2),shimmer?BAR(g,3):0);
}
/* View paint (slot 1): native children, then the Mod FX extras or (run 17) the Send FX pictures. */
__attribute__((used)) void fxv_paint(void *v,void *ctx){
 NFN(0x08171c4c,void(*)(void*,void*))(v,ctx);
 if(ctx&&W(ctx,4)){if(modview(SG(v)))modfx(SG(v),ctx);else sendfx(SG(v),ctx);}
}
/* Mod FX type by list index (Chorus/Phaser/Flanger+Dist = native 1/2/0), committed like the encoder (event D4). */
static void set_type(void *v,u32 i){if(i<3){u32 e[5]={0xd4,W(v,0x9040),0x103,(i+1u)%3u,0};NFN(0x08171d94,void(*)(void*,void*))(v,e);}}
/* View events (slot 13): in the Mod FX view Left/Right (arrow message AA, button 0 / 9) switch the type; natively
   they do nothing here. Everything else native (Send FX keeps native Up/Down between sections). */
__attribute__((used)) void fxv_arrows(void *v,void *event){
 u32 b=W(event,8);
 if(H(event,0)==0xaau&&(b==0||b==9)&&modview(SG(v))){u32 i=type_sel(SG(v));if(b==0?i>0:i<2)set_type(v,b==0?i-1:i+1);return;}
 NFN(0x08149390,void(*)(void*,void*))(v,event);
}
__attribute__((used)) int fxv_accept(void){return 1;}
/* Touch release (slot 6; slot 7 lets the view take touches outside its children): the track toggles (square or name). */
__attribute__((used)) void fxv_up(void *v,void *point,u32 id){
 (void)id;if(!modview(SG(v)))return;int x=(int)W(point,0),top=480-(int)W(point,4);
 if(top>=SQ_TOP-6&&top<SQ_TOP+88){u32 t=(u32)x/160u,h=0,o=9;TRACK_HANDLE(t,&h);if(h&&ui_get(&h,0x2du,&o)&&o<2)ui_post(0xcf,h,0x2du,o^1u);}
}
#endif
