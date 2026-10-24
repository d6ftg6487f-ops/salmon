interface ToggleResponse {
  is_on: boolean;
  press_count: number;
}

function requireBulbElement<T extends Element>(
  selector: string,
  elementType: { new(): T },
): T {
  const element = document.querySelector(selector);
  if (!(element instanceof elementType)) {
    throw new Error(`The bulb control ${selector} is missing or has an unexpected type.`);
  }
  return element;
}

function isToggleRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseToggleResponse(value: unknown): ToggleResponse {
  if (!isToggleRecord(value)) {
    throw new Error("The toggle response is not an object.");
  }

  const { is_on: isOn, press_count: pressCount } = value;
  if (typeof isOn !== "boolean" || typeof pressCount !== "number") {
    throw new Error("The toggle response has an unexpected shape.");
  }
  return { is_on: isOn, press_count: pressCount };
}

const toggleButton = requireBulbElement("#toggle", HTMLButtonElement);
const bulb = requireBulbElement("#bulb", HTMLDivElement);
const statusText = requireBulbElement("#status", HTMLParagraphElement);
const buttonLabel = requireBulbElement("#button-label", HTMLSpanElement);
const pressCount = requireBulbElement("#count", HTMLSpanElement);
const errorMessage = requireBulbElement("#error", HTMLParagraphElement);
const scene = requireBulbElement(".scene", HTMLDivElement);
const favicon = requireBulbElement("#favicon", HTMLLinkElement);
const themeColor = requireBulbElement("#theme-color", HTMLMetaElement);
const faviconOn = favicon.dataset.on;
const faviconOff = favicon.dataset.off;
if (!faviconOn || !faviconOff) {
  throw new Error("The favicon URLs are missing from the page.");
}

toggleButton.addEventListener("click", async () => {
  toggleButton.disabled = true;
  errorMessage.hidden = true;

  try {
    const response = await fetch("/api/toggle", { method: "POST" });

    if (!response.ok) {
      throw new Error(`Toggle request failed with status ${response.status}`);
    }

    const state = parseToggleResponse(await response.json());

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
    favicon.href = state.is_on ? faviconOn : faviconOff;
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
