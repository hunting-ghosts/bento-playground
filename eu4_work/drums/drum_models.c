#include "kick_knobs.h"
#include "drum_models.h"

static unsigned drum_exp2(unsigned base,unsigned num,unsigned den){
 unsigned whole=num/den,f=(num%den)*1024u/den;
 return ((base<<whole)*(1024u+(f*(672u+(352u*f>>10))>>10)))>>10;
}
unsigned drum_tune_hz(unsigned m,unsigned v){
 return drum_sync(m)?drum_exp2(41203,(v<25?0:v-25)*6,155)/1000:
  m==3?drum_exp2(140,v,50):m==5?100+v*107/10:
  m==7?drum_exp2(400,v*3,100):m==9?drum_exp2(40,v<25?0:v-25,28):v;
}
#ifdef BENTO_UI_SHARED_WEAK
/* Knobs per engine (Kick's Click is the separate eighth control). */
unsigned drum_count(unsigned m){return m==1||m==9||drum_sync(m)?7u:5u;}
/* Step-lock kinds are per family: Tom locks use the Kick kinds, Clap the Snare kinds. */
unsigned drum_family(unsigned m){return m==9||drum_sync(m)?1u:m==7?3u:m;}
#endif
