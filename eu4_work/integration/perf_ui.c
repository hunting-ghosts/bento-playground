/* P1 performance page (M4).
 *
 * PROJ opens Perform directly. Perform, Macro and combined Settings use the
 * native four-row GenericProperties host; Proj keeps the native file browser.
 *
 * Perform shows the macro knobs and a combined Chord/Arp strip. Settings
 * keeps Global first, Date and Time second (native Set Time), and Pads third.
 * Tempo/key stay on the existing overlay; the project settings backend is
 * unchanged.
 *
 * Fixed velocity reaches M7 through EuControl.reserved[1] (see live_shared.h);
 * the M7 pad-press hook rewrites the press pressure.
 * Chord (P3): per track On/Off, Type (incl. Diatonic / Diatonic 7,
 * which follow the project Root/Scale), Voicing, Inversion. While on, the
 * selected pitched track's keyboard pads play the chord on their own pitch
 * through the CH6 chord audition (ChordMail). Live chord mode (SEQ double-tap
 * in the piano roll) keeps priority on its own track. */
#include "live_shared.h"
#include "macro_display.h"
#include "encoder_speed.h"
#include "clip_motion.h"
#include "../../chord_work/chords.h"
/* P7 (owner report on 1.6P6):
 * - BPM/Swing/Root/Scale live on the project settings node (08133E54), not on
 *   30030164 (the selection context); reads showed 0 and writes went nowhere.
 * - Voicing "Smooth": each chord takes the inversion/octave closest to the
 *   last chord played on the pads.
 * - The last played chord's name comes from the existing ChordPub press path.
 * - Chord edits here bump a per-track version, so SEQ chord mode adopts them.
 * - The header chord symbol is gone (owner: overlaps the counter). */
#define PROJECT ((void*)0x30030164u)
#define LOCK_HELD W((void*)0x24048d60u,8)
#define LOCK_USED W((void*)0x24048d60u,12)
#define CONSUMED W((void*)0x24048d70u,0)
#define TICK W((void*)0x3001fe2cu,0)
#define PERF_MAGIC 0x31465250u
#define KEY_BPM 0x8cu
#define KEY_SCALE 0x8du
#define KEY_ROOT 0x8eu
#define KEY_SWING 0x8fu
#define KEY_TAP 0x101u
#define KEY_OCTAVE 0x178u
#define KEY_FIXED 0x102u
#define KEY_VELOCITY 0x11cu
#define KEY_CHORD 0x104u
#define KEY_CTYPE 0x132u
#define KEY_VOICING 0x14au
#define KEY_INVERSION 0x144u
#define CHORD_TYPES 17u /* 15 shapes + Diatonic + Diatonic 7 */
/* P28 arpeggiator (owner): per-track Arp (Off/On/Latch), Mode, Rate, Octaves,
   Gate. Keys found empty after native registry
   construction and used nowhere else in the repo. */
