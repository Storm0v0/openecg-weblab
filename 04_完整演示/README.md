# 25 条完整演示

用浏览器打开 `OpenECG_Demo.html`。包含 LUDB 10 条、QTDB 10 条、Apple Watch 匿名记录 A–E 五条；默认展示 A，切换记录自动加载。

```sh
python "04_完整演示/build_demo.py"
node "04_完整演示/verify.cjs"
```

以上命令在仓库根目录运行。构建只读取冻结数据，不需要模型依赖。

| 文件 | 内容 |
| --- | --- |
| `template.html`、`base.css`、`app_template.js` | 页面与交互源码 |
| `build_demo.py` | 内嵌 25 条记录、样式与脚本 |
| `data/anonymous_records.json` | 五条 Apple Watch 匿名记录的冻结结果 |
| `data/inputs/*.json` | 每条所选十秒段的 5120 个 PDF 重建输入点 |
| `data/catalog.json`、`data/provenance.json` | 窗口、输入哈希和模型指纹 |
| `extract_pdf_vectors.py` | 从自行提供的 PDF 提取完整十秒输入 |
| `prepare_applewatch.py` | 使用现有模型重现一条记录 |
| `verify.cjs` | 25 条记录的交互、导出和数据绑定检查 |

A 的原窗为 20–30 秒，B/C/D/E 为 10–20 秒。输入来自 PDF 矢量曲线，采样网格标称 512 Hz，展示为 250 Hz，幅值使用相对 mV。没有人工边界标注，人工对照显示不可评价。

从自行提供的 PDF 提取新文件需要 PyMuPDF：

```sh
python -m pip install PyMuPDF
python "04_完整演示/extract_pdf_vectors.py" input.pdf --record C --start 10 --output selected-input.json
```

该命令要求所选范围的每个点均存在，不补零或插值。它不覆盖已有输出。

在已有 Linux Python 3.11 模型环境中重现 C：

```sh
python "04_完整演示/prepare_applewatch.py" --record C --output replay-c.json
```

依赖见 `03_网站与算法源码/requirements-inference.txt`。命令检查实际模型哈希并写入单独的输出，不修改冻结示例；输出中的 `matchesFrozenResult` 表示与当前 C 的完整结果是否相同。
