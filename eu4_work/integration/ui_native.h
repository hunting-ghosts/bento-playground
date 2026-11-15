/* Space (1.6.8 port): shared wrappers for the most frequent native calls on the
 * model root 30024B00. Same arguments, same native call, result passed through.
 * Weak, so every translation unit (and single-file test fixtures) can include
 * this; the UI link keeps one copy. */
#ifndef UI_NATIVE_H
#define UI_NATIVE_H
#ifndef NFN
#ifdef BENTO_NATIVE_SYMBOLS
#define NFN(a,t) ((t)({extern char NAT_##a[];(void*)NAT_##a;}))
#else
#define NFN(a,t) ((t)((a)|1u))
#endif
#endif
#define UI_MODEL_ROOT ((void*)0x30024b00u)
__attribute__((weak,noinline)) int ui_post(unsigned code,unsigned a,unsigned b,unsigned c){unsigned e[5]={code,a,b,c,0};return NFN(0x081403ec,int(*)(void*,void*))(UI_MODEL_ROOT,e);}
__attribute__((weak,noinline)) int ui_get(void *h,unsigned key,void *out){return NFN(0x08133614,int(*)(void*,void*,unsigned,void*))(UI_MODEL_ROOT,h,key,out);}
__attribute__((weak,noinline)) unsigned ui_type(void *h){return NFN(0x08133f7c,unsigned(*)(void*,void*))(UI_MODEL_ROOT,h);}
__attribute__((weak,noinline)) void ui_commit(void){NFN(0x0813130c,void(*)(void*))(UI_MODEL_ROOT);}
__attribute__((weak,noinline)) int ui_owner(void *out){return NFN(0x08133cfc,int(*)(void*,void*))(UI_MODEL_ROOT,out);}
__attribute__((weak,noinline)) int ui_child(void *parent,unsigned index,void *out){return NFN(0x0813391a,int(*)(void*,void*,unsigned,void*))(UI_MODEL_ROOT,parent,index,out);}
__attribute__((weak,noinline)) void ui_touch(void *handle){NFN(0x081338dc,void(*)(void*,void*))(UI_MODEL_ROOT,handle);}
/* Run 19 (exp8 crashes A/B): the native string getter ALWAYS writes 256 bytes (0812ED98 ends with
 * strncpy(out,text,0xFF); out[0xFF]=0, and strncpy pads with zeros), whatever the length of the name. Never hand
 * it a smaller buffer. ui_name: name (key 82) of the object *handle through a 256-byte buffer, at most 31
 * characters + terminator into out (>= 32 bytes). Returns the getter's result; out is "" when it fails. */
__attribute__((weak,noinline)) int ui_name(void *handle,char *out){
 char full[256];full[0]=0;int ok=NFN(0x0813390e,int(*)(void*,void*,unsigned,void*))(UI_MODEL_ROOT,handle,0x82u,full);
 unsigned i=0;for(;i<31u&&full[i];i++)out[i]=full[i];out[i]=0;return ok;
}
/* Encoder slot idioms: set a slot's key/value (native 08171C1C with the redraw
 * flag) and its title label (native set-text 0817E85E on the label at +0x3C8). */
__attribute__((weak,noinline)) void ui_slot_set(void *slot,unsigned key,int value){NFN(0x08171c1c,void(*)(void*,unsigned,int,unsigned))(slot,key,value,1);}
__attribute__((weak,noinline)) void ui_slot_title(void *slot,const char *text){NFN(0x0817e85e,void(*)(void*,const char*))((unsigned char*)slot+0x3c8,text);}
__attribute__((weak,noinline)) void ui_slot(void *slot,unsigned key,int value,const char *title){ui_slot_set(slot,key,value);ui_slot_title(slot,title);}
/* Run 13 (space): the native bump allocator 08104C08 behind the checks every caller made: heap cursor (3000004C)
 * and end (30000048) inside C0000000..C8000000, cursor <= end, at least `need` bytes left, and the block starts at
 * the cursor. Returns the block, or 0 when refused (the caller keeps its own failure path). */
__attribute__((weak,noinline)) unsigned ui_alloc(unsigned n,unsigned need){
 unsigned cursor=*(volatile unsigned*)0x3000004cu,end=*(volatile unsigned*)0x30000048u;
 if(cursor<0xc0000000u||end>0xc8000000u||cursor>end||end-cursor<need)return 0;
 return NFN(0x08104c08,unsigned(*)(unsigned))(n)==cursor?cursor:0;
}
#endif
