/* Run 15 item C: native SectionGroup tick (vtable slot 0 default) per version. This directory is not translated by
 * make_tree, so both addresses are written out (1.6.1 0816FABC, 1.6.8 08171C1C; same function, study xmap). */
#pragma once
#if BENTO_FW==168
#define SG_NATIVE_TICK 0x08171c1cu
#else
#define SG_NATIVE_TICK 0x0816fabcu
#endif
