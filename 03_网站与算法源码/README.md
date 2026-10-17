# 算法与冻结数据

以仓库根 README 为入口。`scripts/coursework_analysis.py` 仅使用 Python 标准库，
计算 QRS 时限和人工区间对照；`scripts/test_coursework_analysis.py` 是其已知答案检查。
`scripts/prepare_demo.py` 与 `scripts/test_prepare_demo.py` 用于可选的原始信号处理/模型生成，
独立依赖见 `requirements-inference.txt`，实际安装版本、模型哈希与原有结果复现核查分别记录在 public 下的生成/核查清单。

`public/demo` 是 20 条冻结预测，`public/analysis` 是派生分析，`source-data` 保留 60 个 WFDB 原始文件。
来源、署名、许可与修改范围见根目录 `docs/来源与许可说明.md`；定量规则见 `docs/定量对照协议.md`。
