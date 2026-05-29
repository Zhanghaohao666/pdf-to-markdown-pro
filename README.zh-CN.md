# PDF to Markdown Pro

> 一个轻量的 Claude Code / Codex skill，用于把 PDF 转成干净的 Markdown，并可选把内嵌图片 OCR 成纯文字。

[English](README.md) | 中文

## 功能

`pdf-to-markdown-pro` 会先把 PDF 转成 Markdown，再让 Claude Code、Codex 或其他代理读取 Markdown，而不是直接硬读二进制 PDF。

主要功能：

- 将 PDF 转成干净的 Markdown。
- 根据已安装工具自动选择转换引擎。
- 支持中文 / 英文 PDF。
- 可选导出 PDF 内嵌图片。
- 可选把内嵌图片 OCR 成文字。
- 支持纯文字 Markdown 输出，不保留图片链接。
- 避免默认输出到微信 `RWTemp` 等临时目录。
- 每次转换都会生成 JSON 报告，方便排查问题。

## 为什么需要它

大多数 AI 代理读 Markdown 比读 PDF 稳定得多。这个 skill 的工作流是：

1. 探测 PDF 类型。
2. 选择本机可用的最佳转换引擎。
3. 转成 Markdown。
4. 可选把内嵌图片 OCR 成文字。
5. 让代理读取 Markdown。

## 仓库结构

```text
pdf-to-markdown-pro/
  SKILL.md
  agents/
    openai.yaml
  scripts/
    convert_pdf.py
    probe_pdf.py
  references/
    engine-selection.md
```

## 安装

### Claude Code

克隆仓库，然后复制到 Claude skills 目录：

```powershell
git clone https://github.com/Zhanghaohao666/pdf-to-markdown-pro.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force .\pdf-to-markdown-pro "$env:USERPROFILE\.claude\skills\pdf-to-markdown-pro"
```

在 Claude Code 中这样使用：

```text
Use $pdf-to-markdown-pro to convert this PDF into clean Markdown.
```

### Codex

克隆仓库，然后复制到 Codex skills 目录：

```powershell
git clone https://github.com/Zhanghaohao666/pdf-to-markdown-pro.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force .\pdf-to-markdown-pro "$env:USERPROFILE\.codex\skills\pdf-to-markdown-pro"
```

在 Codex 中这样使用：

```text
Use $pdf-to-markdown-pro to read this PDF and summarize the key points.
```

## 依赖

这个 skill 默认很轻，不强制安装所有重型依赖，只会使用本机已安装的引擎。

推荐最小依赖：

```bash
python -m pip install pymupdf pymupdf4llm markitdown[pdf] pypdf
```

图片 OCR：

```bash
python -m pip install rapidocr-onnxruntime pillow opencv-python
```

更高版面解析质量：

```bash
python -m pip install docling
```

中文 / 扫描件 / 重 OCR 可选：

```bash
python -m pip install "mineru[all]"
```

Marker 可选支持：

```bash
python -m pip install marker-pdf
```

## 使用方法

在仓库目录或 skill 目录中运行命令。

### 探测 PDF

```bash
python scripts/probe_pdf.py "document.pdf"
```

会输出：

- 页数
- 抽样文本量
- 中文/CJK 比例
- 图片密度
- 可用转换引擎
- 推荐路由

### 转换 PDF 为 Markdown

```bash
python scripts/convert_pdf.py "document.pdf"
```

默认输出到 PDF 同目录。如果 PDF 来自微信 `RWTemp`、系统 `Temp`、`tmp/cache` 等临时目录，则默认输出到当前工作目录下的 `pdf-to-markdown-output/`。你也可以用 `--output` 指定位置。

### 指定输出路径

```bash
python scripts/convert_pdf.py "document.pdf" --output "document.md"
```

### 快速模式

```bash
python scripts/convert_pdf.py "document.pdf" --mode fast
```

适合有文本层的普通 PDF。

### 高精度模式

```bash
python scripts/convert_pdf.py "document.pdf" --mode accurate
```

适合复杂表格、多栏文档、版面结构要求高的 PDF。

### 中文/CJK 模式

```bash
python scripts/convert_pdf.py "document.pdf" --mode cjk
```

适合中文、日文、韩文、学术论文、扫描技术文档。

### 导出图片

```bash
python scripts/convert_pdf.py "document.pdf" --images
```

如果当前引擎支持，会在 Markdown 中保留图片链接。

### OCR 内嵌图片

```bash
python scripts/convert_pdf.py "document.pdf" --ocr-images --ocr-engine rapidocr
```

保留图片链接，同时在图片附近追加 OCR 识别出的文字。

### 纯文字 Markdown

```bash
python scripts/convert_pdf.py "document.pdf" --pure-text --ocr-engine rapidocr
```

这个模式会：

- 提取 PDF 正文。
- 提取 PDF 内嵌图片。
- 对图片做 OCR。
- 删除所有 Markdown 图片链接。
- 输出纯文字 Markdown。

当你希望 Markdown 里只有可阅读文字时，用这个模式。

### 只转换部分页面

```bash
python scripts/convert_pdf.py "document.pdf" --pages 1-3,7
```

页码从 1 开始。

## 引擎路由

默认使用 `--mode auto`。

| 模式 | 适合场景 | 路由顺序 |
|---|---|---|
| `fast` | 普通文本型 PDF | PyMuPDF4LLM, MarkItDown, pypdf |
| `accurate` | 复杂版面、表格、多栏 PDF | Docling, Marker, PyMuPDF4LLM |
| `ocr` | 扫描件、图片较多的 PDF | MinerU, Marker, Docling, PyMuPDF4LLM |
| `cjk` | 中文/日文/韩文 PDF | MinerU, Docling, Marker, PyMuPDF4LLM |
| `auto` | 通用场景 | 先探测 PDF，再自动选择 |

## 转换报告

每次转换都会生成：

```text
document.conversion-report.json
```

报告包含：

- 最终使用的引擎
- 尝试过的引擎
- 警告信息
- 输出路径
- PDF 探测信息
- 图片 OCR 结果

如果转换效果不好，优先看这个报告。

## 故障排查

### Markdown 是空的

先看转换报告。常见原因：

- PDF 是扫描件，但没有 OCR 引擎。
- 输入 PDF 来自临时目录，后来被清理了。
- 首选引擎失败，fallback 也没成功。

扫描件或图片很多的 PDF 可以试：

```bash
python scripts/convert_pdf.py "document.pdf" --pure-text --ocr-engine rapidocr
```

### PDF 来自微信 `RWTemp`

微信临时目录可能会被自动清理。脚本会检测这类路径，并默认输出到：

```text
./pdf-to-markdown-output/
```

重要文件建议显式指定稳定输出路径：

```bash
python scripts/convert_pdf.py "document.pdf" --output "D:/Documents/document.md" --pure-text
```

### Windows 上 PyMuPDF4LLM 报 ONNX 错误

某些 Windows 环境下，PyMuPDF4LLM 新 layout 路径会触发 ONNXRuntime 类型错误。脚本会自动切到 legacy non-layout 模式重试。

### 图片 OCR 很慢

图片 OCR 比普通文本提取慢。只有确实需要把图片文字也转成 Markdown 时，才建议使用 `--pure-text` 或 `--ocr-images`。

## 隐私

默认工作流是本地处理，skill 本身不会上传 PDF。如果你自己安装并调用云端引擎，则以对应服务的隐私政策为准。

## 许可证

MIT
