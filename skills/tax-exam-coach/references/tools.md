# 本地工具接口 V1.2（兼容V1.1作答与反馈）

每日计划、背诵卡和当日自测命令见 [每日学习工具](daily-study.md)。本页保留通用题库、作答、逐点判定与资料导入约定。

项目根目录执行 `tools.cmd <命令>`；PowerShell 使用 `& '.\tools.cmd' <命令>`，开发环境可用 `python tax_exam.py`。返回 UTF-8 JSON：`{ok,version,data}` 或 `{ok:false,version,error:{code,message}}`；退出码0成功、2失败，doctor不通过为1。不要把用户原文拼进shell命令，应写JSON请求文件。

| 命令 | 用途 |
| --- | --- |
| `doctor` / `index` | 校验资料、索引 / 重建缓存 |
| `materials` | 查看各类来源和版本 |
| `banks` | 题库及参考答案数量 |
| `questions --bank xmu-2023 --query 抵免 --limit 5` | 筛题，不返回答案；也支持 `--subject`、`--kind` |
| `question <完整ID>` | 读题干和共同案情，不返回答案 |
| `answer-context <attempt_id>` | 作答保存后查匹配参考答案及展示顺序 |
| `question <完整ID> --reveal-answer` | 明确讲解模式直接读取答案 |
| `search "税收抵免法" --limit 5` | 默认检索教材、讲义、中英文对照 |
| `search "foreign tax credit" --book 刘剑文` | 指定书目；支持 `--role textbook/lecture/bilingual_notes/guide` |
| `read <block_id> --quote "逐字引文"` | 校验出处；旧引用查归档并标历史 |
| `record <JSON文件>` / `records --date YYYY-MM-DD` | 保存事件 / 读日期记录 |
| `review` / `review --all` | 到期 / 全部复测安排 |
| `mistakes` / `mistakes --due` | 无答案错题列表 / 到期题目 |
| `mistakes --status 待复习 --subject 中国税法学` | 按状态科目筛选 |
| `mistakes --details` / `mistakes --rebuild` | 含答案历史 / 重建Markdown视图；独立测试前不看详情 |
| `import-bank <JSON> [--apply]` | 预览 / 导入标准题库 |
| `import-markdown <MD> --bank-id mock-01 --name 练习集 --subject 中国税法学 [--apply]` | 约定布局题集导入 |
| `import-material <MD> --role lecture --title 名称 --id my-lecture [--apply]` | 预览 / 导入转换后的教材，保存原版本 |
| `mineru-check` / `convert <文件>` | 检查解析环境 / 新建转换任务；详见随包转换Skill |

完整题ID形如 `xmu-2023:q-...`，块ID形如 `b-...`，均从工具结果取得，不能猜。

## 作答与幂等重试

```json
{"kind":"attempt","request_id":"唯一请求ID","question_id":"查询得到的完整ID","answer":"使用者真实作答原文","hints_used":false,"answer_seen":false}
```

`answer_seen` 指本次作答前已经展示过本题答案或刚在同日看过答案，不指作答保存后正常讲解。相同请求重试用相同request_id；内容变化换新ID。

## V1.1反馈

先保存attempt，再调用answer-context和检索教材，建立要点后比较作答。示意占位符必须换为本地真实数据：

```json
{
  "kind":"feedback",
  "request_id":"反馈唯一ID",
  "target_id":"attempt返回的event.id",
  "reference_answer":{"origin":"bank"},
  "rubric":{"version":"本题要点-v1","items":[
    {"id":"本题稳定要点ID","description":"与题意相称的必要要点","importance":"core","evidence":[{"block_id":"真实块ID","quote":"原文逐字引文"}]}
  ]},
  "point_results":[
    {"point_id":"本题稳定要点ID","status":"partial","student_quote":"使用者原话中的真实片段","reason":"已涉及什么、还缺哪个必要条件","error_group":"同一错因可共用ID"}
  ],
  "feedback":"可选简短补充，不用此字段代替完整参考答案",
  "knowledge_points":["本题知识点"]
}
```

参考答案origin选择：

- `bank`：工具原样保存已有答案；不传改写text，不改来源状态。
- `bank_with_supplement`：已有答案另加 `supplement` 和 `evidence:[{block_id,quote}]`，原文不变。
- `textbook_generated`：仅无题库答案时，提供完整 `text` 和非空 `evidence`，标AI依据教材整理、非官方。
- `unavailable`：提供具体 `reason`，可选有依据的部分 `text`；整体待核实，不虚构完整答案。

importance为 `core` 或 `supplement`。point_results必须逐点对应，不多不少。status为 `covered/partial/missing/incorrect/uncertain`；missing的student_quote为null，其他确定项须逐字出现在原作答。除uncertain外，每个要点至少一条本地教材、讲义或明确标注的复习资料证据；重点清单和AI批注不能代替原文。引文匹配只证明出处，不能证明语义判断正确。

工具汇总assessment：核心待核实/答案不可得→unverified；核心错误、部分覆盖或遗漏→needs_work；核心全覆盖但使用提示/看过答案→hinted；其余→independent。通常省略assessment；显式传入时必须匹配。核心/补充归类不能根据作答结果临时改动，要点ID跨复测保持稳定；版本变化时保留旧版并复核对应。

可选 `next_review:"YYYY-MM-DD"` 覆盖1/3/7/14/30天起始规则；失败或提示后次日。`mistake_opt_out:true`仅在使用者明确要求本次不收录错题时使用。独立一次不等于稳定掌握。

成功返回 `rendered_feedback`，按判定→参考答案→对照分析→复习安排展示；自动生成错题视图。若有warning，说明原始日志保存结果与视图修复事项。失败不能假装已保存。

个人笔记：`{"kind":"note","text":"笔记内容"}`。更正反馈：`{"kind":"cancel","target_id":"原反馈ID","text":"更正原因"}`，再保存替代反馈。原文保留，错题与复测从有效事件重建。

## 题库与资料

题库样例见项目examples，字段见docs/question-banks.md。任意布局MD先按原题/原答案整理，不能补造残题。AI题必须附真实教材引文。题库导入不覆盖同ID；资料用稳定 `--id` 更新时归档旧版本，保留历史引用。全文导入前检查图片、页序和来源性质，转换不等于校勘完成。
