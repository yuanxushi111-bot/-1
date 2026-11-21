# MinerU资料转换

私人Windows x64包包含MinerU 4.1.7、第三方依赖、转换适配器和 `/mineru-documents` Skill。与核心CPython运行环境分开，不依赖朋友电脑预装Python。每个依赖原有许可证保留在dist-info，清单见runtime-mineru/third-party-manifest.json；不适用项目MIT许可证。

**不包含大型OCR模型、个人解析配置或远程账号。** Word/Excel等本地flash解析与PDF/图片OCR所需资源不同，首次OCR需按设备准备模型或由用户选择远程服务。已有知识库的检索、记录和错题本可直接运行。

## 检查和转换

在项目根目录用PowerShell：

```powershell
& '.\tools.cmd' mineru-check
& '.\tools.cmd' convert 'D:\资料\新讲义.pdf'
# 等待中的任务：
& '.\tools.cmd' convert --resume task-工具返回的ID
```

默认不上传资料，不传--remote；普通转换只使用本地已备模型，不自动下载，解析错误不会自动切远程或降低质量。即使flash档也可能需要识别资源，缺少时先运行明确的模型准备步骤。任务ID、原件副本、进度、转换MD和图片在userdata/import-tasks，可恢复。源文件不修改，转换结果不自动进入答案库。

转换成功后检查页序、开头/中间/末尾、表格公式和图片；导入预览：

```powershell
& '.\tools.cmd' import-material '任务目录\converted.md' --role lecture --title '新讲义' --id new-lecture
# 检查预览后执行同一命令加 --apply
& '.\tools.cmd' doctor
```

复用--id可更新资料并归档旧版。题集先整理成examples约定格式，用import-bank/import-markdown导入，不能直接从OCR文本推断官方答案。

## 首次准备PDF/图片OCR

基础包只含CLI依赖。使用者明确选择本地basic模型后，执行以下命令会联网下载并校验模型，并更改项目独立MinerU配置；模型资源位于userdata/mineru管理的资源路径，不随公开源码包分发：

```powershell
& '.\runtime\python.exe' scripts/prepare_mineru.py --models basic --enable-local
```

standard需要更多资源，由使用者按设备选择，不自动降档。运行前可不加参数查看计划。模型下载/引擎兼容性以实际设备检查为准，失败保留明确错误，不能宣称OCR已准备好。若选择远程解析，需先配置个人解析服务，再在明确同意上传该文档后传 `convert <文件> --remote`；账号和API Key不写进仓库或发行包。

公开源码包不带大体积依赖，可双击准备MinerU.cmd，或用 `python scripts/prepare_mineru.py --install` 联网安装到项目runtime-mineru；不会升级系统已有MinerU。打包开发者可通过bundle_mineru.py冻结已验证的Windows x64/CPython 3.14依赖环境。

本项目不会运行MinerU的网页界面。CLI内部本地服务属于解析组件，个人服务状态与诊断信息不对外发布。

本地服务限定127.0.0.1并由系统分配独立端口，防止多个解压副本与原有安装互相占用。项目不继承本机其他MINERU环境配置，解析账号在本项目userdata/mineru单独配置。Windows源码准备推荐CPython 3.14，与锁定依赖和私人包保持一致；核心工具本身仍支持Python 3.11+。