#define KEY_ARP 0xa6u
#define KEY_AMODE 0xa7u
#define KEY_ARATE 0xaau
#define KEY_AOCT 0xb2u
#define KEY_AGATE 0xb3u
#define CHORD_DEFAULT_TYPE 15u
#define PERF_TRACKS 16u
/* W14 restores the W13 four-view footer; Macro detail is selected with Down. */
#define PERF_TAB 0x1071u
#define MACRO_TAB 0x1072u
#define SETTINGS_TAB 0x1074u
#define PROJECT_TAB 0x1075u
#define MOTION_TOGGLE 0x1076u
int header_fixed_tab(void*,unsigned,unsigned,const char*,int);
int header_fixed_action(void*,unsigned,unsigned,const char*,int);
void macro_view_set(int);void macro_touch(u32);void macro_binding_tap(u32,u32);void macro_select(u32);void macro_disarm(void);void macro_title(char*);
u32 perf_macro_focus(int);
int fx_screen_active(void);
typedef struct {u32 handle,on,velocity,chord,type,voicing,inversion,ver,arp,amode,arate,aoct,agate;} PerfTrack;
#define SMOOTH 3u
typedef struct {
 u32 magic,active,view,nav,previous,left_down,arrow_down,published,tap_last,tap_count,taps[4];
 PerfTrack tracks[PERF_TRACKS];char titles[4][32];
 u32 chord_sig,chord_serial,chord_pub;const char *type_names[CHORD_TYPES];
 u32 in_get,pad,pad_serial,pad_since,ref_n;int ref[CH_MAX_VOICES];u8 count[12];signed char off[12][CH_MAX_VOICES];char name[12];u32 name_track;
 u32 trk_held,trk_used,trk_page;u8 trk_saved[256]; /* P20: pad colours while TRACKS is held */
 u32 arp_pub; /* P28 */
 u32 mview,macro_edit; /* Macro view: overview or selected-column detail */
 void *workflow;
 u32 focus,macro_focus,touch_bar;
 int touch_x,touch_y;
 EncoderSpeed encoder_speed; /* Session-wide, deliberately not project data. */
 EncoderFraction fx_fraction[8];
 u32 fx_fraction_next;
 ClipMotion motion;
 u32 mute_bank;
} Perf;
void **perf_state_slot(void);
static const char tap_name[]="Tap Tempo",fixed_name[]="Fixed Vel",velocity_name[]="Velocity",chord_name[]="Chord",ctype_name[]="Type",voicing_name[]="Voicing",inversion_name[]="Inversion";
static const char *const voicing_names[4]={"Close","Open","Drop 2","Smooth"};
static const char arp_name[]="Arp",amode_name[]="Arp Mode",arate_name[]="Rate",aoct_name[]="Octaves",agate_name[]="Gate";
static const char *const arp_names[3]={"Off","On","Latch"};
static const char *const amode_names[5]={"Up","Down","Up/Down","As Played","Random"};
static const char *const arate_names[8]={"1/4","1/4T","1/8","1/8T","1/16","1/16T","1/32","1/32T"};
static const char encoder_speed_name[]="Enc Speed";
static const char *const encoder_speed_names[4]={"Default","Slow","Fast","Faster"};
static int encoder_speed_owned(void){
 u32 r=W((void*)0x30031484u,0);
 return r&&W((void*)(r+ENCODER_SPEED_KEY*32),4)==(u32)encoder_speed_name;
}
int arp_publish(u32 on,u32 track,u32 mode,u32 rate,u32 octaves,u32 gate,u32 bpm);
int chord_audition_publish(int active,const u8 *count,const signed char *off,u32 velocity);
u32 chord_mail_serial(void);int chord_diatonic(int root,int seventh);unsigned chord_live_owner(void);int chord_pad_pitch(unsigned pad);u32 chord_pub_serial(void);
/* The project settings node that owns BPM 8C, Scale 8D, Root 8E, Swing 8F. */
static u32 settings(void){u32 h=0;return FN(0x08133e54,int(*)(void*,u32*))(MODEL,&h)?h:0;}
static void zero(void *p,u32 n){for(u32 i=0;i<n;i++)((u8*)p)[i]=0;}
static Perf *perf(int create){
 void **slot=perf_state_slot();if(!slot)return 0;Perf *s=*slot;
 if(s)return s->magic==PERF_MAGIC?s:0;if(!create)return 0;
 u32 cursor=W((void*)0x3000004cu,0),end=W((void*)0x30000048u,0),bytes=(sizeof(Perf)+31u)&~31u;
 if(cursor<0xc0000000u||end>0xc8000000u||cursor>end||end-cursor<bytes+32)return 0;
 s=FN(0x08104c08,void*(*)(u32))(bytes);if((u32)s!=cursor)return 0;zero(s,sizeof(*s));s->magic=PERF_MAGIC;*slot=s;return s;
}
__attribute__((used,retain)) int encoder_speed_delta(void *slot,int delta){
 Perf *s=perf(0);if(!s||!slot)return delta;
 return encoder_speed_scale(&s->encoder_speed,(u32)slot,W(slot,0x34),H(slot,0x9c),delta);
}
__attribute__((used,retain)) int encoder_fx_delta(void *slot,int delta){
 if(!slot||!delta||!fx_screen_active())return delta;
 u32 key=H(slot,0x9c);int index=key_index(key);
 if(index<0||index>=PARAMS||B(slot,0x9e)!=2)return delta;
 int lo=(int)W(slot,0x450),hi=(int)W(slot,0x454);
 u32 quantum=W(slot,0x88);
 if(lo!=fx_lo[index]||hi!=fx_hi[index]||!quantum||quantum>160000u||hi<=lo)return delta;
 Perf *s=perf(1);if(!s)return delta;
 EncoderFraction *f=0;
 for(u32 i=0;i<8;i++)if(s->fx_fraction[i].slot==(u32)slot){f=&s->fx_fraction[i];break;}
 if(!f){f=&s->fx_fraction[s->fx_fraction_next++&7u];zero(f,sizeof(*f));f->slot=(u32)slot;}
 if(f->handle!=W(slot,0x34)||f->key!=key){f->handle=W(slot,0x34);f->key=key;f->remainder=0;}
 /* One slow 160000-unit turn spans the numeric range, while the original
  * slot retains its quantizer, acceleration and end clamps. */
 long long value=(long long)delta*(hi-lo)*quantum+f->remainder;
 long long out=value/160000;
 if(out>0x15555555){f->remainder=0;return 0x15555555;}
 if(out<-0x15555555){f->remainder=0;return -0x15555555;}
 f->remainder=(int)(value-out*160000);return (int)out;
}
void **workflow_state_slot(int create){Perf *s=perf(create);return s?&s->workflow:0;}
__attribute__((section(".pad3"))) int play_mute_bank(int on){
 Perf *s=perf(on>0);if(!s)return 0;
 if(on>=0)s->mute_bank=(u32)on;return (int)s->mute_bank;
}
__attribute__((used,retain)) void motion_capture_begin(void *slot,int delta){
 Perf *s=perf(0);if(s)cm_begin(&s->motion,slot,delta);
}
__attribute__((used,retain)) int motion_capture_event(void *event){
 Perf *s=perf(0);return s?cm_event(&s->motion,event):0;
}
__attribute__((used,retain)) int motion_capture_get(void *handle,u32 key,void *out){
 Perf *s=perf(0);return s?cm_get(&s->motion,handle,key,out):0;
}
__attribute__((used,retain,section(".pad2"))) int motion_active(int stop){
 Perf *s=perf(0);if(!s||!s->motion.enabled)return 0;
 if(stop){cm_enable(&s->motion,0);FN(0x0813130c,void(*)(void*))(MODEL);}
 return 1;
}
__attribute__((used,retain)) void perf_rows_layout(void *group){
 FN(0x08170b7c,void(*)(void*))(group);
 if(fx_screen_active()){
  if(W(group,0x204)!=1)return;
  void *bar=(void*)W(group,0x34);int r[4]={6,50,1268,420};
  FN(W((void*)W(bar,0),0x20),void(*)(void*,void*))(bar,r);
  void *title=(u8*)group+0x44,*box=(u8*)group+0x248;
  B(title,0x30)=B(box,0x30)=1;W(group,8)=64;W(group,16)=408;W(group,0x39c)=0;
  FN(0x0817083c,void(*)(void*))(group);B((u8*)group+0x208,0x30)=1;
  B((u8*)group+0x358,0x30)=1;
  return;
 }
 Perf *s=perf(0);if(!s||!s->active)return;
 if(s->mview==1){
  if(W(group,0x204)!=1)return;
  void *bar=(void*)W(group,0x34);
  int r[4]={6,50,1268,420};
  FN(W((void*)W(bar,0),0x20),void(*)(void*,void*))(bar,r);
  void *title=(u8*)group+0x44,*box=(u8*)group+0x248;
  B(title,0x30)=B(box,0x30)=1;
  W(group,8)=64;W(group,16)=408;W(group,0x39c)=s->focus;
  FN(0x0817083c,void(*)(void*))(group);
  B((u8*)group+0x208,0x30)=1;
  B((u8*)group+0x358,0x30)=1;
  return;
 }
 if(s->mview||W(group,0x204)!=2)return;
 for(u32 i=0;i<2;i++){
  void *bar=(void*)W(group,0x34+i*4);
  int r[4]={6,i?178:278,1268,i?90:194};
  FN(W((void*)W(bar,0),0x20),void(*)(void*,void*))(bar,r);
  void *title=(u8*)group+0x44+i*0x70,*box=(u8*)group+0x248+i*0x44;
  B(title,0x30)=B(box,0x30)=1;
 }
 W(group,8)=64;W(group,16)=408;W(group,0x39c)=s->focus;
 FN(0x0817083c,void(*)(void*))(group);
 B((u8*)group+0x208,0x30)=1;
 B((u8*)group+0x358,0x30)=1;
}
static void descriptor(u32 key,const char *name,u32 type,int lo,int hi){
 u32 r=W((void*)0x30031484u,0);void *d=(void*)(r+key*32);
 zero(d,32);H(d,0)=(u16)key;B(d,2)=(u8)type;W(d,4)=(u32)name;W(d,16)=(u32)lo;W(d,20)=(u32)hi;
}
/* Never take a descriptor someone else owns. */
static int registry(void){
 u32 r=W((void*)0x30031484u,0);if(!r)return 0;
 static const u16 keys[12]={KEY_TAP,KEY_FIXED,KEY_VELOCITY,KEY_CHORD,KEY_CTYPE,KEY_VOICING,KEY_INVERSION,KEY_ARP,KEY_AMODE,KEY_ARATE,KEY_AOCT,KEY_AGATE};const char *names[12]={tap_name,fixed_name,velocity_name,chord_name,ctype_name,voicing_name,inversion_name,arp_name,amode_name,arate_name,aoct_name,agate_name};
 for(u32 i=0;i<12;i++){void *d=(void*)(r+keys[i]*32);if(H(d,0)&&W(d,4)!=(u32)names[i])return 0;}
 for(u32 i=0;i<4;i++)if(H((void*)(r+(KEY_BPM+i)*32),0)!=KEY_BPM+i)return 0; /* native project keys must exist */
 Perf *s=perf(1);if(!s)return 0;
 for(u32 i=0;i<CHORD_TYPES;i++)s->type_names[i]=i<CH_TYPES?chord_type_name(i):i==CH_TYPES?"Diatonic":"Diatonic 7";
 descriptor(KEY_TAP,tap_name,6,0,1);descriptor(KEY_FIXED,fixed_name,6,0,1);descriptor(KEY_VELOCITY,velocity_name,2,1,127);
 descriptor(KEY_CHORD,chord_name,6,0,1);descriptor(KEY_CTYPE,ctype_name,7,0,CHORD_TYPES-1);descriptor(KEY_VOICING,voicing_name,7,0,3);descriptor(KEY_INVERSION,inversion_name,2,0,3);
 void *d=(void*)(r+KEY_CTYPE*32);W(d,8)=(u32)s->type_names;W(d,12)=CHORD_TYPES;d=(void*)(r+KEY_VOICING*32);W(d,8)=(u32)voicing_names;W(d,12)=4;
 descriptor(KEY_ARP,arp_name,7,0,2);descriptor(KEY_AMODE,amode_name,7,0,4);descriptor(KEY_ARATE,arate_name,7,0,7);descriptor(KEY_AOCT,aoct_name,2,1,4);descriptor(KEY_AGATE,agate_name,2,10,100);
 /* Native registry construction leaves A8 empty. A foreign owner disables
  * only this optional Settings field, never an existing native descriptor. */
 d=(void*)(r+ENCODER_SPEED_KEY*32);
 if(!H(d,0)||W(d,4)==(u32)encoder_speed_name){
  descriptor(ENCODER_SPEED_KEY,encoder_speed_name,7,0,3);
  W(d,8)=(u32)encoder_speed_names;W(d,12)=4;
 }
 d=(void*)(r+KEY_ARP*32);W(d,8)=(u32)arp_names;W(d,12)=3;d=(void*)(r+KEY_AMODE*32);W(d,8)=(u32)amode_names;W(d,12)=5;d=(void*)(r+KEY_ARATE*32);W(d,8)=(u32)arate_names;W(d,12)=8;return 1;
}
static u32 current_track(void){u32 t=0;return FN(0x08133cfc,int(*)(void*,void*))(MODEL,&t)?t:0;}
static u32 track_index(void){u32 i=0;FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,PROJECT,0x131,&i);return i;}
static PerfTrack *entry(Perf *s,u32 handle,int create){
 if(!s||!handle)return 0;PerfTrack *free=0;
 for(u32 i=0;i<PERF_TRACKS;i++){if(s->tracks[i].handle==handle)return &s->tracks[i];if(!s->tracks[i].handle&&!free)free=&s->tracks[i];}
 if(!create)return 0;if(!free){for(u32 i=1;i<PERF_TRACKS;i++)s->tracks[i-1]=s->tracks[i];free=&s->tracks[PERF_TRACKS-1];}
 free->handle=handle;free->on=0;free->velocity=100;free->chord=0;free->type=CHORD_DEFAULT_TYPE;free->voicing=0;free->inversion=0;free->ver=0;
 free->arp=0;free->amode=0;free->arate=4;free->aoct=1;free->agate=50;return free;
}
static int pitched(u32 track){u32 t=track?FN(0x08133f7c,u32(*)(void*,void*))(MODEL,&track):0;return t==15||t==18||t==19||t==22;}
/* Chord shape for every pitch class (as CH6 live chord mode publishes it). */
static int distance(const int *a,u32 an,const int *b,u32 bn){
 int d=0;
 for(u32 i=0;i<an;i++){int m=1000;for(u32 j=0;j<bn;j++){int x=a[i]-b[j];if(x<0)x=-x;if(x<m)m=x;}d+=m;}
 for(u32 j=0;j<bn;j++){int m=1000;for(u32 i=0;i<an;i++){int x=a[i]-b[j];if(x<0)x=-x;if(x<m)m=x;}d+=m;}
 return d;
}
/* Smooth: from the close root-position chord (offsets t, n tones) pick the
   inversion and octave nearest to the last chord played. The pad is assumed
   in the octave nearest that chord (offsets are relative to the pad). */
