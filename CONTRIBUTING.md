# 维护与贡献

核心工具仅依赖 Python 标准库。优先修正具体行为，避免把所有逻辑塞进 SKILL.md 或按模型品牌复制一套工具。

- `skills/`：教学决策与工具路由；`src/tax_exam/`：确定性工具；`scripts/prepare_host.py`：宿主目录适配。
- 新增题库来源遵循 `schemas` 与 `docs/question-banks.md`；新宿主优先复用现有 CLI JSON 契约。
- 修改记录格式必须保留历史版本的读取能力，先备份；不得让缓存成为个人学习记录的唯一来源。
- 运行 `python -m unittest discover -s tests -v`；修复实际缺陷时补能复现该行为的小样本。需要检索数据时使用自制文本。
- 发布前运行 `scripts/check_project.py` 和 `scripts/package_release.py`，检查文件清单；完整Windows包另外使用`--private`，并执行发行包验收。
- 本仓库包含`library/`和`indexes/`。资料更新须同步清单、索引与来源哈希；导入正文必须保持原始字节，遵守`.gitattributes`。保留历史资料和卡片版本，以便旧作答继续定位出处。
- 不提交`userdata/`、运行环境、密钥、本机配置和临时测试目录。Windows运行环境与MinerU依赖通过Release完整包分发，不逐文件提交Git。
- 在 `CHANGELOG.md` 描述对使用者可见的变更；公开打包不触发远程发布。

GitHub上传、下载与维护流程见[部署说明](docs/github-deployment.md)。
