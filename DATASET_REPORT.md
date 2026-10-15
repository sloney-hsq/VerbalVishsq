# Dataset boundary verification

更新：2026-10-13。该文件记录通用 DatasetAdapter 边界；Olist 的指标口径、对抗性 fixture 与真实数据结果见 [OLIST_ADAPTER_REPORT.md](OLIST_ADAPTER_REPORT.md)。

## 边界 Contract

- 数据集是受信任的本地 Python interface，不是任意代码沙箱。
- `describe / tool_definitions / execute / close` 为必需方法。
- Tool parameters 使用 JSON Schema，数据集工具只读；图表变更由公共 Toolbox 在 private draft 中完成。
- 结果必须包含稳定的 `rows / columns / truncated / dataset_version`；每行 key 与 columns 完全一致。
- 时间单元格使用 ISO 值，quantitative 单元格禁止 NaN/Infinity，数组或对象不能嵌入表格单元格。
- 加载、执行与 close 由 adapter lock 串行化；动态模块在失败和 close 后清理。

## 当前接口

| Dataset | 数据 | 公开数据集工具 | 说明 |
|---|---|---|---|
| Olist | 9 张真实 CSV | `aggregate`, `compare_segments` | order/item/payment/customer/seller×order grains；多表先聚合后关联 |
| Education | 明确标注的 synthetic CSV | `summarize_learning` | 用于验证非电商接口可插拔性，不是用户研究数据 |

Olist 旧 `compare_commerce` 已从 Tool Schema 和回归调用中删除，不保留给模型可见的兼容别名。

## 验证

2026-10-13 根代理 fresh run：

```text
python -m pytest tests -q
121 passed, 1 warning in 6.30s
```

warning 是 Starlette TestClient 对 httpx 的既有 deprecation warning，不是 dataset correctness 失败。

真实 Olist smoke：

- version：`olist-5-8e2b55985d02985e`；
- 9 张 raw tables 全部存在；
- delivered order count：96,478；
- merchandise revenue：BRL 13,221,498.11；
- Task A：SP weekly 27 rows / 15,495 orders；
- Task B：RJ office_furniture 212 orders vs bed_bath_table 1,357 orders。

测试通过不意味真实 Provider、语音交互或用户研究已完成。
