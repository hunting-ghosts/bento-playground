/* Lean black box (M4, UI task only): \BENTO_CRASHES.log on the SD card.
 *
 * At every boot the M4 startup stub calls bb_boot(), which touches only the
 * 32-byte state below (RAM ops, no card, no peripherals): boot generation + 1
 * when the state is valid, otherwise a fresh state (generation 1).
 *
 * Card access happens only in bb_card(), called by stubs right after stock's
 * own card work returned, on the same task (P168 exp7: that is the native FILE
 * thread pcmStreamer: project load and save are its jobs, 1.6.1 callers
 * 08127666/081285DE/081295AA/08129A0C/08127BE4.., so these lines never compete
 * with the native card work):
 *   - 0813044C: project save, after stock's file writer 08130958 returned;
 *   - 08130522 / 08130774: after stock's document reader 08130A18 returned
 *     (it opens, reads and closes the whole file; the boot autoload goes here).
 * bb_card() opens the file only when something is new: the boot line of this
 * boot, or a stock crash record (RTC backup registers) not yet written. Two
 * failed attempts end the card access for this boot (no retry loop).
 *
 * Stock crash record (verified on 1.6.1, M7 recorder 0804B3C0): RTC_BKP0R at
 * 58004050, BKPn = 58004050 + 4n. [4] fault address (MMFAR/BFAR), [5] CFSR,
 * [6..13] stacked r0 r1 r2 r3 r12 lr pc xpsr, [14..21] r4..r11, [22] frame
 * pointer, [23] EXC_RETURN, [24] crash count (incremented per record),
 * [25] cause, [26] SysTick value, [27] core, [31] = [12] (pc).
 * BKP0..3 are stock's boot words (BKP0R = 4 starts disk mode): read only.
 *
 * Reset-surviving RAM (neither stock nor K16/TF2 startup clears it; no image
 * code addresses it): 24048810 state (32 B), 24048840 FatFS FIL (0x58 B),
 * 240488A0..24048A40 line buffer. Nothing here is followed as a pointer; the
 * state is used only with its magic and check word (junk RAM = fresh state).
 *
 * Written for Bento Playground; the crash-history idea and the stock crash
 * record / FatFS entry points follow romanjeff's bento_enhanced m4_diag.c
 * (GPL-3.0-or-later, reference only, no code copied). */
#include "fx_shared.h"

/* Code is spread over free tails of existing UI caves (no new region). */
#define BB_TEXT __attribute__((section(".stepnote"),noinline))
#define BB_TEXT2 __attribute__((section(".stepui"),noinline))
#define BB_TEXT3 __attribute__((section(".mixstrip"),noinline))
#define BB_TEXT4 __attribute__((section(".stepdraw"),noinline))
#define BB_TEXT5 __attribute__((section(".pad4"),noinline))
#define BB_DATA __attribute__((section(".kitlock")))
#define BB_MAGIC 0x31584242u /* "BBX1" */
#define BB_BOOT 1u    /* this boot's line not written yet */
#define BB_FRESH 2u   /* state was rebuilt: the current record was never written */
typedef struct {u32 magic,gen,logged,flags,fails,check;} BbState;
#define BB ((volatile BbState*)0x24048810u)
#define BB_FIL ((volatile u32*)0x24048840u)     /* FIL is 0x58 bytes on 1.6.1 */
#define BB_FIL_WORDS 24u
#define BB_LINE ((char*)0x240488a0u)
#define BB_LINE_BYTES 0x1a0u                       /* ends 24048A40, below T2 counters 24048A60 */
#define BKP ((volatile u32*)0x58004050u)
#define RTC_TR W((void*)0x58004000u,0)
#define RTC_DR W((void*)0x58004004u,0)
#define TICK_MS W((void*)0x3001fe2cu,0)
#define LABEL_SLOT 0x08131054u                     /* native version-string pointer (identity) */
#define F_OPEN NFN(0x08120148u,u32(*)(volatile void*,const char*,u32))
#define F_WRITE NFN(0x08120604u,u32(*)(volatile void*,const void*,u32,u32*))
#define F_CLOSE NFN(0x08120974u,u32(*)(volatile void*))
#define FA_APPEND_WRITE 0x32u                      /* FA_OPEN_APPEND | FA_WRITE */

/* Line templates: %d decimal, %x 8 hex digits, %s text (printable, <= 31
 * characters), %b BCD date-time; every other character is copied. */
BB_DATA static const char T_path[]="\\BENTO_CRASHES.log",
 T_crash[]="%s gen=%d count=%d cause=%x core=%x pc=%x lr=%x bkp=",
 T_boot[]="boot gen=%d fw=%s rtc=%b-%b ms=%d count=%d state=%s\r\n",T_hex[]="0123456789abcdef",
 T_q[]="?",T_x[]="%x",T_k[]="kept",T_f[]="fresh",T_c[]="crash",T_r[]="record";

BB_TEXT2 static u32 bb_check(const BbState *s){return s->magic^s->gen^(s->logged*3u)^(s->flags<<24)^(s->fails<<28)^0xa5c3e17bu;}
/* Copy the state out of RAM; 1 only if magic and check word match. */
BB_TEXT2 static int bb_load(BbState *s){
 for(u32 i=0;i<sizeof(*s)/4u;i++)((u32*)s)[i]=((volatile u32*)BB)[i];
 return s->magic==BB_MAGIC&&s->check==bb_check(s);
}
BB_TEXT5 static void bb_store(BbState *s){
 s->check=bb_check(s);for(u32 i=0;i<sizeof(*s)/4u;i++)((volatile u32*)BB)[i]=((u32*)s)[i];
}

