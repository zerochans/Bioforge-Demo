# 在线数据源、知识库与检索策略（v3.2.2）


## 2026-10-23：PostgreSQL 知识库与合法资源目录

- 主库：PostgreSQL 16.15 + pgvector 0.8.7，容器名 `bioforge-db`，数据卷 `bioforge_pgdata`，仅绑定 `127.0.0.1:5432`。
- 同步：`scripts/start_postgres.sh` 启动容器并执行 `scripts/sync_postgres.py`；后者把 `data/*.json`、SQLite 文献库和 48,544/76,954 条图谱实体/边写入 PostgreSQL。
- 当前规模：10,000 篇文献、25,062 个文本块、361 条 catalog item、16 条 sources、1 个 owner 用户；`literature_chunks.embedding` 为 `vector(1024)`，尚未回填向量。
- 检索：`/api/v3/knowledge/search` 使用 PostgreSQL `tsvector`；数据库不可用时回退 SQLite FTS5。`/api/v3/knowledge/status` 返回 pgvector 版本、表计数、同步与 embedding 状态。
- 资源目录：`data/resources.json` / `/api/v3/resources`，当前 7 组 45 条。每条包含许可、接入状态、官方 URL 和说明。
- 3.2.2 新增 `spectra` 组 7 条：NIST WebBook、SDBS、HMDB、MetaboLights、GNPS、NMREDATA、PDB CCD；这些入口只用于人工核对谱图/结构证据，不做未授权批量抓取。
- 法律边界：目录明确排除 Sci-Hub；不提供付费墙绕过、验证码规避或未授权批量下载。需要机构许可的资源只显示官方入口。
- DOI/PMID：`/api/v3/library/resolve` 解析 DOI/PMID，调用 Crossref、Europe PMC、Unpaywall（需配置 contact email）并返回合法 OA 位置、DOI/PubMed/图书馆/CARSI 链接。
- 机构访问：软件不收集、不记录、不代存校园账号密码；通过 `BIOFORGE_EZPROXY_PREFIX` 只拼接官方 EZproxy 登录 URL，或让用户从 SCUT/CARSI 官方页面登录。
- 联系方式/礼貌池：从 `runtime/secrets/contact.env` 读取 `BIOFORGE_CONTACT_EMAIL`，不写入前端、日志或文档。

## 原则

v2.1 不再把所有数据库都套在每个查询上。先判断实体类型，再选数据库；跨库身份只使用 InChIKey、UniProt accession 或显式 xref 验证。搜索词本身不是身份证明。

## 数据源

| ID | 数据源 | v2.1 用途 | 实体 | 许可/备注 |
|---|---|---|---|---|
| `pubchem` | PubChem PUG REST / PUG-View | 化合物名称锚点、CID、分子式、SMILES、InChIKey、质谱 | compound / complex | public domain (NCBI) |
| `unichem` | UniChem | 用 InChIKey 验证 PubChem↔ChEBI↔ChEMBL 等映射 | compound / complex | CC BY 4.0 |
| `chebi` | ChEBI | 精确 ID 的化合物本体、定义、公式 | compound / complex | CC BY 4.0 |
| `chembl` | ChEMBL | 精确 ID 的生物活性分子记录 | compound / complex | CC BY-SA 4.0 |
| `uniprot` | UniProt | 蛋白名称、accession、物种、PDB/AlphaFold xref | protein / complex | CC BY 4.0 |
| `pdb` | RCSB PDB | 仅列出 UniProt `uniProtKBCrossReferences` 中的 PDB 结构 | protein / complex | 条目各自许可 |
| `alphafold` | AlphaFold DB | 由 UniProt accession 获取预测结构 | protein / complex | CC BY 4.0 |
| `string` | STRING | 用 UniProt accession + taxon 查相互作用伙伴 | protein / complex | CC BY 4.0 |
| `europepmc` | Europe PMC | 文献检索；只作语境证据 | all | metadata CC BY 4.0；摘要按出版商 |
| `fdc` | USDA FoodData Central | 食品组成；失败时回退本地 SR Legacy 快照 | food | 美国公共领域/CC0；`DEMO_KEY` 限速 |
| `openfoodfacts` | Open Food Facts | 包装食品检索 | food | ODbL 1.0 |
| `massbank` | MassBank | **link-only**；不伪装成 JSON 搜索 | compound / complex | 记录各自许可 |
| `genbank` | NCBI GenBank / Protein | 蛋白名称或 accession 的序列记录（E-utilities） | protein / complex | 美国公共领域；accession 为准 |
| `kegg` | KEGG REST | 化合物、通路和酶的可选查询 | compound | 学术使用；再分发受限，使用前核对条款 |
| `zinc` | ZINC | 名称检索；站点对自动 JSON 启用验证码后降级为 **link-only**，不复制数据 | compound / complex | 研究用途；以浏览器打开为准 |

