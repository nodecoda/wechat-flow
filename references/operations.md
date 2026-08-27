# NCoda 运维细节（operations）

> 本文件收纳 SKILL.md 外移的「条件性细节」：错误处理总表、history.yaml schema、范文注入模板、质量验证标准、辅助功能速查。主流程步骤仍在 SKILL.md，各节下方有回链。

## 错误处理 / 降级总表

（SKILL.md 各 Step 内联了对应降级行；此表为汇总速查。）

| 步骤 | 降级 |
|------|------|
| 环境检查 | 逐项引导，设降级标记 |
| 热点抓取 | WebSearch 替代 |
| 选题为空 | 请用户手动给选题 |
| SEO 脚本 | LLM 判断 |
| 素材采集（WebSearch） | LLM 训练数据中可验证的公开信息 |
| 维度随机化 | history 空时跳过去重 |
| Persona 文件不存在 | 回退到 midnight-friend（默认） |
| 范文库为空 | Fallback 到 exemplar-seeds.yaml（通用模式） |
| 去 AI 验证 | 2 轮定向修复不过则跳过该项 |
| 生图失败 | 输出提示词 |
| 推送失败 | 本地 HTML |
| 历史写入 | 警告不阻断 |
| 效果数据 | 告知等 24h |
| 立意脚手架（Step 2.5） | 模块缺失 → 回退 content-enhance.md 角度发现（LLM 直出，不落盘） |
| 素材溯源（FactSheet） | 无 FactSheet / 模块缺失 → 维持写作规则"真实信息锚定"，跳过引用拦截 |
| 编辑锚点（anchor.py） | 模块缺失 → 纯文本标记（旧语法） |
| 修改执行（revision） | 未触发 → 保持现有自检，零回归 |

## history.yaml schema（Step 8.1）

**8.1 写入历史**（推送成功或降级都要写，文件不存在则创建）：

```yaml
# → {skill_dir}/history.yaml
- date: "{日期}"
  title: "{标题}"
  topic_source: "热点抓取"  # 或 "用户指定"
  topic_keywords: ["{词1}", "{词2}"]
  output_file: "{output 文件路径}"  # e.g. output/2026-03-31-zhangxue-slow-accumulation.md
  framework: "{框架}"
  enhance_strategy: "{增强策略}"  # angle_discovery/density_boost/detail_anchoring/real_feel
  word_count: {字数}
  media_id: "{id}"  # 降级时 null
  writing_persona: "{人格名}"
  dimensions:
    - "{维度}: {选项}"
  closing_type: "{收尾类型}"  # trailing_off/unanswered/scene_revert/abrupt_stop/anti_conclusion/image
  composite_score: {Step 5.3 的 composite_score}  # 0=质量高, 100=问题多
  writing_config_snapshot:  # 本次使用的关键参数（从 writing-config.yaml 提取）
    sentence_variance: {值}
    paragraph_rhythm: "{值}"
    emotional_arc: "{值}"
    word_temperature_bias: "{值}"
    broken_sentence_rate: {值}
    tangent_frequency: "{值}"
    style_drift: {值}
    negative_emotion_floor: {值}
  intent:                     # 立意卡摘要（Phase A 契约；Phase C 启用）
    thesis: "{核心判断}"
    angle: "{反转/升维/预测/筛选}"
    status: "user_confirmed"
  fact_sheet: "output/{slug}-facts.yaml"  # 素材溯源文件（Phase A 契约；Phase D 启用）
  anchors:                    # 编辑锚点统计（toolkit/anchor.py）
    total: {总数}
    filled: {已填写数}
  revision:                   # 修改报告（Phase A 契约；Phase B 启用）
    baseline: null
    after: null
  stats: null
```


## 后续操作速查（Step 8.3）

**8.3 后续操作**：

| 用户说 | 动作 |
|--------|------|
| 润色/缩写/扩写/换语气 | 编辑文章 |
| 封面换暖色调 | 重新生图 |
| 用框架 B 重写 | 回到 Step 4 |
| 换一个选题 | 回到 Step 2.3 |
| 看看有什么主题 | `python3 {skill_dir}/toolkit/cli.py gallery` |
| 换成 XX 主题 | 重新渲染 |
| 看看文章数据 | `读取: {skill_dir}/references/effect-review.md` |
| 学习我的修改 | `读取: {skill_dir}/references/learn-edits.md`。支持本地 markdown 修改和微信草稿箱同步（`--from-wechat`） |
| 学习排版 / 学排版 | `python3 {skill_dir}/scripts/learn_theme.py <url> --name <name>` |
| 做一个小绿书/图片帖 | `python3 {skill_dir}/toolkit/cli.py image-post img1.jpg img2.jpg -t "标题"` |
| 检查一下 / 自检 / 这篇文章怎么样 | 生成报告（生成档案 + 质量检查，见辅助功能） |
| 导入范文 / 建范文库 | `python3 {skill_dir}/scripts/extract_exemplar.py article.md` |
| 查看范文库 | `python3 {skill_dir}/scripts/extract_exemplar.py --list` |


## 范文风格注入（Step 4.3）

**4.3 范文风格注入**（有 `references/exemplars/index.yaml` 时执行）：

从 index.yaml 筛选 category 匹配当前框架类型的范文，取 top 3。读取对应 .md 文件的片段内容。

在写作 prompt 中注入：

> 以下是该公众号风格的真实段落示例，模仿其句长节奏、情绪强度和口语化程度：
>
> 【开头风格】
> {exemplar_1 的开头钩子段}
>
> 【情绪段风格】
> {exemplar_2 的情绪高峰段}
>
> 【转折风格】
> {exemplar_2 或 exemplar_3 的转折/自纠段（如有）}
>
> 【收尾风格】
> {exemplar_3 的收尾段}

