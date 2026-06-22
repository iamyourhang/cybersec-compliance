# 本地补源桥操作说明

当服务器无法访问国外官方站点时，用本地 Mac 抓取官方 PDF/HTML，再把文件包传回服务器入 COS、入文档库和 RAG。

## 1. 服务器导出待补源清单

```bash
cd /opt/cybersec-compliance
python scripts/export_pending_artifacts.py --out /tmp/pending_artifacts.jsonl --limit 200
```

把 `/tmp/pending_artifacts.jsonl` 复制到本地 Mac。

## 2. 本地 Mac 抓取官方原文

```bash
cd /path/to/cybersec-compliance
python scripts/local_official_artifact_fetch.py \
  --input pending_artifacts.jsonl \
  --out local_artifacts \
  --limit 50
```

输出目录形如：

```text
local_artifacts/20260428/
  manifest.jsonl
  <sha>_official_source.pdf
  <sha>_official_page.html
```

## 3. 上传文件包到服务器

```bash
scp -r local_artifacts/20260428 root@49.235.162.135:/opt/cybersec-compliance/inbox/local_artifacts/
```

## 4. 服务器导入、上传 COS、建文档

```bash
cd /opt/cybersec-compliance
python scripts/import_local_artifacts.py \
  --manifest inbox/local_artifacts/20260428/manifest.jsonl \
  --artifact-dir inbox/local_artifacts/20260428
```

如果只想先入库不解析：

```bash
python scripts/import_local_artifacts.py \
  --manifest inbox/local_artifacts/20260428/manifest.jsonl \
  --artifact-dir inbox/local_artifacts/20260428 \
  --no-parse
```

## 真实性规则

- 非官方域名拒绝导入。
- 最终跳转到非官方域名拒绝抓取。
- SHA256 与 manifest 不一致拒绝导入。
- 空文件、错误页、登录页、Cloudflare/CAPTCHA 页拒绝导入。
- 批量导入只创建原文证据和文档，不自动标记 `verified`。
- `verified` 仍必须经过现有审核闸门：官方 URL、原文工件/文档、可读证据备注。
