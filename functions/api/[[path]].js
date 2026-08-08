/**
 * Cloudflare Pages Function：飞书 API 代理
 * 路由：
 *   GET /api/health
 *   GET /api/questions?subject=民法
 *   GET /api/token  （调试用，生产可关掉）
 *
 * 环境变量（Cloudflare Pages Settings）：
 *   FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BASE_ID / FEISHU_QUESTION_TABLE_ID
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

async function listBySubject(env, token, subject, status) {
  const base = env.FEISHU_BASE_ID;
  const table = env.FEISHU_QUESTION_TABLE_ID;
  let pageToken = "";
  const items = [];
  do {
    const url = new URL(
      `https://open.feishu.cn/open-apis/bitable/v1/apps/${base}/tables/${table}/records/search`
    );
    const body = {
      field_names: [
        "题目ID", "科目", "编章", "章节", "题型", "题干",
        "选项A", "选项B", "选项C", "选项D", "选项E",
        "答案", "解析", "考点", "难度", "来源", "年份", "状态", "排序",
      ],
      filter: {
        conjunction: "and",
        conditions: [
          { field_name: "科目", operator: "is", value: [subject] },
          { field_name: "状态", operator: "is", value: [status] },
        ],
      },
      page_size: 500,
    };
    if (pageToken) body.page_token = pageToken;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.code !== 0) throw new Error(data.msg || "搜索飞书记录失败");
    for (const rec of data.data?.items || []) {
      const m = mapRecord(rec.fields || {});
      // 防御：飞书 search 翻页时可能丢弃过滤器，二次校验科目/状态
      if (m.科目 !== subject) continue;
      if (status && m.状态 !== status) continue;
      items.push(m);
    }
    pageToken = data.data?.page_token || "";
    if (!data.data?.has_more) break;
  } while (pageToken);
  return items;
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
      const subject = url.searchParams.get("subject");
      const status = url.searchParams.get("status") || "已发布";

      let list;
      if (subject) {
        list = await listBySubject(env, token, subject, status);
      } else {
        list = await listAllRecords(env, token);
      }

      list = list.filter((q) => {
        if (status && q.状态 && q.状态 !== status) return false;
        if (subject && q.科目 && q.科目 !== subject) return false;
        return Boolean(q.题目ID && q.题干);
      });
      list.sort((a, b) => (a.排序 || 0) - (b.排序 || 0));

      let source = "feishu";
      // 飞书暂缺该科目数据时，回退同源静态资源（如 /data/questions.理论法.json）
      if (list.length === 0 && subject) {
        try {
          const localRes = await fetch(
            new URL(`/data/questions.${encodeURIComponent(subject)}.json`, request.url)
          );
          if (localRes.ok) {
            const local = await localRes.json();
            const localList = (local.questions || local).filter(
              (q) => (!q.状态 || q.状态 === status) && q.题目ID && q.题干
            );
            if (localList.length) {
              list = localList;
              source = "local";
            }
          }
        } catch (e) { /* 忽略本地回退失败 */ }
      }

      return json({ total: list.length, questions: list, source });
    }

    return json({ error: "Not Found", path: action }, 404);
  } catch (err) {
    return json({ error: String(err.message || err) }, 500);
  }
}
