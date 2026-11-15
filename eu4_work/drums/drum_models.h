#pragma once
#ifdef BENTO_SYNCUSSION
#include "syncussion_controls.h"
#endif
static inline unsigned drum_sync(unsigned m){
#ifdef BENTO_SYNCUSSION
 return m==15;
#else
 (void)m;return 0;
#endif
}
static const unsigned char snare_ui_defaults[7]={10,45,50,65,70,0,0}; /* P10: 909 Snare (Tone 50) */
static const char *const snare_labels[7]={"Tune","Decay","Tone","Impact","Snappy","",""};
static const unsigned char hat_ui_defaults[7]={10,70,65,65,30,0,0};
static const char *const hat_labels[7]={"Tune","Decay","Tone","Impact","Noise","",""};
/* CH12: Clap (engine 7) and Tom / FM perc (engine 9). Engine ids follow the
 * carrier lengths 144019 + id - 1; even ids stay reserved (K8 analog variants). */
static const unsigned char clap_ui_defaults[7]={40,40,50,65,40,0,0};
static const char *const clap_labels[7]={"Tune","Decay","Tone","Impact","Spread","",""};
static const unsigned char tom_ui_defaults[7]={86,50,40,65,40,30,10}; /* Tune shares the Kick's 25..180 range (Kick lock kinds); 86 = 180 Hz */
static const char *const tom_labels[7]={"Tune","Decay","Tone","Impact","Sweep","Sweep Dec","Dirt"};
/* A1: engine 13 marks an Analog Wavetable track (values[0] = Sync, 0 off). */
static const unsigned char analog_defaults[7]={0,0,0,0,0,0,0};
static const unsigned char *drum_defaults(unsigned m){
#ifdef BENTO_SYNCUSSION
 if(m==15)return sync_defaults;
#endif
 if(m==13)return analog_defaults;return m==3?snare_ui_defaults:m==5?hat_ui_defaults:m==7?clap_ui_defaults:m==9?tom_ui_defaults:kick_defaults;}
static const char *drum_name(unsigned m){return drum_sync(m)?"Metal":m==3?"Snare":m==5?"HiHat":m==7?"Clap":m==9?"Tom":"Kick";}
/* Knobs per engine (Kick's Click is the separate eighth control). */
#ifdef BENTO_UI_SHARED_WEAK /* UI link (space): one shared copy, defined in drum_models.c */
unsigned drum_count(unsigned m);
unsigned drum_family(unsigned m);
#else
static unsigned drum_count(unsigned m){return m==1||m==9||drum_sync(m)?7u:5u;}
/* Step-lock kinds are per family: Tom locks use the Kick kinds, Clap the Snare kinds. */
static unsigned drum_family(unsigned m){return m==9||drum_sync(m)?1u:m==7?3u:m;}
#endif
/* Tune readout in Hz (integers only, for the UI). 2^f ~ 1 + f(0.6565 + 0.3435f). */
unsigned drum_tune_hz(unsigned,unsigned);
/* P7: the firmware's own folder "Drum Synths" (SD root) holds Kick.wav,
 * Snare.wav, HiHat.wav, Clap.wav and Tom.wav, chosen in the native browser. */
static unsigned drum_folder_name(const char *dir,const char *base){
 const char *want="drum synths";unsigned i=0;for(;want[i];i++){unsigned c=(unsigned char)dir[i];if(c>='A'&&c<='Z')c+=32;if(c!=(unsigned char)want[i])return 0;}
 if(dir+i!=base-1)return 0;
 const char *names[]={"kick.wav","snare.wav","hihat.wav","clap.wav","tom.wav"
#ifdef BENTO_SYNCUSSION
 ,"syncussion.wav","metal.wav" /* R6.6: Metal carrier; old Syncussion.wav still recognised (run 14: melodic carrier retired) */
#endif
 };const unsigned models[]={1,3,5,7,9,15,15};
 for(unsigned k=0;k<sizeof(names)/sizeof(*names);k++){unsigned j=0;for(;names[k][j]&&base[j];j++){unsigned c=(unsigned char)base[j];if(c>='A'&&c<='Z')c+=32;if(c!=(unsigned char)names[k][j])break;}if(!names[k][j]&&!base[j])return models[k];}
 return 0;
}
static unsigned drum_path(const char*s){
 const char *base=s,*dir=s;unsigned n=0;for(;n<256&&s[n];n++)if(s[n]=='/'||s[n]=='\\'){dir=base;base=s+n+1;}if(n==256)return 0;
 {unsigned m=drum_folder_name(dir,base);if(m)return m;}
 const char *names[]={"bento_kick.wav","bento_kick_k1.wav","bento_kick_k2.wav","bento_synth_snare.wav","bento_synth_hihat.wav","bento_synth_clap.wav","bento_synth_tom.wav"
#ifdef BENTO_SYNCUSSION
 ,"bento_synth_syncussion.wav"
#endif
 };
 const unsigned models[]={1,1,1,3,5,7,9,15};
 for(unsigned k=0;k<sizeof(names)/sizeof(*names);k++){unsigned i=0;for(;names[k][i]&&base[i];i++){unsigned c=(unsigned char)base[i];if(c>='A'&&c<='Z')c+=32;if(c!=(unsigned char)names[k][i])break;}if(!names[k][i]&&!base[i])return models[k];}return 0;
}
