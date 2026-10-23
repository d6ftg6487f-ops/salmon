interface ConversationEntry {
  role: "user" | "model";
  text: string;
}

interface ChatSuccessResponse {
  answer: string;
}

interface ChatErrorResponse {
  error?: string;
}

// These elements are part of templates/index.html, loaded before this deferred script.
function requireChatElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) {
    throw new Error(`The chat control ${selector} is missing from the page.`);
  }
  return element;
}

const chatForm = requireChatElement<HTMLFormElement>("#chat-form");
const chatInput = requireChatElement<HTMLInputElement>("#chat-input");
const chatSend = requireChatElement<HTMLButtonElement>("#chat-send");
const chatMessages = requireChatElement<HTMLDivElement>("#chat-messages");
const conversation: ConversationEntry[] = [];

function addMessage(role: "user" | "assistant", text: string) {
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
    const result: unknown = await response.json();
    // app.py supplies error on failure and answer on success. The HTTP status
    // selects that existing contract without adding new response validation.
    if (!response.ok) {
      const failure = result as ChatErrorResponse;
      throw new Error(failure.error || `Chat request failed with status ${response.status}`);
    }
    const success = result as ChatSuccessResponse;

    addMessage("assistant", success.answer);
    conversation.push(
      { role: "user", text: message },
      { role: "model", text: success.answer },
    );
    if (conversation.length > 6) conversation.splice(0, conversation.length - 6);
  } catch (error: unknown) {
    console.error("チャットの回答を取得できませんでした。", error);
    // Preserve the existing truthy .message fallback, including thrown objects.
    const message = error !== null && (typeof error === "object" || typeof error === "function") &&
      "message" in error ? error.message : undefined;
    addMessage("assistant", String(message || "回答を取得できませんでした。少し待ってからお試しください。"));
  } finally {
    chatInput.disabled = false;
    chatSend.disabled = false;
    chatInput.focus();
  }
});
