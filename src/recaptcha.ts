interface RecaptchaEnterpriseApi {
  render(
    container: HTMLElement,
    parameters: {
      sitekey: string;
      action: "SITE_ENTRY";
      size: "compact";
    },
  ): number;
  getResponse(widgetId: number): string;
  reset(widgetId: number): void;
}

interface Window {
  grecaptcha?: { enterprise?: RecaptchaEnterpriseApi };
  recaptchaEnterpriseReady: Promise<void>;
  onRecaptchaEnterpriseLoad: () => void;
  onRecaptchaEnterpriseError: () => void;
}

const form = document.querySelector<HTMLFormElement>("#site-entry-form");
const captchaContainer = document.querySelector<HTMLElement>("#site-entry-captcha");
const submitButton = document.querySelector<HTMLButtonElement>("#site-entry-submit");
const siteEntryErrorMessage = document.querySelector<HTMLParagraphElement>("#site-entry-error");
const siteKey = captchaContainer?.dataset.sitekey;

if (!form || !captchaContainer || !submitButton || !siteEntryErrorMessage || !siteKey) {
  throw new Error("The site-entry reCAPTCHA form is incomplete.");
}

let widgetId: number | undefined;

const captchaReady = window.recaptchaEnterpriseReady.then(() => {
  const enterprise = window.grecaptcha?.enterprise;
  if (!enterprise) {
    throw new Error("The reCAPTCHA Enterprise API did not load.");
  }

  widgetId = enterprise.render(captchaContainer, {
    sitekey: siteKey,
    action: "SITE_ENTRY",
    size: "compact",
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  siteEntryErrorMessage.hidden = true;
  submitButton.disabled = true;

  try {
    await captchaReady;
    const enterprise = window.grecaptcha?.enterprise;
    if (!enterprise || widgetId === undefined) {
      throw new Error("reCAPTCHA を利用できません。ページを再読み込みしてください。");
    }

    const token = enterprise.getResponse(widgetId);
    if (!token) {
      throw new Error("reCAPTCHA の確認を完了してください。");
    }

    const response = await fetch("/api/site-entry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recaptcha_token: token }),
    });
    const result: unknown = await response.json();
    if (!response.ok) {
      const message = typeof result === "object" && result !== null
        && "error" in result && typeof result.error === "string"
        ? result.error
        : `サイトへのアクセス確認に失敗しました (${response.status})`;
      throw new Error(message);
    }

    window.location.replace("/");
  } catch (error: unknown) {
    console.error("サイトへのアクセス確認に失敗しました。", error);
    siteEntryErrorMessage.textContent = error instanceof Error
      ? error.message
      : "確認できませんでした。もう一度お試しください。";
    siteEntryErrorMessage.hidden = false;
    const enterprise = window.grecaptcha?.enterprise;
    if (enterprise && widgetId !== undefined) enterprise.reset(widgetId);
  } finally {
    submitButton.disabled = false;
  }
});

void captchaReady.catch((error: unknown) => {
  console.error("reCAPTCHA Enterprise could not be initialized.", error);
  siteEntryErrorMessage.textContent = "reCAPTCHA を読み込めませんでした。ページを再読み込みしてください。";
  siteEntryErrorMessage.hidden = false;
});
