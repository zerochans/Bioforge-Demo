# 本地机制计算

## 工具链

| 工具 | 本机路径/版本 | 用途 |
|---|---|---|
| AutoDock Vina | `molecule_tools` 环境，1.2.7 | 刚性受体对接（小分子默认） |
| Meeko | 0.8.0 | 受体/配体 PDBQT 准备 |
| GROMACS | `qmmm_env/bin.AVX2_256/gmx`，2025.3 | 溶剂化、EM、NVT MD；支持蛋白-配体复合物 |
| ACPYPE | `molecule_tools/bin/acpype`，2023.10.27 | 复合物配体 GAFF2/AM1-BCC 拓扑 |
| CP2K | `qmmm_env/bin/cp2k.ssmp`，2023.2 | 配体 PBE/DZVP 单点 |
| Open Babel | `mychem/bin/obabel`，3.1.0 | 格式转换/质子化 |
| HADDOCK3 | `/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/haddock3`，2026.5.0 | 蛋白-蛋白、蛋白-配体、蛋白-多糖独立对接/精修任务 |
| OpenMM | 8.4（仅 Reference） | 不用于生产 MD |

任务入口：

```http
POST /api/v2/compute/mechanism
Content-Type: application/json

{"query":"乳清蛋白与槲皮素对接、短MD和QM"}
```

或关联已有设计：

```json
{"design_id":"F...","options":{"md_steps":2000,"temperature_k":310}}
```

## 可调参数

`options` 会先做类型转换和边界夹取，非法值回退到默认值，不会让任务直接崩溃。

| 键 | 默认 | 范围 | 说明 |
|---|---:|---:|---|
| `docking_enabled` | true | bool | 关闭后跳过对接 |
| `docking_exhaustiveness` | 8 | 1–64 | Vina 搜索强度 |
| `docking_poses` | 9 | 1–20 | 输出构象数 |
| `docking_box_size` | 26 | 16–48 Å | 对接盒边长 |
| `docking_seed` / `seed` | 自动 | 0–2³¹−1 | 留空时由任务 UUID 生成 |
| `md_enabled` | true | bool | 关闭后跳过 GROMACS |
| `md_mode` | complex | `complex`/`protein` | 复合物拓扑+短 NVT；失败时回退并记录 |
| `em_steps` | 5000 | 50–5000 | 能量最小化步数；复合物默认 5000，300 步常因初始 clash 未收敛 |
| `md_steps` | 1000 | 100–100000 | NVT 步数 |
| `dt_ps` | 0.002 | 0.001–0.004 | 积分步长（ps） |
| `temperature_k` | 300 | 250–400 | NVT 温度 |
| `box_padding_nm` | 0.8 | 0.6–1.5 | 溶剂化盒边距 |
| `threads` | min(8, CPU) | 1–64 | GROMACS/CP2K 线程 |
| `timeout_prepare` | 300 | 30–3600 | 准备阶段超时（秒） |
| `timeout_docking` | 600 | 30–7200 | 对接阶段超时 |
| `timeout_em` | 900 | 30–7200 | EM 超时 |
| `timeout_md` | 1800 | 30–7200 | MD 超时 |
| `qm_enabled` | true | bool | 关闭后跳过 CP2K |
| `qm_cutoff_ry` | 300 | 150–600 | CP2K CUTOFF（Ry） |
| `qm_max_scf` | 50 | 10–200 | CP2K 最大 SCF 步 |
| `timeout_qm` | 600 | 30–7200 | QM 超时 |
| `haddock_enabled` | false | bool | 开启后运行 HADDOCK3-only 任务，跳过 Vina/MD/QM |
| `haddock_workflow` | protein-protein | `protein-protein`/`protein-ligand`/`protein-polysaccharide` | HADDOCK3 工作流 |
| `haddock_receptor` | — | PDB ID/名称/UniProt 映射 | 受体；留空时从 query 解析 |
| `haddock_receptor_chain` | 自动 | 单字符 | 留空自动选择首个非糖链 ATOM 链 |
| `haddock_partner` | — | PDB ID/名称/SMILES | 蛋白/糖链伙伴或配体 |
| `haddock_partner_chain` | 自动 | 单字符 | 蛋白-多糖时选择糖链；配体忽略 |
| `haddock_active_receptor` | — | 残基列表/范围 | 逗号、空格或 `10-20` |
| `haddock_active_partner` | — | 残基列表/范围 | 配体通常填 `1` |
| `haddock_restraint_radius` | 6.5 | 0–30 Å | 被动残基扩展半径 |
| `haddock_max_restraints` | 200 | 1–1000 | 约束上限 |
| `haddock_sampling` | 20 | 1–500 | 刚体采样数；`crossdock=false` |
| `haddock_tolerance` | 5.0 | 0–99 | CAPRI 聚类/评分容差 |
| `haddock_select_top` | 5 | 1–100 | 进入精修的模型数 |
| `haddock_flexref` / `haddock_emref` | true | bool | 半柔性/能量最小化精修 |
| `haddock_cluster` | true | bool | 聚类并选代表模型 |
| `haddock_min_population` | 1 | 1–100 | 最小簇大小 |
| `haddock_top_models` | 4 | 1–50 | 输出模型数 |
| `haddock_clust_cutoff` | 1.5 | 0.1–20 Å | 配体聚类 RMSD 截断 |
| `haddock_ncores` | min(8, CPU) | 1–64 | HADDOCK3 核数 |
| `haddock_seed` | 917 | 0–10^16−1 | 随机种子 |
| `haddock_timeout` | 1800 | 60–14400 s | 单次 HADDOCK3 超时 |
| `haddock_w_vdw` / `haddock_w_elec` | 1.0 | 0–100 | vdW/静电权重 |
| `haddock_inter_rigid` | 1.0 | 0–1 | 刚体界面权重（仅 rigidbody） |
| `haddock_epsilon` | 10.0 | 1–78 | 介电常数 |
| `haddock_cmrest` / `haddock_ranair` | true/false | bool | 无活性残基时的约束回退 |
| `haddock_mdsteps_rigid` / `haddock_mdsteps_cool1` | 500 | 0–10000 | flexref 刚体/冷却步数 |

