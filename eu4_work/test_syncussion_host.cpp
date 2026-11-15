#include "drums/syncussion.h"
#include "test_syncussion_reference.h"
#include <new>
/* Run 14: the specialised Metal engine (drums/syncussion.h) and, for the bit-identity check, the six-mode
 * reference engine it was cut from (test_syncussion_reference.h). */
extern "C" {
unsigned sync_size(){return sizeof(bento::Syncussion);}
void sync_init(void *p,unsigned seed){new(p)bento::Syncussion;bento::Syncussion *s=(bento::Syncussion*)p;s->Init(seed);}
void sync_trigger(void *p){((bento::Syncussion*)p)->Trigger();}
unsigned sync_active(void *p){return ((bento::Syncussion*)p)->Active();}
void sync_dormant(void *p,unsigned frames){((bento::Syncussion*)p)->AdvanceDormant(frames);}
void sync_render(void *p,const float *v,float ratio,float velocity,float attack,float *out,unsigned frames){
 auto *s=(bento::Syncussion*)p;auto c=s->Prepare(v,ratio,velocity,attack);
 for(unsigned i=0;i<frames;i++)out[i]=s->Process(c);
}
float sync_attack_coefficient(float attack){
 bento::Syncussion s;s.Init(1);float v[7]={78,55,50,65,35,30,0};
 return s.Prepare(v,1,1,attack).attack;
}
float sync_exp2(float x){return bento::Syncussion::exp2(x);}
unsigned ref_size(){return sizeof(bento::SyncussionReference);}
void ref_init(void *p,unsigned seed){new(p)bento::SyncussionReference;((bento::SyncussionReference*)p)->Init(seed);}
void ref_trigger(void *p){((bento::SyncussionReference*)p)->Trigger();}
unsigned ref_active(void *p){return ((bento::SyncussionReference*)p)->Active();}
void ref_dormant(void *p,unsigned frames){((bento::SyncussionReference*)p)->AdvanceDormant(frames);}
void ref_render(void *p,const float *v,unsigned flags,float ratio,float velocity,float attack,float *out,unsigned frames){
 auto *s=(bento::SyncussionReference*)p;auto c=s->Prepare(v,flags,ratio,velocity,attack);
 for(unsigned i=0;i<frames;i++)out[i]=s->Process(c);
}
}
