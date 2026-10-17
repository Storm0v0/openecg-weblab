"""Prepare a whitelist-only public repository snapshot; never publish it.

Python standard library only. Run release_static.py successfully first, then
run this file. --check validates inputs without creating the repository or ZIP.
Only files recorded by this tool's ownership marker may be replaced on reruns;
unrelated files and manually edited generated files are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent
OFFLINE = "01_离线演示"
DEPLOY = "02_华为云部署"
SOURCE = "03_网站与算法源码"
sys.path.insert(0, str(ROOT / SOURCE / "scripts"))
from demo_catalog import RECORDS as RECORD_PARAMETERS
DEFAULT_OUTPUT = ROOT / "06_GitHub发布准备" / "openecg-weblab"
MARKER = ".openecg-package-state.json"
TOOL_ID = "openecg-whitelist-package-v1"
RECORDS = tuple(f"{p[0]}-{p[1]}" for p in RECORD_PARAMETERS)
OPTIONAL_GENERATION = f"{SOURCE}/public/generation_manifest.json"
OPTIONAL_MODEL_REPLAY = f"{SOURCE}/public/model_replay_audit.json"
OPTIONAL_GENERATION_HISTORY = f"{SOURCE}/public/generation_history/generation_14_records_20261018.json"
PUBLIC_PRESERVATION = f"{SOURCE}/public/preservation_14_records_manifest.json"
HANDOFF_PRESERVATION = "05_交接说明/10_扩充前十四条保护清单_20261018.json"
INFERENCE_DEPENDENCIES = (
    "openecg[deploy]==0.11.0", "wfdb==4.3.1", "scipy==1.17.1", "numpy==1.26.4",
)
ZIP_DATE = (2026, 10, 18, 0, 0, 0)
PUBLIC_DEMO_URL = "http://124.71.24.143/"


README = """# OpenECG WebLab

**[打开在线 ECG 演示](__PUBLIC_DEMO_URL__)** · [算法与测量协议](03_网站与算法源码/docs/定量对照协议.md) · [数据来源与许可](docs/来源与许可说明.md)

