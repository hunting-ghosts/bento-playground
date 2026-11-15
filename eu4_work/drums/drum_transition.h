#pragma once

namespace bento {
/* Retrigger bridge for engines that restart from zero state (Snare, HiHat,
 * Clap; Kick/Tom use the old-voice tail in kick.cpp and only the native
 * gain/pan handover here).
 * R6.11: additive instead of a crossfade, so the new hit's onset is never
 * ducked: out = new + h(k) * w(k), where h continues the old output from its
 * last value along its (low-passed, bounded) last slope, decelerating, and w is
 * a smoothstep 1 -> 0 over BRIDGE samples (cubic raised-cosine shape: zero
 * slope at both ends). Isolated hits are unchanged (no bridge without a
 * continuing retrigger). Size stays 32 bytes (pool-cell tail). */
struct DrumTransition {
    static constexpr unsigned BRIDGE = 120;  // 2.5 ms at 48 kHz
    float last, origin;
    unsigned remaining;
    float gain, pan_left, pan_right;
    unsigned pending;
    float slope;

    void Start(bool retrigger, bool hold = true) {
        if(!retrigger)last=gain=pan_left=pan_right=slope=0;
        origin=last;
        remaining=retrigger&&hold?BRIDGE:0;
        pending=retrigger;
    }

    float Process(float sample) {
        if(remaining) {
            origin+=slope;slope*=.875f;  // continue the old slope for ~8 samples
            float u=(float)remaining*(1.f/(float)BRIDGE);
            sample+=origin*(u*u*(3.f-2.f*u));
            --remaining;
        }
        last=sample;
        return sample;
    }

    /* Block end: last output and a low-passed slope estimate, bounded so the
     * continuation can never exceed the held level (noise has no useful slope). */
    void End(const float *samples, unsigned n) {
        last=samples[n-1];slope=0;
        if(n<16)return;
        float a=0,b=0;
        for(unsigned i=0;i<8;i++){a+=samples[n-16+i];b+=samples[n-8+i];}
        float s=(b-a)*(1.f/64.f),limit=(last<0?-last:last)*.125f;
        slope=s>limit?limit:s<-limit?-limit:s;
    }
};
}