另有 `data/sources.json` 的 16 条 curated 来源（食品体系、配料、相互作用、法规与方法），与在线接口分开计数。界面的“在线源”数量以 `datasources.status()` 为准。

`/api/v2/db/status` 还会返回 `catalog`，列出**不抓取**的许可/机构来源：DrugBank、CCDC、ChemBook（需许可/凭据）、NMRShiftDB2、LIPID MAPS、GlyTouCan（公开参考入口）和高校图书馆（需机构代理）。没有凭据时只显示状态和跳转入口，不复制数据。

## 中英文查询扩展（2026-10-22）

- `backend/query_text.py` 提供共享的中文→英文别名、英文缩写、术语抽取和相关度评分。
- 示例：`乳清蛋白与槲皮素结合` → `whey protein quercetin binding`；术语含 `whey`、`protein`、`quercetin`、`binding`。
- 在线记录和本地文献均返回 `relevance` 和 `strength`（high/medium/low）；这是词面覆盖评分，不是统计显著性。
- 化合物查询与蛋白查询分开：化合物走 PubChem/ChEBI/UniChem/KEGG/ZINC 等，蛋白/靶点走 UniProt/GenBank/STRING/PDB 等。

## 实体分类

`POST /api/v2/db/search` 的 `entity` 可为 `auto`、`compound`、`protein`、`food`、`complex`。

- 显式 `entity` 优先。
- 否则检测蛋白/酶/靶点词、食品/配方词、相互作用词。
- 没有蛋白或食品语境时默认 `compound`，只查化合物与文献库，避免把配体名送进 UniProt/PDB/STRING/FDC。
- `complex` 用于“化合物-蛋白对接/结合”类查询，同时查两侧并以标识符连接。

来源策略：

```text
compound: pubchem, unichem, chebi, chembl, europepmc, massbank(link-only)
protein:  uniprot, pdb, alphafold, string, europepmc
food:     fdc, openfoodfacts, europepmc
complex:  pubchem, unichem, chebi, chembl, uniprot, pdb, alphafold, string, europepmc, massbank(link-only)
```

如果显式请求的来源与实体不匹配，返回 `plan.rejected_sources`，不会执行该来源。

## 身份验证链

1. PubChem 名称查询得到 CID、InChIKey。
2. UniChem 用 InChIKey 返回 ChEBI/ChEMBL/DrugBank/HMDB 等映射。
3. ChEBI/ChEMBL 只按 UniChem 返回的精确 ID 取详情；没有精确映射时才用名称搜索，并标记 `match_basis=name_search`。
4. PDB 只取 UniProt 的 PDB xref，不再用 PDB 全文检索猜结构。
5. 每条记录包含 `match_basis` 与 `relevance`。
6. 交叉链接类型只有：
   - `exact_inchikey`
   - `uniprot_pdb_xref`
   - `spectrum_reference`

v2.0 的 `same_compound_candidate` 名称匹配与 `sequence_structure_candidate` 全文命中已删除。

