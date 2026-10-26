# OpenECG WebLab

[在线演示](http://124.71.24.143/) · [25 条完整演示文件](04_完整演示/OpenECG_Demo.html) · [处理与页面源码](04_完整演示/) · [算法与测量协议](03_网站与算法源码/docs/定量对照协议.md)

单导联心电信号分析课程项目，基于 [OpenECG](https://github.com/vitaldb/openecg)。当前版本包含 **25 条十秒记录：LUDB 10 条、QTDB 10 条、匿名记录 A–E 五条**。仓库公开提供源码和演示，五条个人心电片段按授权以匿名记录 A–E 发布。

## 查看演示

```sh
git clone https://github.com/storm0699/openecg-weblab.git
cd openecg-weblab
```

下载后用浏览器打开 **`04_完整演示/OpenECG_Demo.html`**。样式、脚本和数据已内嵌，无需安装 Python 或 npm 依赖。默认展示匿名记录 A；选择记录后自动展示。页面标题下附有本仓库链接。

在线演示：**http://124.71.24.143/**。华为云已部署当前 25 条匿名记录版本，可直接打开，无需登录 GitHub。

## 功能

- 原始／滤波曲线切换，P、QRS、T 和 R 峰叠加。
- 平均心率、瞬时心率范围、RR 间期和 R 峰数量。
- QRS 起止边界、逐搏时限和汇总统计。
- 公开记录与人工标注的区间配对、边界误差和时限误差。
- 拖动框选、Ctrl+滚轮缩放、表格定位、分类筛选。
- CSV、SVG 和 TXT 导出。

Apple Watch 曲线由 PDF 矢量重建，幅值为相对 mV。五条记录均无人工边界标注，人工对照显示“不可评价”。A 使用原报告 20–30 秒，B/C/D/E 使用 10–20 秒。仅保存当前选中片段及分析结果，不包含原始 PDF 或个人身份信息。

## 构建与检查

需要 Python 3.10+ 和 Node.js，在仓库根目录运行：

```sh
python "04_完整演示/release.py"
```

该命令检查课程算法、输入哈希、25 条记录的自动切换、波形交互和导出，重建 HTML 并更新 `release-manifest.json` 与 `SHA256SUMS`。构建不需要模型依赖，不执行推理或部署。

只构建或检查页面：

```sh
python "04_完整演示/build_demo.py"
node "04_完整演示/verify.cjs"
```

## 目录

| 目录 | 用途 |
| --- | --- |
| `04_完整演示/` | 当前 25 条完整版本、页面源码、五条匿名输入和冻结结果 |
| `03_网站与算法源码/scripts/` | 固定滤波、模型调用、QRS 测量、人工区间配对及测试 |
| `03_网站与算法源码/public/` | 20 条公开记录的冻结预测、测量及来源清单 |
| `03_网站与算法源码/source-data/` | 公开数据库的 60 个 WFDB 源文件 |
| `01_离线演示/` | 保留的 20 条公开示例版 |
| `02_华为云部署/` | 20 条公开示例版的部署文件 |
| `docs/` | 数据来源、许可与项目说明 |

原有 `01_离线演示/release_static.py`、`prepare_github.py` 针对 20 条公开示例版；当前 25 条版本使用 `04_完整演示/release.py`。

## 算法与复现

`输入 → 250 Hz 重采样 → 0.5 Hz 高通 → 0.5–40 Hz 带通 → 50 Hz 陷波 → OpenECG 波形边界与 R 峰 → RR、心率、QRS 时限与人工对照`

QRS 时限为 `(end - start) × 1000` 毫秒，窗口边缘区间不计入汇总；平均心率为各相邻 RR 对应的 `60/RR` 的平均。人工区间按同类、时间重叠和中心距离不超过 150 毫秒生成候选，再按时间顺序一对一配对。规则与阈值见[测量协议](03_网站与算法源码/docs/定量对照协议.md)。

真实模型使用 Linux Python 3.11、OpenECG 0.11.0，依赖见 [requirements-inference.txt](03_网站与算法源码/requirements-inference.txt)。当前 TFLite 模型 SHA-256 为：

```text
2e130ed795491764ffa4f7eff5decc06a4531ac69e1cab51bfbffa714bc0b3fb
```

[完整演示目录说明](04_完整演示/README.md) 提供 PDF 曲线提取和单条模型复现命令。模型权重未随仓库分发。

## 来源与许可

公开数据来自 [LUDB 1.0.1](https://physionet.org/content/ludb/1.0.1/) 和 [QT Database 1.0.0](https://physionet.org/content/qtdb/1.0.0/)，保留 ODC Attribution License v1.0 署名。OpenECG 上游代码采用 Apache-2.0。详见[来源与许可说明](docs/来源与许可说明.md)。

个人 Apple Watch 片段不适用公开数据库的数据许可，按持有人授权以匿名记录 A–E 公开展示。项目调用预训练模型，没有训练新模型；测量及边界结果用于课程演示。
