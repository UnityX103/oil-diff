---
name: oil-diff
description: "将 Git 改动、提交范围或工作区修改生成直观易读的可视化 HTML 改动汇报页（含业务模块速览、前后对比图示、具体例子、单行改动文件树与右侧原文审阅抽屉）。用户要求解释一轮代码或文档改了什么、把 git diff 做成汇报页或可视化演示页、向老板或团队展示仓库改动时使用。不用于执行代码修改、Git 提交、常规 Code Review 缺陷审计或制作通用幻灯片。"
license: MIT
compatibility: "核心采集、渲染与校验脚本只依赖 Python 3.10+ 标准库和系统 git 命令；生成的 HTML 汇报页为零外部依赖的单文件页面，可在现代桌面与移动浏览器直接打开。已在 macOS 实机验证，Windows 与 Linux 完成跨平台静态检查。"
metadata:
  version: "0.2.0"
---

# oil-diff

把零散的 Git 改动转化为非代码作者（如项目负责人、产品伙伴、协作者）一眼能看懂的**可视化改动汇报页**。以“让未参与编码的读者 30 秒内看懂改了哪块业务、原来有什么痛点、现在怎么运作、改了哪些文件”为唯一交付标准。

## 仓库安全底线与 `.oil-diff/` 目录约定

- 默认只在目标仓库下的未跟踪目录 `<repo>/.oil-diff/` 写入文件，第一步必须确认 `<repo>/.oil-diff/.gitignore` 内容精确为 `*` 加换行（自动让整个 `.oil-diff/` 对 Git 隐形，不修改目标项目根 `.gitignore`）。
- `<repo>/.oil-diff/index.html` 只放最终交付的自包含单文件汇报页；中间数据（`diff-data.json`）、业务归因规格（`report-spec.json`）及核验截图统一放入 `<repo>/.oil-diff/assets/`。
- 严禁执行 `git add`、`git commit`、`git checkout`、`git reset`、`git stash` 或修改任何已跟踪文件；交付前验证目标仓库的 `HEAD` 与 `git status --short` 和执行前完全一致。

## 先选择模式

| 模式 | 适用情况 | 路径 | 默认停止点 |
| --- | --- | --- | --- |
| 生成汇报 | 给定仓库、分支、提交范围或未提交工作区，首次生成汇报页 | 采集数据 → 业务归因与文案 → 构建图示 → 渲染 HTML → 校验 | 产出 `.oil-diff/index.html` 并通过校验 |
| 局部更新 | 已有 `.oil-diff/`，需调整章节划分、文案、图示或比较范围 | 读取现有配置 → 按需重跑采集或修改规格 → 重新渲染 → 校验 | 更新 `.oil-diff/index.html` 并通过校验 |
| 质量核验 | 已有 `.oil-diff/index.html`，只检查文案、结构与仓库边界 | 运行 `scripts/lint_report.py` → 按需用浏览器工具静态截图检查 | 输出核验结论后停止 |

下文的 `<python>` 指版本不低于 3.10 的 Python 解释器：macOS 与 Linux 通常使用 `python3`，Windows 通常使用 `py -3`。

## 执行工作流

> **默认委托独立子 Agent 执行（保护主对话上下文）**：
> 若当前是主对话 Agent 且宿主支持启动子 Agent，**优先启动一个具备读写与命令执行能力的独立子 Agent** 跑完下方第 1～5 步闭环（避免大体积 `diff-data.json` 撑爆主对话上下文）；若自身已是子 Agent 或宿主不支持子 Agent，则在当前上下文直接执行。
> **主 Agent 启动子 Agent 时必须交接以下 3 项事实（防止子 Agent 脱离上下文盲猜）**：
> 1. **入口与目标**：本 `SKILL.md` 的路径、目标仓库路径与比较范围（要求子 Agent 先完整阅读本 `SKILL.md`、[references/copywriting-and-structure.md](references/copywriting-and-structure.md) 与 [references/visual-and-interaction.md](references/visual-and-interaction.md)）；
> 2. **本轮真实背景摘要**：用 3～5 句话概括本轮改动的目的、解决了什么问题（若主对话刚完成这轮修改，直接把真实意图告诉子 Agent）；
> 3. **实测截图白名单**：明确列出本轮是否有真实运行截出的图片路径；**若无真实实测截图，必须明确指令子 Agent：“本轮无实测截图，严禁从仓库 `_work/`、`research/` 等目录找图，全部使用内置矢量视觉积木”**。

### 1. 采集确定性 Git 改动数据

确定要汇报的仓库路径与比较范围（如未提交工作区、最近一轮提交，或 `base..head` 多段提交范围），运行 [scripts/collect_diff.py](scripts/collect_diff.py)：

```text
<python> scripts/collect_diff.py --repo <目标仓库路径> --output <目标仓库路径>/.oil-diff
```

需要指定多段比较范围时，传入一或多个 `--range <范围ID>:<显示名称>:<起点>..<终点>`（终点为工作区时写 `WT`）。脚本会自动创建 `.oil-diff/.gitignore`（写入 `*`）和 `.oil-diff/assets/`，并提取所有改动文件的路径、增删行数、行级修改块（hunks）及所在章节或函数上下文，保存为 `<output>/assets/diff-data.json`。

