# 部署说明（骨架版）

## 本地

```bash
cd /d/测试
# 可选：复制 .env.example 为 .env 并填写飞书密钥
npm run dev
# 打开 http://localhost:8080
```

未配置飞书时，API 会回退到 `data/questions.sample.json`。

## GitHub + Cloudflare Pages

1. 将本目录推到 GitHub 仓库
2. Cloudflare Pages → Connect to Git → 选仓库
3. Build：None；Output：`/`（根目录）
4. Environment Variables 配置：
   - `FEISHU_APP_ID`
   - `FEISHU_APP_SECRET`
   - `FEISHU_BASE_ID`
   - `FEISHU_QUESTION_TABLE_ID`
5. 部署后访问 `*.pages.dev`

## 导入题目

用 `quiz_import/` 下的 xlsx 导入飞书「题目」表，字段见 `docs/feishu-schema.md`。
