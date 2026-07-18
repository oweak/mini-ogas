"""Build the public Mini-OGAS Chinese operation manual as a PDF."""

from __future__ import annotations

import argparse
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
MANUAL_VERSION = "2026-07-18"
DEFAULT_OUTPUT = ROOT / "docs" / f"Mini-OGAS_操作手册_{MANUAL_VERSION}.pdf"
FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")

BLUE = colors.HexColor("#2E74B5")
DARK_BLUE = colors.HexColor("#1F4D78")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#526579")
PALE_BLUE = colors.HexColor("#E8EEF5")
PALE_GREEN = colors.HexColor("#EAF4EC")
PALE_AMBER = colors.HexColor("#FFF4DA")
PALE_RED = colors.HexColor("#FCE8E6")
LINE = colors.HexColor("#C7D3DF")


def register_fonts() -> None:
    if not FONT_REGULAR.exists() or not FONT_BOLD.exists():
        raise FileNotFoundError("Microsoft YaHei fonts are required to build the manual.")
    pdfmetrics.registerFont(TTFont("MiniOgasCN", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("MiniOgasCN-Bold", str(FONT_BOLD)))
    pdfmetrics.registerFontFamily(
        "MiniOgasCN",
        normal="MiniOgasCN",
        bold="MiniOgasCN-Bold",
    )


def para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


class ManualDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, styles: dict[str, ParagraphStyle]) -> None:
        super().__init__(
            filename,
            pagesize=LETTER,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=0.82 * inch,
            bottomMargin=0.76 * inch,
            title="Mini-OGAS 操作手册",
            author="Mini-OGAS Engineering",
            subject="Mini-OGAS 安装、启动、操作、验证与故障处置",
            creator="Mini-OGAS documentation build",
        )
        self.styles = styles
        self.heading_id = 0
        cover_frame = Frame(
            32 * mm,
            0.65 * inch,
            LETTER[0] - 32 * mm - 0.9 * inch,
            LETTER[1] - 1.3 * inch,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
            id="cover-frame",
            showBoundary=0,
        )
        body_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="body-frame",
            showBoundary=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(id="cover", frames=[cover_frame], onPage=self.draw_cover_page),
                PageTemplate(id="body", frames=[body_frame], onPage=self.draw_body_page),
            ]
        )

    def beforeDocument(self) -> None:
        self.heading_id = 0

    def draw_cover_page(self, canvas, doc) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setFillColor(DARK_BLUE)
        canvas.rect(0, 0, 20 * mm, LETTER[1], fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(20 * mm, 0, 4 * mm, LETTER[1], fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#F4F7FA"))
        canvas.rect(24 * mm, 0, LETTER[0] - 24 * mm, LETTER[1], fill=1, stroke=0)
        canvas.setFillColor(DARK_BLUE)
        canvas.setFont("MiniOgasCN-Bold", 10)
        canvas.drawString(32 * mm, LETTER[1] - 18 * mm, "MINI-OGAS / OPERATIONS")
        canvas.setFillColor(MUTED)
        canvas.setFont("MiniOgasCN", 8)
        canvas.drawRightString(LETTER[0] - 18 * mm, 13 * mm, "PUBLIC OPERATION MANUAL")
        canvas.restoreState()

    def draw_body_page(self, canvas, doc) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(self.leftMargin, LETTER[1] - 0.58 * inch, LETTER[0] - self.rightMargin, LETTER[1] - 0.58 * inch)
        canvas.setFont("MiniOgasCN-Bold", 8)
        canvas.setFillColor(DARK_BLUE)
        canvas.drawString(self.leftMargin, LETTER[1] - 0.43 * inch, "Mini-OGAS 操作手册")
        canvas.setFont("MiniOgasCN", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(LETTER[0] - self.rightMargin, 0.40 * inch, f"第 {doc.page} 页")
        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:  # noqa: ANN001
        if not isinstance(flowable, Paragraph):
            return
        if flowable.style.name not in {"H1", "H2"}:
            return
        level = 0 if flowable.style.name == "H1" else 1
        title = re.sub(r"<[^>]+>", "", flowable.getPlainText())
        key = f"heading-{self.heading_id}"
        self.heading_id += 1
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=level, closed=False)
        self.notify("TOCEntry", (level, title, self.page, key))


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    def style(name: str, **kwargs) -> ParagraphStyle:
        attributes = {"fontName": "MiniOgasCN", "wordWrap": "CJK"}
        attributes.update(kwargs)
        return ParagraphStyle(name, parent=base["BodyText"], **attributes)

    return {
        "CoverKicker": style("CoverKicker", fontName="MiniOgasCN-Bold", fontSize=10, leading=14, textColor=BLUE, spaceAfter=10),
        "CoverTitle": style("CoverTitle", fontName="MiniOgasCN-Bold", fontSize=30, leading=39, textColor=DARK_BLUE, spaceAfter=16),
        "CoverSub": style("CoverSub", fontSize=13, leading=21, textColor=MUTED, spaceAfter=12),
        "CoverMeta": style("CoverMeta", fontSize=9, leading=15, textColor=MUTED),
        "TOCTitle": style("TOCTitle", fontName="MiniOgasCN-Bold", fontSize=22, leading=28, textColor=DARK_BLUE, spaceAfter=16),
        "H1": style("H1", fontName="MiniOgasCN-Bold", fontSize=18, leading=24, textColor=DARK_BLUE, spaceBefore=4, spaceAfter=10, keepWithNext=True),
        "H2": style("H2", fontName="MiniOgasCN-Bold", fontSize=12.5, leading=18, textColor=BLUE, spaceBefore=10, spaceAfter=5, keepWithNext=True),
        "Body": style("Body", fontSize=9.4, leading=15.2, textColor=INK, spaceAfter=6),
        "Small": style("Small", fontSize=8.1, leading=12.5, textColor=MUTED, spaceAfter=4),
        "Table": style("Table", fontSize=8.0, leading=12, textColor=INK),
        "TableHead": style("TableHead", fontName="MiniOgasCN-Bold", fontSize=8.1, leading=12, textColor=colors.white),
        "Code": style("Code", fontName="Courier", fontSize=7.7, leading=12, textColor=INK, leftIndent=0, rightIndent=0),
        "Callout": style("Callout", fontSize=8.7, leading=14, textColor=INK),
        "Caption": style("Caption", fontSize=7.6, leading=11, textColor=MUTED, alignment=TA_CENTER),
    }


def heading(story: list, styles: dict, title: str, level: int = 1) -> None:
    story.append(para(escape(title), styles["H1" if level == 1 else "H2"]))


def body(story: list, styles: dict, text: str) -> None:
    story.append(para(text, styles["Body"]))


def bullets(story: list, styles: dict, items: list[str]) -> None:
    story.append(
        ListFlowable(
            [ListItem(para(item, styles["Body"]), leftIndent=12) for item in items],
            bulletType="bullet",
            start="circle",
            bulletFontName="MiniOgasCN",
            bulletFontSize=6,
            leftIndent=18,
            bulletIndent=5,
            spaceAfter=5,
        )
    )


def codebox(story: list, styles: dict, lines: list[str]) -> None:
    content = "<br/>".join(escape(line).replace(" ", "&#160;") for line in lines)
    box = Table([[para(content, styles["Code"])]], colWidths=[6.5 * inch])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F6F8")),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([box, Spacer(1, 7)])


def callout(story: list, styles: dict, title: str, text: str, kind: str = "info") -> None:
    palette = {
        "info": (PALE_BLUE, BLUE),
        "ok": (PALE_GREEN, colors.HexColor("#3D7A50")),
        "warn": (PALE_AMBER, colors.HexColor("#B7791F")),
        "danger": (PALE_RED, colors.HexColor("#B33A3A")),
    }
    background, accent = palette[kind]
    content = para(f"<b>{escape(title)}</b><br/>{text}", styles["Callout"])
    box = Table([["", content]], colWidths=[4, 6.5 * inch - 4])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BACKGROUND", (0, 0), (0, -1), accent),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ("LEFTPADDING", (1, 0), (1, -1), 10),
                ("RIGHTPADDING", (1, 0), (1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([box, Spacer(1, 7)])


def data_table(story: list, styles: dict, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    cells = [[para(escape(value), styles["TableHead"]) for value in headers]]
    cells.extend([[para(value, styles["Table"]) for value in row] for row in rows])
    table = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([table, Spacer(1, 8)])


def add_page_break(story: list) -> None:
    story.append(PageBreak())


def build_story(styles: dict[str, ParagraphStyle]) -> list:
    story: list = []
    story.extend(
        [
            Spacer(1, 2.0 * inch),
            para("工程运行参考 / 公开版", styles["CoverKicker"]),
            para("Mini-OGAS<br/>操作手册", styles["CoverTitle"]),
            para("安装、启动、自检、日常运行、AI 诊断、报警处置、停机与恢复", styles["CoverSub"]),
            Spacer(1, 0.35 * inch),
            para("版本：2026.07.18<br/>适用环境：Windows 本地主机 / Digital Twin<br/>文档属性：不含密码、API Key、Token 或私有连接串", styles["CoverMeta"]),
            Spacer(1, 1.15 * inch),
            para("本手册以仓库中的真实脚本、端口、权限和验证路径为依据。未完成独立工业现场验证的能力会明确标注，不以界面或模拟数据代替工业证明。", styles["CoverSub"]),
            NextPageTemplate("body"),
            PageBreak(),
        ]
    )

    story.append(para("目录", styles["TOCTitle"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1", fontName="MiniOgasCN-Bold", fontSize=10, leading=17, textColor=DARK_BLUE, leftIndent=0, firstLineIndent=0),
        ParagraphStyle("TOC2", fontName="MiniOgasCN", fontSize=8.5, leading=14, textColor=MUTED, leftIndent=14, firstLineIndent=0),
    ]
    story.extend([toc, PageBreak()])

    heading(story, styles, "1. 使用边界与安全原则")
    body(story, styles, "Mini-OGAS 当前是面向数字孪生与可信控制闭环验证的工程系统。中央事实写入 PostgreSQL，Redis 仅作可重建投影，NATS/JetStream 当前是 Shadow 消息路径；三类车间节点由 SimPy 进程模拟。系统已验证本地主机上的受控命令、审批、节点领取、执行回报、效果验证和审计归档，但尚不能宣称独立工厂主机、高可用、实时 PLC 控制或工业认证已经完成。")
    callout(story, styles, "操作纪律", "任何会改变生产状态的高风险动作必须经过权限检查、安全规则与人工确认。AI 只生成诊断和建议，不拥有生产命令审批权。", "warn")
    bullets(story, styles, [
        "不要把 <b>.env</b>、本地凭据文件、AI Vault、JWT Secret、节点 Token、数据库连接串或日志压缩包提交到 Git。",
        "不要在截图、工单、聊天记录或 PDF 中粘贴真实密码和 API Key。",
        "报警只有在节点结果回报且 Verifier 判定处置有效后才应归档；关闭弹窗不等于问题已解决。",
        "实时状态以 API、PostgreSQL、节点心跳与审计事件为准；界面动画只是表现层。",
    ])

    heading(story, styles, "1.1 已验证与未验证能力", 2)
    data_table(
        story,
        styles,
        ["能力", "当前事实", "操作含义"],
        [
            ["中央事实", "PostgreSQL 主写；Redis 为可重建投影", "故障恢复和审计以 PostgreSQL 为准"],
            ["节点", "3 个本机受管 SimPy 车间进程", "不是三台独立工业主机或 PLC"],
            ["消息", "HTTP/REST 为权威路径；NATS 为 Shadow", "NATS 降级时不应阻断权威闭环"],
            ["AI", "AI Dispatcher 支持供应商链与规则回退", "必须查看 provenance，不能把 fallback 称为 API 诊断"],
            ["安全", "JWT、RBAC、资源权限、安全门和审计已实现", "真实生产接入前仍需独立安全评估"],
            ["备份", "已有策略合同与示例，自动定时备份尚未作为成熟能力验收", "操作员应执行并验证备份演练"],
        ],
        [1.0 * inch, 2.45 * inch, 3.05 * inch],
    )

    heading(story, styles, "2. 系统组成与端口")
    data_table(
        story,
        styles,
        ["组件", "端口", "职责"],
        [
            ["Go Supervisor", "9099", "启动、监视、重启和统一停机"],
            ["Central API", "8080", "认证、事实、命令、审批、快照和审计接口"],
            ["AI Dispatcher", "8081", "模型调用、供应商链、来源记录与规则回退"],
            ["Market Simulator", "8082", "数字孪生需求输入"],
            ["Production Planner", "8083", "工单与调度建议"],
            ["Background Worker", "8084", "周期任务、Outbox、NATS Shadow 消费"],
            ["Dashboard", "5173", "中文运行控制台"],
            ["NATS / Redis / MinIO", "4222 / 6379 / 9000", "Shadow 消息、投影缓存、证据对象"],
            ["生产节点", "无固定 UI 端口", "车削、铣削、磨削心跳与命令执行"],
        ],
        [1.65 * inch, 1.1 * inch, 3.75 * inch],
    )
    callout(story, styles, "端口冲突", "启动脚本检测到端口已被占用时会拒绝重复控制器。只有在确认要把现有进程交给新 Supervisor 时，才使用 -ReplaceRunning。", "warn")

    add_page_break(story)
    heading(story, styles, "3. 首次安装")
    heading(story, styles, "3.1 前置条件", 2)
    bullets(story, styles, [
        "Windows PowerShell、Python、Node.js/npm、Git；脚本会准备 Go 与 Python 虚拟环境。",
        "PostgreSQL 作为中央事实库；本地节点 SQLite 只承担边缘状态与测试用途。",
        "D 盘保留足够空间，默认运行根目录为 <b>D:\\MiniOGAS-VMs</b>。",
        "使用普通管理员工作站账户；不要关闭系统的文件 ACL 保护。",
    ])
    heading(story, styles, "3.2 初始化开发依赖", 2)
    codebox(story, styles, [
        "Set-Location 'D:\\New project\\mini-ogas'",
        ".\\scripts\\setup-dev.ps1",
        ".\\scripts\\install-nats.ps1",
        ".\\scripts\\install-git-hooks.ps1",
    ])
    body(story, styles, "setup-dev.ps1 为 Central API、AI Dispatcher、Market Simulator 和 Production Planner 建立隔离的 Python 环境，并安装 Dashboard 依赖和 Go 模块。NATS 安装脚本只需在运行时缺失时执行。Git 钩子会在提交前执行密钥扫描并拒绝被忽略但仍被跟踪的文件。")
    callout(story, styles, "供应链提醒", "安装依赖前确认网络来源与企业策略。公开仓库不携带 node_modules、虚拟环境、构建产物或本地运行日志。", "info")

    heading(story, styles, "4. 私密配置与 GitHub 发布")
    body(story, styles, "仓库只保存配置示例与引用关系。真实值保存在受限的本地运行目录或加密 Vault 中。生成的凭据不得复制到 README、Issue、Commit Message、PDF 或截图。")
    data_table(
        story,
        styles,
        ["内容", "公开仓库策略", "本地处理"],
        [
            ["AI API Key", "禁止提交", "用 reset-ai-vault.ps1 的安全输入写入加密 Vault"],
            ["管理员密码 / JWT", "禁止提交", "存放在受 ACL 保护的 auth.env；只供本机运行读取"],
            ["节点和服务 Token", "禁止提交", "由启动流程生成、按主体分离并支持轮换"],
            ["数据库 DSN", "禁止提交真实值", "从受限的本地配置加载；示例只保留占位符"],
            ["日志 / 数据库 / 备份", "禁止直接提交", "保留在 .runtime 或 D 盘运行目录，按事件策略归档"],
            ["代理提示词 / 交接草稿", "不属于产品源码", "可在本地保留，但由 .gitignore 排除"],
        ],
        [1.5 * inch, 1.7 * inch, 3.3 * inch],
    )
    codebox(story, styles, [
        "python .\\scripts\\check_secrets.py",
        "git ls-files -ci --exclude-standard",
        "git status --short",
    ])
    callout(story, styles, "发布门禁", "第一条命令必须报告 secret scan passed；第二条命令必须无输出。若扫描失败，先移除密钥并立即轮换已暴露凭据，不要通过改扫描器来绕过。", "danger")

    heading(story, styles, "5. 启动、自检与登录")
    heading(story, styles, "5.1 标准启动", 2)
    codebox(story, styles, [
        "Set-Location 'D:\\New project\\mini-ogas'",
        ".\\scripts\\start-miniogas.ps1",
    ])
    body(story, styles, "该入口把本机运行交给 Go Supervisor。默认使用 digital_twin、simulated、operator_assisted 和 PostgreSQL 事实源。不要并行运行旧脚本控制器。")
    heading(story, styles, "5.2 有意接管已有运行", 2)
    codebox(story, styles, [".\\scripts\\start-miniogas.ps1 -ReplaceRunning"])
    body(story, styles, "仅在确认当前端口属于旧 Mini-OGAS 会话时使用。脚本会先停止旧 Supervisor，再清理受管进程并建立新会话。")
    heading(story, styles, "5.3 登录前动画与门禁", 2)
    bullets(story, styles, [
        "浏览器打开 <b>http://127.0.0.1:5173</b>。登录完成前不应看到系统主界面。",
        "启动动画依次检查 Central API、父子节点、工单/调度、规则引擎和 AI 运行环境。",
        "自检完成后才显示登录表单；失败项必须显示真实原因，不能用固定成功动画代替。",
        "使用本机已配置的管理员账号和受保护密码。公开文档不提供默认密码。",
    ])
    callout(story, styles, "AI 锁定不是系统离线", "AI Vault 未解锁时，系统可以进入规则回退，但界面必须明确显示 fallback/locked；此时不能宣称在线模型已参与。", "warn")

    heading(story, styles, "6. 运行状态验证")
    codebox(story, styles, [
        ".\\scripts\\check-runtime-status.ps1",
        ".\\scripts\\start-system.ps1 -CheckOnly",
        ".\\scripts\\start-system.ps1 -CheckOnly -RequireAiApi",
    ])
    body(story, styles, "第一条命令返回健康、自检与登录探针；输出会移除 access_token，只保留 token 是否存在。第二条验证核心运行；第三条在必须证明在线 AI 时使用。")
    data_table(
        story,
        styles,
        ["检查项", "通过标准"],
        [
            ["Supervisor", "会话新鲜，受管进程与端口一致"],
            ["节点", "turning、milling、grinding 均有新鲜、认证心跳"],
            ["事实源", "PostgreSQL 可写，关键事实可在重启后恢复"],
            ["Dashboard", "生产构建可访问，数据来源与 API 一致"],
            ["AI", "需要在线模型时 provenance/source 必须为 api，不得为 fallback"],
            ["NATS Shadow", "可降级但需可见；REST/PostgreSQL 权威路径仍正常"],
        ],
        [1.7 * inch, 4.8 * inch],
    )

    heading(story, styles, "7. 日常运行流程")
    heading(story, styles, "7.1 节点与生产状态", 2)
    bullets(story, styles, [
        "在父子节点树中查看节点在线状态、run_id、simulation_time、目标/实际速率、利用率、WIP 和缺陷率。",
        "点击节点查看最近心跳、当前工单、待执行命令与最近处置。不要只看 3/3 计数。",
        "正常工况中损耗应按模型时间和负载积累，不应在启动后立即批量产生磨损或高温报警。",
        "数据来源标签必须区分 live、simulated、replay、fallback 或 fixture。",
    ])
    heading(story, styles, "7.2 工单调度", 2)
    body(story, styles, "主机端创建工单后，由 Planner 计算计划并经权限边界形成命令。需要人工批准的调度变更必须显示批准入口、确认码和预期影响；批准后命令由对应节点领取执行。")
    data_table(
        story,
        styles,
        ["阶段", "操作员看到的事实", "完成条件"],
        [
            ["计划", "目标、约束、建议、受影响节点", "方案已计算且版本确定"],
            ["审批", "权限、风险、确认码、审计主体", "合法管理员输入 <b>CONFIRM</b>"],
            ["领取", "命令 ID、节点、时间、状态", "绑定节点成功 claim"],
            ["执行", "执行脚本、前后指标、回报", "节点报告成功或失败"],
            ["验证", "目标率、实际率、产量与质量变化", "Verifier 判定 effective"],
            ["归档", "处理人、权限、事项、结果、证据", "活动队列消失并进入日志管理"],
        ],
        [1.0 * inch, 3.0 * inch, 2.5 * inch],
    )
    callout(story, styles, "审批不是完成", "界面显示“批准成功”只代表命令获准。必须继续看到节点领取、执行回报、效果验证和归档，否则闭环仍未完成。", "warn")

    heading(story, styles, "7.3 报警处置", 2)
    bullets(story, styles, [
        "所有真实规则命中的问题都应弹窗，并按严重度使用不同音效；音效只在新警告出现时播放。",
        "轻微问题可由规则脚本或 AI 建议自动处理，但必须记录前后指标与执行来源。",
        "重大物理故障应给出停机、隔离、派遣人员、检查项目和恢复条件，由人工决策。",
        "关闭弹窗只改变可见状态，不改变问题生命周期。问题仍应留在活动队列。",
        "处置成功后立即从报警队列移除，并写入日志管理；失败时保留并升级。",
    ])

    heading(story, styles, "8. AI 诊断与人工决策")
    heading(story, styles, "8.1 配置加密 AI Vault", 2)
    codebox(story, styles, [
        ".\\deploy\\reset-ai-vault.ps1",
        "# Enter the API key and vault password at the secure prompts.",
        ".\\scripts\\start-miniogas.ps1 -ReplaceRunning",
    ])
    body(story, styles, "reset-ai-vault.ps1 默认配置 DeepSeek 供应商和 deepseek-v4-pro 模型，并把密钥写入本地加密 Vault。脚本结束后会清理临时环境变量。不得把 -UseEnvironment 写进共享脚本或终端录屏；自动化场景应使用受控的秘密管理器。")
    heading(story, styles, "8.2 判断 AI 是否真正参与", 2)
    data_table(
        story,
        styles,
        ["字段/证据", "应检查的内容"],
        [
            ["provider / model", "实际供应商与模型标识，不是固定宣传文案"],
            ["source / provenance", "api 表示外部模型；fallback/rule 表示规则回退"],
            ["request / trace ID", "可关联中央审计与 Dispatcher 日志"],
            ["诊断正文", "根因、证据、风险、建议步骤和恢复条件"],
            ["置信度", "只是辅助指标，不能代替权限和安全门"],
            ["建议选项", "每项说明影响、前提、可逆性和是否需人工批准"],
        ],
        [1.65 * inch, 4.85 * inch],
    )
    callout(story, styles, "禁止误报", "若 Dispatcher 超时或 Vault 锁定，界面必须显示规则回退。不能把预置模板、规则文本或缓存响应标成在线模型诊断。", "danger")

    heading(story, styles, "9. 日志管理与审计")
    body(story, styles, "处理完成的问题、调度变更和人工审批必须进入日志管理。日志是闭环证据，不是单纯的前端消息。")
    data_table(
        story,
        styles,
        ["字段", "用途"],
        [
            ["处理人 / Principal", "证明谁发起、批准或执行"],
            ["角色与权限", "证明当时的授权依据"],
            ["处理事宜", "告警、工单、节点、命令与影响范围"],
            ["处理过程", "诊断、选项、确认、领取、脚本和回报"],
            ["处理结果", "成功、失败、隔离、回滚或人工接管"],
            ["效果证据", "前后指标、Verifier 判定、时间和 run_id"],
            ["AI 来源", "provider、model、source、trace，不保存密钥"],
        ],
        [1.6 * inch, 4.9 * inch],
    )

    heading(story, styles, "10. 停机、重启与降级")
    heading(story, styles, "10.1 标准停机", 2)
    codebox(story, styles, [
        "python -m tools.mogas.cli down",
        "# 或",
        ".\\scripts\\stop-all.ps1",
    ])
    body(story, styles, "停机脚本先调用 Supervisor 的 loopback stopall 接口，再等待全部受管端口关闭；只有 Supervisor 不可用时才执行受限的 PID 清理。停机后应确认 9099、8080-8084、5173、4222、6379 和 9000 均已释放。")
    heading(story, styles, "10.2 重启", 2)
    codebox(story, styles, [".\\scripts\\start-miniogas.ps1 -ReplaceRunning"])
    heading(story, styles, "10.3 NATS Shadow 降级", 2)
    codebox(story, styles, [".\\scripts\\start-miniogas.ps1 -ReplaceRunning -DisableNats"])
    body(story, styles, "该选项只关闭 Central 的 NATS Shadow 发布/消费，不改变 HTTP/PostgreSQL 权威事实路径。Redis 仍是投影，出现不一致时应从 PostgreSQL 重建，而不是修改数据库事实去迁就缓存。")

    heading(story, styles, "11. 备份与恢复")
    callout(story, styles, "当前成熟度", "仓库提供备份/恢复合同与验证步骤，但自动定时备份、WAL 归档和生产级恢复演练尚不能视为全部完成。操作前参考 docs/backup-restore-v3.0.md。", "warn")
    body(story, styles, "实验环境至少应在迁移前和每日执行 PostgreSQL 自定义格式备份，并在独立空数据库验证 pg_restore --list 与恢复。备份输出写入 D 盘受限目录；DSN 从受保护环境读取，不能打印到终端日志。")
    codebox(story, styles, [
        "$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'",
        "$target = \"D:\\MiniOGAS-VMs\\backups\\postgres\\$stamp\"",
        "New-Item -ItemType Directory -Force -Path $target | Out-Null",
        "pg_dump --dbname $env:POSTGRES_DSN --format custom --no-owner --no-privileges --file \"$target\\mini_ogas.dump\"",
        "pg_restore --list \"$target\\mini_ogas.dump\"",
    ])
    bullets(story, styles, [
        "恢复必须先进入新建空数据库，禁止覆盖唯一在线数据库。",
        "校验 SHA-256、表清单、迁移版本、事件顺序、命令状态和审计读取。",
        "边缘 SQLite 使用在线 backup API，不直接复制活动数据库文件。",
        "Redis 不做事实备份；从 PostgreSQL 重建。NATS Shadow 可由已接受事实重放。",
    ])

    heading(story, styles, "12. 常见故障排查")
    data_table(
        story,
        styles,
        ["现象", "优先检查", "处置"],
        [
            ["Dashboard 无法打开", "5173、Supervisor 会话、Dashboard 构建", "运行状态检查；必要时受控重启"],
            ["显示 0/3 节点", "三节点心跳时间、凭据绑定、Central ingest", "检查节点进程与 API 日志，不手工改计数"],
            ["AI 只显示模板", "Vault 状态、source/provenance、Dispatcher 8081", "解锁 Vault；验证 source=api；超时则保留 fallback 标识"],
            ["批准后无变化", "命令状态、claim、节点回报、Verifier", "定位闭环断点；不要直接把告警改为 resolved"],
            ["已处理仍在报警队列", "Verifier 结果、归档事务、日志写入", "失败则保留并升级；成功后重建投影"],
            ["NATS degraded", "4222、凭据、JetStream、Worker 8084", "可用 DisableNats 降级，保持 REST/PostgreSQL 路径"],
            ["端口占用", "9099 与 8080-8084 的 PID", "确认归属后使用 -ReplaceRunning，禁止盲目杀进程"],
            ["密钥扫描失败", "报告文件、.env、日志、压缩包", "撤销跟踪并轮换暴露凭据；重新扫描"],
        ],
        [1.45 * inch, 2.15 * inch, 2.9 * inch],
    )

    heading(story, styles, "13. 完整验证与发布前清单")
    codebox(story, styles, [
        ".\\scripts\\verify-miniogas.ps1 -RequireAiUnlocked",
        "python .\\scripts\\check_secrets.py",
        "git ls-files -ci --exclude-standard",
        "git diff --check",
    ])
    data_table(
        story,
        styles,
        ["清单", "判定"],
        [
            ["测试", "Central、节点、AI、Planner、CLI、Dashboard 与 Go 测试全部通过"],
            ["运行", "受管进程新鲜，3/3 节点认证心跳，PostgreSQL 持久化可证明"],
            ["AI", "要求在线模型时 source=api，trace 可关联；否则明确 fallback"],
            ["闭环", "至少一条命令完成审批、领取、执行、验证和归档"],
            ["安全", "密钥扫描通过，tracked-ignored 无输出，无本地日志或凭据待提交"],
            ["GitHub", "只发布产品源码、正式文档、配置示例和可复现脚本；CI 通过"],
        ],
        [1.3 * inch, 5.2 * inch],
    )
    callout(story, styles, "最终判定", "任一安全、事实源、节点身份、审批或效果验证门禁失败时，不得将页面显示当作完成证据。先修复根因，再重新运行验证。", "danger")

    heading(story, styles, "附录 A：常用命令速查")
    data_table(
        story,
        styles,
        ["任务", "命令"],
        [
            ["安装依赖", ".\\scripts\\setup-dev.ps1"],
            ["安装 NATS", ".\\scripts\\install-nats.ps1"],
            ["启用 Git 钩子", ".\\scripts\\install-git-hooks.ps1"],
            ["启动", ".\\scripts\\start-miniogas.ps1"],
            ["接管并重启", ".\\scripts\\start-miniogas.ps1 -ReplaceRunning"],
            ["状态检查", ".\\scripts\\check-runtime-status.ps1"],
            ["严格运行检查", ".\\scripts\\start-system.ps1 -CheckOnly -RequireAiApi"],
            ["完整验证", ".\\scripts\\verify-miniogas.ps1 -RequireAiUnlocked"],
            ["配置 AI Vault", ".\\deploy\\reset-ai-vault.ps1"],
            ["停机", ".\\scripts\\stop-all.ps1"],
            ["密钥扫描", "python .\\scripts\\check_secrets.py"],
            ["构建本手册", "python .\\scripts\\build_operation_manual.py"],
        ],
        [1.7 * inch, 4.8 * inch],
    )
    body(story, styles, "文档结束。所有示例均故意省略真实凭据；本手册不能替代现场安全规程、设备厂商说明、风险评估或独立工业验收。")
    return story


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    register_fonts()
    styles = make_styles()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDocTemplate(str(args.output), styles)
    doc.multiBuild(build_story(styles))
    print(args.output)


if __name__ == "__main__":
    main()
