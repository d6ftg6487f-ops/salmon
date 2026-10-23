import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { Script } from "node:vm";
import { test as base, expect, type Page } from "@playwright/test";

interface BrowserErrors {
  allowed: RegExp[];
}

const test = base.extend<{ browserErrors: BrowserErrors }>({
  browserErrors: [async ({ page }, use) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    const errors: BrowserErrors = { allowed: [] };
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await use(errors);
    expect(pageErrors, "No uncaught browser exceptions").toEqual([]);
    expect(consoleErrors.filter((message) =>
      !errors.allowed.some((pattern) => pattern.test(message))),
    "No unexpected console errors").toEqual([]);
  }, { auto: true }],
});

function gate() {
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => { release = resolve; });
  return { pending, release };
}

async function expectBulb(page: Page, on: boolean, count: number) {
  await expect(page.locator("#toggle")).toHaveAttribute("aria-pressed", String(on));
  await expect(page.locator("#bulb")).toHaveAttribute("aria-label", on ? "点灯中" : "消灯中");
  await expect(page.locator("#status")).toHaveText(on ? "ON" : "OFF");
  await expect(page.locator("#status")).toHaveAttribute("aria-label", on ? "ついています" : "消えています");
  await expect(page.locator("#button-label")).toHaveText(on ? "消す" : "つける");
  await expect(page.locator("#count")).toHaveText(String(count));
  await expect(page.locator("#favicon")).toHaveAttribute("href", `/static/favicon-${on ? "on" : "off"}.svg`);
  await expect(page.locator("#theme-color")).toHaveAttribute("content", on ? "#3a3029" : "#15181c");
  expect(await page.locator("body").evaluate((element) => element.classList.contains("lights-on"))).toBe(on);
  expect(await page.locator("#bulb").evaluate((element) => element.classList.contains("is-on"))).toBe(on);
}

test("initial UI and two real toggles retain state after reload", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("豆電球");
  await expect(page.locator("h1")).toHaveText("豆電球");
  await expect(page.locator(".scene")).toHaveCSS("position", "fixed");
  await expect(page.locator('link[rel="stylesheet"]')).toHaveAttribute("href", "/static/styles.css");
  const on = await page.locator("#toggle").getAttribute("aria-pressed") === "true";
  const count = Number(await page.locator("#count").textContent());
  await expectBulb(page, on, count);

  for (const step of [1, 2]) {
    const requestGate = gate();
    await page.route("**/api/toggle", async (route) => {
      await requestGate.pending;
      await route.continue();
    }, { times: 1 });
    const response = page.waitForResponse((response) => response.url().endsWith("/api/toggle"));
    await page.locator("#toggle").click();
    try {
      await expect(page.locator("#toggle")).toBeDisabled();
    } finally {
      requestGate.release();
    }
    const actual = await response;
    expect(actual.request().method()).toBe("POST");
    expect(actual.ok()).toBe(true);
    await expectBulb(page, step === 1 ? !on : on, count + step);
    await expect(page.locator("#toggle")).toBeEnabled();
  }
  await page.reload();
  await expectBulb(page, on, count + 2);
});

for (const failure of ["http", "network"] as const) {
  test(`toggle recovers after ${failure} failure`, async ({ page, browserErrors }) => {
    browserErrors.allowed.push(/豆電球の状態を更新できませんでした。/, /Failed to load resource/);
    await page.goto("/");
    const count = Number(await page.locator("#count").textContent());
    const on = await page.locator("#toggle").getAttribute("aria-pressed") === "true";
    const requestGate = gate();
    await page.route("**/api/toggle", async (route) => {
      await requestGate.pending;
      if (failure === "http") await route.fulfill({ status: 500, body: "failed" });
      else await route.abort("failed");
    });
    await page.locator("#toggle").click();
    try {
      await expect(page.locator("#toggle")).toBeDisabled();
    } finally {
      requestGate.release();
    }
    await expect(page.locator("#error")).toBeVisible();
    await expect(page.locator("#error")).toHaveText("保存できませんでした。少し待ってからもう一度押してください。");
    await expect(page.locator("#toggle")).toBeEnabled();
    await expectBulb(page, on, count);
    await page.unroute("**/api/toggle");
    await page.locator("#toggle").click();
    await expectBulb(page, !on, count + 1);
    await expect(page.locator("#error")).toBeHidden();
    await expect(page.locator("#toggle")).toBeEnabled();
  });
}