static void smooth(Perf *s,u32 pc,int *t,int n){
 if(!s->ref_n||n<1)return;int sum=0;for(u32 i=0;i<s->ref_n;i++)sum+=s->ref[i];int centre=sum/(int)s->ref_n;
 int r=(int)pc+12*((centre-(int)pc+6+120)/12-10),best[CH_MAX_VOICES],bd=1<<30;
 for(int inv=0;inv<n;inv++)for(int shift=-12;shift<=12;shift+=12){
  int c[CH_MAX_VOICES];for(int i=0;i<n;i++)c[i]=t[i]+(i<inv?12:0)+shift;
  int a[CH_MAX_VOICES];for(int i=0;i<n;i++)a[i]=r+c[i];int d=distance(a,(u32)n,s->ref,s->ref_n);
  if(d<bd){bd=d;for(int i=0;i<n;i++)best[i]=c[i];}
 }
 for(int i=0;i<n;i++)t[i]=best[i];
 for(int i=1;i<n;i++)for(int j=i;j>0&&t[j]<t[j-1];j--){int x=t[j];t[j]=t[j-1];t[j-1]=x;}
}
static void chord_publish(Perf *s,PerfTrack *e){
 u8 *count=s->count;signed char (*off)[CH_MAX_VOICES]=s->off;
 for(u32 pc=0;pc<12;pc++){
  Chord c;zero(&c,sizeof(c));c.root=(int16_t)(48+pc);c.voicing=(int16_t)(e->voicing==SMOOTH?CH_CLOSE:e->voicing);c.inversion=(int16_t)(e->voicing==SMOOTH?0:e->inversion);
  c.type=(int16_t)(e->type<CH_TYPES?e->type:chord_diatonic(c.root,e->type==CH_TYPES+1));
  c.velocity=100;c.end=1; /* chord_notes checks a playable chord */
  int p[CH_MAX_VOICES];int n=chord_notes(&c,p);
  /* Triads have no third inversion or Drop 2: use the nearest that exists. */
  while(n<0&&c.inversion>0){c.inversion--;n=chord_notes(&c,p);}
  if(n<0&&c.voicing==CH_DROP2){c.voicing=CH_OPEN;c.inversion=(int16_t)e->inversion;n=chord_notes(&c,p);while(n<0&&c.inversion>0){c.inversion--;n=chord_notes(&c,p);}}
  if(n<=0){n=1;p[0]=c.root;}
  int t[CH_MAX_VOICES];for(int i=0;i<n;i++)t[i]=p[i]-c.root;
  if(e->voicing==SMOOTH)smooth(s,pc,t,n);
  count[pc]=(u8)n;for(int i=0;i<CH_MAX_VOICES;i++)off[pc][i]=(signed char)(i<n?t[i]:0);
 }
 chord_audition_publish(1,count,&off[0][0],127);
}
static void chord_tick(Perf *s,u32 track,PerfTrack *e){
 u32 live=chord_live_owner();int want=e&&e->chord&&pitched(track)&&live!=track;
 if(!want){
  /* Turn our chord off, unless live chord mode now owns the pads. */
  if(s->chord_pub&&live!=track)chord_audition_publish(0,0,0,0);
  s->chord_pub=0;return;
 }
 u32 root=0,scale=0,h=e->type>=CH_TYPES?settings():0;
 if(h){FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,KEY_ROOT,&root);FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,KEY_SCALE,&scale);}
 u32 sig=track*31u^e->type<<1^e->voicing<<6^e->inversion<<9^root<<12^scale<<18;
 if(e->voicing==SMOOTH)for(u32 i=0;i<s->ref_n;i++)sig=sig*31u+(u32)s->ref[i];
 if(s->chord_pub&&s->chord_sig==sig&&chord_mail_serial()==s->chord_serial)return;
 chord_publish(s,e);s->chord_pub=1;s->chord_sig=sig;s->chord_serial=chord_mail_serial();
}
static void refresh(Perf *s);
static const char *const note_names[12]={"C","C#","D","D#","E","F","F#","G","G#","A","A#","B"};
static const char *const suffixes[CH_TYPES]={"","m","dim","aug","sus2","sus4","maj7","m7","7","add9","m7b5","mMaj7","4ths","dim7","+maj7"};
static void put(char **d,const char *t){while(*t)*(*d)++=*t++;}
/* Name the actual published notes, not a possibly newer encoder setting. */
int perf_notes_name(u32 root,const u32 *notes,char *out){
 if(root>127)return 0;u32 mask=0,bass=128;
 for(u32 p=0;p<128;p++)if(notes[p>>5]&(1u<<(p&31u))){mask|=1u<<(p%12);if(bass==128)bass=p;}
 for(u32 type=0;type<CH_TYPES;type++){
  Chord c;zero(&c,sizeof(c));c.root=(int16_t)(48+root%12);c.type=(int16_t)type;c.velocity=100;c.end=1;
  int pitches[CH_MAX_VOICES];int n=chord_notes(&c,pitches);u32 expected=0;
  for(int i=0;i<n;i++)expected|=1u<<((u32)pitches[i]%12);
  if(n>0&&expected==mask){char *d=out;put(&d,note_names[root%12]);put(&d,suffixes[type]);
   if(bass%12!=root%12){*d++='/';put(&d,note_names[bass%12]);}*d=0;return 1;}
 }
 return 0;
}
/* "Dm7", "C/E": root, quality, and the bass when it is not the root. */
static void played_name(Perf *s,PerfTrack *e,int pitch){
 u32 pc=(u32)pitch%12u;int type=e->type<CH_TYPES?(int)e->type:chord_diatonic(48+(int)pc,e->type==CH_TYPES+1);
 char *d=s->name;put(&d,note_names[pc]);if(type>=0&&type<CH_TYPES)put(&d,suffixes[type]);
 int low=127;for(u32 i=0;i<s->count[pc];i++)if(s->off[pc][i]<low)low=s->off[pc][i];
 u32 bass=(u32)((int)pc+low+120)%12u;if(s->count[pc]&&bass!=pc){*d++='/';put(&d,note_names[bass]);}*d=0;
}
/* P7: a pad press (fx_dispatch code AC) is matched with the pitch the audio
   core published for it (ChordPub, after the chord started). */
