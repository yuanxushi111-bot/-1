# DeepSeek Harness 接入

核对日期：2026-11-10。参考官方 `master` 文档；其根 package.json 当时标识为 `0.2.2-rc.1`。该信息是文档快照，不是本机已安装版本或联调认证。

## 使用路径

运行 `python scripts/prepare_host.py` 生成 `.dsh/skills/tax-exam-coach`。私人包已包含生成结果。Harness 在所选项目根目录发现此目录后，可通过 `/tax-exam-coach` 加载；日常命令由宿主的命令执行工具运行 `tools.cmd`。

安装官方桌面版、配置模型、选择整个项目为工作区。创建新会话，输入 `/tax-exam-coach` 后要求运行 doctor，然后选择一道题开始。Windows 工具包内的 CPython 不替代 Harness 的安装环境。

官方 npm 启动方式是 `npx @deepseek-ai/dsh web`，它打开的是 Harness 自身界面。本项目不自动执行该下载命令，也不以其替代用户选择的桌面宿主。用户自行选择该方式时，Node 版本等依赖以所安装 Harness 版本要求为准。

## 工作区与权限

官方 filesystem provider 按最近的 `.git` 祖先定位项目；没有该标记时使用工作目录。开发仓库有自己的 `.git`，分发包需解压到独立目录并选中该目录。不要把多个朋友的资料放进同一个父 Git 仓库后假定能自动发现子目录 Skill。

该 Skill 不修改全局模型配置、不复制 API Key、不改变宿主审批策略。首次执行文件读取和命令时，按宿主实际权限提示操作。Skill 的目录约束是工作约定，不宣称构成宿主级文件访问沙箱。

## 官方依据

- [Skill filesystem provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md)：项目目录、格式、发现优先级和 `/name` 入口的相关能力。
- [Skill capability family](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/README.md)：目录发现、catalog 与 tool-skill 的职责。
- [用户工作区与模型配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/index.md)：选择工作区、在宿主配置模型。
- [官方入口](https://www.deepseek.com/harness/) 与 [CLI](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md)。

V1 已做的本地检查与尚未完成的宿主模型联调，分别记录在 `verification.md`。
