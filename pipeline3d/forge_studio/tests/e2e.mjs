// End-to-end: built Forge Studio + a running forge_server, Gemini mocked at the network layer.
//   FORGE_URL=http://127.0.0.1:8765 FORGE_TOKEN=... APP_URL=http://127.0.0.1:4173 node tests/e2e.mjs
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

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
let geminiCalls = 0;
await page.route("https://generativelanguage.googleapis.com/**", async (route) => {
  geminiCalls++;
  const body = JSON.parse(route.request().postData() || "{}");
  if (!JSON.stringify(body).includes("longer blade")) throw new Error("user text not sent to Gemini");
  await route.fulfill({ contentType: "application/json", body: JSON.stringify({
    candidates: [{ content: { role: "model", parts: [{ text: JSON.stringify(geminiReply) }] }, finishReason: "STOP" }],
  }) });
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

await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: `${OUT}/studio_mobile.png`, fullPage: true });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
await browser.close();

console.log(JSON.stringify({ ok: true, geminiCalls, stageStates, mobileHorizontalOverflow: overflow }));
if (overflow) process.exitCode = 1;
