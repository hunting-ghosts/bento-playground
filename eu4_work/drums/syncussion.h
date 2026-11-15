/* Syncussion-inspired percussion, not an analog circuit emulation.
 * Run 14 (owner, 13 Nov, item 5b): specialised to the one configuration the firmware plays, engine 15 "Metal":
 * mode B Metallic, sweep down, LFO wave off, sample & hold on (kick.cpp R6.4 switch word 1+6*2+18*0+54*1).
 * The other modes, sweep directions, LFO waves and the switch word are gone; every remaining expression is
 * the original one with those switches folded, so Metal stays bit-identical (host test against the six-mode
 * reference copy test_syncussion_reference.h, emulator hashes in test_engines.py).
 * Project DSP GPL-3.0-or-later; adapted mappings/topology: syncussion.LICENSE.
 * Fixed state, no allocation, no general routing graph, no per-sample libm.
 */
#pragma once
#include <math.h>
#include "syncussion_controls.h"
namespace bento {
#ifdef BENTO_SYNCUSSION
#define SYNC_CODE(name) __attribute__((noinline,section(name)))
#else
#define SYNC_CODE(name)
#endif
class Syncussion {
 public:
  struct Block {
    float base,cutoff,decay,sweep_decay,range,width,lfo_inc,depth,velocity,attack;
  };
  SYNC_CODE(".sync_control.init") void Init(unsigned seed) {
    phase1_=phase2_=lfo_=held_=env_=sweep_=gain_=ic1_=ic2_=previous_=last_=bridge_=slope_=0;
    random_=seed?seed:1;attack_=sweep_attack_=fade_=0;previous_osc_=lfo_inc_=0;active_=prepared_=false;
  }
  SYNC_CODE(".sync_control.trigger") void Trigger() {
    /* Preserve phases/filter and start from the current envelopes on retrigger.
     * The short output bridge also covers changed velocity or mode. */
    attack_=sweep_attack_=1;fade_=120;bridge_=last_+slope_;active_=true; /* R6.11: continue the last slope one sample; 2.5 ms smoothstep (was: repeat the last sample, 1 ms linear) */
  }
  bool Active() const {return active_;}
  SYNC_CODE(".sync_process") Block Prepare(const float *v,float ratio,float velocity,float attack=0) {
    bool same=prepared_&&bits(ratio)==bits(prepared_ratio_)&&
      bits(velocity)==bits(prepared_velocity_)&&bits(attack)==bits(prepared_attack_);
    for(unsigned i=0;same&&i<7;i++)same=bits(v[i])==bits(prepared_values_[i]);
    if(same)return prepared_block_;
    prepared_block_=Coefficients(v,ratio,velocity,attack);
    for(unsigned i=0;i<7;i++)prepared_values_[i]=v[i];
    prepared_ratio_=ratio;prepared_velocity_=velocity;prepared_attack_=attack;prepared_=true;
    return prepared_block_;
  }
 private:
  SYNC_CODE(".sync_control.prepare") Block Coefficients(const float *v,float ratio,float velocity,float attack) {
    const float rate=48000.f;
    Block c;
    float tune=bound(v[0],25,180);
    c.base=440.f*exp2((28.f+72.f*(tune-25.f)/155.f-69.f)/12.f)*bound(ratio,.0000152587890625f,64.f)/rate;
    c.cutoff=bound(c.base*rate*2.f,12.f,18000.f);
    c.decay=exp2(-4.61662413084f/(rate*.006f*exp2(bound(v[1],0,100)*.087027499f)));
    c.sweep_decay=exp2(-4.61662413084f/(rate*.02f*exp2((100.f-bound(v[3],0,100))*.069657843f)));
    c.range=bound(v[4],0,100)*.03f;c.width=bound(v[2],0,100)*.06f;
    c.lfo_inc=.4f*exp2(bound(v[5],0,100)*.069657843f)/rate;
    c.depth=bound(v[6],0,100)*.01f;c.depth*=c.depth;
    c.velocity=bound(velocity,0,1);
    c.attack=attack<=0?.0327839f:1.f-exp2(-2.32192809489f/(rate*.001f*exp2(bound(attack,0,100)*.089657843f)));
    lfo_inc_=c.lfo_inc;
    return c;
  }
 public:
  SYNC_CODE(".sync_process") float Process(const Block &c) {
    if(!active_)return 0;
    envelope(env_,attack_,c.decay,c.attack);envelope(sweep_,sweep_attack_,c.sweep_decay);
    float ev=env_*c.velocity,mod=0;
    /* Keep the free-running phase even at zero depth; no oscillator waveform,
     * random draw or pitch exponent is evaluated for disabled modulation. */
    lfo_+=c.lfo_inc;
    if(lfo_>=1){lfo_-=1;held_=noise();}
    if(c.depth>0) {
      mod+=held_*c.depth;
    }
    float x=0,osc1=0;
    {
      float sweep=-1.f*c.range*(1.f-sweep_);
      float increment=c.base;
      if(mod!=0||sweep!=0)increment*=exp2(mod+sweep);
      float inc1=increment;
      phase1_=advance(phase1_,inc1);osc1=triangle(phase1_);
      {
        float inc2=increment*(450.f/440.f);
        /* Reference FM is exponential pitch modulation, not sine PM.
         * Its routed oscillator value is from the preceding sample. */
        inc2*=exp2(2.f*previous_osc_);
        phase2_=advance(phase2_,inc2);x=triangle(phase2_);
      }
      previous_osc_=osc1;
    }
    float width=c.width*ev;
    /* Prepared width and envelope/velocity keep this exponent in [0,6]. */
    float fc=bound(c.cutoff*exponent(width,(int)width),12.f,20160.f);
    /* TPT SVF, Q=.5, twice sampled as in the reference. Padé tan error is
     * bounded by the host tests over the actual cutoff range. */
    float a=3.14159265358979323846f*fc/96000.f,q=a*a;
    float g=a*(105.f-10.f*q)/(105.f-45.f*q+q*q);
    float a1=1.f/(1.f+g*(g+2.f)),a2=g*a1,a3=g*a2,lp=0;
    for(unsigned os=0;os<2;os++) {
      float input=soft((os?x:(x+previous_)*.5f)*.8f);
      float v3=input-ic2_,bp=a1*ic1_+a2*v3;
      lp=ic2_+a2*ic1_+a3*v3;ic1_=2.f*bp-ic1_;ic2_=2.f*lp-ic2_;
    }
    previous_=x;gain_+=(ev-gain_)*.017211379f;
    float out=lp*1.25f*gain_;
    if(fade_) {
      if(fade_==120)bridge_-=out;
      float u=(float)fade_*(1.f/120.f);
      out+=bridge_*(u*u*(3.f-2.f*u));fade_--;
    }
    slope_=out-last_;last_=out;
    if(!attack_&&env_<.00002f&&gain_<.00002f){active_=false;last_=slope_=0;return 0;}
    return out;
  }
  /* Catch up a dormant pad from a caller-owned sample count. No background
   * audio processing or loops proportional to the elapsed idle time. */
  void AdvanceIdle(unsigned frames,float increment) {
    float cycles=lfo_+(float)frames*increment;unsigned n=(unsigned)cycles;
    lfo_=cycles-(float)n;
    if(n){random_^=n*0x9e3779b9u;held_=noise();}
  }
  void AdvanceDormant(unsigned frames){if(!active_)AdvanceIdle(frames,lfo_inc_);}
  SYNC_CODE(".sync_control.exp2") static float exp2(float x) {
    x=bound(x,-24,24);int n=(int)x;if((float)n>x)n--;
    return exponent(x,n);
  }
 private:
  float phase1_,phase2_,lfo_,held_,env_,sweep_,gain_,ic1_,ic2_,previous_,last_,bridge_,slope_=0,previous_osc_=0,lfo_inc_;
  unsigned random_,attack_,sweep_attack_,fade_;
  bool active_,prepared_;
  Block prepared_block_;
  float prepared_values_[7],prepared_ratio_,prepared_velocity_,prepared_attack_;
  static unsigned bits(float x){union {float f;unsigned u;} value={x};return value.u;}
  __attribute__((always_inline)) static inline float exponent(float x,int n){
    float f=(x-(float)n)*.6931471805599453f;
    float y=1.f+f*(1.f+f*(.5f+f*(.1666666666667f+f*(.0416666666667f+f*(.0083333333333f+f*(.0013888888889f+f*.0001984126984f))))));
    union {unsigned bits;float value;} scale={(unsigned)(n+127)<<23};return y*scale.value;
  }
  static float bound(float x,float lo,float hi){return x<lo?lo:x>hi?hi:x;}
  static float triangle(float p){return p<.5f?4.f*p-1.f:3.f-4.f*p;}
  static float advance(float p,float inc){p+=bound(inc,0,.45f);return p>=1?p-1:p;}
  static float soft(float x){float q=x*x;return x*(135135.f+q*(17325.f+q*(378.f+q)))/(135135.f+q*(62370.f+q*(3150.f+28.f*q)));}
  static void envelope(float &e,unsigned &attack,float decay,float rise=.0327839f){
    if(attack){e+=(1.25f-e)*rise;if(e>=1){e=1;attack=0;}}
    else e*=decay;
  }
  float noise(){unsigned r=random_;r^=r<<13;r^=r>>17;r^=r<<5;random_=r;return (float)(int)(r>>8)*(1.f/8388608.f)-1.f;}
};
#undef SYNC_CODE
} // namespace bento