void perf_pad(u32 code,u32 index){
 Perf *s=perf(0);if(!s||code!=0xac||index>=16)return;s->pad=index|0x100u;s->pad_serial=chord_pub_serial();s->pad_since=TICK;
}
static void played(Perf *s,u32 track,PerfTrack *e){
 if(!(s->pad&0x100u))return;
 if(TICK-s->pad_since>300u){s->pad=0;return;}
 if(chord_pub_serial()==s->pad_serial)return;
 int pitch=chord_pad_pitch(s->pad&15u);s->pad=0;if(pitch<0||!e||!s->chord_pub)return;
 u32 pc=(u32)pitch%12u;s->ref_n=s->count[pc];for(u32 i=0;i<s->ref_n;i++)s->ref[i]=pitch+s->off[pc][i];
 played_name(s,e,pitch);s->name_track=track;
 if(s->active)refresh(s); /* the header shows it (perf_header) */
}
/* Called for every UI message: the selected track's fixed velocity and chord. */
/* P20 (owner: holding TRACKS and picking a pad needs looking at the screen).
 * While TRACKS (button 2) is held, each track's two pads (n and n+8, as in the
 * native scene builder 081355D8) show that track's colours (08140F50 / 08140EF0
 * / 08140FB4); pads without a track are off (08140FBC(0)). The native pad
 * colours are saved on press and given back on release. Written only when they
 * differ, so the native page cannot make them flicker by itself. */
#define PADS ((u8*)MODEL+0x19c4)
static void track_pads(Perf *s){
 u32 want[16][3],off=FN(0x08140fbc,u32(*)(u32))(0);
 for(u32 i=0;i<16;i++){want[i][0]=want[i][1]=want[i][2]=off;}
 void *root=(void*)W(MODEL,0);
 for(u32 i=0;root&&i<16;i++){
  void *obj=0;if(!FN(0x0812d78a,int(*)(void*,u32,void*))(root,i,&obj)||!obj)break;
  u32 n=FN(0x0812dc74,u32(*)(void*,u32))(obj,0x73);if(n>7)continue;
  u32 a=FN(0x08140f50,u32(*)(u32))(n),b=FN(0x08140ef0,u32(*)(u32))(n),c=FN(0x08140fb4,u32(*)(u32))(n);
  for(u32 r=0;r<2;r++){want[n+r*8][0]=a;want[n+r*8][1]=b;want[n+r*8][2]=c;}
 }
 int changed=0;
 for(u32 i=0;i<16;i++){u8 *e=PADS+i*16;
  if(W(e,0)!=want[i][0]||W(e,4)!=want[i][1]||W(e,8)!=want[i][2]||B(e,12)||B(e,13)){W(e,0)=want[i][0];W(e,4)=want[i][1];W(e,8)=want[i][2];B(e,12)=0;B(e,13)=0;changed=1;}}
 if(changed)FN(0x081257f0,void(*)(void*))(PADS);
 (void)s;
}
/* P21 (owner on P20: after switching to INST or SEQ through the hold, the pads
 * went back to the old colours). Once a track is picked during the hold (a pad
 * press or record, or the page changes), painting stops and the new page keeps
 * its own pad colours; only a hold without a switch gives the old ones back. */
