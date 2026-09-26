// End-to-end: built Forge Studio + a running forge_server, Gemini mocked at the network layer.
//   FORGE_URL=http://127.0.0.1:8765 FORGE_TOKEN=... APP_URL=http://127.0.0.1:4173 node tests/e2e.mjs
// The fitted-creature scenario needs the server started against tests/mock_gemini.py (no key on the
// server: the key comes from Studio's settings via X-Gemini-Key):
//   GOOGLE_GEMINI_BASE_URL=http://127.0.0.1:8799 GEMINI_API_BASE=http://127.0.0.1:8799/v1beta python forge_server.py
import { chromium } from "playwright";

const APP = process.env.APP_URL || "http://127.0.0.1:4173";
const SERVER = process.env.FORGE_URL || "http://127.0.0.1:8765";
const TOKEN = process.env.FORGE_TOKEN;
const OUT = process.env.SHOT_DIR || ".";
const NAME = "karambit_long";

const manifest = {
  name: NAME, kind: "weapon",
  generate: { procedural: "build_karambit.py", config: { blade_sweep_deg: 170 } },
  cleanup: false, rig: { method: "none" }, animations: { method: "none" }, export: { collision: "convex" },
};
const geminiReply = {
  reply: "A karambit with a longer 170° hook. It's procedural, so no credits. Ready to forge.",
  manifest_json: JSON.stringify(manifest), ready: true,
};
const HORSE = "horse_fit";
const horseManifest = {
  name: HORSE, kind: "quadruped",
  concept: { tool: "banana", subject: "bay horse", auto_approve: true },
  generate: { procedural: "build_lowpoly_creature.py", config: { preset: "deer", height_m: 1.6, muscle: 0.6 },
              fit_reference: { animal: "bay horse" } },
  cleanup: false, rig: { method: "quadruped", clip_prefix: "horse_" }, animations: { method: "procedural" }, export: { collision: null },
};
const horseReply = {
  reply: "No horse preset, so I'll fit the deer preset to a Nano Banana side view of a bay horse.",
  manifest_json: JSON.stringify(horseManifest), ready: true,
};

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
let geminiCalls = 0;
await page.route("https://generativelanguage.googleapis.com/**", async (route) => {
  geminiCalls++;
  const req = JSON.parse(route.request().postData() || "{}");
  const said = (req.contents || []).filter((c) => c.role === "user").map((c) => c.parts.map((p) => p.text).join(""));
  if (!said.length || !said[0].includes("longer blade")) {
    console.error("unexpected Gemini request", JSON.stringify(req).slice(0, 400));
    return route.abort();
  }
  const last = said.at(-1).includes("horse") ? horseReply : geminiReply;
  await route.fulfill({ contentType: "application/json", body: JSON.stringify({
    candidates: [{ content: { role: "model", parts: [{ text: JSON.stringify(last) }] }, finishReason: "STOP" }],
  }) });
});
const jobKeys = [];
page.on("request", (r) => {
  if (r.method() === "POST" && r.url().endsWith("/api/assets")) jobKeys.push(r.headers()["x-gemini-key"] || "");
});
page.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });

await page.goto(APP);
await page.getByLabel("Forge server URL").fill(SERVER);
await page.getByLabel("Forge token").fill(TOKEN);
await page.getByLabel("Gemini API key").fill("test-key");
await page.getByRole("button", { name: "Save" }).click();
await page.locator(".dot.on").waitFor({ timeout: 10000 });

await page.getByPlaceholder(/low-poly dire boar/).fill("make me a karambit with a longer blade");
await page.getByRole("button", { name: "Send" }).click();
await page.getByText("longer 170° hook").waitFor({ timeout: 10000 });
const editor = await page.locator("textarea.code").inputValue();
if (!editor.includes(NAME)) throw new Error("manifest not placed in editor");
await page.getByText("valid JSON").waitFor();
await page.screenshot({ path: `${OUT}/studio_chat.png` });

await page.getByRole("button", { name: "Forge it" }).click();
const badge = page.locator(`section[aria-label="Asset ${NAME}"] .badge`);
await badge.waitFor({ timeout: 15000 });
await page.waitForFunction((n) => document.querySelector(`section[aria-label="Asset ${n}"] .badge`)?.textContent === "done",
  NAME, { timeout: 240000 });
await page.locator(".previews img").nth(2).waitFor({ timeout: 30000 });
const stageStates = await page.locator(`section[aria-label="Asset ${NAME}"] .stages li`).evaluateAll((els) => els.map((e) => e.className));
await page.screenshot({ path: `${OUT}/studio_done.png` });

// Fitted creature: Nano Banana side view -> Gemini marks the joints -> deer preset reshaped into a horse.
// The server has no key of its own; Studio sends the one from Settings with the job.
let horse = { skipped: true };
if (process.env.FIT_SCENARIO !== "0") {
  await page.getByPlaceholder(/low-poly dire boar/).fill("now a horse, low-poly, walking");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText("fit the deer preset").waitFor({ timeout: 10000 });
  await page.getByRole("button", { name: "Forge it" }).click();
  await page.locator(`section[aria-label="Asset ${HORSE}"] .badge`).waitFor({ timeout: 15000 });
  await page.waitForFunction((n) => ["done", "error", "waiting"].includes(
    document.querySelector(`section[aria-label="Asset ${n}"] .badge`)?.textContent || ""), HORSE, { timeout: 300000 });
  const status = await page.locator(`section[aria-label="Asset ${HORSE}"] .badge`).textContent();
  if (status !== "done") {
    console.error(await page.locator(`section[aria-label="Asset ${HORSE}"]`).innerText());
    throw new Error(`fitted horse ended ${status}`);
  }
  await page.locator(`section[aria-label="Asset ${HORSE}"] .previews img`).nth(3).waitFor({ timeout: 30000 });
  const previews = await page.locator(`section[aria-label="Asset ${HORSE}"] .previews img`).evaluateAll((els) => els.map((e) => e.alt));
  if (!previews.some((p) => p.endsWith("_fit.svg"))) throw new Error("fit overlay missing from previews");
  if (!jobKeys.at(-1)) throw new Error("Gemini key not sent with the job");
  await page.locator(`section[aria-label="Asset ${HORSE}"]`).screenshot({ path: `${OUT}/studio_fitted.png` });
  horse = { status, previews, keySent: Boolean(jobKeys.at(-1)) };
}

await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: `${OUT}/studio_mobile.png`, fullPage: true });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
await browser.close();

console.log(JSON.stringify({ ok: true, geminiCalls, stageStates, horse, mobileHorizontalOverflow: overflow }));
if (overflow) process.exitCode = 1;
