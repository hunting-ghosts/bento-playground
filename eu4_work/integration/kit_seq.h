#pragma once
/* Existing K16 non-cacheable input state: M7 owns +6, M4 owns +14/+15.
 * The native heap/MPU and all existing structures keep their original bounds. */
#define KIT_SEQ_ACTION 0x107eu
#define KIT_SEQ_CONTEXT 0x3151534bu
#define KIT_SEQ_INPUT 0x24048ca0u
#define KIT_LOCK __attribute__((section(".kitlock")))
#define KIT_CONTEXT __attribute__((section(".kitcontext")))
#define KIT_INPUT __attribute__((section(".kitinput")))
#define KIT_EVENT __attribute__((section(".kitevent")))
#define KIT_DRAW __attribute__((section(".kitdraw")))
#define STEP_NOTE __attribute__((section(".stepnote")))
#define STEP_UI __attribute__((section(".stepui")))
#define STEP_DRAW __attribute__((section(".stepdraw")))
#define STEP_TEXT __attribute__((section(".steptext")))
typedef struct {
 int value[5];
 unsigned mixed,empty,first,used,condition,choosing,picks[2],pad;
} KitStep;
STEP_NOTE int locks_step_snapshot(unsigned,unsigned,unsigned,unsigned,KitStep*);
/* R6.11: in the bank-1 M4 cave (.stepnote was full; needs BENTO_M4_MPU_WIDE=1). */
__attribute__((section(".text.bank1b"))) int locks_step_edit(unsigned,unsigned,unsigned,unsigned,unsigned,int,int);
STEP_DRAW int live_manual_steps(unsigned,unsigned,unsigned,int);
STEP_NOTE int locks_step_registry(unsigned);
STEP_NOTE unsigned locks_step_choice(unsigned,unsigned,int);
STEP_UI int kit_seq_strip_snapshot(void*,KitStep*);
STEP_UI int kit_seq_strip_touch(void*,void*,unsigned,int);
STEP_UI int kit_seq_step_focus(int);
void kit_seq_strip_bind(void*);
KIT_LOCK int kit_seq_step_event(unsigned,int);
KIT_LOCK int kit_seq_step_touch(unsigned,int);
STEP_DRAW void drum_panel_hold_reset(void);
KIT_CONTEXT void kit_seq_bind(void*);
KIT_DRAW void kit_seq_after(void*);
KIT_CONTEXT void kit_seq_nav(void);
KIT_CONTEXT void kit_seq_periodic(void);
KIT_LOCK int kit_seq_toolbar(void*);
void kit_seq_header_reset(void*); /* R6.2: main text */
KIT_EVENT int kit_seq_event(void*,void*);
KIT_INPUT int kit_seq_dispatch(unsigned,unsigned,const unsigned*);
KIT_EVENT int kit_seq_increment(void*);
KIT_DRAW unsigned kit_seq_touch_context(void*);
int kit_seq_touch(void*,int); /* R6.2: main text */
KIT_DRAW int kit_seq_value_hit(void*,void*);
KIT_DRAW int kit_seq_point(void*,void*,void**);
KIT_CONTEXT int kit_seq_holding(void);
KIT_CONTEXT int kit_seq_value(unsigned,int,int*);
KIT_CONTEXT unsigned kit_seq_signature(void);
int kit_seq_lights(void*); /* R6.2: main text */
KIT_DRAW int kick_base_value(void*,unsigned,int*);
KIT_LOCK unsigned locks_direct_kind(unsigned,unsigned);
KIT_LOCK int locks_direct_edit(unsigned,unsigned,unsigned,unsigned,unsigned,int,int);
KIT_LOCK int locks_direct_value(unsigned,unsigned,unsigned,unsigned,unsigned,int,int*,unsigned*);
