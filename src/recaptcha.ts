type RecaptchaAction = "CHAT" | "TOGGLE";

interface RecaptchaEnterpriseApi {
  render(
    container: HTMLElement,
    parameters: {
      sitekey: string;
      action: RecaptchaAction;
      size: "compact";
      callback: (token: string) => void;
      "expired-callback": () => void;
      "error-callback": () => void;
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
  getRecaptchaToken: (action: RecaptchaAction) => Promise<string>;
  resetRecaptcha: (action: RecaptchaAction) => void;
}

const captchaWidgets = new Map<RecaptchaAction, number>();

const captchaReady = window.recaptchaEnterpriseReady.then(() => {
  const enterprise = window.grecaptcha?.enterprise;
  if (!enterprise) {
    throw new Error("The reCAPTCHA Enterprise API did not load.");
  }

  document.querySelectorAll<HTMLElement>(".g-recaptcha").forEach((container) => {
    const action = container.dataset.action;
    const sitekey = container.dataset.sitekey;
    if ((action !== "CHAT" && action !== "TOGGLE") || !sitekey) {
      throw new Error("The reCAPTCHA widget is missing its action or site key.");
    }

    const widgetId = enterprise.render(container, {
      sitekey,
      action,
      size: "compact",
      callback: () => {
        container.dataset.verified = "true";
      },
      "expired-callback": () => {
        delete container.dataset.verified;
      },
      "error-callback": () => {
        delete container.dataset.verified;
      },
    });
    captchaWidgets.set(action, widgetId);
  });
});

void captchaReady.catch((error: unknown) => {
  console.error("reCAPTCHA Enterprise could not be initialized.", error);
});

window.getRecaptchaToken = async (action) => {
  await captchaReady;
  const enterprise = window.grecaptcha?.enterprise;
  const widgetId = captchaWidgets.get(action);
  if (!enterprise || widgetId === undefined) {
    throw new Error("reCAPTCHA を利用できません。ページを再読み込みしてください。");
  }

  const token = enterprise.getResponse(widgetId);
  if (!token) {
    throw new Error("送信前に reCAPTCHA の確認を完了してください。");
  }
  return token;
};

window.resetRecaptcha = (action) => {
  const enterprise = window.grecaptcha?.enterprise;
  const widgetId = captchaWidgets.get(action);
  if (enterprise && widgetId !== undefined) {
    enterprise.reset(widgetId);
  }
};
