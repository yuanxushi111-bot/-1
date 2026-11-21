# 从V1.0升级

1. 关闭旧项目会话，复制整个旧目录作为备份；不要在旧版原位置覆盖解压。
2. 把V1.1私人包解压到新的独立目录，双击检查安装.cmd，应显示version=1.1.0、ready=true。
3. 将旧版userdata复制到新版根目录。这里包含每日MD、额外题库、个人笔记和备份；不要覆盖新版library、indexes、runtime、runtime-mineru、skills和.dsh。
4. 在新版运行 `tools.cmd review --all`、`tools.cmd mistakes --rebuild`。检查日期记录、额外题库和错题是否对应。原始V1.0反馈仍然可读，未保存的答案或错因只显示缺失，不由模型补写历史。
5. 在DeepSeek Harness切换到新版项目根目录，开启新会话并加载 `/tax-exam-coach`，避免沿用旧Skill上下文。说“检查V1.1，并从到期错题开始，先让我独立回答”。

V1.1私人包保留V1.0教材与索引归档，旧块引用可定位历史版本。题库ID与当前四年真题版本保持不变。新反馈需使用要点清单格式，旧请求JSON不可直接当新反馈提交。

MinerU个人配置不随包复制。首次准备OCR模型见mineru.md；已有资料复习不需要下载OCR模型。升级回退时保留新产生的userdata备份，勿用旧版重新写入不了解的新反馈字段。
