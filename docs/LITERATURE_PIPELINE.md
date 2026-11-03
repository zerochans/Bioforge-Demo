# OA 文献 → Obsidian → RAG / 知识图谱

日期：2026-10-22  
脚本：`scripts/literature_pipeline.py`  
数据根目录：`/media/h3c/Win11Pro X64/data/literature`

## 目标

把合法开放获取（OA）文献整理成本地、可检索、可追溯的知识库，为配方/机制解释提供文献上下文。它不替代原文阅读，也不把摘要检索结果当成实验证据。

## 数据源与许可

- 主源：Europe PMC REST `search`，查询限定 `OPEN_ACCESS:Y`。
- 每条记录保留 `license`、DOI、PMID、PMCID、期刊、年份、来源链接和 `retrieved_at`。
- 只对许可以 `cc by`、`cc by-nc`、`cc by-nc-nd`、`cc0` 开头的记录尝试下载全文。
- 不绕过付费墙，不使用 Sci-Hub，不抓取未授权 PDF。
- Europe PMC 的 `?pdf=render` 端点对脚本返回 403/Cloudflare 挑战；因此全文优先使用官方 `fullTextXML`，PDF 路径仍保留但成功率取决于来源。
- 公共 API 限速、缓存、重试；失败不会写入伪造内容。

## 命令

```bash
cd /home/h3c/md-agent/bioforge/v3.0.0
PY=/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python

# 采集 1 万条 OA 元数据 + 12 篇全文 + 重建索引 + 导出 Obsidian
$PY scripts/literature_pipeline.py harvest --target 10000 --pdf-limit 12 --build

# 只重建 FTS/知识图谱
$PY scripts/literature_pipeline.py build --export

# 从 Europe PMC 补充 MeSH / 作者关键词 / 化合物，再重建
$PY scripts/literature_pipeline.py enrich --limit 1000
$PY scripts/literature_pipeline.py build --export

# BM25 检索（返回标题、年份、DOI、许可和摘要片段）
$PY scripts/literature_pipeline.py search 'quercetin protein interaction' --limit 8

# 统计
$PY scripts/literature_pipeline.py stats
```

可选参数：

- `--query`：可重复；默认 12 个主题（配方、MD、对接、结构、包埋、美拉德、食品蛋白、多酚、机器学习、知识图谱等）。
- `--root`：覆盖数据根目录。
- `--no-export`：只入库，不生成 Obsidian 笔记。
- `--pdf-limit N`：最多处理 N 篇全文；0 表示只采元数据。

## 产物

```
/media/h3c/Win11Pro X64/data/literature/
├── bioforge_literature.db      # papers / FTS5 / chunks / entities / edges
├── obsidian/<year>/*.md        # 按年份的 Obsidian 笔记
├── fulltext/<paper_id>.md      # OA 全文转换文本
├── xml/<paper_id>.xml          # Europe PMC JATS XML
└── pdf/<paper_id>.pdf          # 可选；受许可与端点限制
```

## 数据库

| 表 | 内容 |
|---|---|
| `papers` | 元数据、许可、摘要、hash、全文路径、抓取时间 |
| `papers_fts` | 标题/摘要/作者/topic/MeSH/keyword/chemical FTS5 |
| `chunks` + `chunks_fts` | 约 1000 字符、150 字符重叠的检索块 |
| `entities` | `paper:` / `concept:` / `author:` / `journal:` 节点 |
| `edges` | `mentions` / `authored_by` / `published_in`，带权重和证据 |

`paper_id` 优先使用 PMID/PMCID，否则用 DOI/标题的 SHA-1 前缀；DOI 唯一约束用于去重。`papers` 额外保存 `mesh`、`keywords`、`chemicals`（JSON 数组），用于检索和 Obsidian 标签；知识图谱仍只用 topic，避免主题词淹没概念图。

## 标签映射

| Obsidian 标签 | 数据库字段 | 含义 |
|---|---|---|
| `topic/<category>` | `category` / `tags` | 规则主题（formulation、docking 等） |
| `mesh/<term>` | `mesh` | Europe PMC MeSH 主题词 |
| `keyword/<term>` | `keywords` | 作者关键词 |
| `chemical/<name>` | `chemicals` | Europe PMC 化学物列表 |

标签是检索线索，不是人工主题标注；同一论文可有多个主题。

## 2026-10-21 实跑

- 10,000 篇 OA 元数据；12 个主题查询，游标分页。
- 10,000 条 Obsidian 笔记。
- 25,062 个 RAG 文本块（重建后；随全文/分块策略变化）。
- 48,544 个实体；76,954 条边。
- 12 篇 OA 全文转为 Markdown。
- 9,197 条有 PMID 记录完成 MeSH/keyword/chemical 富化：3,777 条 MeSH、8,108 条 keywords、3,439 条 chemicals；798 条无 PMID 记录保持原样。
- 数据目录约 157 MB。
- 检索示例：`quercetin protein interaction` 能返回 BSA–槲皮素、网络药理学和分子对接文献。

主题分布前几名（命中的论文数）：蛋白质配方 5,458、安全/毒性 1,509、生物活性 876、分析 733、对接 392、食品蛋白 357、机器学习 234、分子动力学 136。

## RAG 与知识图谱

- 当前 RAG 是词法 BM25/FTS5，不是向量检索；无需 `sentence_transformers`。
- 后续可在 `chunks` 上增加本地 embedding，但必须保留原文和 chunk 定位。
- 知识图谱的边是可追溯的元数据关系；`mentions` 来自标题/摘要关键词，不代表论文证明该概念。
- 可用于：
  - 为机制报告补充文献背景；
  - 按概念/作者/期刊浏览；
  - 从候选配方或靶点反查相关论文；
  - 导出 Obsidian 做人工阅读和双链笔记。

## 限制

- 元数据检索不是系统综述；没有 PRISMA 流程、人工筛查或偏倚评估。
- 关键词标签是规则匹配，可能漏标/误标。
- 摘要与全文可能含预印本、勘误或版本差异；引用前必须核对原文。
- 全文只有 12 篇；1 万篇 PDF 会超出当前磁盘（仅约 1.2 GB 可用）。
- Europe PMC PDF 端点被 Cloudflare 拦截；当前全文本地转换主要来自 JATS XML。
- 文献记录是背景证据，不是湿实验数据，也不能自动生成法规结论。
- MeSH/关键词/化合物是外部元数据，可能缺项、拼写不一致或版本滞后；不要把标签计数当成研究热度或因果证据。
