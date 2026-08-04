# 部署说明：本地 → GitHub → Cloudflare Pages

> 配套项目：`D:\测试`（法考学习站测试骨架）

---

## 1. 本地阶段

### 1.1 启动开发服务器

```powershell
cd D:\测试
npm run dev
```

浏览器打开：http://localhost:8080

- 默认密码：`2026`
- 已配置 `.env` 时，自动读飞书；未配置时读 `data/questions.sample.json`

### 1.2 飞书连通自检

```powershell
cd D:\测试
npm run check:feishu
```

或双击 `D:\测试\检查飞书.cmd`。

期望输出：

```text
✅ 4 个变量都已填
✅ tenant_access_token 获取成功
✅ 题目表原始记录数: 6 条
✅ 有效题目: 6 条
```

---

## 2. GitHub 阶段

### 2.1 在 GitHub 创建仓库

1. 打开 https://github.com/new
2. 仓库名建议：`law-exam-test`
3. 可见性：**Private**（密钥虽然不上传，但代码本身也建议私有）
4. **不要**勾选 “Initialize this repository with a README”

### 2.2 本地关联并推送

```powershell
cd D:\测试
git remote add origin https://github.com/你的用户名/law-exam-test.git
git branch -M main
git push -u origin main
```

> 第一次会要求登录 GitHub，按提示用浏览器或 Personal Access Token 完成认证。

### 2.3 推送后确认

- GitHub 仓库主页应看到 `index.html`、`functions/api/[[path]].js` 等文件
- 确认**没有 `.env` 文件**（它已被 `.gitignore` 排除）

---

## 3. Cloudflare Pages 阶段

### 3.1 创建 Pages 项目

1. 打开 https://dash.cloudflare.com/ → **Pages**
2. 点击 **Create a project** → **Connect to Git**
3. 选择 GitHub 账号 → 选择 `law-exam-test` 仓库 → **Install & Authorize**
4. 开始设置：

| 设置项 | 值 |
|--------|------|
| Production branch | `main` |
| Framework preset | **None** |
| Build command | 留空 |
| Build output directory | `.`（根目录，注意不是 `/`） |

> 注意：填 `/` 会导致 Cloudflare 执行 `/` 命令并报 `Permission denied`，必须填 `.`。

5. 点击 **Save and Deploy**

### 3.2 配置环境变量（关键）

项目创建后：

1. 进入项目 → **Settings** → **Environment variables**
2. 添加以下 4 个变量（Production 环境）：

| 变量名 | 值 |
|--------|------|
| `FEISHU_APP_ID` | 你的 App ID |
| `FEISHU_APP_SECRET` | 你的 App Secret |
| `FEISHU_BASE_ID` | 多维表格 Base ID |
| `FEISHU_QUESTION_TABLE_ID` | 题目表 Table ID |

3. 保存后，回到 **Deployments** → 找到最新部署 → 点击 **Retry deployment**（重新部署，让环境变量生效）

### 3.3 拿到访问域名

部署完成后，Cloudflare 会给你一个类似：

```text
https://law-exam-test.pages.dev
```

打开即可访问。

---

## 4. 上线验收清单

打开线上地址，逐项验证：

- [ ] 密码 `2026` 能进入
- [ ] 首页显示题目数量与飞书一致
- [ ] 作答后能看到正确/错误及解析
- [ ] 错题本会记录答错的题
- [ ] 错题本页可“重练”和“移除”
- [ ] 在飞书修改一道题 → 刷新线上页面 → 内容已更新
- [ ] 浏览器控制台无 401 / CORS 报错

---

## 5. 常见问题

### 线上显示 “飞书环境变量未配置完整”

环境变量没填对，或填完没重新部署。去 Cloudflare 检查并 Retry deployment。

### 线上显示 0 题

1. 检查环境变量里的 Base ID / Table ID 是否正确（区分大小写）
2. 检查飞书应用是否已授权到该 Base
3. 检查题目表状态是否为“已发布”或留空

### 更新代码后没有自动重新部署

确认 `git push` 到了 `main` 分支；Cloudflare 会自动触发。

---

## 6. 日常内容更新流程

| 你要做什么 | 操作 |
|-----------|------|
| 加题/改题 | 改飞书多维表格 → 刷新网页即可 |
| 改站点功能 | 改本地代码 → `git push origin main` → 自动部署 |
| 备份题库 | 用飞书导出或 `lark-cli base +record-list` |

---

## 7. 自定义域名（可选）

Cloudflare Pages → 项目 → **Custom domains** → 按向导添加你自己的域名。

