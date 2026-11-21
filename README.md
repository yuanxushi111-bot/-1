# 税法备考 Skill · V1.2

面向厦门大学税法学备考，以本地教材解释题目，把真实作答、教材出处和复测安排保存在日期命名的 Markdown 中。默认宿主为 **DeepSeek Harness**；没有另做学习网页，不直接管理模型 API Key。

V1.2新增每日学习、严明讲义背诵卡和根据当日已背内容出自测题。先看 [V1.2 使用教程](docs/v1.2-guide.md)；原有练题、错题本和MinerU操作详见 [基础教程](docs/user-guide.md)。

也可查看 [图文教程](docs/user-guide-illustrated.md) 或 [可单独发送的浏览器图文版](docs/user-guide-illustrated.html)。

本版设计与实施范围见 [V1.2：每日学习、讲义重点背诵与自测](docs/v1.2-plan.md)。

## GitHub下载

本仓库按维护者要求包含完整知识库：`library/`中的教材、讲义、题库、图片、背诵卡及历史资料，以及`indexes/`中的检索索引。个人学习记录和模型密钥保存在使用者电脑，不上传。

**Windows使用者请打开 [V1.2完整部署下载页](https://github.com/yuanxushi111-bot/-1/releases/tag/v1.2.0)**。大附件上传不稳定时，发行页使用分段附件和`download-complete-v1.2.0.cmd`下载器：只需下载并双击下载器，它会自动下载、逐段校验、合成为原始完整ZIP，其中包含知识库、Python和MinerU依赖。详细步骤见[GitHub部署与维护说明](docs/github-deployment.md)。文件名中的`private`沿用早期完整资料包命名，在此公开仓库中不表示下载权限受限。

GitHub的Code ZIP和`git clone`包含代码与知识库，未附Windows运行环境；`public-source.zip`另为不含教材的源码包。直接给朋友部署时选择上述完整包。

## 给朋友使用

1. 使用 `windows-x64-private.zip`，解压到自己有写入权限的独立目录，不要放进别的 Git 仓库，也不要覆盖旧学习目录。
2. 安装并打开 [DeepSeek Harness 官方桌面版](https://www.deepseek.com/harness/)，在宿主中配置自己的模型连接。本包不包含 Harness 安装程序或模型密钥；**工具的 Python 运行环境已包含在 Windows 私人包中**。
3. 双击 `检查安装.cmd`，确认 `ready: true`。
4. 在 Harness 中选择解压后的项目根目录为工作区。在新会话输入 `/tax-exam-coach`，然后说：

   > 今天有30分钟，按严明讲义安排学习和背诵，背完后根据今天实际背过的内容出两道自测题，一次一题，答完再给答案和分析。

宿主支持目录 `.dsh/skills/tax-exam-coach`；发布包已生成该目录。若没有出现 Skill，核查工作区是否选中了整个项目、宿主是否启用了 filesystem skill provider、是否位于别的 `.git` 目录之下。详见 [宿主接入](docs/deepseekharness.md)。

## V1.2 包含什么

- 当天时间动态排任务；支持缩短剩余时间、保留已完成内容、继续旧题及预算外顺延。计划、自测任务和真实学习日志均为本地日期Markdown。
- 私人包随附8张可追溯的严明讲义起步卡，分中国税法/国际税法各4张，含完整正文、记忆骨架、抽查问题和来源；可通过card-save继续扩充，**未宣称446页全部完成拆卡**。
- 根据今日实际背过的卡片生成回忆题，或由宿主模型拟判断说理、比较、应用等有依据的小题再导入。题目、答案、要点和版本在作答前固定，题干视图隐藏答案。
- 同日看正文后练习不计跨日独立通过；按整卡核心点覆盖和不同日期的独立抽查恢复巩固状态，关键错误继续进入错题本。

- 中文/英文关键词与术语别名检索；教材原文引用含文件、行号、PDF页序、块 ID 和资料版本。
- 作答后按“简短判定 → 完整参考答案 → 要点对照分析 → 复习安排”反馈：有题库答案先展示原文，没有则依据已核对教材拟答并标为非官方。
- 以核心/补充要点和五种覆盖状态判定，保存实际作答引文、理由、出处及清单版本，不把可选扩展未写算作核心遗漏。
- 私人包更新为21份Markdown、150张图片、1份来源PDF；包含四本教材、严明法学讲义、两份中英文对照、2023—2026真题、2023/2024截图参考答案及重点清单/批注。默认检索教材、讲义和对照资料，批注不重复作为原文证据。
- 保留共同案情和题附条文；缺失信息标记待核实，测试默认排除残题；2025/2026没有配套参考答案，不错配旧答案。
- 导入 JSON 或约定格式的 Markdown 题库，区分真题、教材习题、模拟题、自建题与 AI 自拟题。
- 保存使用者原话、提示使用情况、有教材引文的 AI 反馈、个人笔记及次日/跨日复测任务。
- 同日记录追加到 `userdata/study-records/YYYY-MM-DD.md`，保留手工笔记和历史作答；没有聊天历史也可从这些文件重建到期任务。
- 自动生成 `userdata/mistake-book/YYYY-MM-DD.md` 与 `错题索引.md`；相同题聚合、保留错因、待核实单列，至少两次不同日期的无提示复测覆盖原错点后标记已巩固。
- 随包提供 `mineru-documents` Skill、MinerU 4.1.7 独立依赖和转换/导入工具；新资料可继续补充。OCR模型需按设备另行准备，默认不远程上传，见 [MinerU使用说明](docs/mineru.md)。
- 公开源码包和私人完整包分别打包，排除真实个人记录和本机配置。

## 开发者快速开始

Python 3.11+，核心工具无第三方依赖。无需提供模型密钥就能运行测试与自制演示：

```powershell
python -m unittest discover -s tests -v
python scripts/prepare_host.py
python scripts/build_library.py --demo
python tax_exam.py import-bank examples/demo-bank.json --apply
python tax_exam.py doctor
python tax_exam.py search "借阅额度"
```

演示教材与题目是自制的软件样本，不是法律或考试资料。`--demo` 用于独立开发副本，会重建该副本的资料清单；不要用它替换正在使用的真实资料库。

导入自己的转换资料（支持当前“教材 / 真题和答案 / 重点”目录以及旧的平铺目录）：

```powershell
python scripts/build_library.py --source "D:\我的转换资料"
python tax_exam.py banks
python tax_exam.py search "税收抵免法" --book 廖益新
```

首次复制后检索与阅读已有资料无需联网。讲解依赖宿主所配置的模型；使用云端模型时会发送必要题目、作答和教材片段。资料转换与学习模型连接分别配置，解析不自动切换远程。

## 维护与打包

```powershell
python -m unittest discover -s tests -v
python scripts/package_release.py
# 在 Windows x64 的 CPython 环境执行，工具运行环境不含 site-packages：
python scripts/bundle_runtime.py
# 由已验证的Windows Python 3.14环境冻结第三方依赖，或按docs/mineru.md准备：
python scripts/bundle_mineru.py --site-packages "D:\isolated-mineru\Lib\site-packages"
python scripts/package_release.py --private
python scripts/smoke_release.py
```

产物在 `dist/`，含文件清单和 SHA-256。公开源码包只含代码、Skill、文档和自制样本；私人包额外含清单选定的当前/历史资料、索引、CPython与MinerU依赖。第三方许可证随依赖保留。不会把整个目录、真实 `userdata`、个人MinerU缓存、`.git` 或 API Key 压进去。

升级到新目录后复制旧版 `userdata`，运行 `tools.cmd doctor`、`tools.cmd review --all` 和 `tools.cmd mistakes --rebuild`。V1.0/V1.1日志继续可读；新背诵卡和新增教材需一并保留、核对后导入，不只搬userdata。详见 [V1.2升级说明](docs/upgrade-v1.2.md)。

## 当前验证边界

本地工具可以独立测试。DeepSeek Harness 的接入依据其官方项目 Skill 发现规范；真实宿主中的模型讲解、工具权限和完整教学体验需在安装宿主并配置模型后联调，不能以本地测试通过代替。具体已执行检查见 [验证记录](docs/verification.md)。

V1.2不提供官方评分、法规自动更新、全量教材校勘或已校准的掌握概率。教材与历史参考答案可能存在OCR、版本和观点差异，反馈应显示依据与待核实处；本地检查不等于真实宿主模型教学质量已验证。

[题库格式](docs/question-banks.md) · [学习记录](docs/records.md) · [架构](docs/architecture.md) · [贡献指南](CONTRIBUTING.md)

代码以 MIT 许可提供；知识库和完整包中的教材、题目与截图保留各自权利，不因随库交付而适用项目代码许可。早期设计文档中的“资料不进入公开仓库”描述原有分发方式，本仓库自2026-11-21按维护者要求同时发布资料，当前分发约定见GitHub部署说明。
