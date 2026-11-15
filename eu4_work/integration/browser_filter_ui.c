/* Browser carrier filter (listing only; nothing on the card changes).
 * In root "Drum Synths" the native browser no longer lists
 *  - "Subtractive.wav" of exactly 288102 bytes (retired engine), always;
 *  - "Syncussion.wav" of exactly 288110 bytes (R6.6: listed as Metal.wav), always;
 *  - "Syncussion Melodic.wav" (also the older packaged underscore spelling)
 *    of exactly 288114 bytes, always (run 14: melodic Syncussion retired; until then only for the "*.wav"
 *    browser request made while the current track is a one-shot, type 14).
 * Hooks (stock BL preimages; evidence and native run in test_browser_filter.py):
 *  08104296 PrepareFileList 081041F8 file pass, BL 081020AC(list,name) with
 *           r6=FILINFO (u64 size at +0), r10=directory argument;
 *  0816CA0E browser view 0816C9B0 mode 0, BL 08132DB4(MODEL,path,folders). */
#include "fx_shared.h"
#include "../drums/kick_knobs.h"
/* KickKnobs.reserved[2]; zeroed with KNOBS on magic mismatch = melodic shown. */
#define BROWSER_CONTEXT (KNOBS->reserved[2])
#define BROWSER_ONE_SHOT 0x4f534842u
#define STRCMP NFN(0x0818730au,int(*)(const char*,const char*))
#define STRNCMP NFN(0x08187010u,int(*)(const char*,const char*,u32))
__attribute__((used,retain,section(".pad5"))) void browser_list_add(void *list,const char *name,const char *dir,const u32 *fno){
 u32 melodic=fno[0]==288114u; /* run 14: hidden in every browser context */
 /* R6.6: the old "Syncussion.wav" carrier (same size) is listed as Metal.wav now. */
 const char *want=fno[0]==288102u?"Subtractive.wav":fno[0]==288110u?"Syncussion.wav":
  melodic?"Syncussion Melodic.wav":0;
 if(want&&!fno[1]&&(!STRCMP(name,want)||
    (melodic&&!STRNCMP(name,want,10)&&name[10]=='_'&&!STRCMP(name+11,want+11)))){
  if(dir[0]&&dir[1]==':')dir+=2;
  while(*dir=='\\'||*dir=='/')dir++;
  if(!STRNCMP(dir,"Drum Synths",11)){
   dir+=11;while(*dir=='\\'||*dir=='/')dir++;
   if(!*dir)return;
  }
 }
 NFN(0x081020acu,void(*)(void*,const char*))(list,name);
}
__attribute__((naked,used,retain,section(".kitdraw"))) void browser_list_hook(void){
 __asm__ volatile("mov r2, r10\n\tmov r3, r6\n\tb browser_list_add\n");
}
__attribute__((used,retain,section(".stepui"))) void browser_request(void *model,const char *path,u32 folders){
 u32 t=0,c=0;
 /* 0818B374 is the native "*.wav" literal the Load WAV handler copies. */
 if(!STRCMP((const char*)model+0x18b8,(const char*)0x0818b374u)&&NFN(0x08133cfcu,int(*)(void*,u32*))(model,&t)&&t&&
    NFN(0x08133f7cu,u32(*)(void*,u32*))(model,&t)==14u)c=BROWSER_ONE_SHOT;
 BROWSER_CONTEXT=c;
 NFN(0x08132db4u,void(*)(void*,const char*,u32))(model,path,folders);
}