static void tracks_button(void *m,u32 code,u32 index){
 Perf *s=perf(0);
 if(s&&s->trk_held&&(code==0xac||code==0xfe||B(m,0x12c)!=s->trk_page))s->trk_used=1;
 if(index!=2||(code!=0xaf&&code!=0xb0))return;
 s=perf(code==0xaf);if(!s)return;
 if(code==0xaf&&!s->trk_held){for(u32 i=0;i<256;i++)s->trk_saved[i]=PADS[i];s->trk_held=1;s->trk_used=0;s->trk_page=2;track_pads(s);return;} /* P22 (owner): TRACKS opens the Tracks page (2); that jump is not a switch */
 if(code==0xb0&&s->trk_held){s->trk_held=0;if(!s->trk_used){for(u32 i=0;i<256;i++)PADS[i]=s->trk_saved[i];FN(0x081257f0,void(*)(void*))(PADS);}}
}
void perf_tick(void){
 Perf *s=perf(0);if(!s)return;
 if(s->motion.enabled){int position=0;cm_context(&s->motion,&position);}
 if(s->trk_held&&!s->trk_used&&B(MODEL,0x12c)==s->trk_page)track_pads(s);u32 track=current_track();PerfTrack *e=entry(s,track,0);
 u32 v=e&&e->on&&e->velocity>=1&&e->velocity<=127?PERF_FIXED_TAG|e->velocity:0;
 if(EC->reserved[1]!=v||s->published!=v){EC->reserved[1]=v;s->published=v;__asm__ volatile("dsb" ::: "memory");}
 played(s,track,e);
 chord_tick(s,track,e);
 /* P28: the selected track's arp (pads play the selected track). */
 u32 arp=e&&e->arp&&pitched(track)?e->arp:0;
 if(arp||s->arp_pub){u32 bpm=120,h=settings();if(h)FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&h,KEY_BPM,&bpm); /* only while an arp is (or was) on */
  arp_publish(arp,track,e?e->amode:0,e?e->arate:4,e?e->aoct:1,e?e->agate:50,bpm);s->arp_pub=arp!=0;}
}
static void project_set(u32 key,int value){
 u32 h=settings();if(!h)return;u32 ev[5]={0xcf,h,key,(u32)value,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,ev);FN(0x0813130c,void(*)(void*))(MODEL);
}
static void refresh(Perf *s){if(s->view)FN(0x08145cf4,void(*)(void*))((void*)s->view);}
static void nav(Perf *s,void *m,u32 page){s->nav=1;FN(0x081420ec,void(*)(void*,u32,u32,u32,u32))(m,page,0,0,0);s->nav=0;}
static void toggle(void *m){
 Perf *s=perf(1);if(!s)return;
 if(!registry())return;s->previous=B(m,0x12c);s->active=1;s->view=0;s->mview=0;s->tap_count=0;s->focus=s->macro_focus=0;s->touch_bar=0;nav(s,m,0x1a);
}
/* Before every other custom button handling (fx_dispatch). */
int perf_dispatch(void *m,u32 code,u32 index){
 tracks_button(m,code,index); /* P20; the press goes on to K16 */
 if(index==7&&(code==0xaf||code==0xb0)){
  LOCK_HELD=LOCK_USED=CONSUMED=0;
  if(code==0xaf){macro_disarm();toggle(m);} /* owner, 28 Oct: PROJ also ends mapping */
  return 1;
 }
 Perf *s=perf(0);
 if(s&&(index==0||index==1||index==8||index==9)&&(code==0xaf||code==0xb0)){
  u32 bit=1u<<index;
  if(code==0xb0&&(s->arrow_down&bit)){s->arrow_down&=~bit;return 1;}
  if(code==0xaf&&s->active&&s->mview==1){
   s->arrow_down|=bit;
   if(index==1||index==8){
    u32 edit=index==8;
    if(s->macro_edit!=edit){s->macro_edit=edit;refresh(s);}
   }else{
    int focus=(int)perf_macro_focus(-1)+(index==9?1:-1);
    if(focus<0)focus=0;if(focus>7)focus=7;
    macro_select((u32)focus);refresh(s);
   }
   return 1;
  }
  if(index!=1&&index!=8)return 0;
  if(code==0xaf&&s->active&&pitched(current_track())){
   s->arrow_down|=bit;u32 track=current_track();int offset=0;
   FN(0x08133614,int(*)(void*,void*,u32,void*))(MODEL,&track,KEY_OCTAVE,&offset);
   offset+=index==1?1:-1;if(offset<-5)offset=-5;if(offset>5)offset=5;
   u32 ev[5]={0xcf,track,KEY_OCTAVE,(u32)offset,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,ev);
   FN(0x08139138,void(*)(void*))(MODEL);FN(0x0813130c,void(*)(void*))(MODEL);refresh(s);return 1;
  }
 }
 return 0;
}
void perf_nav(u32 page){(void)page;Perf *s=perf(0);if(s&&!s->nav){s->active=0;s->view=0;if(s->mview){s->mview=0;macro_view_set(0);}}}
int perf_macro_view(void){Perf *s=perf(0);return s&&s->active&&s->mview<=1?1:0;}
int perf_macro_targets(void){Perf *s=perf(0);return s&&s->active&&s->mview==1&&s->macro_edit;}
/* One focused macro for Perform and the Macro tab; set < 0 only reads it. */
u32 perf_macro_focus(int set){
 Perf *s=perf(0);if(!s)return 0;
 if(set>=0&&set<8){s->macro_focus=(u32)set;if(s->mview==1)macro_title(s->titles[0]);}
 return s->macro_focus&7u;
}
__attribute__((used,retain)) int perf_toolbar(void *model,void *out){
 Perf *s=perf(0);if(!s||!s->active||!out||(B(model,0x12c)!=0x1a&&B(model,0x12c)!=0x13))return 0;
 if(s->mview==3){
  for(u32 i=1;i<4;i++){void *r=(u8*)out+0x74+i*48;zero(r,48);B(r,0x20)=1;}
  int changed=header_fixed_tab(out,0,PROJECT_TAB,"Proj",1);
  changed|=header_fixed_action(out,1,MOTION_TOGGLE,"Motion",s->motion.enabled);
  changed|=header_fixed_action(out,4,0x8f,"Save",0);
  changed|=header_fixed_action(out,5,0x8b,"Load",0);
  return changed;
 }
 int changed=header_fixed_tab(out,0,PERF_TAB,"Perform",s->mview==0);
 changed|=header_fixed_tab(out,1,MACRO_TAB,"Macro",s->mview==1);
 changed|=header_fixed_tab(out,2,SETTINGS_TAB,"Settings",s->mview==2);
 changed|=header_fixed_tab(out,3,PROJECT_TAB,"Proj",0);
 changed|=header_fixed_action(out,4,MOTION_TOGGLE,"Motion",s->motion.enabled);
 if(s->mview==2)changed|=header_fixed_action(out,5,0x36,"Set Time",0);
 return changed;
}
static void copy(char *d,const char *a,const char *b){while(*a)*d++=*a++;while(b&&*b)*d++=*b++;*d=0;}
static int global_config_key(u32 key){return key==0x83||key==0xa2||key==0xa3||key==0xe1||key==0x67||key==0xa4;}
static int pad_config_key(u32 key){return key==KEY_FIXED||key==KEY_VELOCITY||key==KEY_OCTAVE;}
int perf_header(void *out,u32 caller){
 Perf *s=perf(0);if(!s||!s->active||(caller&~1u)!=0x08145f22u||!registry())return 0;
 if(s->mview==3)return 0;
 s->view=(u32)out-0x93c4;zero(out,0x54);B(out,0)=3;
 if(s->mview==2){
  static const char *const labels[2]={"Global Settings","Date and Time"};
  /* The native Set Time action reads the second strip. */
  static const u16 keys[3][8]={{0x83,0xa2,0xa3,0xe1,0x67,0xa4,0,0},{0x1d4,0x1d5,0x1d6,0,0,0,0x1d7,0x1d8},{KEY_FIXED,KEY_VELOCITY,KEY_OCTAVE,0,0,0,0,0}};
  char n[2]={(char)('1'+track_index()),0};copy(s->titles[2],"Pads / Track ",n);
  for(u32 r=0;r<3;r++){W(out,4+r*4)=(u32)(r<2?labels[r]:s->titles[2]);for(u32 i=0;i<8;i++)H(out,0x14+r*16+i*2)=keys[r][i];}
  if(encoder_speed_owned())H(out,0x14+12)=ENCODER_SPEED_KEY;
  return 1;
 }
 if(s->mview==1){
  macro_title(s->titles[0]);
  B(out,0)=1;W(out,4)=(u32)s->titles[0];
  for(u32 i=0;i<8;i++)H(out,0x14+i*2)=0;
  return 1;}
 char n[3]={'1',0,0};u32 t=track_index();n[0]=(char)('1'+(t<8?t:0));
 copy(s->titles[1],"Chord & Arp / Track ",n);
 B(out,0)=2;W(out,4)=(u32)"Macros";W(out,8)=(u32)s->titles[1];
 static const u16 row[8]={KEY_CTYPE,KEY_VOICING,KEY_INVERSION,KEY_AMODE,KEY_ARATE,KEY_AOCT,KEY_AGATE,KEY_ARP};
 for(u32 i=0;i<8;i++)H(out,0x24+i*2)=row[i];
 return 1;
}
int perf_get(void *m,void *handle,u32 key,void *out){
 if(m==MODEL&&motion_capture_get(handle,key,out))return 1;
 Perf *s=perf(0);if(!s||!s->active||!out)return 0;
 if(s->mview==2&&!pad_config_key(key)){
  if(key==ENCODER_SPEED_KEY){if(!encoder_speed_owned())return 0;W(out,0)=s->encoder_speed.mode;return 1;}
  if(!global_config_key(key))return 0;
  if(s->in_get)return 0;u32 h=0xfffffffeu;
  s->in_get=1;int ok=FN(0x08133614,int(*)(void*,void*,u32,void*))(m,&h,key,out);s->in_get=0;return ok;
 }
 if(s->mview==3)return 0;
 if(key==KEY_OCTAVE){if(s->in_get)return 0;u32 h=current_track();s->in_get=1;int ok=FN(0x08133614,int(*)(void*,void*,u32,void*))(m,&h,key,out);s->in_get=0;if(!ok)W(out,0)=0;return 1;}
 if(key>=KEY_BPM&&key<=KEY_SWING){
  if(s->in_get)return 0; /* our own read of the settings node (below) */
  u32 h=settings();if(!h)return 0;
  s->in_get=1;int ok=FN(0x08133614,int(*)(void*,void*,u32,void*))(m,&h,key,out);s->in_get=0;
  if(!ok)W(out,0)=0;return 1;
 }
 /* Only our own keys below: current_track() itself reads the project's
    property 131 through this very getter, so looking it up for every key
    recursed until the stack overflowed (1.6P5 reset on PROJ+PLAY). */
 if(!key){W(out,0)=0;return 1;} /* empty encoder slots */
 if(key!=KEY_TAP&&key!=KEY_FIXED&&key!=KEY_VELOCITY&&key!=KEY_CHORD&&key!=KEY_CTYPE&&key!=KEY_VOICING&&key!=KEY_INVERSION&&key!=KEY_ARP&&key!=KEY_AMODE&&key!=KEY_ARATE&&key!=KEY_AOCT&&key!=KEY_AGATE)return 0;
 PerfTrack *e=entry(s,current_track(),0);
 if(key==KEY_TAP){W(out,0)=s->tap_count&1u;return 1;} /* flips with every tap */
 if(key==KEY_FIXED){W(out,0)=e&&e->on;return 1;}
 if(key==KEY_VELOCITY){W(out,0)=e?e->velocity:100;return 1;}
 if(key==KEY_CHORD){W(out,0)=e&&e->chord;return 1;}
 if(key==KEY_CTYPE){W(out,0)=e?e->type:CHORD_DEFAULT_TYPE;return 1;}
 if(key==KEY_VOICING){W(out,0)=e?e->voicing:0;return 1;}
 if(key==KEY_INVERSION){W(out,0)=e?e->inversion:0;return 1;}
 if(key==KEY_ARP){W(out,0)=e?e->arp:0;return 1;}
 if(key==KEY_AMODE){W(out,0)=e?e->amode:0;return 1;}
 if(key==KEY_ARATE){W(out,0)=e?e->arate:4;return 1;}
 if(key==KEY_AOCT){W(out,0)=e?e->aoct:1;return 1;}
 if(key==KEY_AGATE){W(out,0)=e?e->agate:50;return 1;}
 return 0;
}
/* Tap tempo: a tap is any change of the Tap field (touch or a knob nudge).
   Taps 0.2..2 s apart; the average of the last four intervals sets BPM. */