/* M4 startup (before the scheduler; RAM only). */
__attribute__((used,retain,section(".stepui"))) void bb_boot(void){
 BbState s;
 if(bb_load(&s)){s.gen=s.gen+1u?s.gen+1u:1u;s.flags|=BB_BOOT;}
 else{s.magic=BB_MAGIC;s.gen=1u;s.logged=0;s.flags=BB_BOOT|BB_FRESH;}
 s.fails=0;bb_store(&s);
 for(u32 i=0;i<8u;i++)((volatile u32*)0x24048a40u)[i]=0; /* exp7: the card request box of kick_ui.c (CardBox) */
}

BB_TEXT static u32 fmt(u32 n,const char *f,const u32 *a){
 char *p=BB_LINE;
 for(;*f&&n<BB_LINE_BYTES-40u;f++){
  if(*f!='%'){p[n++]=*f;continue;}
  char c=*++f;u32 v=*a++;
  if(c=='x')for(int i=28;i>=0;i-=4)p[n++]=T_hex[(v>>i)&15u];
  else if(c=='b')for(int i=20;i>=0;i-=4)p[n++]=T_hex[(v>>i)&15u];
  else if(c=='s')for(u32 i=0;i<31u;i++){char t=((const volatile char*)v)[i];if(t<32||t>126)break;p[n++]=t;}
  else{char t[10];u32 k=0;do{t[k++]=(char)('0'+v%10u);v/=10u;}while(v);while(k)p[n++]=t[--k];}
 }
 return n;
}
BB_TEXT4 static int bb_write(u32 n){u32 done=0;return !F_WRITE(BB_FIL,BB_LINE,n,&done)&&done==n;}
BB_TEXT3 static int crash_line(const BbState *s,u32 count){
 /* P168 exp3: pc is BKP[31]. The native fault recorder (cause 1..4) writes the stacked pc to [12] and [31];
  * the native watchdog recorder (cause 5, M4 08107AE8) writes only [31] (the interrupted pc), [8], [9], [16]
  * and [23]..[27] and leaves [4]..[7], [10]..[15] from the last fault: the old lines repeated a stale pc. */
 u32 a[7]={(u32)(s->flags&BB_FRESH?T_r:T_c),s->gen,count,BKP[25],BKP[27],BKP[31],BKP[11]};
 u32 n=fmt(0,T_crash,a);
 for(u32 i=0;i<32u;i++){u32 w=BKP[i];n=fmt(n,T_x,&w);BB_LINE[n++]=i==31u?'\r':',';}
 BB_LINE[n++]='\n';return bb_write(n);
}
BB_TEXT static int boot_line(const BbState *s,u32 count){
 /* Firmware label: the native version-string pointer, only inside bank 2. */
 u32 label=W((void*)LABEL_SLOT,0);if(label<0x08100000u||label>=0x081e0000u-32u)label=(u32)T_q;
 u32 tr=RTC_TR,dr=RTC_DR;
 u32 a[7]={s->gen,label,dr&0xff1f3fu,tr&0x3f7f7fu,TICK_MS,count,(u32)(s->flags&BB_FRESH?T_f:T_k)};
 return bb_write(fmt(0,T_boot,a));
}

/* P168 exp3 (owner: boot -> crash -> boot cycles; the records are cause 5): the native M4 watchdog
 * monitor 081082F8 stops refreshing the hardware watchdog when the main thread has not reported for
 * 3332 ticks ("Main Timed Out") or the file thread for 6249 ("PcmThread Timed Out"); the record does
 * not say which. Just before the native recorder stores cause 5, both ages are put into BKP[22]
 * (unused by a cause 5 record): low half main thread, high half file thread, in monitor ticks.
 * Entered by b.w from 08107B56 (mov.w lr,#5) with r3 = 58004000, interrupts off. */
__attribute__((naked,used,retain)) void bb_watchdog(void){
 __asm__("push {r0,r1}\n ldr r0,=0x3000f624\n ldr r1,[r0,#8]\n ldr lr,[r0,#4]\n sub lr,r1,lr\n ldr r0,[r0]\n subs r1,r1,r0\n"
         "uxth lr,lr\n orr lr,lr,r1,lsl #16\n str lr,[r3,#0xa8]\n pop {r0,r1}\n mov lr,#5\n ldr pc,=(0x08107b5a+1)\n .ltorg\n");
}

/* After stock's own card work, UI task. Opens the file only when there is
 * something new; at most two failed attempts per boot. */
__attribute__((used,retain,section(".stepnote"))) void bb_card(void){
 BbState s;
 if(!bb_load(&s)||s.fails>=2u)return;
 u32 count=BKP[24];
 int crash=s.flags&BB_FRESH?count!=0:count!=s.logged;
 if(!crash&&!(s.flags&BB_BOOT))return;
 for(u32 i=0;i<BB_FIL_WORDS;i++)BB_FIL[i]=0;
 int ok=!F_OPEN(BB_FIL,T_path,FA_APPEND_WRITE),opened=ok;
 if(ok&&crash&&(ok=crash_line(&s,count))){s.logged=count;if(!(s.flags&BB_BOOT))s.flags&=~BB_FRESH;}
 if(ok&&(s.flags&BB_BOOT)&&(ok=boot_line(&s,count)))s.flags&=~(BB_BOOT|BB_FRESH);
 if(opened&&F_CLOSE(BB_FIL))ok=0; /* only a file that was opened is closed */
 if(!ok)s.fails++;
 bb_store(&s);
}
