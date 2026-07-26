# 法考学习站 · 测试骨架

本地项目路径：`D:\测试`

基于 **GitHub + Cloudflare Pages/Functions + 飞书多维表格** 的法考刷题站最小可运行骨架。

## 目录结构

```text
D:\测试\
├── index.html                 # 前端单页（登录 + 刷题 + 错题本）
├── functions/api/[[path]].js  # Cloudflare Functions 飞书代理
├── scripts/
│   ├── dev-server.js          # 本地开发服务器（含 /api）
│   └── check-feishu.js        # 飞书连通自检
├── data/questions.sample.json # 离线样例题
├── quiz_import/               # 飞书导入用表格（xlsx/csv/json）
├── docs/
│   ├── feishu-schema.md       # 飞书字段设计
│   ├── deploy.md              # 本地 → GitHub → Cloudflare 部署说明
│   └── 接飞书操作步骤.md       # 解决“只显示 2 题”等问题
├── package.json
├── .env.example
├── .gitignore
├── 启动.cmd
└── 检查飞书.cmd
```

## 本地启动（1 分钟）

```powershell
cd D:\测试
npm run dev
```

浏览器打开：http://localhost:8080  
默认密码：`2026`

未配置飞书时，自动读取 `data/questions.sample.json`（2 题）。

## 接飞书

1. 复制 `.env.example` 为 `.env`，填写：
   - `FEISHU_APP_ID`
   - `FEISHU_APP_SECRET`
   - `FEISHU_BASE_ID`（区分大小写）
   - `FEISHU_QUESTION_TABLE_ID`
2. 按 `docs/feishu-schema.md` 建表
3. 用 `quiz_import/` 里的 xlsx 导入题目
4. 双击 `D:\测试\检查飞书.cmd` 或运行 `npm run check:feishu`
5. 双击 `D:\测试\启动.cmd` 或运行 `npm run dev`

详细排错见 `docs/接飞书操作步骤.md`。

## 上线 Cloudflare

见 `docs/deploy.md`：推 GitHub → 连 Pages → 配环境变量 → 自动部署。

## 当前能力（MVP）

- 密码门
- 科目筛选
- 单选/多选作答、即时判分、解析展示
- **本地错题本（localStorage）**：答错自动收录、错题重练、移除/清空
- 本地 sample / 飞书双数据源

## 下一步可加

- 考点笔记页（第二张飞书表）
- 批量导入脚本
- 每日打卡 / 正确率统计
- AI 解析代理（建议腾讯云 SCF，不直连 CF→国内模型）
