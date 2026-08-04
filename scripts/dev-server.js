/**
 * 本地开发服务器
 * - 静态托管项目根目录
 * - 代理 /api/* ：有飞书配置则走飞书，否则回退 data/questions.sample.json
 *
 * 用法：
 *   npm run dev
 *   或：
 *   FEISHU_APP_ID=... FEISHU_APP_SECRET=... node scripts/dev-server.js
 */

const http = require("http");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");

const ROOT = path.resolve(__dirname, "..");
const PORT = Number(process.env.PORT || 8080);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".md": "text/markdown; charset=utf-8",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".csv": "text/csv; charset=utf-8",
};

function loadEnvFile() {
  const envPath = path.join(ROOT, ".env");
  if (!fs.existsSync(envPath)) return;
  const text = fs.readFileSync(envPath, "utf8");
  for (const line of text.split(/\r?\n/)) {
    const s = line.trim();
    if (!s || s.startsWith("#")) continue;
    const i = s.indexOf("=");
    if (i < 0) continue;
    const k = s.slice(0, i).trim();
    const v = s.slice(i + 1).trim();
    if (!(k in process.env)) process.env[k] = v;
  }
}

function sendJson(res, data, status = 200) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(body);
}

function serveStatic(req, res, urlPath) {
  let rel = decodeURIComponent(urlPath.split("?")[0]);
  if (rel === "/") rel = "/index.html";
  const filePath = path.normalize(path.join(ROOT, rel));
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    res.writeHead(404);
    res.end("Not Found");
    return;
  }
  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
  fs.createReadStream(filePath).pipe(res);
}

function pickText(field) {
  if (field == null) return "";
  if (typeof field === "string" || typeof field === "number") return String(field);
  if (Array.isArray(field)) {
    return field
      .map((x) => (typeof x === "object" ? x.text || x.name || "" : String(x)))
      .join("");
  }
  if (typeof field === "object") {
    return field.text || field.name || field.value || JSON.stringify(field);
  }
  return String(field);
}

function mapRecord(fields) {
  return {
    题目ID: pickText(fields["题目ID"]),
    科目: pickText(fields["科目"]),
    编章: pickText(fields["编章"]),
    章节: pickText(fields["章节"]),
    题型: pickText(fields["题型"]),
    题干: pickText(fields["题干"]),
    选项A: pickText(fields["选项A"]),
    选项B: pickText(fields["选项B"]),
    选项C: pickText(fields["选项C"]),
    选项D: pickText(fields["选项D"]),
    选项E: pickText(fields["选项E"]),
    答案: pickText(fields["答案"]).replace(/\s+/g, "").toUpperCase(),
    解析: pickText(fields["解析"]),
    考点: pickText(fields["考点"]),
    难度: pickText(fields["难度"]),
    来源: pickText(fields["来源"]),
    年份: pickText(fields["年份"]),
    状态: pickText(fields["状态"]) || "已发布",
    排序: Number(pickText(fields["排序"])) || 0,
  };
}

async function getTenantToken() {
  const res = await fetch(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_id: process.env.FEISHU_APP_ID,
        app_secret: process.env.FEISHU_APP_SECRET,
      }),
    }
  );
  const data = await res.json();
  if (!data.tenant_access_token) {
    throw new Error(data.msg || "获取飞书 token 失败");
  }
  return data.tenant_access_token;
}

async function listFeishuQuestions() {
  const base = process.env.FEISHU_BASE_ID;
  const table = process.env.FEISHU_QUESTION_TABLE_ID;
  const token = await getTenantToken();
  let pageToken = "";
  const items = [];

  do {
    const url = new URL(
      `https://open.feishu.cn/open-apis/bitable/v1/apps/${base}/tables/${table}/records`
    );
    url.searchParams.set("page_size", "500");
    if (pageToken) url.searchParams.set("page_token", pageToken);
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (data.code !== 0) throw new Error(data.msg || "读取飞书失败");
    for (const rec of data.data?.items || []) {
      items.push(mapRecord(rec.fields || {}));
    }
    pageToken = data.data?.page_token || "";
    if (!data.data?.has_more) break;
  } while (pageToken);

  return items;
}

function loadSampleQuestions() {
  const p = path.join(ROOT, "data", "questions.sample.json");
  const raw = JSON.parse(fs.readFileSync(p, "utf8"));
  return raw.questions || [];
}

function hasFeishuConfig() {
  return Boolean(
    process.env.FEISHU_APP_ID &&
      process.env.FEISHU_APP_SECRET &&
      process.env.FEISHU_BASE_ID &&
      process.env.FEISHU_QUESTION_TABLE_ID
  );
}

async function handleApi(req, res, url) {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    res.end();
    return;
  }

  const parts = url.pathname.replace(/^\/api\/?/, "").split("/").filter(Boolean);
  const action = parts[0] || "health";

  try {
    if (action === "health") {
      return sendJson(res, {
        ok: true,
        service: "law-exam-test-dev",
        hasFeishu: hasFeishuConfig(),
        mode: hasFeishuConfig() ? "feishu" : "sample",
      });
    }

    if (action === "questions") {
      let list;
      let source;
      if (hasFeishuConfig()) {
        list = await listFeishuQuestions();
        source = "feishu";
      } else {
        list = loadSampleQuestions();
        source = "sample";
      }

      const subject = url.searchParams.get("subject");
      const status = url.searchParams.get("status") || "已发布";
      list = list.filter((q) => {
        if (status && q.状态 && q.状态 !== status) return false;
        if (subject && q.科目 && q.科目 !== subject) return false;
        return Boolean(q.题目ID && q.题干);
      });
      list.sort((a, b) => (a.排序 || 0) - (b.排序 || 0));
      return sendJson(res, { total: list.length, questions: list, source });
    }

    return sendJson(res, { error: "Not Found", path: action }, 404);
  } catch (err) {
    return sendJson(res, { error: String(err.message || err) }, 500);
  }
}

loadEnvFile();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (url.pathname.startsWith("/api/")) {
    return handleApi(req, res, url);
  }
  return serveStatic(req, res, url.pathname);
});

server.listen(PORT, () => {
  console.log(`法考学习站开发服务器已启动`);
  console.log(`  本地地址: http://localhost:${PORT}`);
  console.log(`  数据模式: ${hasFeishuConfig() ? "飞书多维表格" : "本地 sample JSON"}`);
  console.log(`  项目目录: ${ROOT}`);
});
