const toggleButton = document.querySelector("#toggle");
const bulb = document.querySelector("#bulb");
const statusText = document.querySelector("#status");
const buttonLabel = document.querySelector("#button-label");
const pressCount = document.querySelector("#count");
const errorMessage = document.querySelector("#error");

toggleButton.addEventListener("click", async () => {
  toggleButton.disabled = true;
  errorMessage.hidden = true;

  try {
    const response = await fetch("/api/toggle", { method: "POST" });

    if (!response.ok) {
      throw new Error(`Toggle request failed with status ${response.status}`);
    }

    const state = await response.json();

    document.body.classList.toggle("lights-on", state.is_on);
    bulb.classList.toggle("is-on", state.is_on);
    bulb.setAttribute("aria-label", state.is_on ? "点灯中" : "消灯中");
    toggleButton.setAttribute("aria-pressed", String(state.is_on));
    statusText.textContent = state.is_on ? "ついています" : "消えています";
    buttonLabel.textContent = state.is_on ? "消す" : "つける";
    pressCount.textContent = state.press_count;
  } catch (error) {
    console.error("豆電球の状態を更新できませんでした。", error);
    errorMessage.hidden = false;
  } finally {
    toggleButton.disabled = false;
  }
});