### 2. 按业务模块归因并撰写结构化文案

先完整读取 [文案与三层排版规范](references/copywriting-and-structure.md)。不要按文件列表逐个罗列改动，而是站在熟悉项目业务的汇报者视角，把全部改动文件归纳为 **3～7 件业务事项**，生成 `<output>/assets/report-spec.json`：

1. **业务模块与标题**：每件事必须标注简短的 `module`（业务模块胶囊，如 `工作区评审`、`鉴权中间件`），标题遵循「所属业务模块/工具 + 具体动作 + 机制变化」，禁止写成脱离项目语境的泛泛常识句。
2. **一两句话讲清痛点与改法（`overview`）**：用 1～2 句平实中文写好 `overview`，交代清楚原来有什么具体麻烦、现在改成怎么运作，把作者自造缩写翻译为具体动作。
3. **具体改法要点与核心文件归类**：每件事拆分为 2～4 个改法要点（`points`），将真正改动核心逻辑的文件挂在对应要点下（渲染为 `🎯 核心必看` 胶囊）；其余顺手同步修改的外围文档只需列入章节 `fileIds`，渲染器会自动将其收进章节底部的 `📎 外围同步` 折叠条。

### 3. 配置实拍截图与微缩可视化舞台（配图零段落）

先读取 [视觉风格、可视化模式与交互规范](references/visual-and-interaction.md)。在 `.oil-diff/assets/report-spec.json` 的每个章节项中配置结构化 `"diagram"` 对象（遵循「配图是配图，文字是文字」，`<figure class="diagram">` 内严禁出现 `<p>` 段落长句）：

- **真实截图防伪铁律（`type: "screenshots"` 仅限真实运行产物，必须标注 `captureSource`）**：只有当本次改动确实由 Agent 实机运行并截出画面（`"captureSource": "live-capture"`）、用户明确提供了本次改动的实测截图（`"captureSource": "user-provided"`）、或图片本身就是本次 Git Diff 的跟踪文件（`"captureSource": "git-diff"`）时，才允许放入 `<output>/assets/shots/` 并使用截图字段。**严禁从仓库的临时目录（如 `_work/`、`research/`、调研素材、网上参考图）拷贝非本次实测的图片冒充修改前后截图**；`scripts/lint_report.py` 会通过 SHA-256 哈希比对自动拦截任何从仓库非改动区拷贝的图片。纯文档、规则或后端改动无真实运行截图时，一律使用下方的矢量微缩积木。
- **无实拍图时选用 5 类纯视觉积木**：从 `"type": "routing" | "scenarios" | "flow" | "schema" | "diagnostics"`（或 `"comparison" | "alignment"`）中选择与章节主题 100% 对应的结构化模式，并根据项目实际业务填写自定义字段（如 `brand`、`goodHeading`、`badText`、`goodText`），避免直接沿用无关兜底词。
- 如需自定义 `diagramHtml`，必须包含微缩视觉图元且只放 2～10 字的极简短标签，严禁塞入 `<p>` 段落句子。

### 4. 渲染自包含 HTML 汇报页（Bento 看板与分类必看漏斗）

运行 [scripts/render_report.py](scripts/render_report.py)，将 `.oil-diff/assets/diff-data.json`、`.oil-diff/assets/report-spec.json` 与内置静态资源合成为单文件页面：

```text
<python> scripts/render_report.py --report-dir <output>
```

渲染器会自动校验所有改动文件是否均已归入章节、核对摘录行号是否存在，并嵌入 [assets/report.css](assets/report.css) 与 [assets/report.js](assets/report.js)，生成包含以下核心能力的 `index.html`：
- **默认 Bento 看板布局（`#bento-deck`）**：首屏通过单行紧凑模块卡片（`1..N`）导航直达各章，不重复摘抄正文段落；主体采用双列 Bento 书页网格，高密度整合每章结论、实拍截图/架构图与改动要点，不输出底部冗余全量文件表（`#all-files`）；
- **按具体改动分类的「🎯 核心必看 / 📎 外围同步」漏斗**：在每个章节卡底部，将核心代码文件（`🎯 核心必看`）直接归类挂在 `1`、`2` 具体改法要点下方（`.point-pills`），将顺手同步的外围引用文件收进底部的 `📎 外围同步` 折叠条；
- **可收起的窄栏改动文件树与右侧原文审阅抽屉**：桌面右侧文件树默认 `256px` 窄栏，抽屉占 `80vw`；`720px` 及以下默认折叠文件树，以底部悬浮按钮按需打开，选中文件后进入接近全屏的源码抽屉。
- **默认支持移动端预览**：手机使用单列章节与图示，标题、路径和元信息可换行；主要按钮至少 `44px` 高，源码保持原始行结构并仅在代码区横向滚动。面板适配安全区，打开手机面板时锁住正文滚动，关闭后保留阅读位置。此行为由模板提供，无需在用户级或项目级 AGENTS.md 重复声明。

