# OpenECG WebLab

**[打开在线 ECG 演示](http://124.71.24.143/)** · [算法与测量协议](03_网站与算法源码/docs/定量对照协议.md) · [数据来源与许可](docs/来源与许可说明.md)

基于 [OpenECG](https://github.com/vitaldb/openecg) 的单导联心电信号分析课程项目，包含 LUDB 与 QTDB 各 10 条、共 20 条十秒演示记录。
OpenECG 提供预训练波形分界模型和 QRS 检测；本项目实现信号处理流程集成、QRS 时限测量、人工区间定量对照、静态交互和部署。
所有示例均已离线计算，网页不接受文件导入，不上传信号，也不执行在线模型推理。
当前源码仓库为私有，查看和克隆需要获得仓库访问权限；在线演示独立提供访问，老师查看演示无需先访问 GitHub。

## 演示功能

- 打开页面自动展示 LUDB 16，点击数据库或选择其他记录后自动切换展示。
- 对比重采样后的原始曲线与滤波曲线，叠加 P/QRS/T 预测、人工标注和 R 峰。
- 查看逐搏 RR、瞬时心率、平均/最低/最高心率，以及 QRS 起止时间和估计时限。
- 查看人工区间配对率、起止边界误差、时限误差和双边界阈值达标率。
- 缩放、悬停读数、从表格定位到局部波形，按波形类别或对照状态筛选明细。
- 导出波形与测量 CSV、当前视图 SVG 和结果说明 TXT。

在线 HTTP 服务和首页访问已核验，初始演示页面已由使用者确认可见；自动浏览器在当前客户端受到限制，尚未完成全套真实浏览器交互与下载验收。

## 下载和本机查看

```sh
git clone https://github.com/storm0699/openecg-weblab.git
cd openecg-weblab
```

最直接的方式是用现代浏览器打开 `01_离线演示/OpenECG_Demo.html`。波形、样式、脚本和统计均已内嵌，不需要安装 Python 包或 npm 依赖。

也可以用 Python 3 启动本机 HTTP 服务：

```sh
cd "02_华为云部署"
python server.py --host 127.0.0.1 --port 8080
```

打开 [本机演示](http://127.0.0.1:8080/)，按 `Ctrl+C` 停止服务。服务只提供首页和 `/health` 健康检查。
若要安装到 Ubuntu 服务器，参见[部署说明](02_华为云部署/部署说明.md)，默认 HTTP 80 端口，无需端口后缀。
仓库记录可直接访问的演示网址，但不包含 SSH 凭据、用户内部路径、私钥或私有部署记录。

## 重建分析和静态页面

在仓库根目录执行，需 Python 3.10 或更高版本及 Node.js；静态构建仅使用 Python 标准库，无需 pip/npm 安装：

```sh
python "01_离线演示/release_static.py"
```

该命令重新计算冻结预测之上的课程测量与人工对照，运行算法测试和模拟 DOM 检查，重建 HTML，核验本机 HTTP 服务，并生成部署 ZIP 和 SHA-256 清单。它不重新运行 OpenECG 模型，也不连接服务器。
当前检查包括 16 项测量测试、19 项生成保护测试、17 类损坏记录恢复，以及 20 条记录的自动切换与导出逻辑。模拟 DOM 检查不代替真实浏览器验收。

只核查算法时可分别运行：

```sh
python "03_网站与算法源码/scripts/test_coursework_analysis.py"
python "03_网站与算法源码/scripts/test_prepare_demo.py"
```

## 算法流程与核心文件

`公开 ECG → 250 Hz 重采样 → 基线校正/带通/工频滤波 → OpenECG 波形分界与 R 峰 → 测量与人工对照 → 静态展示`

| 文件 | 作用 |
| --- | --- |
| [prepare_demo.py](03_网站与算法源码/scripts/prepare_demo.py) | 读取 WFDB、固定十秒窗口、滤波、调用模型并保存预计算结果 |
| [coursework_analysis.py](03_网站与算法源码/scripts/coursework_analysis.py) | QRS 时限、R 峰关联、人工区间一对一配对和误差汇总 |
| [demo_catalog.py](03_网站与算法源码/scripts/demo_catalog.py) | 20 条记录的数据库、导联、标注扩展名和时间窗口 |
| [download_demo_sources.py](03_网站与算法源码/scripts/download_demo_sources.py) | 从 PhysioNet 下载源文件并核对官方 SHA-256 |
| [app.js](01_离线演示/app.js) | 波形绘制、缩放、定位、筛选及导出 |
| [build_demo.py](01_离线演示/build_demo.py) | 将数据、分析、样式和交互内嵌为单文件 HTML |

固定预处理包括二阶 0.5 Hz 高通基线校正、三阶 0.5–40 Hz 带通及 50 Hz 陷波（Q=30），均采用前后向滤波。页面“原始信号”已统一至展示采样率，但尚未经过后续滤波。

QRS 时限按 `(end - start) × 1000` 毫秒计算，可能被窗口截断的区间不进入时限汇总。RR 为相邻 R 峰的时间差，逐 RR 心率为 `60 / RR秒数`，平均心率取这些逐 RR 心率的算术均值。
250 Hz 对应 4 毫秒采样步长，不代表模型达到 4 毫秒测量精度。

人工 P/QRS/T 区间按类别做保序一对一匹配，候选需时间重叠且中心相差不超过 150 毫秒；误差方向为“预测减人工”。配对率和双边界达标率均以完整人工区间数为分母。
未标注部分不计误检；没有完整人工区间的类别显示不可评价，不输出准确率、精确率或 F1。具体阈值及配对规则见[定量对照协议](03_网站与算法源码/docs/定量对照协议.md)。
缩放、定位和筛选只改变查看范围，页面统计与 CSV 始终基于完整十秒记录；SVG 导出当前波形视图。

## 可选：真实模型运行环境

真实模型流程使用 Linux Python 3.11 与 `openecg[deploy]==0.11.0`；依赖组合见 [requirements-inference.txt](03_网站与算法源码/requirements-inference.txt)，实际包版本、模型哈希和运行范围见 `03_网站与算法源码/public/` 内的生成及复现清单。
Windows/Python 3.12 的静态分析与网页构建无需模型依赖；不承诺该平台能直接运行 TFLite 推理。模型权重未随仓库分发，获取和使用遵循上游条款。

在独立 Linux 实验副本中安装推理环境：

```sh
python3.11 -m venv .venv-inference
source .venv-inference/bin/activate
python -m pip install -r "03_网站与算法源码/requirements-inference.txt"
python "03_网站与算法源码/scripts/prepare_demo.py" --new-only
```

`--new-only` 逐字节保留有效的现有记录，只推理缺失条目；仓库中已有全部 20 条时仅校验，不运行模型、不覆盖推理清单。
在实验副本中去掉该参数可全量重跑，但会替换 `public/demo/` 结果；发布保护检查会报告其与冻结结果的差异。

## 数据与计算溯源

- `03_网站与算法源码/source-data/`：60 个官方 WFDB 文件；来源 URL、官方哈希与选窗依据见 `public/source_manifest.json`。
- `03_网站与算法源码/public/demo/` 和 `public/analysis/`：20 条冻结预测与派生测量；每份分析记录其输入 JSON 的 SHA-256。
- `public/generation_manifest.json`：最近一次新增 6 条的实际运行证据，同时列出保留 14 条的哈希；模型运行信息只适用于所列新增记录。
- `public/generation_history/generation_14_records_20261018.json`：此前十四条生成清单的原字节副本。
- `public/model_replay_audit.json`：最初四条与实际模型环境的复现核查。
- `public/preservation_14_records_manifest.json`：保护既有十四条预测、十四份分析和四十二个源文件的七十文件哈希清单。

以上 `public/` 路径均位于 `03_网站与算法源码/`。根目录 `release-manifest.json` 与 `SHA256SUMS` 记录发布文件，便于复核完整性。

## 来源、许可与局限

源数据来自 [LUDB 1.0.1](https://physionet.org/content/ludb/1.0.1/) 与 [QT Database 1.0.0](https://physionet.org/content/qtdb/1.0.0/)，按 ODC Attribution License v1.0 保留数据署名。
[OpenECG](https://github.com/vitaldb/openecg) 上游代码采用 Apache-2.0；模型、数据和第三方组件继续适用各自条款。作者、DOI、官方链接与派生变换详见[来源与许可说明](docs/来源与许可说明.md)。
课程新增代码尚未单独选择对外授权许可证，不将第三方组件统一重新授权。

本项目没有训练新模型，也没有实物采集功能。演示记录可能与预训练模型的训练数据重叠，不能作为独立泛化测试。人工区间对照及展示阈值用于课程分析，不构成临床诊断或临床有效性证据。