能力与默认值：`GET /api/v2/compute/capabilities`。工具路径：`GET/PUT /api/v3/tools`，见 `docs/API_V3.md`。

## 步骤

1. `resolve`：从 query 识别蛋白与配体。内置：乳清蛋白/β-乳球蛋白→1BEB，GFP→1GFL，溶菌酶→1LYZ，白蛋白→1AO6，藻蓝蛋白→1GH0；配体：槲皮素、姜黄素、咖啡因、芦丁、白藜芦醇。
2. `prepare`：下载/缓存 PDB，`mk_prepare_receptor.py` 生成 receptor.pdbqt/json；配体从 SMILES 生成 3D，`mk_prepare_ligand.py` 生成 ligand.pdbqt。对接关闭时仍会产出 `receptor.pdb` / `ligand.sdf`。
3. `docking`：Vina；盒子、采样、构象数、种子来自配置；输出 `vina_result.json` 与 `poses.pdbqt`。
4. `gromacs`：纯 ATOM PDB → `pdb2gmx -ff amber99sb-ildn -water tip3p` → `editconf` → `solvate` → `grompp em` → `mdrun em` → `grompp md` → `mdrun md`。复合物模式先把对接 pose 映射到配体模板，ACPYPE 生成 GAFF2/AM1-BCC `LIG_GMX.itp/.gro`；合并蛋白+配体 gro，在 forcefield 后插入 `LIG.acpype/LIG_GMX.itp`，`genion -neutral` 后用合并拓扑跑 EM/NVT。ACPYPE 或拓扑失败时回退蛋白-only，写入 `complex_error`。
5. `cp2k`：配体 3D → XYZ → PBE/DZVP-MOLOPT-GTH 单点；C/H/O 使用 GTH-PBE-q4/q1/q6；CUTOFF、SCF 步数和线程可调。
6. `report`：`report.md`、`report.html`，汇总对接分数、EM 势能、MD 时长、QM 能量、参数 JSON、运行指纹、命令和限制。

阶段失败相互隔离：某一阶段报错会记录到 `steps[].error` 和报告，已完成阶段保留；全部启用阶段结束后任务状态仍可为 `complete`。

HADDOCK3 任务走独立管线，不混入 Vina/MD/QM：

1. `resolve`：解析受体、伙伴/配体；蛋白-配体用 RDKit 生成 3D 配体 PDB，蛋白-多糖识别 `NDG/NAG` 等糖链。
2. `prepare`：下载/缓存 PDB，拆分并重写链（受体 A、伙伴 B），生成 `ambig.tbl`（活性残基 + 被动残基）或回退到 `cmrest`/`ranair`；写出 `haddock.cfg` 与 `haddock_inputs.json`。
3. `haddock`：执行 `haddock3 haddock.cfg`；按参数运行 rigidbody → caprieval → flexref/emref → clustfcc/clustrmsd → seletopclusts。
4. `report`：复制 `best_model.pdb`、`capri_ss.tsv`、`capri_clt.tsv`、`haddock_analysis.html`，写 `haddock_models.csv`、`report.md`、`report.html`。

HADDOCK score 使用任意单位（a.u.，越低越好），不是结合自由能；没有实验参考结构时不把 CAPRI RMSD 当作验证。score ≥ 9999 的拒绝/无分数模型会被过滤。

## 运行指纹

`parameter_fingerprint` 是目标（PDB ID、SMILES、配体）与规范化配置的 SHA-256。相同参数重跑得到相同指纹，便于比较；它不是结果哈希，也不保证数值逐位相同。

实测：

- seed 42 与 seed 43：Vina `-7.475` vs `-7.465 kcal/mol`，指纹不同。
- CP2K 单点 32 atoms：`-203.4343556229248 Ha`（`-5535.73 eV`），约 36 s。

