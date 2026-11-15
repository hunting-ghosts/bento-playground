#include "native_ids.h" /* 1.6.8 port: NKEY/NUI */
/* BENTO_MOD L7: lossless two-lock coding in the existing native +20 word. */
typedef unsigned int u32;
typedef unsigned char u8;
#ifndef W
#define W(p,o) (*(volatile u32 *)((u8*)(p)+(o)))
#define B(p,o) (*(volatile u8 *)((u8*)(p)+(o)))
#define H(p,o) (*(volatile unsigned short *)((u8*)(p)+(o)))
#endif
#define FN(a,t) ((t)((a)|1u))
#ifdef BENTO_NATIVE_SYMBOLS /* 1.6.8 port/space: direct BL via linker symbol NAT_<address> */
#define NFN(a,t) ((t)({extern char NAT_##a[];(void*)NAT_##a;}))
#else
#define NFN(a,t) FN(a,t)
#endif
#define LOCK_TAG 0x51000000u
#define LOCK_PAIR_COUNT 1519176901u
/* R6.2: one copy of these helpers in the UI image. The single UI link (LTO)
   defines BENTO_UI_SHARED_WEAK, so the per-file copies merge into one weak
   definition; audio builds and test fixtures keep them static. */
#ifndef SLS
#if defined(BENTO_UI_SHARED_WEAK) && !defined(__cplusplus)
#define SLS __attribute__((weak,section(".text.sls")))
#else
#define SLS static
#endif
#endif
SLS u32 value_count(u32 k){return k==0?1:k==1?1081:k==2?48001:(k==3||k==4)?2001:k<=11?1001:k==12?156:k<=29?101:(k<=31)?1001:0;}
SLS u32 lock_kind(u32 w){
 u32 k=(w>>16)&255,v=w&65535;
 return (w&0xff000000u)==LOCK_TAG && k && k<=31 && v<value_count(k)?k:0;
}
static u32 synth_model(u32 k){return k>=12&&k<=19?1:k>=20&&k<=24?3:k>=25&&k<=29?5:0;}
SLS u32 synth_index(u32 k){return k-(k<=19?12:k<=24?20:25);}
SLS u32 native_key(u32 k){static const u32 keys[]={0,2,3,4,0x32,0x33,0x1e,0x1f,0x20,0x21,0x36,0x37};static const u32 synthkeys[]={NKEY(0x1a0),NKEY(0x1a1),NKEY(0x1a2),NKEY(0x1a4),NKEY(0x1a5),NKEY(0x1a6),NKEY(0x1a9),NKEY(0x1b0)};return k<=11?keys[k]:k<=29?synthkeys[synth_index(k)]:k==30?0xb4:k==31?0xb5:0;}
SLS int decode_value(u32 w){u32 k=lock_kind(w),v=w&65535;return k==1?(int)v*100-96000:k==2?(int)v-24000:k==12?(int)v+25:(int)v-((k==3||k==4)?1000:0);}
SLS u32 encode_value(u32 k,int v){
 int lo=k==1?-96000:k==2?-24000:(k==3||k==4)?-1000:k==12?25:0,hi=k==1?12000:k==2?24000:k==12?180:k>11&&k<30?100:1000;
 if(!k || k>31)return 0;if(v<lo)v=lo;if(v>hi)v=hi;
 return LOCK_TAG|(k<<16)|(u32)(k==1?(v+96000)/100:k==2?v+24000:k==12?v-25:v+((k==3||k==4)?1000:0));
}
/* K16: legacy pair order is frozen. Synth pairs append after all legacy pairs.
 * Enumerate all ordered, distinct target pairs and their full value ranges.
 * 1,290,761,893 combinations fit in 31 bits. Bit 31 tags v2; v1 stays exact.
 * No pointers, mutable dictionary, quantization loss or new native note size. */
/* Skip complete target rows rather than scanning every value-pair group. */
SLS u32 row_count(u32 a,u32 pass){
 u32 sum=pass?(a<=11?1873u:61965u):60092u;
 if(a && (!pass || a>11))sum-=value_count(a);
 return value_count(a)*sum;
}
/* EU7 immutable conditional payloads. Native notes retain their 24-byte size.
 * Tokens occupy a previously invalid lock-word tag, with guarded SDRAM records.
 * Records never mutate: native Undo/copy retain the exact old sound/condition. */