### 5. 质量核验与桌面、移动端视觉检查

渲染完成后，运行 [scripts/lint_report.py](scripts/lint_report.py) 执行静态质量、防伪与安全边界检查：

```text
<python> scripts/lint_report.py --repo <目标仓库路径> --report-dir <output>
```

- 校验器会强制检查：
  1. **截图真实性防伪（SHA-256 比对 + `captureSource` 核验）**：拦截未声明 `captureSource` 的截图，以及从仓库非 Diff 目录（如 `_work/`、历史素材）搬运冒充的图片；
  2. **配图零段落与排版精简**：禁止 `<figure class="diagram">` 内出现 `<p>` 段落句子，确认启用 `#bento-deck`、按要点分类的 `.point-pills`、文件树折叠按钮 `[data-tree-toggle]`，且无冗余 `#all-files` 总表；
  3. **文风与仓库零污染**：拦截空洞套话、检查 `.gitignore` 严格隔离及仓库 `git status` 未被污染。
- 若当前宿主提供浏览器工具，在 **桌面 `1440px`、笔记本 `1100px`、手机 `375px` 与 `430px`** 视口下打开 `<output>/index.html` 检查，长路径或复杂图示另加 `320px` 窄屏检查。确认正文没有横向溢出、手机首屏能直接读到汇报、图示与按钮可读可点、文件树开关与文件切换正常、源码抽屉关闭后保留正文滚动位置。源码长行仅在代码区滚动；至少保存桌面、手机正文和手机抽屉截图。只用静态截图与 DOM/触控检查，不录制视频；未实际检查的平台或浏览器不宣称通过。

## 资源导航

- **参考规范**：
  - [references/copywriting-and-structure.md](references/copywriting-and-structure.md)：撰写章节标题、速览句子与编写 `report-spec.json` 前必读。
  - [references/visual-and-interaction.md](references/visual-and-interaction.md)：设计每章 HTML/CSS 可视化舞台与检查右侧抽屉交互前必读。

- **脚本与静态资源**：
  - [scripts/collect_diff.py](scripts/collect_diff.py)：步骤 1 采集 Git 改动并初始化 `.oil-diff/.gitignore`。
  - [scripts/render_report.py](scripts/render_report.py)：步骤 4 内联 [assets/report.css](assets/report.css) 与 [assets/report.js](assets/report.js) 生成 `index.html`。
  - [scripts/lint_report.py](scripts/lint_report.py)：步骤 5 校验文案、DOM 结构与 Git 零污染边界；修改脚本后运行 [tests/test_oil_diff.py](tests/test_oil_diff.py)。

## 输出与停止条件

当 `<output>/index.html` 生成完毕、`scripts/lint_report.py` 输出 `PASS`、且确认目标仓库的 Git 状态无任何新增修改时停止。向用户交付 `<output>/index.html` 的文件路径，并简要列出所归纳的业务事项标题与改动文件统计。

## 路径与代码配色

抽屉标题必须显示完整相对路径，允许任意位置软换行，不继承列表胶囊的限宽、省略号或 nowrap。列表仍保持紧凑。

代码对照区复用已确认的 `rider-code-preview` 配色部分，随本 Skill 保存在 `assets/rider/`（源为 MIDA `.agents/skills/rider-code-preview`）。Rider Dark、内嵌 JetBrains Mono 常规/斜体、17px、1.2 行距、tab 4；未改行灰色，新改行绿色底，删除行灰底，语法为词法近似。页面其它区域仍用暖纸样式。主视图仅展示固定 target 的新增／修改后代码段，单栏按行着色；删除的旧行仅在下方折叠辅助区展示。长代码行禁止软换行，使用代码区横向滚动。更新配色应先读取现有 rider-code-preview Skill 及其 preferences/render-contract，再同步资源；字体保留 OFL。

## 单栏源码与 VS Code 定位

抽屉在桌面占视口宽度 80%，手机接近全宽。差异计算使用采集的完整目标源码，但主视图只渲染新增／修改后行；未改内容不进入预览 DOM，非连续段用省略分隔符分开；缺完整快照应重新按原比较范围采集。新增和修改行绿底、未改行隐藏、删除行单独折叠并标旧行号。代码不软换行；路径标题仍允许换行。上一处／下一处改动按连续修改段导航，点击目标行号选择定位行，空文件和二进制禁用定位。

底部区域无独立背景，按钮采用页面暖纸／琥珀描边风格（透明底），不使用代码区黑色背景，通过 `archify-vscode://open?root=...&path=...&line=...` 调用已有 rider-code-preview 的 launcher。项目根从本地 `.oil-diff` 页面路径推导，仓库相对路径和真实目标行号经 URL 编码；单次 VS Code CLI 请求同时传项目目录与 `--goto`，禁止先后两个独立打开请求或孤立文件链接。历史快照按钮明确打开的是当前工作区文件。远程页面不猜本机路径，不能定位时禁用按钮并说明。首次系统协议确认交给用户，不自动触发外部应用。
