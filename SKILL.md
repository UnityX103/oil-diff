---
name: oil-diff
description: "把 Git 工作区或提交范围的改动按业务归类，使用内置模板生成自包含 HTML 汇报页；Prefab 仅列变更目标。适用于改动汇报与可视化 diff 说明，不用于代码修改或缺陷审计。"
license: MIT
metadata:
  version: "0.4.0"
  runtime: "Python 3.10+ 标准库和系统 git；HTML 零外部依赖。"
---

# oil-diff

把改动按业务目的组织成非作者也能读懂的汇报页。**默认复用模板，只写结构化文案与分组；不重新编写 HTML/CSS/JS。**

## 边界

- 只在目标仓库未跟踪的 `.oil-diff/` 内写报告；采集器创建内容为 `*` 加换行的 `.oil-diff/.gitignore`。不修改项目源码、根 `.gitignore`，不执行 Git 暂存、提交或切换操作。交付前核对 `HEAD` 和 `git status --short` 与生成前一致。
- **`.prefab` 和 `.prefab.meta` 仅列目标**：不读取 YAML、不解释内部字段、不查组件或引用关系、不生成内容摘录或前后对照。采集器只保留路径、状态和可用的 Git 行数统计。重要目标直接挂到对应要点；其余保留在外围文件列表/文件树。重要性依据用户背景与目标路径，不能通过阅读 Prefab 内容判断，也不能编造资源的具体变化。
- 完整文本快照仅供渲染器本地生成代码抽屉。**不要把整个 `diff-data.json`、生成的 HTML、模板源码或静态资源读进模型上下文。**
- 不因使用本 Skill 默认启动子 Agent；确有已授权的委派时，传递背景、范围、截图白名单及用户当前的提问规则，不重复加载所有参考文件。

## 默认流程：采集 → 小量阅读 → 填模板 → 渲染/校验

命令中的 `<skill>` 为本 Skill 目录，`<repo>` 为目标仓库，`<python>` 为 Python 3.10+。先确认仓库与范围。

```text
<python> <skill>/scripts/collect_diff.py --repo <repo>
<python> <skill>/scripts/report_context.py --report-dir <repo>/.oil-diff --init-spec
```

- 采集器把完整数据保存到 `assets/diff-data.json`，同时生成不含源码的 `assets/change-summary.json`。第二条命令打印前 60 条精简文件摘要，并从 `assets/report-spec.template.json` 创建规格骨架；已有规格不会覆盖。用 `--offset 60 --limit 60` 分页，直到掌握整个比较范围。
- `fileRecords` 为 0 时说明本范围无改动并停止，不填空报告。
- 指定范围用一或多个 `--range <id>:<名称>:<base>..<target>`；工作区目标写 `WT`。默认行为沿用现有脚本：有未提交修改时同时采集工作区与最近一次提交，无未提交修改时采集最近一次提交。明确指定范围可避免混入不相关改动。
- 已有本轮真实背景时直接复用。仅对影响归因的代码/文档按文件读取必要片段：

```text
<python> <skill>/scripts/report_context.py --report-dir <repo>/.oil-diff --file <文件ID或相对路径> --max-lines 80
```

输出保留真实行号，默认最多 80 行、单行最多 500 字符；`nextOffset` 非空时按需续读。输出被截断时不能宣称覆盖完整内容。Prefab 查询始终只返回目标信息。禁止用整仓库 `git diff` 或直接读文件绕过这一约定。

编辑 `assets/report-spec.json`，填完骨架中的 `__FILL__` 字段并移除 `_draft`：

- 按实际规模归纳业务事项，小改动可只有 1 项，通常不超过 7 项；无需为凑章节拆分同一件事。
- 每项填 `module`、`title`、`overview` 和 `points`。标题说明哪块业务怎么变；`overview` 用一两句交代已知的前后变化，未知动机不猜。全页 `summary` 概括本轮改动，不重复各章正文。
- **用选择器减少机械抄写**：章节和要点都支持 `files: ["相对路径", "目录/*", "完整文件ID"]`。渲染器自动展开为 `fileIds` 与 `diffs`，并把要点文件纳入章节；未被要点点名的章节文件自动进入外围列表。路径匹配跨全部比较范围，精确到一个范围时使用完整 ID。通配符遵循 Python `fnmatch`，`*` 可跨目录；未匹配项会报错，所有改动仍须归组。原有 `fileIds`/`diffs` 格式继续可用。
- 默认使用骨架的 `diagram.type: "scenarios"`，只填主题与前后短标签。仅列资源目标的章节改用 `diagram: {"type": "targets"}`，由模板列出本章目标；不要为 Prefab 编造前后变化。其它模式的字段只在需要时查参考文件。
- 保留真实截图来源；没有本轮实测图时用内置图示，不去临时目录找图。使用截图需读下方对应规范。

```text
<python> <skill>/scripts/render_report.py --report-dir <repo>/.oil-diff
<python> <skill>/scripts/lint_report.py --repo <repo> --report-dir <repo>/.oil-diff
```

渲染器负责文件覆盖、行号、图示、暖纸布局、文件树、Rider 源码抽屉、移动适配与离线资源。校验器检查未填模板、文案、截图来源、Prefab 内容遗漏策略、DOM 结构和报告目录隔离。

## 核验与交付

- **直接使用内置模板时，只运行上述静态校验，不要求逐份打开窄屏、截图或重复验证移动适配。** 普通文案、文件分组和结构化图示字段变化不触发窄屏核验。
- 只有修改模板布局/CSS/交互或新增自定义 `diagramHtml` 时，才做受影响视口与交互的浏览器检查；细则在视觉参考中。未实测的浏览器/设备不能写成已通过。
- 静态校验 `PASS`，且仓库状态核对无意外变化后，交付 `.oil-diff/index.html` 路径、业务事项、文件数量和必要的覆盖限制。禁止把草稿当成完成报告。

## 局部更新与按需参考

- 只改文案/分组：只读现有 `report-spec.json` 的相关项，复用采集数据后渲染、校验。只核验：直接运行 `lint_report.py`。比较范围或源码变化、旧数据含 Prefab 内容时才重新采集。
- 文案、旧规格和显式行号摘录：[references/copywriting-and-structure.md](references/copywriting-and-structure.md)。普通生成已由本入口与骨架覆盖，不必预读。
- 截图、其它图示模式或模板维护：[references/visual-and-interaction.md](references/visual-and-interaction.md)。按对应小节读取；布局、Rider 配色、完整方法体与 VS Code 定位属于模板维护约束。
- 修改脚本/模板后执行 `python3 -m unittest discover -s <skill>/tests -v`；普通生成报告不运行 Skill 自测。