test("chat trims input, renders text, caps API history at six and resets on reload", async ({ page }) => {
  const requests: unknown[] = [];
  const requestGate = gate();
  await page.route("**/api/chat", async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["content-type"]).toBe("application/json");
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) await requestGate.pending;
    await route.fulfill({ json: { answer: `<b>answer-${requests.length}</b>` } });
  });
  await page.goto("/");
  await page.locator("#chat-input").fill("   ");
  await page.locator("#chat-send").click();
  await expect(page.locator(".chat__message")).toHaveCount(1);
  expect(requests).toEqual([]);

  await page.locator("#chat-input").fill("  <i>question-1</i>  ");
  await page.locator("#chat-send").click();
  try {
    await expect(page.locator("#chat-input")).toHaveValue("");
    await expect(page.locator("#chat-input")).toBeDisabled();
    await expect(page.locator("#chat-send")).toBeDisabled();
    await expect.poll(() => requests.length).toBe(1);
  } finally {
    requestGate.release();
  }
  await expect(page.locator(".chat__message--assistant").last()).toHaveText("<b>answer-1</b>");
  await expect(page.locator(".chat__message--user").last()).toHaveText("<i>question-1</i>");
  await expect(page.locator("#chat-messages b, #chat-messages i")).toHaveCount(0);
  await expect(page.locator("#chat-input")).toBeFocused();
  await expect(page.locator("#chat-send")).toBeEnabled();
  expect(requests[0]).toEqual({ message: "<i>question-1</i>", history: [] });

  const history = [
    { role: "user", text: "<i>question-1</i>" },
    { role: "model", text: "<b>answer-1</b>" },
  ];
  for (let turn = 2; turn <= 5; turn += 1) {
    await page.locator("#chat-input").fill(`question-${turn}`);
    await page.locator("#chat-send").click();
    await expect(page.locator(".chat__message--assistant").last()).toHaveText(`<b>answer-${turn}</b>`);
    expect(requests[turn - 1]).toEqual({ message: `question-${turn}`, history: history.slice(-6) });
    history.push({ role: "user", text: `question-${turn}` }, { role: "model", text: `<b>answer-${turn}</b>` });
  }
  await page.reload();
  await expect(page.locator(".chat__message")).toHaveCount(1);
  await page.locator("#chat-input").fill("after reload");
  await page.locator("#chat-send").click();
  await expect(page.locator(".chat__message--assistant").last()).toHaveText("<b>answer-6</b>");
  expect(requests[5]).toEqual({ message: "after reload", history: [] });
});

for (const failure of ["http", "http-without-message", "network"] as const) {
  test(`chat restores controls and excludes ${failure} failures from history`, async ({ page, browserErrors }) => {
    browserErrors.allowed.push(/チャットの回答を取得できませんでした。/, /Failed to load resource/);
    const requests: unknown[] = [];
    const requestGate = gate();
    await page.route("**/api/chat", async (route) => {
      requests.push(route.request().postDataJSON());
      if (requests.length === 2) {
        await requestGate.pending;
        if (failure === "network") await route.abort("failed");
        else await route.fulfill({ status: 503, json: failure === "http" ? { error: "<b>一時エラー</b>" } : {} });
      } else await route.fulfill({ json: { answer: "回答" } });
    });
    await page.goto("/");
    await page.locator("#chat-input").fill("successful question");
    await page.locator("#chat-send").click();
    await expect(page.locator(".chat__message--assistant").last()).toHaveText("回答");
    await page.locator("#chat-input").fill("failed question");
    await page.locator("#chat-send").click();
    try {
      await expect(page.locator("#chat-input")).toBeDisabled();
      await expect(page.locator("#chat-send")).toBeDisabled();
    } finally {
      requestGate.release();
    }
    const errorText = failure === "http" ? "<b>一時エラー</b>"
      : failure === "http-without-message" ? "Chat request failed with status 503" : "Failed to fetch";
    await expect(page.locator(".chat__message--assistant").last()).toHaveText(errorText);
    await expect(page.locator("#chat-messages b")).toHaveCount(0);
    await expect(page.locator("#chat-input")).toBeEnabled();
    await expect(page.locator("#chat-send")).toBeEnabled();
    await expect(page.locator("#chat-input")).toBeFocused();
    await page.locator("#chat-input").fill("retry question");
    await page.locator("#chat-send").click();
    await expect(page.locator(".chat__message--assistant").last()).toHaveText("回答");
    expect(requests[2]).toEqual({ message: "retry question", history: [
      { role: "user", text: "successful question" }, { role: "model", text: "回答" },
    ] });
  });
}

