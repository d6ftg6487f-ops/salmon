const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
const chatSend = document.querySelector("#chat-send");
const chatMessages = document.querySelector("#chat-messages");
const conversation = [];

function addMessage(role, text) {
  const message = document.createElement("p");
  message.className = `chat__message chat__message--${role === "user" ? "user" : "assistant"}`;
  message.textContent = text;
  chatMessages.append(message);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  addMessage("user", message);
  chatInput.value = "";
  chatInput.disabled = true;
  chatSend.disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: conversation.slice(-6) }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || `Chat request failed with status ${response.status}`);
    }

    addMessage("assistant", result.answer);
    conversation.push(
      { role: "user", text: message },
      { role: "model", text: result.answer },
    );
    if (conversation.length > 6) conversation.splice(0, conversation.length - 6);
  } catch (error) {
    console.error("チャットの回答を取得できませんでした。", error);
    addMessage("assistant", error.message || "回答を取得できませんでした。少し待ってからお試しください。");
  } finally {
    chatInput.disabled = false;
    chatSend.disabled = false;
    chatInput.focus();
  }
});
