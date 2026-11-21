# 题库导入

题库 ID、题目 ID 使用小写字母、数字、短横线或下划线；题目完整 ID 是 `bank-id:question-id`。来源 `source_type` 为 `past_exam`、`textbook`、`mock`、`custom` 或 `ai_generated`。未知年份、分值不补造。

## 标准 JSON

见 `examples/demo-bank.json` 与 `schemas/question-bank.schema.json`。必要字段为 `schema_version:1`、`id`、`name`、字符串 `version`、`source_type`、非空 `questions`。

每题包含 `id`、`subject`、`kind`、`stem`，可带 `context`、`knowledge_points`、`completeness` 和 `answer`。题型支持名词解释、简答、论述、案例、计算、选择、其他。`answer` 为 null 或含 text/status 的对象；非官方来源不可填官方性声明。

AI 自拟题额外要求 `evidence:[{block_id,quote}]`，不允许考试年份，导入时核对原文引文。证据存在不等于拟题正确。

先 `import-bank path.json` 预览，再加 `--apply` 写入。精确相同题干与案情会提示重复；近似题和不同答案不会自动合并。V1 拒绝覆盖已有 bank ID，更新请使用新的 ID 并保留旧版本。

## 约定 Markdown

```markdown
# 练习题

## q1 | 简答

完整题干，保留原文。

### 共同案情

可选的完整案情。

### 参考答案

可选的原资料答案；没有就省略该小节。
```

命令：

```powershell
python tax_exam.py import-markdown "练习题.md" --bank-id mock-01 --name "模拟练习" --subject 中国税法学 --source-type mock
# 核对预览后，原命令加 --apply
```

不符合该结构的文档需先人工或由 Agent 忠实整理。该操作不负责 OCR，不猜缺失内容。AI 自拟题使用 JSON 格式，以保留证据链。

## 当前内置资料策略

2023/2024采用 `### 第N题` 布局；2025/2026采用科目、题型与编号列表布局。案例共同案情与题附条文一起保留，条文编号不能当成题号。2025/2026没有配套参考答案，不从备份目录配对答案。2024中国税法案例中的缺失信息按残题标记。

截图转录及考生回忆版保持来源提示，不宣称校方官方答案或完整试卷。
