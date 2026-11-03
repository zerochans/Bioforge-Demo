# 21 个端到端案例

所有案例均可从 `/api/v2/cases` 或 Web 案例库复现。多数体系返回 8 个候选，果冻等策略较少的体系返回 7 个；`selected` 是综合评分最高的候选，`portfolio` 包含全部候选。

| ID | 标题 | 关键约束 | 当前结果（示例） |
|---|---|---|---|
| `case_bread_high_protein` | 高蛋白软面包 | 蛋白 ≥ 12%、无麸质、7 天 | 稳定性优先；pH 5.6、P 13.7%、S 3.2%、Na 688 mg |
| `case_yogurt_low_sugar` | 低糖酸奶 | 糖降低 40%、清洁标签 | 植物基；pH 4.5、P 15.1%、S 2.5%、Na 0 |
| `case_plant_meat` | 植物基肉饼 | 蛋白 ≥ 18%、无大豆 | 稳定性优先；pH 6.2、P 19.2%、S 0.8%、Na 381 mg |
| `case_gummy_natural` | 天然色素软糖 | 无合成色素、pH 3.4 | 高蛋白策略；pH 3.4、P 6.8%、S 56.2%；甜菜红 + 花青素 |
| `case_sauce_low_sodium` | 低钠番茄酱 | 钠降低 30%、pH 3.7 | 均衡型；pH 3.7、Na 470 mg |
| `case_ice_cream_plant` | 植物基冰淇淋 | 无乳、清洁标签 | 感官优先；pH 6.6、P 1.9%、燕麦 14% + 椰子油 |
| `case_phycocyanin` | 藻蓝蛋白饮料 | 酸性、护色 | 清洁标签；pH 4.2、藻蓝蛋白 0.15%；工艺温度警告 |
| `case_polyphenol_dock` | 乳清蛋白-槲皮素机制 | 对接/MD/QM | 清洁标签；pH 3.8、槲皮素 0.05% |
| `case_clear_apple_juice` | 澄清苹果汁 | 糖 ≤ 8%、pH 3.5、80°C 15 秒 | 果汁饮料；控制褐变与货架期 |
| `case_oat_milk_uht` | 燕麦奶植物基饮料 | 无乳、蛋白 ≥ 3%、UHT 121°C 4 秒 | 植物基饮料；控制沉淀与口感 |
| `case_low_sugar_sponge_cake` | 低糖海绵蛋糕 | 糖降低 30%、aw ≤ 0.85、14 天 | 烘焙；保持蛋香与蓬松 |
| `case_low_salt_sausage` | 低盐乳化香肠 | 钠降低 35%、蛋白 ≥ 12%、冷藏 30 天 | 肉制品；控制出水 |

## 说明

- 表中的数值是当前模板/先验结果，会随数据或算法调整变化；以 API 返回为准。
- “约束达标”指该候选满足该体系的硬约束；不等于法规、安全或感官验收。
- 软糖案例会出现“高蛋白”策略候选：这是策略组合为了展示蛋白强化方向而加入少量乳清，并不表示产品必须有蛋白目标。属于已知的展示性瑕疵，不影响约束判断。
- 面包含微量 β-胡萝卜素，来自天然色素/功能组合的候选路径；实际配方应做感官和法规复核。
- 案例用于演示“多答案 + 证据 + 机制”，不是可直接生产的配方。

## 复现

```bash
curl -s -c c.txt -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"bioforge-demo"}' \
  http://127.0.0.1:8010/api/auth/login

curl -s -b c.txt -H 'Content-Type: application/json' \
  -d '{"query":"设计一款高蛋白软面包，蛋白质 ≥ 12%，无麸质，保质期 7 天，成本适中","options":{"mode":"food"}}' \
  http://127.0.0.1:8010/api/v2/design
```
## 2026-10-22 新增加工案例（共 17 个）

| ID | 标题 | 体系 | 关注点 |
|---|---|---|---|
| `case_protein_bar_high_protein` | 高蛋白谷物棒 | cereal_bar | ['high_protein', 'texture', 'shelf_life'] |
| `case_extruded_high_fiber` | 高纤挤压膨化零食 | snack_extruded | ['high_fiber', 'low_sodium', 'extrusion'] |
| `case_kimchi_low_salt` | 低盐发酵泡菜 | fermented_vegetable | ['low_sodium', 'fermentation', 'safety'] |
| `case_edible_film` | 可食性保鲜膜 | edible_film | ['edible_film', 'antioxidant', 'barrier'] |
| `case_probiotic_powder` | 益生菌固体饮料 | powder_drink | ['probiotic', 'low_sugar', 'shelf_life'] |
| `case_low_sugar_jelly` | 低糖高纤果冻 | jelly | ['low_sugar', 'high_fiber', 'gelation'] |
| `case_uht_milk` | 超高温灭菌乳 | dairy_milk | ['uht', 'protein', 'maillard'] |
| `case_low_fat_mayo` | 低脂蛋黄酱 | sauce_emulsion | ['low_fat', 'emulsion', 'stability'] |
| `case_reduced_sugar_chocolate` | 减糖黑巧克力 | confectionery_chocolate | ['low_sugar', 'crystal', 'shelf_life'] |

新增案例覆盖挤压膨化、发酵蔬菜、益生菌固体饮料、低糖果冻、UHT 乳、低脂蛋黄酱和减糖巧克力。所有案例的 `selected` 候选在本地回归中通过硬约束；案例数值仍随数据/算法调整，以 API 返回为准。

