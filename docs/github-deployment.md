# GitHub部署与维护

仓库：https://github.com/yuanxushi111-bot/-1

自2026-11-21起，按维护者要求，该公开仓库同时包含代码和知识库。早期V1.0—V1.2设计文档中不公开资料的约定属于历史分发方案。本页说明当前方式；功能版本仍为V1.2.0。

## 下载给Windows朋友使用

1. 打开[V1.2发行页](https://github.com/yuanxushi111-bot/-1/releases/tag/v1.2.0)。
2. 下载`tax-exam-skill-1.2.0-windows-x64-private.zip`，这是包含资料和运行环境的完整包；名称沿用旧版本，不代表私有下载。
3. 解压到有写入权限的新目录，双击`检查安装.cmd`。
4. 在DeepSeek Harness中选择整个项目根目录，配置自己的模型连接，并在新会话调用`/tax-exam-coach`。
5. 从[每日背诵与自测教程](v1.2-guide.md)开始；从旧版本迁移先看[升级说明](upgrade-v1.2.md)。

随包MinerU依赖可用，但大型OCR模型不在包内，须按[转换说明](mineru.md)明确准备。Python运行环境只面向Windows x64；宿主程序和模型密钥不随包提供。

## 仓库与Release的内容

| 位置 | 内容 |
| --- | --- |
| `src/`、`skills/`、`scripts/`、`tests/` | 核心工具、两个Skill、维护脚本和行为测试 |
| `docs/`、`config/`、`schemas/`、`examples/` | 教程、配置、接口约定和自制样例 |
| `library/sources/`、`library/manifest.json` | 已导入的教材、讲义、真题、参考答案、图片和来源清单 |
| `library/recitation-cards/`及其清单 | 8张当前起步背诵卡与历史版本 |
| `library/history/` | 资料版本归档及对应索引，保留旧记录引用能力 |
| `indexes/materials.sqlite` | 当前可直接使用的检索索引 |
| Release完整ZIP | 上述项目、资料和索引，加上Windows Python、MinerU独立依赖及生成的宿主Skill目录 |
| Release源码ZIP | 代码、Skill、文档和自制样例，沿用不包含知识库的源码分发格式 |

完整资料包不会包含真实学习记录、个人笔记、模型密钥、本机配置、个人MinerU缓存或OCR模型。朋友新生成的学习记录仍写入自己电脑的`userdata/`日期Markdown，不自动同步GitHub。

## 开发与更新

```powershell
git clone https://github.com/yuanxushi111-bot/-1.git tax-exam-skill
cd tax-exam-skill
python scripts/check_project.py
python scripts/prepare_host.py
python tax_exam.py doctor
```

源码使用Python 3.11+，核心工具无第三方依赖。`git clone`和GitHub的Code ZIP带知识库，但没有`runtime/`、`runtime-mineru/`；要直接使用包内Windows工具，请用Release完整包。开发机器若要重建完整包，须先按README准备两套运行环境。

资料经导入工具更新后，再同步提交清单、正文、索引与历史归档。不要手改原文、忽略哈希失败或用演示库覆盖真实库；`.gitattributes`保证资料不被Git换行转换，避免引用校验失效。私人学习日志始终排除在提交之外。

发布更新前，先运行仓库检查，再生成源码包和完整包；在新的中文空格目录执行`scripts/smoke_release.py`。通过后将ZIP、文件清单与SHA-256文件作为同一版本的Release附件上传，避免用户逐文件安装运行环境。每个版本使用独立标签，保留旧版下载。

## 验证与许可

V1.2本地已验证70项行为测试和37项Windows发行包检查，细节见[验证记录](verification.md)。真实Harness模型教学对话、扫描PDF复杂OCR及学习效果仍需实际验证。

项目代码和自制样例采用MIT许可；教材、讲义、题库、截图和第三方运行组件保留各自许可及权利，详见根目录LICENSE和随依赖保留的许可证。
