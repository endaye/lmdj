import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const render = vi.fn();
const getAudio = vi.fn(async () => ({
  engine: {},
  decode: vi.fn(),
}));

vi.mock("react-dom/client", () => ({
  createRoot: vi.fn(() => ({ render })),
}));

vi.mock("./ui/useEngine", () => ({
  getAudio,
}));

describe("web startup", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("VITE_PRODUCT_VERSION", "v0.2.0");
    vi.stubEnv(
      "VITE_BUILD_REVISION",
      "afa06994f35e97ce8fd1729f10d69958524ec634",
    );
    document.body.innerHTML = '<div id="root"></div>';
    render.mockClear();
    getAudio.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("prints the complete build identity exactly once", async () => {
    const consoleInfo = vi.spyOn(console, "info").mockImplementation(() => {});

    await import("./main");
    await vi.waitFor(() => expect(render).toHaveBeenCalledOnce());

    expect(consoleInfo).toHaveBeenCalledOnce();
    expect(consoleInfo).toHaveBeenCalledWith(
      "[LMDJ] v0.2.0 · afa06994",
    );
  });
});