static void tap(Perf *s){
 u32 now=TICK,dt=now-s->tap_last;
 if(!s->tap_count||dt<200||dt>2000){s->tap_count=1;s->tap_last=now;return;}
 for(u32 i=3;i>0;i--)s->taps[i]=s->taps[i-1];s->taps[0]=dt;s->tap_last=now;if(s->tap_count<5)s->tap_count++;
 u32 n=s->tap_count-1,sum=0;for(u32 i=0;i<n;i++)sum+=s->taps[i];
 int bpm=(int)((60000u*n+sum/2)/sum);if(bpm<40)bpm=40;if(bpm>250)bpm=250;project_set(KEY_BPM,bpm);
}
int perf_page_active(void){Perf *s=perf(0);return s&&s->active;}
int perf_navigation(void *event){
 if(H(event,0)==MOTION_TOGGLE){
  Perf *s=perf(0);if(!s||!s->active)return 0;
  cm_enable(&s->motion,!s->motion.enabled);
  FN(0x0813130c,void(*)(void*))(MODEL);return 1;
 }
 u32 c=H(event,0);if(c!=PERF_TAB&&c!=MACRO_TAB&&c!=SETTINGS_TAB&&c!=PROJECT_TAB)return 0;
 Perf *s=perf(0);if(!s||!s->active)return 0;
 u32 want=c==MACRO_TAB?1:c==SETTINGS_TAB?2:c==PROJECT_TAB?3:0;
 if(s->mview!=want){
  macro_view_set(0);s->mview=want;s->macro_edit=0;s->view=0;
  nav(s,MODEL,want==3?0x13:0x1a);
 }return 1;
}
int perf_event(void *v,void *event){
 Perf *s=perf(0);if(!s||!s->active)return 0;
 if(perf_navigation(event))return 1;
 if(s->mview==3)return 0;
 {extern int seq_nav_global(void*,void*);u32 c=H(event,0);if(c>=0x1062u&&c<=0x1064u)return seq_nav_global(MODEL,event);} /* P17 burger */
 if(s->view!=(u32)v||H(event,0)!=0xcf)return 0;
 u32 key=W(event,8);int value=(int)W(event,12);
 if(s->mview==2&&!pad_config_key(key)){
  if(key==ENCODER_SPEED_KEY){
   if(!encoder_speed_owned())return 0;
   if(value<0)value=0;if(value>3)value=3;
   if(s->encoder_speed.mode!=(u32)value){zero(&s->encoder_speed,sizeof(s->encoder_speed));zero(s->fx_fraction,sizeof(s->fx_fraction));s->fx_fraction_next=0;s->encoder_speed.mode=(u32)value;}
   refresh(s);return 1;
  }
  if(!global_config_key(key))return 0;
  u32 e[5]={0xcf,0xfffffffeu,key,(u32)value,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,e);
  refresh(s);return 1;
 }
 if(key==KEY_OCTAVE){u32 t=current_track();if(value<-5)value=-5;if(value>5)value=5;u32 ev[5]={0xcf,t,key,(u32)value,0};FN(0x081403ec,int(*)(void*,void*))(MODEL,ev);FN(0x08139138,void(*)(void*))(MODEL);FN(0x0813130c,void(*)(void*))(MODEL);}
 else if(key>=KEY_BPM&&key<=KEY_SWING)project_set(key,value);
 else if(key==KEY_TAP)tap(s);
 else if(key==KEY_FIXED||key==KEY_VELOCITY||key==KEY_CHORD||key==KEY_CTYPE||key==KEY_VOICING||key==KEY_INVERSION){
  PerfTrack *e=entry(s,current_track(),1);if(!e)return 1;
  if(value<0)value=0;
  if(key==KEY_FIXED)e->on=value?1:0;else if(key==KEY_VELOCITY)e->velocity=(u32)(value<1?1:value>127?127:value);
  else if(key==KEY_CHORD)e->chord=value?1:0;else if(key==KEY_CTYPE)e->type=(u32)value<CHORD_TYPES?(u32)value:CHORD_TYPES-1;
  else if(key==KEY_VOICING)e->voicing=value>3?3:(u32)value;else e->inversion=value>3?3:(u32)value;
  if(key>=KEY_CHORD&&key!=KEY_FIXED&&key!=KEY_VELOCITY){e->ver++;if(!e->ver)e->ver=1;} /* SEQ chord mode adopts it */
  perf_tick();FN(0x0813130c,void(*)(void*))(MODEL);
 }else if(key>=KEY_ARP&&(key==KEY_ARP||key==KEY_AMODE||key==KEY_ARATE||key==KEY_AOCT||key==KEY_AGATE)){
  PerfTrack *e=entry(s,current_track(),1);if(!e)return 1;
  if(key==KEY_ARP)e->arp=value<0?0:value>2?2:(u32)value;
  else if(key==KEY_AMODE)e->amode=value<0?0:value>4?4:(u32)value;
  else if(key==KEY_ARATE)e->arate=value<0?0:value>7?7:(u32)value;
  else if(key==KEY_AOCT)e->aoct=value<1?1:value>4?4:(u32)value;
  else e->agate=value<10?10:value>100?100:(u32)value;
  perf_tick();FN(0x0813130c,void(*)(void*))(MODEL);
 }else return 0;
 refresh(s);return 1;
}
int perf_bar_kind(void *bar){
 Perf *s=perf(0);if(!s||!s->active||!s->view||!bar||B(MODEL,0x12c)!=0x1a)return 0;
 if(s->mview==1)return (u32)bar==s->view+0x38u?3:0;
 if(s->mview)return 0;
 if((u32)bar==s->view+0x38u)return 1;
 if((u32)bar==s->view+0x2430u)return 2;
 return 0;
}
int perf_point_hit(void *app,void *point,void **out){
 Perf *s=perf(0);if(!s||!s->active||!s->view||!point||!out||B(MODEL,0x12c)!=0x1a||s->mview>1)return 0;
 if((W(app,0x48)&&!B((void*)W(app,0x48),0x30))||(W(app,0x44)&&!B((void*)W(app,0x44),0x30)))return 0;
 int x=(int)W(point,0),top=480-(int)W(point,4);
 if(x<6||x>=1274||top<8||top>=(s->mview==1?428:302))return 0;
 *out=(void*)(s->view+(s->mview==0&&top>=202?0x2430u:0x38u));return 1;
}
u32 perf_display_state(char *name){
 Perf *s=perf(0);if(!s)return 0;
 if(s->active&&s->view&&!s->mview){
  s->focus=W((void*)(s->view+0x9018u),0x39c)?1:0;
  B((void*)(s->view+0x9220u),0x30)=1;
 }
 PerfTrack *e=entry(s,current_track(),0);
 if(name){u32 i=0;if(s->name_track==current_track())while(s->name[i]&&i<11){name[i]=s->name[i];i++;}name[i]=0;}
 return s->focus|(s->macro_focus<<1)|(e&&e->chord?16u:0)|(e?e->arp<<5:0)|(track_index()<<8);
}
int perf_bar_down(void *bar,void *point){
 int kind=perf_bar_kind(bar);if(!kind||!point)return 0;
 Perf *s=perf(0);s->touch_bar=(u32)bar;s->touch_x=(int)W(point,0);s->touch_y=(int)W(point,4);return 1;
}
int perf_bar_up(void *bar,void *point){
 int kind=perf_bar_kind(bar);if(!kind)return 0;
 Perf *s=perf(0);u32 down=s->touch_bar;s->touch_bar=0;if(down!=(u32)bar||!point)return 1;
 int x=(int)W(point,0),y=(int)W(point,4),dx=x-s->touch_x,dy=y-s->touch_y;
 if(dx<-30||dx>30||dy<-30||dy>30||x<6||x>=1274)return 1;
 if(kind==2&&y>=236&&((x>=6&&x<165)||(x>=483&&x<642))){
  PerfTrack *e=entry(s,current_track(),0);u32 key=x<165?KEY_CHORD:KEY_ARP;
  u32 value=key==KEY_CHORD?!(e&&e->chord):!(e&&e->arp);
  u32 event[5]={0xcf,0xfffffffeu,key,value,0};perf_event((void*)s->view,event);return 1;
 }
 if(kind==3){
  u32 i=(u32)(x-6)/159u;if(i>7)i=7;
  int top=480-y;if(top<8||top>=428)return 1;
  s->macro_edit=top>=88;
  if(!s->macro_edit)macro_touch(i);else{macro_select(i);if(top>=104&&top<104+3*104)macro_binding_tap(i,(u32)(top-104)/104u);}
  refresh(s);
  FN(0x0813130c,void(*)(void*))(MODEL);return 1;
 }
 s->focus=kind==2;
 if(kind==1){u32 i=(u32)(x-6)/159u;macro_touch(i<8?i:7);} /* focus; a double tap arms */
 void *group=(void*)(s->view+0x9018u);
 FN(0x08170c86,void(*)(void*,u32))(group,s->focus);
 B((u8*)group+0x208,0x30)=1;
 FN(0x0813130c,void(*)(void*))(MODEL);return 1;
}
/* Saved with the track object (fx_save/fx_load). */
static void attr(void *params,const char *name,u32 value){void *a=FN(0x08109cdc,void*(*)(void*,const char*))(params,name);if(a)FN(0x0810958e,void(*)(void*,u32))(a,value);}
void perf_save(void *object,void *params){
 Perf *s=perf(0);if(!s||!object||!params)return;PerfTrack *e=entry(s,W(object,0x10),0);
 if(e&&(e->on||e->velocity!=100))attr(params,"bento_perf_velocity",e->on<<8|e->velocity);
 if(e&&(e->chord||e->type!=CHORD_DEFAULT_TYPE||e->voicing||e->inversion))attr(params,"bento_perf_chord",1u<<24|e->inversion<<16|e->voicing<<12|e->type<<4|e->chord);
 if(e&&(e->arp||e->amode||e->arate!=4||e->aoct!=1||e->agate!=50))attr(params,"bento_perf_arp",1u<<28|e->agate<<16|e->aoct<<12|e->arate<<8|e->amode<<4|e->arp); /* P28 */
}
static int read(void *params,const char *name,u32 *value){void *a=params?FN(0x08109c64,void*(*)(void*,const char*))(params,name):0;return a&&!FN(0x08109566,int(*)(void*,void*))(a,value);}
void perf_load(void *node,void *object){
 if(!node||!object||!W(object,0x10))return;Perf *s=perf(0);
 if(s)cm_enable(&s->motion,0);
 void *params=FN(0x08109268,void*(*)(void*,const char*))(node,"params");
 u32 vel=0,chord=0,arp=0;int has_vel=read(params,"bento_perf_velocity",&vel),has_chord=read(params,"bento_perf_chord",&chord),has_arp=read(params,"bento_perf_arp",&arp);
 if(!has_vel&&!has_chord&&!has_arp){PerfTrack *e=entry(s,W(object,0x10),0);if(e){u32 h=e->handle;zero(e,sizeof(*e));e->handle=h;e->velocity=100;e->type=CHORD_DEFAULT_TYPE;e->arate=4;e->aoct=1;e->agate=50;}return;}
 if(!s)s=perf(1);PerfTrack *e=entry(s,W(object,0x10),1);if(!e)return;
 u32 v=vel&255;e->on=has_vel?(vel>>8)&1:0;e->velocity=has_vel&&v>=1&&v<=127?v:100;
 if(has_chord&&(chord>>24)==1){e->ver=1;e->chord=chord&1;u32 t=(chord>>4)&255;e->type=t<CHORD_TYPES?t:CHORD_DEFAULT_TYPE;e->voicing=(chord>>12)&15;if(e->voicing>3)e->voicing=0;e->inversion=(chord>>16)&15;if(e->inversion>3)e->inversion=0;}
 else{e->chord=0;e->type=CHORD_DEFAULT_TYPE;e->voicing=0;e->inversion=0;}
 /* P28 arp: version 1 in bits 28..31 */
 if(has_arp&&(arp>>28)==1){e->arp=arp&15;if(e->arp>2)e->arp=0;e->amode=(arp>>4)&15;if(e->amode>4)e->amode=0;e->arate=(arp>>8)&15;if(e->arate>7)e->arate=4;
  e->aoct=(arp>>12)&15;if(e->aoct<1||e->aoct>4)e->aoct=1;e->agate=(arp>>16)&255;if(e->agate<10||e->agate>100)e->agate=50;}
 else{e->arp=0;e->amode=0;e->arate=4;e->aoct=1;e->agate=50;}
}

