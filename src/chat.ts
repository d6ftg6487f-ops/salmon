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

function requireChatElement<T extends Element>(
  selector: string,
  elementType: { new(): T },
): T {
  const element = document.querySelector(selector);
  if (!(element instanceof elementType)) {
    throw new Error(`The chat control ${selector} is missing or has an unexpected type.`);
  }
  return element;
}

function isChatRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseChatSuccessResponse(value: unknown): ChatSuccessResponse {
  if (!isChatRecord(value) || typeof value.answer !== "string") {
    throw new Error("The chat response has an unexpected shape.");
  }
  return { answer: value.answer };
}

function parseChatErrorResponse(value: unknown): ChatErrorResponse {
  if (!isChatRecord(value) || (value.error !== undefined && typeof value.error !== "string")) {
    return {};
  }
  return { error: value.error };
}

function getChatErrorMessage(error: unknown): string | undefined {
  if (!isChatRecord(error) || typeof error.message !== "string") {
    return undefined;
  }
  return error.message;
}

const chatForm = requireChatElement("#chat-form", HTMLFormElement);
const chatInput = requireChatElement("#chat-input", HTMLInputElement);
const chatSend = requireChatElement("#chat-send", HTMLButtonElement);
const chatMessages = requireChatElement("#chat-messages", HTMLDivElement);
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

  chatInput.disabled = true;
  chatSend.disabled = true;

  try {
    addMessage("user", message);
    chatInput.value = "";
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: conversation.slice(-6),
      }),
    });
    const result: unknown = await response.json();
    if (!response.ok) {
      const failure = parseChatErrorResponse(result);
      throw new Error(failure.error || `Chat request failed with status ${response.status}`);
    }
    const success = parseChatSuccessResponse(result);

    addMessage("assistant", success.answer);
    conversation.push(
      { role: "user", text: message },
      { role: "model", text: success.answer },
    );
    if (conversation.length > 6) conversation.splice(0, conversation.length - 6);
  } catch (error: unknown) {
    console.error("チャットの回答を取得できませんでした。", error);
    addMessage(
      "assistant",
      getChatErrorMessage(error) || "回答を取得できませんでした。少し待ってからお試しください。",
    );
  } finally {
    chatInput.disabled = false;
    chatSend.disabled = false;
    chatInput.focus();
  }
});