基于 [OpenECG](https://github.com/vitaldb/openecg) 的单导联心电信号分析课程项目，包含 LUDB 与 QTDB 各 __PER_DATASET_COUNT__ 条、共 __RECORD_COUNT__ 条十秒演示记录。
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
当前检查包括 16 项测量测试、19 项生成保护测试、17 类损坏记录恢复，以及 __RECORD_COUNT__ 条记录的自动切换与导出逻辑。模拟 DOM 检查不代替真实浏览器验收。

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
| [demo_catalog.py](03_网站与算法源码/scripts/demo_catalog.py) | __RECORD_COUNT__ 条记录的数据库、导联、标注扩展名和时间窗口 |
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

`--new-only` 逐字节保留有效的现有记录，只推理缺失条目；仓库中已有全部 __RECORD_COUNT__ 条时仅校验，不运行模型、不覆盖推理清单。
在实验副本中去掉该参数可全量重跑，但会替换 `public/demo/` 结果；发布保护检查会报告其与冻结结果的差异。

## 数据与计算溯源

- `03_网站与算法源码/source-data/`：__SOURCE_FILE_COUNT__ 个官方 WFDB 文件；来源 URL、官方哈希与选窗依据见 `public/source_manifest.json`。
- `03_网站与算法源码/public/demo/` 和 `public/analysis/`：__RECORD_COUNT__ 条冻结预测与派生测量；每份分析记录其输入 JSON 的 SHA-256。
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
"""

DEPLOY_DOC = """# 静态演示部署

本目录仅发布内嵌预计算数据的首页，不接受文件导入，不执行在线模型推理。
本部署说明使用通用地址占位符，在线演示入口见根 README；仓库不包含 SSH 账号凭据、内部路径或密钥。

## 在本机预览

在本目录运行 `python server.py --host 127.0.0.1 --port 8080`，然后打开
`http://127.0.0.1:8080/`。健康检查为 `/health`。`python verify_server.py` 检查本机 HTTP 行为。

## 在 Ubuntu 服务器安装

将本目录的五个文件复制到你指定的部署目录。在服务器上切换到该目录后运行：

```sh
sudo bash install.sh
systemctl status openecg-demo --no-pager
curl http://127.0.0.1/health
```

安装器写入其管理的 `/opt/openecg-demo` 和 `openecg-demo.service`，使用低权限账户服务；
会先检查同名目标和端口，不覆盖无管理标记的已有目录或服务。
默认端口为 80；低于 1024 的端口只授予服务绑定端口所需的 `CAP_NET_BIND_SERVICE`，仍使用低权限账户运行，无需安装 Nginx。
仅在确认本机检查通过后，根据你自己的服务器配置放通 TCP 80，并从另一台机器测试首页、波形和导出。
默认公网访问形式为 `http://<你的弹性公网IP>/`，无需端口后缀。若要用 8080，可运行 `sudo bash install.sh 8080` 并放通对应端口。
服务支持 gzip 传输，演示首页仍为内嵌预计算数据。域名、HTTPS 和站点发布条件由实际部署环境决定。
生产使用前查阅云服务商适用于服务器地域的最新网站发布要求。

## 查看与停止

```sh
journalctl -u openecg-demo -n 30 --no-pager
sudo systemctl stop openecg-demo
```

本说明不表示本包已经部署到任何服务器，也不表示公网或实际浏览器验收已经完成。
"""

LICENSE_DOC = """# 来源与许可说明

官方来源核对日期：2026-10-18。以下说明保留第三方的作者和许可范围，不给第三方数据或模型重新授权。

## OpenECG

- 项目：Hyung-Chul Lee and OpenECG contributors，https://github.com/vitaldb/openecg 。
- 上游代码许可证：Apache License 2.0，官方文件：https://github.com/vitaldb/openecg/blob/main/LICENSE 。
- 本项目通过依赖调用 `openecg[deploy]==0.11.0`，冻结预测标签记录为 `v56c int8`。
- 本包不包含 OpenECG 上游源码副本或模型权重；权重的使用与分发应遵守实际下载版本的上游条款。
- 本包没有训练新模型，也不把上游模型能力列为本项目原创。

## LUDB

- Lobachevsky University Electrocardiography Database，version 1.0.1，PhysioNet。
- 作者：Alena Kalyakulina, Igor Yusipov, Viktor Moskalenko, Alexander Nikolskiy, Konstantin Kosonogov, Nikolai Zolotykh, Mikhail Ivanchenko。
- 官方数据页：https://physionet.org/content/ludb/1.0.1/ ；DOI：https://doi.org/10.13026/eegm-h675 。
- 官方许可证：https://physionet.org/files/ludb/1.0.1/LICENSE.txt ，Open Data Commons Attribution License v1.0。
- 本包包含 __LUDB_RECORDS__ 的 `.dat`、`.hea`、`.ii` 文件，演示使用 II 导联前十秒。

## QT Database

- QT Database，version 1.0.0，PhysioNet；Roger Mark, George Moody。
- 官方数据页：https://physionet.org/content/qtdb/1.0.0/ ；DOI：https://doi.org/10.13026/C24K53 。
- 官方许可证页：https://physionet.org/content/qtdb/view-license/1.0.0/ ，Open Data Commons Attribution License v1.0。
- 引用：Laguna P, Mark RG, Goldberger AL, Moody GB. A Database for Evaluation of Algorithms for Measurement of QT and Other Waveform Intervals in the ECG. Computers in Cardiology 24:673-676 (1997).
- 本包包含 __QTDB_RECORDS__ 的 `.dat`、`.hea`、`.q1c` 文件；各导联和十秒窗口以 `scripts/demo_catalog.py` 为准。

## 数据及派生结果的署名

Contains information from the Lobachevsky University Electrocardiography Database and QT Database,
which are made available under the ODC Attribution License v1.0.

许可正文 URI：https://opendatacommons.org/licenses/by/1-0/ 。
原始 __SOURCE_FILE_COUNT__ 个文件按字节保留；`public/demo/` 是抽取、重采样、滤波、截窗与模型预测后的派生 JSON；
`public/analysis/` 是从这些冻结 JSON 计算的课程测量与对照结果；网页内嵌这些派生数据。
数据许可证和归属同样适用于相关信息，不能把这些数据与模型权重统一标成课程新增代码的许可证。
原始文件和派生文件的 SHA-256 在根目录清单中列出。

## 课程新增代码与依赖

本准备包没有替作者选择新增代码的对外授权许可证；如需开源授权，可在明确选择后单独添加，
同时保留本说明和原始数据署名。依赖项各按自身许可证使用；本包不捆绑第三方 Python 包。
历史 React/Sites 模板、其 vendor 文件、旧截图、SSH 交接文档和内部云主机配置没有纳入仓库；演示访问入口见根 README。
"""

SOURCE_README = """# 算法与冻结数据

以仓库根 README 为入口。`scripts/coursework_analysis.py` 仅使用 Python 标准库，
计算 QRS 时限和人工区间对照；`scripts/test_coursework_analysis.py` 是其已知答案检查。
`scripts/prepare_demo.py` 与 `scripts/test_prepare_demo.py` 用于可选的原始信号处理/模型生成，
独立依赖见 `requirements-inference.txt`，实际安装版本、模型哈希与原有结果复现核查分别记录在 public 下的生成/核查清单。

`public/demo` 是 __RECORD_COUNT__ 条冻结预测，`public/analysis` 是派生分析，`source-data` 保留 __SOURCE_FILE_COUNT__ 个 WFDB 原始文件。
来源、署名、许可与修改范围见根目录 `docs/来源与许可说明.md`；定量规则见 `docs/定量对照协议.md`。
"""


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encoded(text: str) -> bytes:
    replacements = {
        "__PUBLIC_DEMO_URL__": PUBLIC_DEMO_URL,
        "__RECORD_COUNT__": str(len(RECORD_PARAMETERS)),
        "__PER_DATASET_COUNT__": str(sum(p[0] == "ludb" for p in RECORD_PARAMETERS)),
        "__SOURCE_FILE_COUNT__": str(len(RECORD_PARAMETERS) * 3),
        "__LUDB_RECORDS__": "、".join(p[1] for p in RECORD_PARAMETERS if p[0] == "ludb"),
        "__QTDB_RECORDS__": "、".join(p[1] for p in RECORD_PARAMETERS if p[0] == "qtdb"),
    }
    for marker, value in replacements.items():
        text = text.replace(marker, value)
    return (text.rstrip() + "\n").encode("utf-8")


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Unsafe package path: {name}")
    if any(part.lower() in (".git", ".env", "__pycache__", "node_modules") for part in path.parts):
        raise ValueError(f"Forbidden package component: {name}")
    return path


def whitelist() -> list[str]:
    paths = [f"{OFFLINE}/{name}" for name in (
        "template.html", "base.css", "app.js", "build_demo.py", "verify.cjs",
        "release_static.py", "prepare_github.py", "OpenECG_Demo.html",
    )]
    paths += [f"{DEPLOY}/{name}" for name in ("index.html", "server.py", "install.sh", "verify_server.py")]
    paths += [f"{SOURCE}/scripts/{name}" for name in (
        "coursework_analysis.py", "test_coursework_analysis.py", "prepare_demo.py", "test_prepare_demo.py",
        "demo_catalog.py", "download_demo_sources.py",
    )]
    paths += [f"{SOURCE}/docs/{name}" for name in ("定量对照协议.md", "GitHub发布结构.md")]
    paths += [f"{SOURCE}/public/{folder}/{record}.json" for folder in ("demo", "analysis") for record in RECORDS]
    paths += [f"{SOURCE}/public/analysis/{name}.csv" for name in (
        "qrs_measurements", "reference_comparisons", "comparison_summary",
    )]
    paths += [f"{SOURCE}/source-data/{p[0]}/{p[1]}.{ext}" for p in RECORD_PARAMETERS for ext in ("dat", "hea", p[3])]
    paths.append(f"{SOURCE}/public/source_manifest.json")
    if (ROOT / OPTIONAL_GENERATION).is_file():
        paths.append(OPTIONAL_GENERATION)
    if (ROOT / OPTIONAL_MODEL_REPLAY).is_file():
        paths.append(OPTIONAL_MODEL_REPLAY)
    for optional in (OPTIONAL_GENERATION_HISTORY, PUBLIC_PRESERVATION):
        if (ROOT / optional).is_file():
            paths.append(optional)
    return paths


def preservation_projection() -> dict | None:
    """Return a public path/hash-only guard, validating every protected byte."""
    result = None
    prefixes = {f"{SOURCE}/public/demo/": 14, f"{SOURCE}/public/analysis/": 14,
                f"{SOURCE}/source-data/": 42}
    for name in (HANDOFF_PRESERVATION, PUBLIC_PRESERVATION):
        path = ROOT / name
        if not path.is_file():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))["files"]
        names = [row["path"] for row in rows]
        if len(rows) != 70 or len(set(names)) != 70 or any(sum(item.startswith(prefix) for item in names) != count for prefix, count in prefixes.items()):
            raise RuntimeError(f"Invalid prior-record preservation scope: {name}")
        projected = []
        for row in rows:
            safe_relative(row["path"])
            target = (ROOT / row["path"]).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                raise RuntimeError(f"Missing or escaped protected input: {row['path']}")
            content = target.read_bytes()
            if len(content) != row["bytes"] or digest(content) != row["sha256"]:
                raise RuntimeError(f"Previously frozen 14-record scientific file changed: {row['path']}")
            projected.append({"path": row["path"], "bytes": row["bytes"], "sha256": row["sha256"]})
        projection = {"scope": "preserve existing 14 frozen predictions, 14 analysis JSONs, and 42 official source files",
                      "files": sorted(projected, key=lambda item: item["path"])}
        if result is not None and result != projection:
            raise RuntimeError("Public and handoff preservation guards disagree")
        result = projection
    return result


def scan_public_content(files: dict[str, bytes]) -> None:
    """Catch accidental local paths, external IPv4 addresses and private keys.

    This is a narrow packaging guard, not a general-purpose secret scanner.
    Explicit whitelisting remains the primary control.
    """
    ip_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    # The user authorized this exact demo URL in the root README and this
    # packaging source only. Subpaths, ports, other addresses and other files
    # still go through the unchanged address/path/private-key guards.
    public_url_pattern = re.compile(r"(?<![A-Za-z0-9+._:/-])" + re.escape(PUBLIC_DEMO_URL)
                                    + r'''(?=$|[\s<>"'`)\]])''')
    key_pattern = re.compile(r"^-----BEGIN [A-Z ]*PRIVATE KEY-----", re.MULTILINE)
    local_pattern = re.compile(r"[A-Za-z]:[\\/]Users[\\/]|/home/[^/\s]+/\.ssh/", re.IGNORECASE)
    text_extensions = {".py", ".js", ".cjs", ".html", ".css", ".md", ".txt", ".json", ".sh"}
    for name, content in files.items():
        if PurePosixPath(name).suffix not in text_extensions:
            continue
        text = content.decode("utf-8")
        if name in {"README.md", f"{OFFLINE}/prepare_github.py"}:
            text = public_url_pattern.sub("", text)
        if key_pattern.search(text) or local_pattern.search(text):
            raise RuntimeError(f"Potential local path/private key in public file: {name}")
        for match in ip_pattern.finditer(text):
            if match.group() not in {"127.0.0.1", "0.0.0.0"}:
                # Dependency version strings can have four numeric components.
                if match.start() and text[match.start() - 1] in "=v":
                    continue
                raise RuntimeError(f"Unexpected numeric network address in public file: {name}")


def verify_release_ready() -> None:
    """Do not package a changed source tree against a stale successful release."""
    manifest_path = ROOT / "静态发布清单_20261018.json"
    if not manifest_path.is_file():
        raise RuntimeError("Run release_static.py successfully before preparing the repository.")
    entries = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", [])
    checked = set()
    for entry in entries:
        name = entry["path"]
        safe_relative(name)
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or digest(path.read_bytes()) != entry["sha256"]:
            raise RuntimeError(f"Successful release is stale or incomplete; rerun release_static.py: {name}")
        checked.add(name)
    required = {f"{OFFLINE}/{name}" for name in ("app.js", "template.html", "build_demo.py", "verify.cjs", "release_static.py", "OpenECG_Demo.html")}
    required.update(f"{SOURCE}/scripts/{name}" for name in ("coursework_analysis.py", "test_coursework_analysis.py", "prepare_demo.py", "test_prepare_demo.py", "demo_catalog.py", "download_demo_sources.py"))
    required.add(f"{SOURCE}/public/source_manifest.json")
    for optional in (OPTIONAL_GENERATION, OPTIONAL_MODEL_REPLAY, OPTIONAL_GENERATION_HISTORY,
                     HANDOFF_PRESERVATION, PUBLIC_PRESERVATION):
        if (ROOT / optional).is_file():
            required.add(optional)
    required.update(f"{SOURCE}/public/{folder}/{record}.json" for folder in ("demo", "analysis") for record in RECORDS)
    required.update(f"{SOURCE}/source-data/{p[0]}/{p[1]}.{ext}" for p in RECORD_PARAMETERS for ext in ("dat", "hea", p[3]))
    if not required.issubset(checked):
        raise RuntimeError("Successful release does not cover the required source files; rerun release_static.py.")


def collect() -> dict[str, bytes]:
    verify_release_ready()
    preservation = preservation_projection()
    files: dict[str, bytes] = {}
    for name in whitelist():
        safe_relative(name)
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise RuntimeError(f"Missing or escaped whitelisted input: {name}")
        files[name] = path.read_bytes()
    if files[f"{OFFLINE}/OpenECG_Demo.html"] != files[f"{DEPLOY}/index.html"]:
        raise RuntimeError("Offline/deployment pages differ. Run release_static.py first.")
    dependency_file = ROOT / SOURCE / "backend/requirements.txt"
    if not dependency_file.is_file():
        # A prepared repository deliberately excludes the live FastAPI backend.
        dependency_file = ROOT / SOURCE / "requirements-inference.txt"
    lines = dependency_file.read_text(encoding="utf-8").splitlines()
    if any(lines.count(requirement) != 1 for requirement in INFERENCE_DEPENDENCIES):
        raise RuntimeError("Historical inference requirements changed; review the dependency whitelist.")
    files.update({
        "README.md": encoded(README),
        ".gitignore": encoded("__pycache__/\n*.py[cod]\n.venv/\n.env\n.env.*\n.DS_Store\nThumbs.db\n*.tmp\n06_GitHub发布准备/\n.openecg-package-state.json"),
        "docs/来源与许可说明.md": encoded(LICENSE_DOC),
        "docs/发布准备说明.md": (ROOT / SOURCE / "docs/GitHub发布结构.md").read_bytes(),
        f"{DEPLOY}/部署说明.md": encoded(DEPLOY_DOC),
        f"{SOURCE}/README.md": encoded(SOURCE_README),
        f"{SOURCE}/requirements-inference.txt": encoded("\n".join(INFERENCE_DEPENDENCIES)),
    })
    if preservation is not None:
        files[PUBLIC_PRESERVATION] = encoded(json.dumps(preservation, ensure_ascii=False, indent=2))
    notice = encoded("# 数据署名与许可\n\n" + LICENSE_DOC)
    for folder in ("source-data", "public/demo", "public/analysis"):
        files[f"{SOURCE}/{folder}/ATTRIBUTION.md"] = notice
    scan_public_content(files)
    sums = "".join(f"{digest(content)}  {name}\n" for name, content in sorted(files.items()))
    files["SHA256SUMS"] = sums.encode("utf-8")
    manifest = {
        "schema": TOOL_ID,
        "scope": "static demo and frozen-output analysis; no upload or publication performed",
        "checksumRule": "files lists every packaged file except release-manifest.json; SHA256SUMS excludes itself and release-manifest.json",
        "validationStatus": "packaging integrity only; run release_static.py and assess browser/public checks separately",
        "optionalModelGenerationManifestIncluded": OPTIONAL_GENERATION in files,
        "optionalModelReplayAuditIncluded": OPTIONAL_MODEL_REPLAY in files,
        "optionalGenerationHistoryIncluded": OPTIONAL_GENERATION_HISTORY in files,
        "priorFourteenRecordPreservationGuardIncluded": PUBLIC_PRESERVATION in files,
        "files": [{"path": name, "bytes": len(content), "sha256": digest(content)} for name, content in sorted(files.items())],
    }
    files["release-manifest.json"] = encoded(json.dumps(manifest, ensure_ascii=False, indent=2))
    return files


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prior_state(output: Path) -> dict:
    marker = output / MARKER
    if not output.exists():
        return {"schema": TOOL_ID, "files": {}}
    if not output.is_dir() or not marker.is_file():
        raise RuntimeError("Output already exists without this tool's ownership marker; choose a new directory.")
    state = json.loads(marker.read_text(encoding="utf-8"))
    if state.get("schema") != TOOL_ID or not isinstance(state.get("files"), dict):
        raise RuntimeError("Invalid package ownership marker.")
    return state


def preflight_output(output: Path, files: dict[str, bytes]) -> dict:
    if output == ROOT or ROOT.is_relative_to(output):
        raise RuntimeError("The output must not replace this source tree or one of its ancestors.")
    if output.is_relative_to(ROOT) and output.relative_to(ROOT).parts[0] != "06_GitHub发布准备":
        raise RuntimeError("Inside the source root, output is confined to 06_GitHub发布准备.")
    state = prior_state(output)
    for name, content in files.items():
        safe_relative(name)
        path = output / name
        if not path.resolve().is_relative_to(output):
            raise RuntimeError(f"Output path escapes through a link: {name}")
        if path.exists():
            if not path.is_file():
                raise RuntimeError(f"A directory collides with a package file: {name}")
            current = digest(path.read_bytes())
            accepted = {state["files"].get(name), state.get("previousFiles", {}).get(name), digest(content)}
            if name not in state["files"] or current not in accepted:
                raise RuntimeError(f"Preserved unowned/manually edited file; package update stopped: {name}")
    archive = output.with_name(output.name + ".zip")
    if archive.exists() and digest(archive.read_bytes()) not in {state.get("archiveSha256"), state.get("previousArchiveSha256")}:
        raise RuntimeError("An unowned or manually edited ZIP exists; package update stopped.")
    return state


def build_zip(output: Path, files: dict[str, bytes]) -> bytes:
    # In-memory assembly keeps the ZIP whitelist independent of extra files in output.
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(output.name + "/" + name, date_time=ZIP_DATE)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, content, compresslevel=9)
    result = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as bundle:
        expected = {output.name + "/" + name: digest(content) for name, content in files.items()}
        if bundle.testzip() is not None or len(bundle.namelist()) != len(expected) or set(bundle.namelist()) != set(expected):
            raise RuntimeError("Prepared ZIP whitelist/integrity check failed.")
        for name, expected_digest in expected.items():
            if digest(bundle.read(name)) != expected_digest:
                raise RuntimeError(f"Prepared ZIP hash mismatch: {name}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Managed repository output directory")
    parser.add_argument("--check", action="store_true", help="Check inputs and collisions only; do not write any file")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    files = collect()
    state = preflight_output(output, files)
    if args.check:
        print(f"PASS: {len(files)} whitelisted files; inputs and output collisions checked; no output written")
        return
    archive = build_zip(output, files)
    output.mkdir(parents=True, exist_ok=True)
    # Record both old and new accepted hashes before writes so an interrupted
    # update can resume without allowing arbitrary manually edited content.
    next_state = {
        "schema": TOOL_ID,
        "files": {**state["files"], **{name: digest(content) for name, content in files.items()}},
        "archiveSha256": digest(archive),
        "previousFiles": state["files"],
        "previousArchiveSha256": state.get("archiveSha256"),
    }
    atomic_write(output / MARKER, encoded(json.dumps(next_state, ensure_ascii=False, indent=2)))
    for name, content in sorted(files.items()):
        atomic_write(output / name, content)
    atomic_write(output.with_name(output.name + ".zip"), archive)
    next_state.pop("previousFiles")
    next_state.pop("previousArchiveSha256")
    atomic_write(output / MARKER, encoded(json.dumps(next_state, ensure_ascii=False, indent=2)))
    print(f"PASS: {len(files)} whitelisted files prepared: {output}")
    print(f"ZIP SHA256: {digest(archive)}")
    print("No GitHub upload, repository creation, remote login or server change was performed.")


if __name__ == "__main__":
    main()
