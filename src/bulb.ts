interface ToggleResponse {
  is_on: boolean;
  press_count: number;
}

const toggleButton = document.querySelector<HTMLButtonElement>("#toggle");
const bulb = document.querySelector<HTMLDivElement>("#bulb");
const statusText = document.querySelector<HTMLParagraphElement>("#status");
const buttonLabel = document.querySelector<HTMLSpanElement>("#button-label");
const pressCount = document.querySelector<HTMLSpanElement>("#count");
const errorMessage = document.querySelector<HTMLParagraphElement>("#error");
const scene = document.querySelector<HTMLDivElement>(".scene");
const favicon = document.querySelector<HTMLLinkElement>("#favicon");
const themeColor = document.querySelector<HTMLMetaElement>("#theme-color");

// All elements are required by templates/index.html and exist before this deferred script runs.
if (!toggleButton || !bulb || !statusText || !buttonLabel || !pressCount ||
    !errorMessage || !scene || !favicon || !themeColor) {
  throw new Error("The bulb controls are missing from the page.");
}

toggleButton.addEventListener("click", async () => {
  toggleButton.disabled = true;
  errorMessage.hidden = true;

  try {
    const response = await fetch("/api/toggle", { method: "POST" });

    if (!response.ok) {
      throw new Error(`Toggle request failed with status ${response.status}`);
    }

    // app.py returns Database.toggle() with this schema on a successful response.
    // Keep the existing API behavior; do not add new rejection or coercion rules.
    const state = await response.json() as ToggleResponse;

    document.body.classList.toggle("lights-on", state.is_on);
    bulb.classList.toggle("is-on", state.is_on);
    bulb.setAttribute("aria-label", state.is_on ? "点灯中" : "消灯中");
    toggleButton.setAttribute("aria-pressed", String(state.is_on));

    // ステータスは ON / OFF 表記。読み上げ用には文章を残す
    statusText.textContent = state.is_on ? "ON" : "OFF";
    statusText.setAttribute("aria-label", state.is_on ? "ついています" : "消えています");

    buttonLabel.textContent = state.is_on ? "消す" : "つける";
    pressCount.textContent = String(state.press_count);

    // タブのアイコンとブラウザーのテーマ色も切り替える
    favicon.href = String(state.is_on ? favicon.dataset.on : favicon.dataset.off);
    themeColor.content = state.is_on ? "#3a3029" : "#15181c";
  } catch (error) {
    console.error("豆電球の状態を更新できませんでした。", error);
    errorMessage.hidden = false;
  } finally {
    toggleButton.disabled = false;
  }
});

// マウス位置に応じて、手前（電球）と奥（壁）にわずかな視差をつける
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (!reduceMotion) {
  window.addEventListener("pointermove", (event) => {
    const x = event.clientX / window.innerWidth - 0.5;
    const y = event.clientY / window.innerHeight - 0.5;
    scene.style.setProperty("--px", x.toFixed(3));
    scene.style.setProperty("--py", y.toFixed(3));
  });
}
