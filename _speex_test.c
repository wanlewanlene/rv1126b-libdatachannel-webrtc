// Speex preprocess 配置矩阵测试: 定位 48k 下静音问题 + 找可用配置
#include <speex/speex_preprocess.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

static void analyze(const int16_t* p, int n, const char* tag) {
    long long sum = 0; int peak = 0;
    for (int i = 0; i < n; ++i) {
        long long s = p[i]; sum += s * s;
        int a = abs(p[i]); if (a > peak) peak = a;
    }
    double rms = sqrt((double)sum / n);
    double db = 20 * log10(rms / 32767.0 + 1e-9);
    printf("  [%s] RMS=%d (%.1f dBFS) peak=%d\n", tag, (int)rms, db, peak);
}

static void run_cfg(int16_t* in, int nf, int fs, int ns, int agc_on, int agc_level,
                    const char* tag) {
    int16_t* buf = (int16_t*)malloc(sizeof(int16_t) * nf);
    memcpy(buf, in, sizeof(int16_t) * nf);
    SpeexPreprocessState* st = speex_preprocess_state_init(fs, 48000);
    if (ns > 0) speex_preprocess_ctl(st, SPEEX_PREPROCESS_SET_NOISE_SUPPRESS, &ns);
    if (agc_on) {
        int one = 1;
        speex_preprocess_ctl(st, SPEEX_PREPROCESS_SET_AGC, &one);
        speex_preprocess_ctl(st, SPEEX_PREPROCESS_SET_AGC_LEVEL, &agc_level);
    }
    for (int i = 0; i + fs <= nf; i += fs)
        speex_preprocess_run(st, buf + i);
    printf("  [%s]:\n", tag);
    analyze(buf, nf, tag);
    speex_preprocess_state_destroy(st);
    free(buf);
}

int main() {
    FILE* f = fopen("/tmp/mic_test.wav", "rb");
    if (!f) { printf("open failed\n"); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    int16_t* raw = (int16_t*)malloc(sz);
    fread(raw, 1, sz, f); fclose(f);
    int frames = (sz - 44) / 2;
    int nf = 48000 * 2;
    if (nf > frames / 2) nf = frames / 2;
    int16_t* L = (int16_t*)malloc(sizeof(int16_t) * nf);
    for (int i = 0; i < nf; ++i) L[i] = raw[2 * i];
    printf("wav 前 %d 样本(2s)\n", nf);
    analyze(L, nf, "原始");

    run_cfg(L, nf, 960, 0, 0, 0,          "A: 全关(raw通过)");
    run_cfg(L, nf, 960, 18, 0, 0,         "B: 仅NS18");
    run_cfg(L, nf, 960, 0, 1, 8000,       "C: 仅AGC8000");
    run_cfg(L, nf, 960, 18, 1, 8000,      "D: NS18+AGC8000(现用配置)");
    run_cfg(L, nf, 480, 18, 0, 0,         "E: 10ms帧 仅NS18");
    free(L); free(raw);
    return 0;
}
