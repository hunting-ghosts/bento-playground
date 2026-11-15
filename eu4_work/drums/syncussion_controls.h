/* Syncussion-inspired mappings adapted from KnowYourSynth, MIT.
 * See syncussion.LICENSE. Engine 15; no mailbox or native note ABI change. */
#pragma once
#define SYNCUSSION_ENGINE 15u
#define SYNCUSSION_FRAMES 144033u
#define SYNCUSSION_MELODIC_FRAMES 144035u
static const unsigned char sync_defaults[7]={78,55,50,65,0,30,0}; /* R6.4 owner: Metal Sweep Range and LFO Depth default 0 */
static const char *const sync_labels[7]={"Tune","Decay","Width","Sweep Speed","Sweep Range","LFO Speed","LFO Depth"};
/* Run 14 (owner, 13 Nov): the Mode/Sweep/LFO Wave/Sample Hold switches and their packed word are retired with
 * Syncussion; engine 15 "Metal" has them folded into its DSP (syncussion.h). */
