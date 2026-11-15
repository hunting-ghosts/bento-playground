/* BENTO_MOD Track FX T1. Caller-owned DSP; no firmware addresses or allocation. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { TF_TRACKS=8, TF_SCHEMA=3 };
typedef struct {
    uint32_t eq_enabled, comp_enabled, clip_enabled, auto_makeup;
    float low_hz, low_db, mid_hz, mid_db, mid_q, high_hz, high_db;
    float threshold_db, ratio, attack_ms, release_ms, makeup_db, comp_mix;
    float clip_ceiling_db;
} TfSettings;
/* Run 17 (owner, 13 Nov, saturator FINAL; 1.6.8 builds compile with TF_SATURATOR): the clipper becomes a saturator
 * in the SAME settings layout. clip_enabled packs bit 0 On, bit 1 Mode (0 Soft = DaisySP SoftClip as before,
 * 1 Hard = clean clamp), bits 8-15 the output Level in dB (int8, -12..+12, 0 = unity). Drive = -clip_ceiling_db
 * (0..24 dB): the gain into the curve; the automatic level compensation is its inverse after the curve, so an old
 * ceiling c is exactly Drive 1/c (c*SoftClip(x/c)) and old settings (Soft, Level 0 dB) stay bit-exact.
 * Without TF_SATURATOR every byte of the previous behaviour is kept. */
#define TF_CLIP_ON(v) ((v)&1u)
#define TF_CLIP_HARD(v) (((v)>>1)&1u)
#define TF_CLIP_LEVEL_DB(v) ((int)(signed char)((v)>>8))
typedef struct { float input_peak, output_peak, reduction_db; uint32_t faults; } TfMeters;
size_t tf_bank_bytes(void);
size_t tf_bank_alignment(void);
void tf_defaults(TfSettings *settings);
/* memory must have tf_bank_bytes() bytes and tf_bank_alignment() alignment. */
int tf_init(void *memory, float sample_rate);
/* Invalid settings fail atomically, retaining the last accepted settings. */
int tf_configure(void *memory, unsigned track, const TfSettings *settings);
int tf_get_settings(const void *memory, unsigned track, TfSettings *settings);
/* In-place planar stereo; left/right MUST be disjoint, or right may be NULL (mono).
 * Returns 0 without writes for invalid arguments. Maximum block is 4096 frames.
 * API calls must be serialized by the audio owner; UI must use a separate mailbox.
 */
int tf_process(void *memory, unsigned track, float *left, float *right, size_t frames);
int tf_meters(const void *memory, unsigned track, TfMeters *meters);
int tf_reset_track(void *memory, unsigned track);
#ifndef TF_NO_RECORD /* firmware (1.6.8, run 17): the record API is host-only; the M7 image never calls it */
/* Portable little-endian settings-only record, versioned with CRC32.
 * Loading never partially applies a damaged record. No DSP state or pointers saved.
 * Integration must store this separately from the native project, e.g. sidecar.
 */
size_t tf_record_bytes(void);
int tf_save(const void *memory, void *record, size_t bytes);
int tf_load(void *memory, const void *record, size_t bytes);
#endif
#ifdef __cplusplus
}
#endif
