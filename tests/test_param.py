# 参数层单元测试：低分初稿应生成多条建议，高分终稿应生成少/无建议
import io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "toolkit"))
import revision

# 模拟初稿（47 分时代）的 tier 结构
def mk_tier(entries):
    d = {n: {"score": s, "detail": dt, "param": p} for n, s, dt, p in entries}
    d["_summary"] = {"mean_score": sum(e[1] for e in entries) / len(entries)}
    return d

draft_scored = {
    "tier1": mk_tier([
        ("sentence_length_stddev", 0.28, "stddev=14.0 (target >=15)", "sentence_variance"),
        ("sentence_length_range", 0.10, "range=65", "sentence_variance"),
        ("negative_emotion_ratio", 0.16, "negative=3/74 (4%, target >=20%)", "negative_emotion_floor"),
        ("vocabulary_richness", 0.59, "bigram_ttr=0.810, temps=2/4", "word_temperature_bias"),
        ("adverb_density", 1.0, "density=0.6/100chars", "adverb_density"),
    ]),
    "tier2": mk_tier([
        ("broken_sentences", 0.71, "7 broken", "broken_sentence_rate"),
        ("self_correction", 0.67, "2 self-corrections", "self_correction_rate"),
        ("real_sources", 0.60, "3 indicators", "real_data_density"),
        ("word_temperature_mix", 0.33, "2/4 bands", "word_temperature_bias"),
    ]),
}
f = revision.check_params(draft_scored)
print("draft-scenario findings:")
for x in f:
    print(f"  [{x['impact']}] {x['location']} | {x['issue'][:30]}...")
params = {x["location"].split(" ")[0] for x in f}
assert "negative_emotion_floor" in params, "初稿应有负面情绪建议"
assert "sentence_variance" in params, "初稿应有句长建议"
assert "word_temperature_bias" in params, "初稿应有温度带建议"
# 聚合验证：sentence_variance 只出现一次
n_sv = sum(1 for x in f if x["location"].startswith("sentence_variance"))
assert n_sv == 1, f"sentence_variance 应聚合为 1 条, got {n_sv}"
# 高分终稿（当前文章）应少于 3 条
import subprocess
final_f = revision.check_params({"tier1": mk_tier([
    ("sentence_length_stddev", 0.61, "stddev=15.2", "sentence_variance"),
    ("sentence_length_range", 0.05, "range=81", "sentence_variance"),
    ("negative_emotion_ratio", 0.76, "16/84", "negative_emotion_floor"),
    ("vocabulary_richness", 1.0, "temps=4/4", "word_temperature_bias"),
]), "tier2": mk_tier([
    ("broken_sentences", 0.97, "6", "broken_sentence_rate"),
    ("self_correction", 0.66, "2", "self_correction_rate"),
    ("real_sources", 0.80, "4", "real_data_density"),
])})
print("final-scenario findings:", len(final_f), [x["location"] for x in final_f])
assert len(final_f) <= 2, "终稿建议应很少"
print("PASS: 参数层初稿→终稿分级正确")