#ifndef BENTO_ENCODER_SPEED_H
#define BENTO_ENCODER_SPEED_H

#define ENCODER_SPEED_KEY 0xa8u
#define ENCODER_SPEED_LIMIT 0x01111111
typedef struct {
 unsigned slot,handle,key;
 int remainder;
} EncoderFraction;
typedef struct {
 unsigned mode,next;
 EncoderFraction fraction[8];
} EncoderSpeed;

/* Bound non-default input before the inherited synth x5 and native x6. */
static inline int encoder_speed_scale(EncoderSpeed *s,unsigned slot,unsigned handle,unsigned key,int delta){
 if(!s||!s->mode||s->mode>3||key==ENCODER_SPEED_KEY||!delta)return delta;
 if(delta>ENCODER_SPEED_LIMIT)delta=ENCODER_SPEED_LIMIT;
 if(delta<-ENCODER_SPEED_LIMIT)delta=-ENCODER_SPEED_LIMIT;
 if(s->mode==1){
  EncoderFraction *f=0;
  for(unsigned i=0;i<8;i++)if(s->fraction[i].slot==slot){f=&s->fraction[i];break;}
  if(!f){f=&s->fraction[s->next++&7u];f->slot=slot;f->handle=handle;f->key=key;f->remainder=0;}
  if(f->handle!=handle||f->key!=key){f->handle=handle;f->key=key;f->remainder=0;}
  int total=delta+f->remainder,out=total/2;f->remainder=total-out*2;return out;
 }
 int factor=s->mode==2?2:4;
 if(delta>ENCODER_SPEED_LIMIT/factor)return ENCODER_SPEED_LIMIT;
 if(delta<-ENCODER_SPEED_LIMIT/factor)return -ENCODER_SPEED_LIMIT;
 return delta*factor;
}

int encoder_speed_delta(void *slot,int delta);
int encoder_fx_delta(void *slot,int delta);
#endif