for (const reducedMotion of ["reduce", "no-preference"] as const) {
  test(`pointer parallax respects reduced motion: ${reducedMotion}`, async ({ page }) => {
    await page.setViewportSize({ width: 1000, height: 800 });
    await page.emulateMedia({ reducedMotion });
    await page.goto("/");
    await page.mouse.move(750, 600);
    const expected = reducedMotion === "reduce" ? "" : "0.250";
    await expect.poll(() => page.locator(".scene").evaluate((element) => [
      element instanceof HTMLElement ? element.style.getPropertyValue("--px") : "wrong element",
      element instanceof HTMLElement ? element.style.getPropertyValue("--py") : "wrong element",
    ])).toEqual([expected, expected]);
  });
}

test("HTTP assets preserve classic scripts and the unused vendored ESM import graph", async ({ page, request }) => {
  const root = process.env.FRONTEND_APP_ROOT || process.cwd();
  for (const filename of ["bulb.js", "chat.js", "three-bulb.js", "styles.css", "favicon-on.svg", "favicon-off.svg",
    "vendor/three.module.min.js", "vendor/three.core.min.js", "vendor/THREE-LICENSE.txt"]) {
    const response = await request.get(`/static/${filename}`);
    expect(response.status()).toBe(200);
    expect(await response.body()).toEqual(await readFile(resolve(root, "static", filename)));
    if (filename.endsWith(".js")) expect(response.headers()["content-type"]).toMatch(/(?:text|application)\/javascript/);
    if (filename === "bulb.js" || filename === "chat.js") {
      const source = await response.text();
      expect(() => new Script(source)).not.toThrow();
      expect(source).not.toMatch(/\b(?:require\s*\(|module\.exports|exports\.)/);
    }
    if (filename === "three-bulb.js") {
      expect(await response.text()).toContain('from "./vendor/three.module.min.js"');
    }
  }

  const moduleRequests: string[] = [];
  page.on("request", (request) => {
    if (/three(?:-bulb|\.module\.min|\.core\.min)\.js/.test(request.url())) moduleRequests.push(request.url());
  });
  await page.goto("/");
  expect(await page.locator("script").evaluateAll((scripts) => scripts.map((script) => ({
    src: script.getAttribute("src"), defer: script.hasAttribute("defer"), type: script.getAttribute("type") || "",
  })))).toEqual([
    { src: "/static/bulb.js", defer: true, type: "" },
    { src: "/static/chat.js", defer: true, type: "" },
  ]);
  expect(moduleRequests).toEqual([]);
  await expect(page.locator(".bulb__canvas, .has-webgl")).toHaveCount(0);

  // Test-only import: the application HTML intentionally does not enable Three.js.
  await page.evaluate(async (url) => { await import(url); }, "/static/three-bulb.js");
  expect(moduleRequests.map((url) => new URL(url).pathname).sort()).toEqual([
    "/static/three-bulb.js", "/static/vendor/three.core.min.js", "/static/vendor/three.module.min.js",
  ]);
  await expect(page.locator(".bulb__canvas, .has-webgl")).toHaveCount(0);
});
