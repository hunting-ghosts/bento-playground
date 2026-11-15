#pragma once
#define MACRO_RING_RADIUS 37
#define MACRO_BODY_TOP 118
#define MACRO_TARGET_TOP 128
#define MACRO_TARGET_PITCH 96

typedef struct {
 unsigned track,valid;
 int low,high,from,to,current;
 char name[12];
} MacroTargetDisplay;
typedef struct {
 unsigned value,count,armed,rejected;
 MacroTargetDisplay targets[3];
 unsigned sensitivity;
} MacroDisplay;
int macro_snapshot(unsigned,MacroDisplay*);
int perf_bar_kind(void*);
unsigned perf_display_state(char*);
int perf_bar_down(void*,void*);
int perf_bar_up(void*,void*);
