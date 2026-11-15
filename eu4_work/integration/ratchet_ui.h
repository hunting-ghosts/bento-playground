/* R6.14 ratchet UI (M4): registry keys and shared helpers (ratchet_ui.c). */
#pragma once
#define RT_KEY_COUNT 0x9fu
#define RT_KEY_SHAPE 0xa0u
#define RT_KEY_DEPTH 0xa1u
#define RT_KEY_PROB 0xa5u
u32 rt_ui_key(u32 field);u32 rt_ui_field(u32 key);const char *rt_ui_title(u32 field);
int rt_ui_registry(void);int rt_ui_value(u32 word,u32 field);u32 rt_ui_word(u32 word,u32 field,int value);
void rt_ui_publish(u32 owner,int step_ticks,int amount);u32 rt_ui_grid_ticks(u32 grid);
int rt_ui_arrows(u32 code,u32 index);int rt_ui_step_arrow(u32 index);void rt_note_ticks(void *grid,void *ctx);