## 示例

```http
POST /api/v2/db/search
Content-Type: application/json

{"query":"quercetin","entity":"auto"}
```

v2.1 实测结果（2026-10-20）：

- entity = `compound`
- PubChem CID `5280343`
- InChIKey `REFJWTPEDVJJIY-UHFFFAOYSA-N`
- UniChem → `CHEBI:16243`、`CHEMBL50`、`DB04216`、`HMDB0005794`
- MassBank `link_only`，谱图 accession 通过 PubChem 谱图引用
- 没有调用 UniProt、PDB、STRING、FDC、Open Food Facts

蛋白示例 `beta-lactoglobulin`：

- UniProt 返回 `P02754` 等记录
- PDB 通过 UniProt xref 返回 `1B0O`、`1B8E` 等
- STRING 使用 `P02754 + taxon 9913`（牛），不再硬编码人类 9606
- 不调用 PubChem 作为蛋白身份

## 食品与 FDC

- FDC 实时 API 需要 key；`DEMO_KEY` 会返回 429。
- 失败时自动回退到版本化快照 `data/ingredient_composition.json`，状态为 `degraded`，记录标记 `match_basis=local_fdc_snapshot`。
- 快照来源：USDA FDC SR Legacy 2018-04，7,793 条，zip SHA-256 `70d4235ae3a2bdf48a7b9eaa1286a83fa67b6f3270436c9ce8b008213f500129`。
- FDC 是参考组成数据，不是供应商批次检测。
- Open Food Facts 使用 legacy CGI `search.pl`（v2 search 端点的全文本行为不稳定），并按名称/类别做相关性过滤。

## 缓存、限速与失败

- 缓存：`runtime/cache/`，24 小时；缓存键带 v2.1 版本后缀。
- 单源失败写入 `sources.<id>.status = "error"`，不会让整个请求失败。
- `db/search` 40 次/分钟；`design` 20 次/分钟。
- KEGG 默认不查询（条款限制）；MassBank 仅链接记录页。
- 在线记录不能替代法规文本、实验测量或安全结论。

## 与需求清单的对应关系（2026-10-22）

| 需求 | 当前状态 | 说明 |
|---|---|---|
| RCSB PDB | 已接入 | 通过 UniProt xref 列结构，不把名称猜测当结构身份 |
| UniProt | 已接入 | 蛋白名称/accession/物种/xref |
| GenBank | 已接入 | NCBI protein E-utilities，accession 为稳定链接 |
| DrugBank | 未接入（需许可） | 只登记 `catalog`，无 API key 不查询 |
| PubChem | 已接入 | CID、性质、InChIKey、GC-MS 谱峰 |
| KEGG | 已接入 | 化合物/通路文本搜索；学术使用，再分发受限 |
| ZINC | link-only | 站点对自动 JSON 启用验证码；只提供跳转，不复制数据 |
| ChemBook | 未接入（需凭据） | 需要机构入口/授权 |
| CCDC | 未接入（需许可） | 晶体结构库需机构订阅 |
| 蛋白/多肽 | 部分 | UniProt/GenBank/PDB/AlphaFold/STRING；缺少专门的多肽库 |
| 多糖/聚糖 | 参考入口 | GlyTouCan accession 参考；未批量接入聚糖结构库 |
| 脂质 | 参考入口 | LIPID MAPS 分类参考；未批量接入 |
| 小分子 | 已接入 | PubChem/ChEBI/ChEMBL/UniChem/KEGG/ZINC link-only |
| NMR | 参考入口 | NMRShiftDB2；未接入谱图搜索 |
| UV/IR | 未接入 | 无公开、稳定、可自动查询的通用授权端点；不伪造数据 |
| MS | 部分 | PubChem GC-MS 谱峰 + MassBank link-only |

未接入的库不会出现在“可查询源”列表；如果后续提供 API key、机构代理或明确许可，可按同一连接器模式增加。
