const toggleButton = document.querySelector("#toggle");
const bulb = document.querySelector("#bulb");
const statusText = document.querySelector("#status");
const buttonLabel = document.querySelector("#button-label");
const pressCount = document.querySelector("#count");
const errorMessage = document.querySelector("#error");
const scene = document.querySelector(".scene");
const favicon = document.querySelector("#favicon");
const themeColor = document.querySelector("#theme-color");

const defaultErrorText = errorMessage.textContent.trim();

function showError(message = defaultErrorText) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

toggleButton.addEventListener("click", async () => {
  toggleButton.disabled = true;
  errorMessage.hidden = true;

  try {
    // auth.js が読み込まれていない場合は undefined になる
    const token = await window.getIdToken?.();
    if (!token) {
      showError("操作するにはログインしてください。");
      return;
    }

    const response = await fetch("/api/toggle", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 401) {
      showError("ログインの有効期限が切れました。もう一度ログインしてください。");
      return;
    }

    if (response.status === 403) {
      showError("このアカウントでは操作できません。");
      return;
    }

    if (!response.ok) {
      throw new Error(`Toggle request failed with status ${response.status}`);
    }

    const state = await response.json();

    document.body.classList.toggle("lights-on", state.is_on);
    bulb.classList.toggle("is-on", state.is_on);
    bulb.setAttribute("aria-label", state.is_on ? "点灯中" : "消灯中");
    toggleButton.setAttribute("aria-pressed", String(state.is_on));

    statusText.textContent = state.is_on ? "ON" : "OFF";
    statusText.setAttribute("aria-label", state.is_on ? "ついています" : "消えています");

    buttonLabel.textContent = state.is_on ? "消す" : "つける";
    pressCount.textContent = state.press_count;

    favicon.href = state.is_on ? favicon.dataset.on : favicon.dataset.off;
    themeColor.content = state.is_on ? "#3a3029" : "#15181c";
  } catch (error) {
    console.error("豆電球の状態を更新できませんでした。", error);
    showError();
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
