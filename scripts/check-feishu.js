/**
 * 飞书连通性自检
 * 用法：node scripts/check-feishu.js
 * 依赖：项目根目录 .env 已填写
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

function loadEnvFile() {
  const envPath = path.join(ROOT, ".env");
  if (!fs.existsSync(envPath)) {
    console.error("❌ 找不到 D:\\测试\\.env");
    console.error("   请先复制 .env.example 为 .env 并填写 4 个飞书变量");
    process.exit(1);
  }
  const text = fs.readFileSync(envPath, "utf8");
  for (const line of text.split(/\r?\n/)) {
    const s = line.trim();
    if (!s || s.startsWith("#")) continue;
    const i = s.indexOf("=");
    if (i < 0) continue;
    const k = s.slice(0, i).trim();
    const v = s.slice(i + 1).trim().replace(/^['"]|['"]$/g, "");
    if (!(k in process.env)) process.env[k] = v;
  }
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

async function main() {
  loadEnvFile();
  const required = [
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BASE_ID",
    "FEISHU_QUESTION_TABLE_ID",
  ];
  console.log("== 1) 检查 .env ==");
  let missing = false;
  for (const k of required) {
    const ok = Boolean(process.env[k] && !String(process.env[k]).includes("xxxx"));
    console.log(`  ${ok ? "✅" : "❌"} ${k}=${ok ? "已填" : "未填/仍是占位符"}`);
    if (!ok) missing = true;
  }
  if (missing) {
    console.error("\n先把 4 个变量填真实值，再重跑本脚本。");
    process.exit(1);
  }

  console.log("\n== 2) 获取 tenant_access_token ==");
  const tokenRes = await fetch(
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
  const tokenData = await tokenRes.json();
  if (!tokenData.tenant_access_token) {
    console.error("❌ 换 token 失败：", tokenData.code, tokenData.msg || tokenData);
    console.error("   检查 AppID / AppSecret 是否正确、应用是否已启用");
    process.exit(1);
  }
  console.log("✅ token 获取成功");

  console.log("\n== 3) 读取题目表记录 ==");
  const base = process.env.FEISHU_BASE_ID;
  const table = process.env.FEISHU_QUESTION_TABLE_ID;
  const url = `https://open.feishu.cn/open-apis/bitable/v1/apps/${base}/tables/${table}/records?page_size=500`;
  const recRes = await fetch(url, {
    headers: { Authorization: `Bearer ${tokenData.tenant_access_token}` },
  });
  const recData = await recRes.json();
  if (recData.code !== 0) {
    console.error("❌ 读表失败：", recData.code, recData.msg || recData);
    console.error("   常见原因：");
    console.error("   1) BaseID / TableID 填错");
    console.error("   2) 应用未添加到该多维表格");
    console.error("   3) 应用未开通「多维表格」读权限，或权限变更后未发布");
    process.exit(1);
  }

  const items = recData.data?.items || [];
  console.log(`✅ 读到原始记录 ${items.length} 条`);

  let published = 0;
  let draft = 0;
  let noId = 0;
  const preview = [];
  for (const rec of items) {
    const f = rec.fields || {};
    const id = pickText(f["题目ID"]);
    const status = pickText(f["状态"]) || "(空)";
    const stem = pickText(f["题干"]);
    if (!id || !stem) noId += 1;
    if (status === "已发布" || status === "(空)") published += 1;
    else draft += 1;
    if (preview.length < 5) {
      preview.push({ 题目ID: id || "(无)", 状态: status, 题干前20: (stem || "").slice(0, 20) });
    }
  }

  console.log("\n== 4) 字段抽查 ==");
  console.table(preview);
  console.log(`  可用于前端的大致数量（有题目ID+题干）: ${items.length - noId}`);
  console.log(`  状态=已发布 或 空: ${published}`);
  console.log(`  其他状态(含草稿): ${draft}`);
  console.log(`  缺题目ID/题干: ${noId}`);

  console.log("\n== 结论 ==");
  if (items.length === 0) {
    console.log("❌ 表是空的，或 TableID 指错表。");
  } else if (items.length - noId < 10) {
    console.log("⚠️  原始记录有，但有效题不足 10。检查「题目ID」「题干」列名是否完全一致。");
  } else {
    console.log("✅ 飞书侧可读。下一步：重启 npm run dev，打开网页应显示飞书题。");
    console.log("   自检：http://localhost:8080/api/health  期望 hasFeishu=true, mode=feishu");
    console.log("   自检：http://localhost:8080/api/questions 期望 total≈10, source=feishu");
  }
}

main().catch((e) => {
  console.error("❌ 异常：", e.message || e);
  process.exit(1);
});