Category 映射规则：

| 框架类型 | exemplar category |
|----------|-------------------|
| 痛点型 | tech-opinion |
| 故事型 / 复盘型 | story-emotional |
| 清单型 / 对比型 | list-practical |
| 热点解读型 / 纯观点型 | hot-take |
| 其他 | general |

如果匹配到的范文不足 3 篇，用 general category 补足。

**Fallback（范文库为空时）**：读取 `{skill_dir}/references/exemplar-seeds.yaml`，从每个段落类型中随机选 1 个注入 prompt。种子段落只示范人类写作的结构模式（句长方差、情绪锐度、自我纠正、非总结式收尾），不携带特定风格。注入时使用：

> 以下是人类写作的结构模式示例，注意模仿其句长节奏和情绪表达方式（不要模仿具体内容或风格）：
>
> 【开头模式】{seeds.opening_hooks 随机 1 个}
>
> 【情绪段模式】{seeds.emotional_peaks 随机 1 个}
>
> 【转折模式】{seeds.transitions 随机 1 个}
>
> 【收尾模式】{seeds.closings 随机 1 个}

建库命令：`python3 {skill_dir}/scripts/extract_exemplar.py article.md`


## 质量验证标准（Step 5.2）

**5.2 质量验证**（两个维度，每项逐一检查）：

**A. 写作质量**（writing-guide.md 基础规则）：

| 检查项 | 标准 | 规则 |
|--------|------|------|
| 句长方差 | 最短与最长句相差 ≥ 30 字 | 1.1 |
| 词汇温度 | 任意 500 字 ≥ 3 种温度 | 1.2 |
| 段落节奏 | 无连续 2 个相近长度段落 | 1.3 |
| 情绪极性 | 负面情绪 ≥ 2 处，无平铺直叙 | 1.4 |
| 禁用词 | 命中数 = 0 | 2.1 |
| 真实锚定 | 每个 H2 ≥ 1 条真实素材，零编造 | 3.1 |
| 具体性 | 每 500 字 ≥ 2 处具体细节 | 3.2 |

**B. 内容质量**（基于 Step 3.2 的增强策略检查）：

| 检查项 | 标准 | 适用框架 |
|--------|------|---------|
| 增强贯穿 | 增强策略的核心输出（角度/密度/细节/体感）在全文可见，不只出现在一段 | 所有 |
| 开头钩子 | 前 3 句能制造悬念、冲突或好奇心（不是背景铺垫） | 所有 |
| 金句密度 | 至少 1 处可独立截图转发的句子 | 所有 |
| 操作密度 | 每个 H2 有可操作要点（工具/步骤/参数） | 痛点/清单 |
| 角度锐度 | 核心观点能引发同意或反对，不是"两面都有道理" | 热点解读/纯观点 |
| 场景感 | 至少 2 处有时间/地点/对话等画面细节 | 故事/复盘 |
| 真实声音 | 至少 1 处引用真实用户评价或体验 | 对比 |

不通过 → **定向修复**：只替换不达标的具体句子/段落，不动已通过的部分。每轮最多改 3 处，改完立即重新检查该项。2 轮仍不过 → 标注跳过，继续下一项。


## 脚本辅助验证细则（Step 5.3）

**5.3 脚本辅助验证**（补充 5.2 的逐项检查）：

Agent 在 5.2 检查过程中同步完成综合评估（各 H2 之间的语气差异度、信息密度的高低交替、段落间的节奏变化、整体阅读流畅度），产出 0-1 分数。

```bash
python3 {skill_dir}/scripts/humanness_score.py {article_path} --json --tier3 {agent_tier3_score}
```

解读 JSON 中 `composite_score`（0=质量高, 100=问题多）：
- < 30 → 通过，继续 Step 6
- 30-50 → 查看 `param_scores` 中最低分的 1-2 项，只修复对应的具体句子（不重写整段），改完重新打分。1 轮即可
- \> 50 → 取 `param_scores` 最低的 2-3 项，逐项定向修复（每项只改最相关的 1-2 处），最多 2 轮。仍 > 50 则标记 DONE_WITH_CONCERNS 继续


## 自检报告生成（辅助功能）

- 用户说"检查一下"/"自检"/"这篇文章怎么样" → 对最近一篇生成的文章（或用户指定的文章）执行自检，输出生成报告：

  **第一部分：生成档案**（告诉用户这篇文章是怎么来的）
  1. 读取 `history.yaml` 最近一条记录，提取：
     - 使用的框架类型 + 写作人格
     - 激活的维度随机化组合
     - 素材采集来源（WebSearch 还是降级到 LLM）
     - 内容增强策略（角度发现/密度强化/细节锚定/真实体感）
     - 范文风格库是否命中（用了哪几篇 exemplar，还是 fallback 到种子）
     - playbook 中生效的规则条数
  2. 如果 history.yaml 无记录或用户指定了外部文章 → 跳过此部分，提示"这篇文章不是 NCoda 生成的，只做质量检查"

  **第二部分：质量检查**（告诉用户哪里还能改）
  1. `python3 {skill_dir}/scripts/humanness_score.py {article_path} --json`
  2. Agent 解读 JSON 中每项得分，翻译为用户可操作的建议，格式：
     - 每条建议定位到具体段落或句子（"第 3 段连续 4 句长度接近"）
     - 给出具体改法（"建议把第 3 句拆成两个短句"、"这里可以加一句你自己的感受"）
     - 按影响度排序，最多 5 条
  3. 如果所有项得分都不错 → "这篇文章质量不错，建议在编辑锚点处加入你的个人内容就可以发了。"

  **输出格式**：自然语言报告，不输出 JSON 或分数（用户不需要看数字）