/* P5: one chord per track. The performance page keeps it; SEQ chord mode
   (device.c) writes Type/Voicing/Inversion here when you edit them and starts
   an empty clip from it. */
/* Returns the chord's version (0: none). SEQ chord mode applies the chord when
   the version differs from the one it last saw. Smooth reads as Close there. */
int perf_chord_shared(u32 handle,u32 *type,u32 *voicing,u32 *inversion){
 PerfTrack *e=entry(perf(0),handle,0);if(!e||!e->ver)return 0;*type=e->type;*voicing=e->voicing==SMOOTH?0:e->voicing;*inversion=e->inversion;return (int)e->ver;
}
/* From SEQ chord mode. Keeps Smooth if SEQ only changed the type. */
void perf_chord_share(u32 handle,u32 type,u32 voicing,u32 inversion){
 PerfTrack *e=entry(perf(1),handle,1);if(!e||type>=CHORD_TYPES||voicing>2||inversion>3)return;
 if(!(e->voicing==SMOOTH&&voicing==0))e->voicing=voicing;
 e->type=type;e->inversion=inversion;if(!e->ver)e->ver=1;FN(0x0813130c,void(*)(void*))(MODEL);
}

/* P29 (owner: the arp kept the pads but played nothing). While the
   Performance page shows an armed arp, the top bar's counter shows what the
   audio core reports: "A<blocks/100> P<presses> N<notes>". Blocks not
   counting = the arp clock never runs; notes counting but silent = the notes
   are posted but not played. */
int arp_diag(u32 *out);
static void put_num(char *p,u32 *k,u32 v){char t[10];u32 n=0;do{t[n++]=(char)('0'+v%10);v/=10;}while(v&&n<10);while(n)p[(*k)++]=t[--n];}
void perf_readout(void *out){
 Perf *s=perf(0);if(!s||!out)return;char *p=(char*)out+0x196;
 if((p[0]=='R'&&p[1]=='E'&&p[2]=='C')||(p[0]=='N'&&p[1]=='O'))return;
 if(s->motion.enabled||s->motion.error){
  copy(p,"Motion: ",s->motion.error?cm_label(&s->motion):s->motion.count?"writing":"armed");return;
 }
 if(!s->active||!s->arp_pub)return;
 u32 d[8];if(!arp_diag(d))return;u32 k=0;
 p[k++]='A';put_num(p,&k,(d[0]/100u)%1000u);p[k++]=' ';p[k++]='P';put_num(p,&k,d[1]%1000u);p[k++]=' ';p[k++]='N';put_num(p,&k,d[2]%1000u);p[k]=0;
}