#define LC_MAGIC 0x37434c42u
/* R6.11 ratchets: the record's spare half carries a ratchet word at +16 with
 * its own check at +20 (+24..+31 stay zero). Old records have +16 = 0 and are
 * accepted exactly as before (condition 1..134, check at +12 unchanged). A
 * record with a ratchet may have condition 0 (ratchet only).
 * Ratchet word: bits 24..31 tag 0x52, 0..2 count-1 (1..7 = 2..8 hits; count 1
 * = off = no word), 3..4 shape (0 flat, 1 fade, 2 swell), 8..14 depth 0..100,
 * 16..23 probability 0..134 (lock-condition coding, 0 = always); others 0.
 * Ratchet check (+20) = ~(+12 ^ +16): address-bound through the +12 check. */
#define RT_TAG 0x52000000u
#if defined(BENTO_UI_SHARED_WEAK) && !defined(__cplusplus)
#define SLS_B1 __attribute__((weak,section(".text.bank1a")))
#else
#define SLS_B1 static
#endif
/* R6.17 trigger conditions (owner): codes 0 none/Always, 1..99 %, 100..134
 * A:B (T2 order), 135 1ST, 136 !1ST, 137 PRE, 138 !PRE. Existing values keep
 * their meaning; the new codes were invalid before, so no saved project has
 * them. Lock condition (record +8) and ratchet Prob (8-bit field) alike. */
#define RT_CONDITIONS 139u
/* P168 exp5 picker order (owner, 12 Nov: 1ST/PRE quick to reach, A:B at most 4:4 in every list): positions
 * 0..98 %, 99 Always, 100..108 A:B 1:2..4:4, 109..112 1ST !1ST PRE !PRE are offered (COND_OFFERED);
 * a saved A:B above 4:4 (codes 109..134) keeps its code and is shown at positions 113..138, never offered.
 * Stored codes are unchanged (0 Always, 1..99 = 0..98 %, 100..134 A:B, 135..138 1ST..!PRE). */
#define COND_OFFERED 113u
SLS unsigned cond_pos(unsigned c){return !c||c>=RT_CONDITIONS?99u:c<100?c-1u:c<109?c:c<135?c+4u:c-26u;}
SLS unsigned cond_code(int v){if(v<0)v=0;if(v>(int)COND_OFFERED-1)v=(int)COND_OFFERED-1;unsigned p=(unsigned)v;return p==99?0:p<99?p+1:p<109?p:p+26u;}
SLS_B1 u32 rt_ok(u32 r){return (r&0xff0080e0u)==RT_TAG && (r&7u) && ((r>>3)&3u)<3u && ((r>>8)&127u)<=100u && ((r>>16)&255u)<RT_CONDITIONS;}
SLS u32 lc_address(u32 w){u32 a=0xc0000000u|(w&0x0fffffffu);return (w&0xf000001fu)==0x60000000u && a>=0xc0000000u && a<=0xc7ffffe0u?a:0;}
SLS_B1 u32 lc_valid(u32 w){
 u32 a=lc_address(w);if(!a)return 0;
#ifdef LOCK_M7
 __asm__ volatile("dsb" ::: "memory");if(W((void*)0xe000ed14u,0)&(1u<<16))W((void*)0xe000ef5cu,0)=a;__asm__ volatile("dsb" ::: "memory");
#endif
 void *p=(void*)a;
#ifdef LOCK_M7
 /* M7 cave space: original order; a ratchet-only record (condition 0) needs
    its ratchet check (M4 writes only rt_ok words, never c=0 without a ratchet;
    future M7 ratchet playback must check rt_ok / clamp the fields it reads). */
 return W(p,0)==LC_MAGIC && W(p,8)<RT_CONDITIONS && W(p,12)==(LC_MAGIC^a^W(p,4)^W(p,8)) && !lc_address(W(p,4)) && (W(p,8)>0 || W(p,20)==~(W(p,12)^W(p,16)));
#else
 u32 c=W(p,8),r=W(p,16);
 if(W(p,0)!=LC_MAGIC || c>=RT_CONDITIONS || W(p,12)!=(LC_MAGIC^a^W(p,4)^c) || lc_address(W(p,4)))return 0;
 return r?rt_ok(r) && W(p,20)==~(W(p,12)^r):c>0;
#endif
}
static u32 lc_word(u32 w){return lc_valid(w)?W((void*)lc_address(w),4):w;}
SLS u32 lc_condition(u32 w){return lc_valid(w)?W((void*)lc_address(w),8):0;}
/* Tagged ratchet word, 0 = none. meta = condition | ratchet payload << 8:
 * everything a record adds to the pair word (0 = plain word, no record). */