## 超时与进程清理

- `_run` 使用 `Popen(start_new_session=True)`；超时向整个进程组发 SIGTERM，等待后仍存活则 SIGKILL。
- 这样可避免 GROMACS/CP2K 子进程变成孤儿并继续占用 CPU。
- 输出、错误和返回码写入 `job.json`，日志保留在任务目录。

## 实测耗时（本机）

| 步骤 | 时间 |
|---|---|
| 准备 + Vina | 约 10–20 s |
| GROMACS 蛋白-only EM + 0.2–2 ps NVT（按 `md_steps`） | 约 40–70 s |
| GROMACS 复合物 EM + 0.2 ps NVT（1BEB+quercetin，10,000+ atoms） | 约 60–120 s（含 ACPYPE） |
| CP2K 单点（32 atoms，8 threads） | 约 36–90 s |
| 全流程 | 约 2–4 min |

任务在后台线程运行；UI 每 5 秒轮询 `GET /api/v2/compute/jobs/{id}`。artifact 通过 `GET .../artifacts/{path}` 下载。

## HADDOCK3 工作流

- 已接入 `POST /api/v2/compute/mechanism`：`options.haddock_enabled=true` 时创建 HADDOCK3-only 作业，步骤为 `resolve`/`prepare`/`haddock`/`report`，并强制关闭 Vina/MD/QM。
- 支持 `protein-protein`、`protein-ligand`、`protein-polysaccharide`；配体用名称/SMILES，糖链 PDB 可写 `1LMQ:B`。
- UI 的 HADDOCK3 卡片暴露采样、容差、select top、flexref/emref、聚类、最小簇、输出模型、聚类截断、核数、种子、超时、vdW/静电/界面权重、介电常数和 mdsteps；所有数值进入 `haddock.cfg`。
- 蛋白-配体需要 RDKit；蛋白-多糖依赖 HADDOCK3 的碳水化合物模板。运行前检查 `haddock/haddock_inputs.json`、`haddock/haddock.cfg` 和 `haddock/stdout.log`。
- 示例配置：`/home/h3c/softwares/haddock3/examples/`。

## 关键环境修复

- `OMP_NUM_THREADS` 必须与 `gmx mdrun -nt` 一致。
- `pdb2gmx` 只接受纯 `ATOM` 行；下载的 PDB 需去除 `HETATM`/硫酸根等。
- 力场重复发现问题：把 `amber99sb-ildn.ff` 复制到任务目录，运行时移除 `GMXLIB`，使用 `-ff amber99sb-ildn`。
- 复合物拓扑中 `LIG.acpype/LIG_GMX.itp` 必须放在 forcefield 之后、protein chain topology 之前，否则 `grompp` 报 `Invalid order for directive atomtypes`。
- `genion` 通过 stdin 输入 `SOL`；后台调用必须设置 `stdin=PIPE`，否则报 `Cannot read from input`。
- CP2K 必须使用 `DZVP-MOLOPT-GTH`，不是 `DZVP-MOLOPT-SR-GTH`；并显式加 `&XC / &XC_FUNCTIONAL PBE`。
- CP2K 数据路径：`share/BASIS_MOLOPT`、`share/GTH_POTENTIALS` 符号链接到 `share/cp2k/data/`。
- OpenMM 只有 Reference 平台，不作为默认引擎。

## 结果解释

- Vina affinity 是打分函数，不是结合自由能；不能直接换算 Kd。
- 复合物 MD 从刚性对接 pose 出发，只做短 NVT；能检查配体是否留在结合位点、拓扑/溶剂化是否稳定，但不证明结合模式或结合自由能。
- 1BEB+quercetin 实测首轮 EM 5000 步后 Fmax 仍为 5707.8 kJ/mol/nm；自动二次 EM 244 步收敛到 456.8。默认 5000 步并自动续跑，但仍必须检查 `result.gromacs.em_converged`/`em.log`。
- 自动 ACPYPE 电荷与质子化、蛋白质子化态、互变异构、金属/辅因子/膜环境需要人工复核；EM 未收敛时仍可能继续 NVT，必须查看 `em.log` 的 `Fmax`。
- CP2K 单点是配体气相/周期盒电子结构，不含蛋白口袋、溶剂和熵；不能单独证明机制。
- 所有结果都需要更长 MD、MM/PBSA、QM/MM 或实验验证。

## 失败排查

- 查看 `runtime/compute/<id>/job.json` 的 `steps[].detail`、`result.<stage>.error` 和对应日志。
- `receptor.pdb` 是否含非标准残基；`gromacs/em_mdrun.log` 是否有原子/电荷错误。
- `cp2k/cp2k.out` 是否找到 basis/potential；确认 symlink。
- 若 `gmx` 报线程不整除，检查 `OMP_NUM_THREADS`。
- 工具路径错误：`PUT /api/v3/tools` 会返回具体缺失/不可执行项。
