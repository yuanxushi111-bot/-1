"""Build an offline illustrated manual; optional PNG rendering uses resvg-py."""
from pathlib import Path
from html import escape
import argparse
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets/guide-v1.1"
INK, MUTED, GREEN = "#193C35", "#546B63", "#1D705A"
PAPER, LINE, SOFT = "#F4F7F2", "#D8E2DA", "#E5F1E9"


class Drawing:
    def __init__(self, number, title, subtitle, height):
        self.number, self.height = number, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title-{number} desc-{number}">',
                      f'<title id="title-{number}">{escape(title)}</title><desc id="desc-{number}">{escape(subtitle)}；操作示意，不是真实软件截图。</desc>',
                      f'<defs><marker id="arrow-{number}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{GREEN}"/></marker></defs>']
        self.rect(0, 0, 1200, height, PAPER, radius=0)
        self.text(50, 59, title, 36, weight=700)
        self.text(50, 101, subtitle, 21, MUTED)

    def rect(self, x, y, w, h, fill="white", stroke=None, radius=18):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"' + (f' stroke="{stroke}" stroke-width="1.5"' if stroke else "") + '/>')

    def text(self, x, y, value, size=22, color=INK, weight=400, anchor="start"):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}">{escape(value)}</text>')

    def lines(self, x, y, lines, size=22, gap=35, color=INK):
        for i, value in enumerate(lines):
            self.text(x, y + gap * i, value, size, color)

    def arrow(self, x1, y1, x2, y2):
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GREEN}" stroke-width="2.5" marker-end="url(#arrow-{self.number})"/>')

    def step(self, x, y, number, title):
        self.parts.append(f'<circle cx="{x+20}" cy="{y-9}" r="20" fill="{GREEN}"/>')
        self.text(x + 20, y - 1, str(number), 23, "white", 700, "middle")
        self.text(x + 54, y, title, 26, weight=700)

    def finish(self):
        self.text(50, self.height - 22, "V1.1 使用教程 · 操作示意，非真实软件截图", 17, MUTED)
        self.text(1150, self.height - 22, f"0{self.number} / 04", 18, MUTED, anchor="end")
        self.parts.append('</svg>')
        result = "\n".join(self.parts)
        ET.fromstring(result)
        return result


def start():
    d = Drawing(1, "第一次使用：完成这四步", "Windows私人完整包 + DeepSeek Harness；找到含 tools.cmd 的项目根目录。", 800)
    for x, y in [(50, 130), (615, 130), (50, 410), (615, 410)]:
        d.rect(x, y, 535, 250, stroke=LINE)
    d.step(75, 175, 1, "解压到独立目录")
    d.text(85, 219, "D:\\kaoyan-agent", 25, GREEN, 700)
    d.lines(105, 260, ["检查安装.cmd", "tools.cmd", "library / runtime / .dsh"], 22, 34)
    d.step(640, 175, 2, "双击“检查安装.cmd”")
    d.rect(645, 202, 475, 115, INK, radius=12)
    d.text(672, 246, '"version": "1.1.0"', 25, "#F3F8F4")
    d.text(672, 285, '"ready": true', 25, "#A8E8BD", 700)
    d.text(645, 351, "ready仅表示本地资料和工具检查通过", 20, MUTED)
    d.step(75, 455, 3, "在Harness选择项目")
    d.rect(85, 482, 465, 64, SOFT, radius=10)
    d.text(107, 524, "工作区：D:\\kaoyan-agent", 23, GREEN)
    d.lines(85, 588, ["选中含 tools.cmd 的那一层。", "在宿主里配置自己的模型连接。"], 22, 37)
    d.step(640, 455, 4, "新会话加载Skill")
    d.rect(645, 482, 475, 64, SOFT, radius=10)
    d.text(668, 524, "/tax-exam-coach", 27, GREEN, 700)
    d.lines(645, 588, ["再告诉它：今天有多久，想练什么。", "一次只出一题，先让我独立回答。"], 22, 37)
    d.rect(50, 699, 1100, 52, SOFT, radius=12)
    d.text(74, 733, "复习现有资料：不用先下载OCR模型；私人包已带工具运行环境。", 23, GREEN)
    return d.finish()


def practice():
    d = Drawing(2, "每天练题：你先答，它再讲", "题目先隐藏答案；作答后，同一轮完成参考答案与分析。", 1000)
    d.rect(50, 135, 470, 525, stroke=LINE)
    d.rect(550, 135, 600, 525, stroke=LINE)
    d.text(78, 181, "你只需做两件事", 27, weight=700)
    d.rect(75, 212, 420, 115, SOFT, radius=14)
    d.lines(96, 247, ["今天有20分钟，先练一道到期错题。", "先不要展示答案。"], 21, 35)
    d.text(79, 372, "Skill先出题，等待你回答。", 23, MUTED)
    d.rect(75, 414, 420, 160, SOFT, radius=14)
    d.text(96, 456, "我的回答是：……", 25, GREEN, 700)
    d.lines(96, 498, ["这里提交你的真实作答。", "用过提示或看过答案，也要说明。"], 21, 35)
    d.text(78, 624, "答后自动保存到日期Markdown", 22, MUTED)
    d.text(580, 181, "答完后，按这个顺序看", 27, weight=700)
    rows = [("判定", "一句话说明本次作答情况。"),
            ("完整参考答案", "有题库答案就给原文；没有则依据教材拟答。"),
            ("要点对照分析", "覆盖 / 部分覆盖 / 遗漏 / 错误 / 待核实"),
            ("复习安排", "说明原错点、下次日期与实际保存结果。")]
    for i, (title, detail) in enumerate(rows):
        y = 207 + i * 107
        d.rect(575, y, 550, 91, SOFT if i == 1 else PAPER, radius=12)
        d.text(596, y + 33, f"{i+1:02}   {title}", 25, GREEN, 700)
        d.text(596, y + 67, detail, 20, MUTED)
    for x, title, lines in [
        (50, "题库有答案", ["直接展示原文与来源性质。", "参考答案不自动升级为官方标准。"]),
        (425, "题库没有答案", ["核对本地教材，再整理完整拟答。", "标注：AI依据教材整理，非官方。"]),
        (800, "资料证据不足", ["明确指出缺口，保留待核实。", "不强行编答案或确定判分。"]),
    ]:
        d.rect(x, 708, 350, 167, stroke=LINE)
        d.text(x + 24, 751, title, 26, weight=700)
        d.lines(x + 24, 799, lines, 19, 34, MUTED)
    d.text(50, 929, "只想要提示？明确说：先给一个小提示，暂不展示完整答案。", 23, GREEN)
    return d.finish()


def mistakes():
    d = Drawing(3, "错题自动收录，跨日再验证", "同题聚合保存经历；当天看答案后重答，不算跨日掌握。", 820)
    for x, title, lines, fill in [
        (50, "待复习", ["重要错误、核心遗漏", "或依赖提示时自动收录"], "white"),
        (440, "复测中", ["一次跨日、无提示通过", "仍需覆盖原先的错点"], SOFT),
        (830, "已巩固", ["两个不同日期独立通过", "原错点覆盖，历史继续保留"], SOFT),
    ]:
        d.rect(x, 158, 320, 160, fill, LINE)
        d.text(x + 28, 204, title, 30, GREEN, 700)
        d.lines(x + 28, 252, lines, 22, 35, MUTED)
    d.arrow(382, 238, 428, 238)
    d.arrow(772, 238, 818, 238)
    d.parts.append(f'<path d="M 990 331 V 377 H 210 V 331" fill="none" stroke="{GREEN}" stroke-width="2.5" marker-end="url(#arrow-3)"/>')
    d.text(600, 417, "再次答错或依赖提示 → 回到待复习", 23, GREEN, anchor="middle")
    d.rect(50, 451, 1100, 69, "#F8F0DF", radius=12)
    d.text(74, 494, "待核实", 26, "#7B5927", 700)
    d.text(221, 493, "来源冲突、题目不完整或证据不足：保留问题，不计为确认错误。", 22, "#7B5927")
    for x, title, first, second, detail in [
        (50, "原始学习记录", "userdata/study-records/", "YYYY-MM-DD.md", "真实作答、答案与复测事件"),
        (615, "自动错题本", "userdata/mistake-book/", "YYYY-MM-DD.md + 错题索引.md", "可从学习日志重建的错题视图"),
    ]:
        d.rect(x, 552, 535, 178, stroke=LINE)
        d.text(x + 26, 592, title, 26, weight=700)
        d.lines(x + 26, 635, [first, second], 22, 33, GREEN)
        d.text(x + 26, 705, detail, 21, MUTED)
    d.text(50, 764, "个人笔记写学习日志；不要直接改自动生成的错题页或结构化JSON。", 21, MUTED)
    return d.finish()


def materials():
    d = Drawing(4, "有新资料时，再走这条路线", "新教材、讲义和题集，都能继续补充；转换完成后，还需要导入。", 870)
    for x in (50, 450, 850):
        d.rect(x, 148, 300, 262, stroke=LINE)
    d.text(76, 194, "01  准备资料", 26, GREEN, 700)
    d.lines(76, 242, ["Markdown / TXT", "直接读取，无需OCR"], 22, 35)
    d.lines(76, 331, ["PDF / 图片 / Office", "先转换，保留图片附件"], 21, 35)
    d.arrow(366, 279, 433, 279)
    d.text(476, 194, "02  转换与检查", 26, GREEN, 700)
    d.text(473, 251, "/mineru-documents", 24, GREEN, 700)
    d.lines(476, 305, ["给出真实文件路径。", "核对全文页序、图片、", "表格和公式。"], 22, 35)
    d.arrow(766, 279, 833, 279)
    d.text(876, 194, "03  预览，再导入", 26, GREEN, 700)
    d.lines(876, 251, ["教材 / 讲义 → 知识库", "习题 / 答案 → 规范题库"], 21, 44)
    d.lines(876, 352, ["试检索一次，", "确认新资料可以被引用。"], 21, 34)
    d.rect(50, 454, 1100, 98, "#F8F0DF", radius=14)
    d.text(75, 492, "缺模型？先准备，再继续。", 26, "#7B5927", 700)
    d.text(75, 530, "包内含MinerU依赖；OCR模型需另行准备，普通转换不会自动下载或上传。", 23, "#7B5927")
    d.rect(50, 591, 1100, 164, SOFT, radius=16)
    d.text(75, 631, "可直接复制给Agent", 25, GREEN, 700)
    d.lines(75, 676, ["请把 D:\\资料\\新讲义.pdf 转为Markdown，检查页序和图片；", "预览后作为讲义加入知识库。只用本地解析，缺模型先告诉我。"], 23, 38)
    d.text(50, 810, "只生成Markdown ≠ 已入库；导入成功后，新资料才能用于检索、讲题和拟答。", 23, MUTED)
    return d.finish()


PAGES = [
    ("01-start", "第一次启动", start,
     "解压私人完整包，检查ready，选择整个项目，加载 /tax-exam-coach。",
     "今天有20分钟，请先检查本地资料和到期任务，一次只出一题，先让我独立回答。"),
    ("02-practice", "日常练题", practice,
     "提交真实作答后，依次查看判定、完整参考答案、逐点分析和复习安排。",
     "答完后请直接给完整参考答案，再逐点分析，最后说明复测日期和实际保存位置。"),
    ("03-mistakes", "错题与记录", mistakes,
     "关键错误和提示依赖自动收录；两次不同日期独立通过、覆盖原错点后标记已巩固。",
     "今天先练到期错题，只给题干，不展示我的旧答案和解析，答完再对照原错点分析。"),
    ("04-materials", "新资料导入", materials,
     "Markdown直接读取，其他支持格式使用MinerU转换；检查与预览之后，再导入对应资料库。",
     "请把 D:\\资料\\新讲义.pdf 转为Markdown，检查页序和图片；预览后作为讲义加入知识库。只用本地解析，缺模型先告诉我。"),
]


def build(png=False):
    ASSETS.mkdir(parents=True, exist_ok=True)
    articles, md = [], ["# V1.1 图文使用教程", "", "以下均为操作示意图，非真实软件截图。按启动、练题、错题复测、补充资料的顺序阅读。", ""]
    for name, title, draw, detail, prompt in PAGES:
        svg = draw()
        (ASSETS / (name + ".svg")).write_text(svg, encoding="utf-8")
        if png:
            import resvg_py
            font_root = Path("C:/Windows/Fonts")
            fonts = [str(font_root / name) for name in ("msyh.ttc", "msyhbd.ttc") if (font_root / name).exists()]
            (ASSETS / (name + ".png")).write_bytes(resvg_py.svg_to_bytes(svg_string=svg, font_files=fonts, font_family="Microsoft YaHei", width=1600))
        articles.append(f'<section id="{name}" aria-label="{title}"><figure>{svg}<figcaption>{escape(detail)}</figcaption></figure><div class="prompt"><span>直接这样说</span><p>{escape(prompt)}</p></div></section>')
        md += [f"## {title}", "", f"![{title}操作示意](assets/guide-v1.1/{name}.png)", "", detail, "", "> " + prompt, ""]
    nav = "".join(f'<a href="#{name}">{i+1:02} {title}</a>' for i, (name, title, *_rest) in enumerate(PAGES))
    html = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V1.1 图文使用教程</title>
<style>
:root{color-scheme:light;--ink:#193c35;--muted:#546b63;--paper:#f4f7f2;--line:#d8e2da;--green:#1d705a}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.8 "Microsoft YaHei","PingFang SC",sans-serif}
main{max-width:1200px;margin:auto;padding:38px 24px 55px}header{padding:10px 26px 22px}.eyebrow{font-size:14px;letter-spacing:.12em;color:var(--green)}h1{font-size:36px;line-height:1.3;margin:10px 0 14px}header p{margin:0;color:var(--muted)}nav{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0 0}a{color:var(--green)}nav a{padding:8px 16px;background:white;border:1px solid var(--line);border-radius:30px;text-decoration:none}
section{scroll-margin-top:20px;margin:0 0 30px}figure{margin:0}figure svg{display:block;width:100%;height:auto}figcaption{padding:0 26px 15px;color:var(--muted)}.prompt{margin:0 26px;padding:16px 20px;background:white;border-left:4px solid var(--green);border-radius:0 12px 12px 0}.prompt span{font-size:14px;font-weight:700;color:var(--green)}.prompt p{margin:5px 0 0;overflow-wrap:anywhere}aside{margin:30px 26px;padding:20px 24px;background:white;border:1px solid var(--line);border-radius:16px}aside h2{margin:0 0 8px;font-size:23px}aside p{margin:7px 0}code{font-size:.93em;overflow-wrap:anywhere}footer{margin:0 26px;color:var(--muted);font-size:14px}
@media(max-width:600px){main{padding:20px 8px}header{padding:8px 14px 18px}h1{font-size:28px}.prompt,aside,footer{margin-left:14px;margin-right:14px}figcaption{padding-left:14px;padding-right:14px}nav a{font-size:14px}}
@media print{body{background:white}main{max-width:none;padding:0}header{padding:0 0 12px}nav{display:none}section{break-inside:avoid;margin:0 0 20px}svg{max-height:220mm}aside{break-inside:avoid}.prompt{background:white}a{text-decoration:none;color:inherit}}
</style></head><body><main><header><div class="eyebrow">税法备考 SKILL · WINDOWS · V1.1</div><h1>从第一次启动，到每天复习</h1><p>四张操作示意图，跟着顺序使用。这里是使用指南，学习对话仍在DeepSeek Harness中进行。</p><nav aria-label="教程章节">''' + nav + '''</nav></header>''' + "\n".join(articles) + '''
<aside><h2>第一次遇到问题时</h2><p><strong>找不到Skill：</strong>核对工作区是不是含 <code>tools.cmd</code> 的项目根目录，再开新会话加载。</p><p><strong>缺少OCR模型：</strong>复习已有资料不受影响；转换新资料前，再按设备准备模型。不要把依赖安装等同于模型就绪。</p><p><strong>记录怎样带走：</strong>日常备份 <code>userdata</code>。自己导入过新教材时，迁移整个项目更省事。升级到新包需另行保留并导入新增教材。</p><p><strong>个人笔记：</strong>写学习日志，不直接编辑自动错题页或折叠区中的JSON。</p></aside>
<footer>本页所有界面均为功能与操作示意，非真实Harness截图。学习记录保存在本机；使用云端学习模型时，必要题目、作答和教材片段会发送给所配置模型。模型反馈与本地参考答案不自动等于官方答案。页中目录均为示例，请替换为自己电脑上的真实位置。</footer>
</main></body></html>'''
    (ROOT / "docs/user-guide-illustrated.html").write_text(html, encoding="utf-8")
    md += ["## 遇到问题", "", "找不到Skill时先核对工作区；缺少OCR模型时先准备资源；备份保留userdata，新增教材随整个项目保留。", "", "完整步骤见[文字版教程](user-guide.md)。[浏览器图文版](user-guide-illustrated.html)内嵌示意图，可单独复制给朋友。", ""]
    (ROOT / "docs/user-guide-illustrated.md").write_text("\n".join(md), encoding="utf-8")
    return {"illustrations": len(PAGES), "png": png, "html": "docs/user-guide-illustrated.html", "markdown": "docs/user-guide-illustrated.md"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", action="store_true", help="Render previews with optional resvg-py")
    print(json.dumps(build(parser.parse_args().png), ensure_ascii=False))
