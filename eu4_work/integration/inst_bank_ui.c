/* One-shot INST bank only. Static tile content (ground, number, name, mute)
 * is redrawn only when it changes. Playback/level/status widgets receive the
 * unmodified native paint/walk context exactly as stock. */
#include "fx_shared.h"
#define BANK_VT 0x0819e5c4u
#define TILE_VT 0x081b2e88u
#define MAGIC 0x31424e49u
typedef struct {
 u32 rect[4],flags,colour;
 char name[64];
} Tile;
typedef struct {
 u32 magic,view,valid,ready;
 Tile tiles[16];
 short progress[16];
 u8 label[0x80];
} Bank;
void **inst_bank_state_slot(void);
static void zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static Bank *state(void){
 void **slot=inst_bank_state_slot();if(!slot)return 0;Bank *s=*slot;
 if(s)return s->magic==MAGIC?s:0;
 u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),bytes=(sizeof(Bank)+31u)&~31u;
 if(cursor<0xc0000000u||end>0xc8000000u||cursor>end||end-cursor<bytes+32)return 0;
 s=FN(0x08104c08,void*(*)(u32))(bytes);if((u32)s!=cursor)return 0;
 zero(s,sizeof(*s));for(u32 i=0;i<16;i++)s->progress[i]=-1;s->magic=MAGIC;*slot=s;return s;
}
static void *bank_of(void *tile,u32 *pad){
 void *v=(void*)W(tile,0x2c);
 if(!v||W(tile,0)!=TILE_VT||W(v,0)!=BANK_VT)return 0;
 u32 off=(u32)tile-(u32)v-0x50u;
 if(off%0x400u||off/0x400u>=16u||H(v,0x6b4c)>=8u)return 0;
 *pad=off/0x400u;return v;
}
__attribute__((used,retain)) void inst_bank_colours(void *tile){
 FN(0x0817948a,void(*)(void*))(tile);
 u32 pad;void *bank=bank_of(tile,&pad);if(!bank)return;
 u32 colour=FN(0x08140ebc,u32(*)(u32))(H(bank,0x6b4c));
 if(!B(tile,0x3f9))colour=0x62u;
 else if(B(tile,0x3fb))colour=0x62u;
 FN(0x0817843c,void(*)(void*,u32))((u8*)tile+0x70,colour);
 FN(0x0817e8b4,void(*)(void*,u32))((u8*)tile+0x18c,colour);
}
static void fill(void *ctx,int x,int y,int w,int h,u32 colour){
 if(w<=0||h<=0)return;int r[4]={x,y,w,h};
 FN(0x08166ef6,void(*)(void*,u32,void*))(r,colour,(void*)W(ctx,4));
}
static void text(Bank *s,void *ctx,int x,int y,int w,int h,const char *str,u32 colour,u32 ground){
 void *l=s->label;
 if(!s->ready){FN(0x0817e7c0,void(*)(void*))(l);s->ready=1;}
 FN(0x0817e810,void(*)(void*,u32))(l,0);
 B(l,0x53)=(u8)colour;B(l,0x54)=(u8)ground;B(l,0x56)=1;B(l,0x51)=1;
 FN(0x0817e85e,void(*)(void*,const char*))(l,str);
 int r[4]={x,y,w,h};for(u32 i=0;i<4;i++)W(l,4+i*4)=(u32)r[i];
 FN(0x0817e448,void(*)(void*,void*,void*))(l,ctx,r);
}
static int equal(const void *a,const void *b,u32 n){
 for(u32 i=0;i<n;i++)if(((const u8*)a)[i]!=((const u8*)b)[i])return 0;return 1;
}
static void child(void *tile,u32 off,void *ctx){
 void *w=(u8*)tile+off;
 if(!B(w,0x30))FN(W((void*)W(w,0),4),void(*)(void*,void*))(w,ctx);
}
static int geometry_ok(void *tile){
 int x=(int)W(tile,4),y=(int)W(tile,8),w=(int)W(tile,12),h=(int)W(tile,16);
 return x>=0&&y>=0&&w>=100&&w<=180&&h>=140&&y<=424&&h<=424-y&&x<=1280-w;
}
static int draw(void *tile,void *ctx){
 u32 pad;void *v=bank_of(tile,&pad);if(!v)return 0;
 if(!ctx||(!B(ctx,0)&&!B(ctx,1))||B(tile,0x30)||!W(ctx,4))return 1;
 int x=(int)W(tile,4),y=(int)W(tile,8),w=(int)W(tile,12),h=(int)W(tile,16);
 if(!geometry_ok(tile))return 0;
 Bank *s=state();if(!s)return 0;
 if(s->view!=(u32)v){s->view=(u32)v;s->valid=0;}
 Tile next;zero(&next,sizeof(next));for(u32 i=0;i<4;i++)next.rect[i]=W(tile,4+4*i);
 next.flags=(W(v,0x6b34)==pad)|((u32)B(tile,0x3f9)<<1)|((u32)B(tile,0x3fa)<<8)|((u32)B(tile,0x3fb)<<16);
 static const u16 offsets[4]={0x1fc,0x250,0x29c,0x2e8};
 for(u32 i=0;i<4;i++)next.flags|=(u32)(B(tile,offsets[i]+0x30)!=0)<<(24+i);
 next.colour=FN(0x08140ebc,u32(*)(u32))(H(v,0x6b4c));
 for(u32 i=0;i<63;i++)next.name[i]=B(tile,0xa1+i);
 int redraw=B(ctx,0)||!(s->valid&(1u<<pad))||!equal(&next,&s->tiles[pad],sizeof(next));
 u32 force[2]={0x101,W(ctx,4)};void *paint=redraw?force:ctx;
 if(redraw){
  u32 ground=next.flags&1u?0xa3u:0xf1u,loaded=next.flags&2u,muted=(next.flags>>16)&255u;
  int width=w;
  if((pad&7u)!=7u){
   int edge=(int)W((u8*)tile+0x400,4);
   if(edge>=x+w&&edge<=x+w+4)width=edge-x;
  }
  fill(ctx,x,y,width,h,ground);
  fill(ctx,x+width-1,y,1,h,0xf3);
  fill(ctx,x,y,width,1,0xf3);
  if(loaded)fill(ctx,x+14,y+h-1,w-28,1,next.colour);
  char number[3]={(char)('0'+(pad+1)/10),(char)('0'+(pad+1)%10),0};
  text(s,paint,x+10,y+h-32,40,28,number,loaded?next.colour:0x62,ground);
  if(muted&&loaded)text(s,paint,x+w-32,y+h-32,24,28,"M",0xf6,ground);
  if(loaded){
   void *name=(u8*)tile+0x70;
   int r[4]={x+6,y+h-90,w-12,56};
   FN(0x0817858c,void(*)(void*,void*))(name,r);
   FN(0x0817843c,void(*)(void*,u32))(name,muted?0x62u:0xf2u);
   FN(0x08178464,void(*)(void*,u32))(name,ground);
   child(tile,0x70,paint);
  }
  void *status=(u8*)tile+0x2e8;
  if(B(status,0x54)!=ground){B(status,0x54)=(u8)ground;B(status,0x5c)=1;}
  s->tiles[pad]=next;s->valid|=1u<<pad;
 }
 /* Native completion leaves the previous bar pixels; erase once when the
  * native position goes from playing to idle. */
 void *bar=(u8*)tile+offsets[0];short pos=(short)H(bar,0x44);
 if(!redraw&&s->progress[pad]>=0&&pos<0&&!B(bar,0x30))
  fill(ctx,(int)W(bar,4),(int)W(bar,8),(int)W(bar,12),(int)W(bar,16),next.flags&1u?0xa3u:0xf1u);
 s->progress[pad]=pos;
 for(u32 i=0;i<4;i++)child(tile,offsets[i],redraw?paint:ctx);
 return 1;
}
__attribute__((used,retain)) void inst_bank_paint(void *tile,void *ctx){
 if(!draw(tile,ctx))FN(0x0816faec,void(*)(void*,void*))(tile,ctx);
}
__attribute__((used,retain)) void inst_bank_walk(void *tile,void *ctx,void *clip){
 u32 pad;void *v=bank_of(tile,&pad);
 if(v&&geometry_ok(tile)){
  void **slot=inst_bank_state_slot();Bank *s=slot?*slot:0;
  /* Static labels were painted in slot 1; only playback/level/status
   * children keep their native walk, so '+' overlays stay omitted. */
  if(s&&s->magic==MAGIC&&s->view==(u32)v&&(s->valid&(1u<<pad))){
   static const u16 offsets[4]={0x1fc,0x250,0x29c,0x2e8};
   for(u32 i=0;i<4;i++){
    void *w=(u8*)tile+offsets[i];
    if(!B(w,0x30))FN(W((void*)W(w,0),8),void(*)(void*,void*,void*))(w,ctx,clip);
   }
   return;
  }
 }
 FN(0x0816f9e8,void(*)(void*,void*,void*))(tile,ctx,clip);
}
