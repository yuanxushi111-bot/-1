# V1.2 每日学习工具

所有命令在项目根目录使用tools.cmd；PowerShell写作 `& '.\tools.cmd' ...`。模型沿用DeepSeek Harness配置，工具不直接调用模型API。核心JSON约定与保存作答方法见 [工具接口](tools.md)。

## 入口

| 命令 | 用途 |
| --- | --- |
| `daily --minutes 30 [--subject 中国税法学]` | 按用户本次时间建立当天任务 |
| `daily` | 恢复同日计划与日志派生状态，不随机更换卡片 |
| `daily --remaining 10` | 以剩余时间重排待办，保留已经完成的任务 |
| `daily --revise` | 资料/卡片扩充后明确修订当天计划 |
| `cards` | 查看当前卡片、版本、前置条件、状态和未测点，不显示背诵正文 |
| `card <id>` | 卡片元数据与闭卷抽查question_id |
| `card <id> --learn [--request-id 唯一ID]` | 记录正文展示并返回完整卡片，随后向用户展示 |
| `card <id> --complete [--request-id 唯一ID]` | 仅在用户确认背完后记录自报完成；不等于正确或通过 |
| `card <id> --reference` | 教师核对正文，不自动认定学生看过；若要向学生展示，使用--learn |
| `recitation-review [--due]` | 重建卡片覆盖与到期状态；不只看单题总判定 |
| `card-candidates "主题"` | 从主讲义检索候选完整段落，仍需read核对 |
| `card-save <JSON> [--apply]` | 预览/保存新卡；同ID新内容生成新版本，保留历史 |
| `self-test context [--include-due]` | 教师拟题上下文：今日实际已背卡、版本、要点、剩余题数 |
| `self-test create [--count 2] [--new]` | 自动生成已背卡的闭卷回忆题；同一任务重复打开不重复生成 |
| `self-test import --file <JSON>` | 保存模型拟好的判断、比较、应用等题目和冻结答案/要点 |
| `self-test next [--set-id <id>]` | 只返回一道未完成题；已有未反馈作答时先完成反馈 |
| `self-test list` | 今日已生成自测任务的无答案概要 |
| `settings` | 查看实际生效的学习配置 |
| `settings <JSON> --apply` | 修改本机偏好，写入userdata/study-settings.json |

`--include-due`只在用户明确要求额外测试到期旧卡时使用；普通今日自测不扩大范围。已背范围不足时可以减少题数，或从同卡不同已学要点生成有依据的变式。`self-test create`每张卡默认生成一道完整回忆题，不能宣称它已经自动完成所有题型的语义拟题。

## 开始、学习与调整

1. 用doctor和daily确认状态。时间缺失时只问今天能学多久。daily任务中的分钟数是估计，既不是计时器，也不证明学习已经发生。
2. 到期旧卡先按question_id出题；不先读取正文或答案。用户提交后保存attempt、取answer-context、提交逐点反馈。
3. 新卡学习调用card --learn，向用户提供完整rendered_card，保留边界。用户说背完才card --complete。不会口头说完就代写作答或给独立通过。
4. 剩余时间有变化就daily --remaining，更新任务而不回退已经完成的部分。可跳过任务，不能把跳过记成完成。

跳过：`{"kind":"study","action":"skipped","task_id":"今日任务ID","text":"用户说明的跳过原因"}`。结束总结可以 `{"kind":"study","action":"task_done","task_id":"summary任务ID","text":"实际完成情况"}`。自测/复测任务不能用task_done手动标成通过。

## 按今日已背内容拟自测题

调用self-test context得到实际卡片与版本；该输出是教师资料，不能整段发给用户。出题和评分标准在学生作答前固定，默认只考一张卡的已学内容。

```json
{
  "questions": [
    {
      "card_id": "实际已背卡ID",
      "card_version": "context返回的版本",
      "point_ids": ["本题实际考查要点ID"],
      "kind": "简答",
      "stem": "不泄露答案的题干",
      "answer": "依据上述要点和讲义原文整理的完整参考答案"
    }
  ]
}
```

kind使用现有标准题型，判断说理可用其他。比较题的比较维度和应用题的全部必要规则都须在所选卡片范围内。题干、答案和要点之间的语义对应由教师核对；工具只能验证卡片、引用、范围、版本和预算，不能凭字段存在证明语义正确。

保存后只展示next.question；其中没有答案、rubric或教材逐字引文。用户回答后：

1. record保存原始attempt。工具保留卡片版本，并根据当天正文展示/学习记录自动标记answer_seen。
2. answer-context读取该题固定答案及rubric，不事后重写标准。
3. record提交feedback和point_results。rubric可省略，由工具加载冻结版；显式传入必须一致。逐点状态和student_quote遵循原工具接口。
4. 展示rendered_feedback：判定、完整参考答案与出处、逐点分析、复习安排。说明实际记录和错题本保存结果。
5. 继续self-test next。pending_verification为true时先核对争议，不自动算整组或整卡已通过。

题数按context.estimated_minutes_per_question的估计预算控制，每题以短设问为单位。长案例应拆成有依据的小问，或先明确调整估时设置及计划。缩短时间后，daily保留预算内的既有题目；next.budget_complete为true表示本轮预算已用完、仍有题顺延，不等于整组通过。误报背完或误跳过时可用cancel取消对应study事件，正文曝光历史仍保留。

每题只算自己的已测范围；查看recitation-review中的unmeasured_points和independent_pass_days。一次答对或同日多次重答，不能替代跨日完整覆盖。

## 扩充背诵卡

先card-candidates，必要时追加search/read核对上下文、分册与完整段落，再制作JSON：

```json
{
  "id":"稳定小写卡ID",
  "title":"主题与范围",
  "subject":"中国税法学",
  "source_id":"lecture-yanming-2026",
  "body":"可以直接背诵的完整正文，保留条件与边界",
  "memory_outline":["记忆骨架"],
  "prompt":"闭卷抽查的提问，不含答案",
  "priority":"A1",
  "learn_minutes":12,
  "points":[{"id":"稳定要点ID","description":"要点标签","importance":"core","evidence":[{"block_id":"真实块ID","quote":"主讲义逐字引文"}]}],
  "prerequisites":[],
  "known_limits":["未覆盖的扩展、版本或待核实事项"],
  "related_question_ids":[]
}
```

ID限制使用小写字母、数字、短横线/下划线，最多40字符。前置卡必须已存在。related_question_ids只填真实题库ID；不确定关联时留空。主讲义由settings.main_source_id确定。理论同义表达允许成立；不可将旧规则、OCR疑点、论文建议及条件截断当作统一规则。

card-save预览后按用户补充学习内容的授权--apply。新卡/修订建立版本，旧题目与记录继续可读；版本或主讲义变化时先核对再恢复练习。卡片不足时建立小批、显示实际覆盖，不虚报整本完成。

## 数据位置

卡片：library/recitation-cards；清单：library/recitation-manifest.json。每日任务：userdata/daily-plans/YYYY-MM-DD.md。自测任务：userdata/daily-self-tests/YYYY-MM-DD.md。真实学习和作答仍为study-records同日MD，错题本继续由日志重建。

任务/自测试卷文件保存分配和版本，不能靠手改勾选制造完成；个人笔记写学习日志的结构块外。自测文件的机器折叠区含教师答案，闭卷时不打开；若用户已查看，主动保留看过答案的背景。