SLS_B1 u32 lc_ratchet(u32 w){return lc_valid(w)?W((void*)lc_address(w),16):0;}
SLS_B1 u32 lc_meta(u32 w){return lc_valid(w)?W((void*)lc_address(w),8)|W((void*)lc_address(w),16)<<8:0;}
SLS __attribute__((noinline)) void lock_slots(u32 packed,u32 *first,u32 *second){
 *first=*second=0;
 packed=lc_word(packed);
 if(!(packed&0x80000000u)){if(lock_kind(packed))*first=packed;return;}
 u32 code=packed&0x7fffffffu;
 if(code>=LOCK_PAIR_COUNT){
  code-=LOCK_PAIR_COUNT;
  for(u32 a=0;a<=31;a++)for(u32 b=a<30?30:0;b<=31;b++){
   if(a==b)continue;u32 n=value_count(a)*value_count(b);
   if(code>=n){code-=n;continue;}
   if(a)*first=LOCK_TAG|(a<<16)|(code/value_count(b));
   if(b)*second=LOCK_TAG|(b<<16)|(code%value_count(b));
   return;
  }
  return;
 }
 for(u32 pass=0;pass<2;pass++)for(u32 a=0;a<=(pass?29u:11u);a++){
  u32 row=row_count(a,pass);if(code>=row){code-=row;continue;}
  for(u32 b=pass&&a<=11?12:0;b<=(pass?29u:11u);b++){
   if(a && a==b)continue;u32 n=value_count(a)*value_count(b);
   if(code>=n){code-=n;continue;}
   if(a)*first=LOCK_TAG|(a<<16)|(code/value_count(b));
   if(b)*second=LOCK_TAG|(b<<16)|(code%value_count(b));
   return;
  }
 }
}
static u32 lock_slot(u32 packed,u32 slot){u32 a,b;lock_slots(packed,&a,&b);return slot?b:a;}
static u32 lock_pair(u32 first,u32 second){
 u32 a=lock_kind(first),b=lock_kind(second);if(a && a==b)return 0xffffffffu;
 if(!b)return a?first:0;
 if(a>=30||b>=30){
  u32 code=LOCK_PAIR_COUNT;
  for(u32 i=0;i<=31;i++)for(u32 j=i<30?30:0;j<=31;j++){
   if(i==j)continue;
   if(i==a&&j==b)return 0x80000000u|code;
   code+=value_count(i)*value_count(j);
  }
  return 0xffffffffu;
 }
 u32 code=0;
 for(u32 pass=0;pass<2;pass++)for(u32 i=0;i<=(pass?29u:11u);i++){
  if(i!=a || ((a>11 || b>11)!=pass)){code+=row_count(i,pass);continue;}
  for(u32 j=pass&&i<=11?12:0;j<=(pass?29u:11u);j++){
   if(i && i==j)continue;if(j==b)return 0x80000000u|code;
   code+=value_count(i)*value_count(j);
  }
 }return 0xffffffffu;
}
static u32 pack_locks(u32 first,u32 second){
 u32 base=lock_pair(first,second);if(base==0xffffffffu || !(base&0x80000000u))return base;
 return base+(lock_kind(first)?(first&65535u)*value_count(lock_kind(second)):0)+(second&65535u);
}
static int has_locks(u32 w){u32 a,b;lock_slots(w,&a,&b);return a!=0||b!=0;}
