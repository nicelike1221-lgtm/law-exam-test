/**
 * Cloudflare Pages Function：飞书 API 代理
 * 路由：
 *   GET /api/health
 *   GET /api/questions?subject=民法
 *   GET /api/token  （调试用，生产可关掉）
 *
 * 环境变量（Cloudflare Pages Settings）：
 *   FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BASE_ID / FEISHU_QUESTION_TABLE_ID
 *   GARMIN_BACKEND_URL（可选：受保护的 Garmin 教练后端地址，不要填写 localhost）
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

async function getTenantToken(env) {
  const res = await fetch(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_id: env.FEISHU_APP_ID,
        app_secret: env.FEISHU_APP_SECRET,
      }),
    }
  );
  const data = await res.json();
  if (!data.tenant_access_token) {
    throw new Error(data.msg || "获取飞书 token 失败");
  }
  return data.tenant_access_token;
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

async function listAllRecords(env, token) {
  const base = env.FEISHU_BASE_ID;
  const table = env.FEISHU_QUESTION_TABLE_ID;
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
    if (data.code !== 0) {
      throw new Error(data.msg || "读取飞书记录失败");
    }
    for (const rec of data.data?.items || []) {
      items.push(mapRecord(rec.fields || {}));
    }
    pageToken = data.data?.page_token || "";
    if (!data.data?.has_more) break;
  } while (pageToken);

  return items;
}

async function proxyGarmin(request, env, action) {
  const backend = String(env.GARMIN_BACKEND_URL || "").trim().replace(/\/$/, "");
  if (!backend) {
    return json(
      {
        ok: false,
        error: "线上 Garmin 教练服务尚未配置。请在 Cloudflare Pages 的 Production 环境变量中设置 GARMIN_BACKEND_URL。",
        code: "GARMIN_BACKEND_NOT_CONFIGURED",
      },
      503
    );
  }

  let backendUrl;
  try {
    backendUrl = new URL(`${backend}/${action || "health"}`);
    if (!["http:", "https:"].includes(backendUrl.protocol)) throw new Error("协议不安全");
  } catch {
    return json({ ok: false, error: "GARMIN_BACKEND_URL 配置无效。", code: "GARMIN_BACKEND_URL_INVALID" }, 500);
  }

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", "application/json");

  try {
    const upstream = await fetch(backendUrl, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    });
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.set("Access-Control-Allow-Origin", "*");
    responseHeaders.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    responseHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    return json({ ok: false, error: `Garmin 教练服务连接失败：${err.message}`, code: "GARMIN_BACKEND_UNREACHABLE" }, 502);
  }
}

export async function onRequest(context) {
  const { request, env } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }

  const url = new URL(request.url);
  // path after /api/
  const parts = url.pathname.replace(/^\/api\/?/, "").split("/").filter(Boolean);
  const action = parts[0] || "health";

  try {
    if (action === "health") {
      return json({
        ok: true,
        service: "law-exam-test",
        hasFeishu: Boolean(
          env.FEISHU_APP_ID &&
            env.FEISHU_APP_SECRET &&
            env.FEISHU_BASE_ID &&
            env.FEISHU_QUESTION_TABLE_ID
        ),
      });
    }

    if (action === "token") {
      if (!env.FEISHU_APP_ID || !env.FEISHU_APP_SECRET) {
        return json({ error: "未配置 FEISHU_APP_ID / FEISHU_APP_SECRET" }, 500);
      }
      const token = await getTenantToken(env);
      return json({ token: token.slice(0, 8) + "...", ok: true });
    }

    if (action === "questions") {
      if (
        !env.FEISHU_APP_ID ||
        !env.FEISHU_APP_SECRET ||
        !env.FEISHU_BASE_ID ||
        !env.FEISHU_QUESTION_TABLE_ID
      ) {
        return json(
          {
            error: "飞书环境变量未配置完整",
            need: [
              "FEISHU_APP_ID",
              "FEISHU_APP_SECRET",
              "FEISHU_BASE_ID",
              "FEISHU_QUESTION_TABLE_ID",
            ],
          },
          500
        );
      }

      const token = await getTenantToken(env);
      let list = await listAllRecords(env, token);
      const subject = url.searchParams.get("subject");
      const status = url.searchParams.get("status") || "已发布";

      list = list.filter((q) => {
        if (status && q.状态 && q.状态 !== status) return false;
        if (subject && q.科目 && q.科目 !== subject) return false;
        return Boolean(q.题目ID && q.题干);
      });
      list.sort((a, b) => (a.排序 || 0) - (b.排序 || 0));

      return json({ total: list.length, questions: list, source: "feishu" });
    }

    if (action === "garmin") {
      const garminAction = parts[1] || "health";
      if (!["health", "chat"].includes(garminAction)) {
        return json({ ok: false, error: "Garmin 接口不存在", path: garminAction }, 404);
      }
      return proxyGarmin(request, env, garminAction);
    }

    return json({ error: "Not Found", path: action }, 404);
  } catch (err) {
    return json({ error: String(err.message || err) }, 500);
  }
}
