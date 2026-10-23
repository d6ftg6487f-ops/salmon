import { defineConfig } from "@playwright/test";

const externalURL = process.env.FRONTEND_BASE_URL;
const localURL = "http://127.0.0.1:8765";
const python = process.env.PYTHON || "python3";
const quote = (value: string) => `'${value.replaceAll("'", `'"'"'`)}'`;

export default defineConfig({
  testDir: "./tests/frontend",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    browserName: "chromium",
    baseURL: externalURL || localURL,
    trace: "retain-on-failure",
  },
  webServer: externalURL ? undefined : {
    command: `${quote(python)} tests/frontend/server.py`,
    url: localURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
