import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  AppSettings,
  BridgeEvent,
  ConnectionTestResult,
  IntentCommand,
  LearnedCommand,
  MascotState,
  ModelInfo,
  QueueItem,
  UpdateStatus,
} from "../types";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export const isTauriEnv = (): boolean =>
  typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);

const DEFAULT_INTENTS: IntentCommand[] = [
  {
    name: "open_app",
    description: "Launch any installed Windows app (Notepad, Calculator, Chrome, VS Code, Spotify).",
    phrases: ["open notepad", "open calculator", "launch chrome", "open code"],
    category: "Apps & Windows",
  },
  {
    name: "window_minimize",
    description: "Minimize the currently active window.",
    phrases: ["minimize window", "minimize", "hide window"],
    category: "Apps & Windows",
  },
  {
    name: "window_maximize",
    description: "Maximize the active window to fill the screen.",
    phrases: ["maximize window", "maximize", "fullscreen window"],
    category: "Apps & Windows",
  },
  {
    name: "window_snap_left",
    description: "Snap the active window to the left half of the screen.",
    phrases: ["snap window left", "snap left", "tile left"],
    category: "Apps & Windows",
  },
  {
    name: "window_snap_right",
    description: "Snap the active window to the right half of the screen.",
    phrases: ["snap window right", "snap right", "tile right"],
    category: "Apps & Windows",
  },
  {
    name: "window_close",
    description: "Close the active window (requires guardrail confirmation).",
    phrases: ["close window", "close app"],
    category: "Apps & Windows",
    destructive: true,
  },
  {
    name: "browser_new_tab",
    description: "Open a new tab in your active browser.",
    phrases: ["new browser tab", "new tab", "open tab"],
    category: "Browser & Web",
  },
  {
    name: "browser_close_tab",
    description: "Close the current browser tab.",
    phrases: ["close tab", "shut tab"],
    category: "Browser & Web",
  },
  {
    name: "search_youtube",
    description: "Search YouTube for videos or music.",
    phrases: ["search youtube for lofi hip hop", "youtube search"],
    category: "Browser & Web",
  },
  {
    name: "search_google",
    description: "Search Google in your default browser.",
    phrases: ["google weather today", "search google for"],
    category: "Browser & Web",
  },
  {
    name: "volume_up",
    description: "Increase system audio volume.",
    phrases: ["volume up", "increase volume", "louder"],
    category: "Media & System",
  },
  {
    name: "volume_down",
    description: "Decrease system audio volume.",
    phrases: ["volume down", "lower volume", "softer"],
    category: "Media & System",
  },
  {
    name: "volume_mute",
    description: "Toggle system audio mute.",
    phrases: ["mute audio", "mute", "unmute"],
    category: "Media & System",
  },
  {
    name: "media_play_pause",
    description: "Play or pause active media playback.",
    phrases: ["play music", "pause music", "play", "pause"],
    category: "Media & System",
  },
  {
    name: "take_screenshot",
    description: "Capture a screenshot of your active monitor.",
    phrases: ["take screenshot", "screenshot", "capture screen"],
    category: "Media & System",
  },
  {
    name: "vision_agent",
    description: "Use Tier-2 AI Vision to inspect the screen and click/type on any UI element.",
    phrases: [
      "click the sign in button",
      "scroll down and open settings",
      "summarize what is on my screen",
    ],
    category: "AI Vision",
  },
];

const DEFAULT_SETTINGS: AppSettings = {
  vision_api_key: "",
  openrouter_api_key: "",
  vision_api_base: "https://openrouter.ai/api/v1",
  vision_model: "google/gemini-2.5-flash",
  stt_engine: "parakeet",
  stt_cloud_model: "google/gemini-2.5-flash",
  theme: "dark",
  max_vision_steps: 8,
  use_jev: true,
  always_on_top: false,
  has_api_key: true,
  masked_key: "sk-or-v1-••••••demo",
  has_local_model: false,
  app_version: "2.5.0",
};

type Listener = (ev: BridgeEvent) => void;
const browserListeners = new Set<Listener>();
let browserState: MascotState = "ready";
let browserMicTimer: number | null = null;
let browserDownloadTimer: number | null = null;
let browserSettings: AppSettings = { ...DEFAULT_SETTINGS };

function emitBrowser(ev: BridgeEvent) {
  browserListeners.forEach((fn) => fn(ev));
}

export async function subscribeBridgeEvents(
  onEvent: (event: BridgeEvent) => void
): Promise<UnlistenFn> {
  if (isTauriEnv()) {
    return listen<BridgeEvent>("bridge-event", (msg) => {
      if (msg?.payload) {
        onEvent(msg.payload);
      }
    });
  }

  browserListeners.add(onEvent);
  return () => {
    browserListeners.delete(onEvent);
  };
}

export async function getInitialState(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("get_initial_state");
    return;
  }
  setTimeout(() => {
    emitBrowser({
      event: "state",
      state: browserState,
      text: "Nova is ready. Hold Left Ctrl or type a command.",
      detail: "Browser preview mode (Tauri IPC inactive)",
    });
    emitBrowser({ event: "settings", data: { ...browserSettings } });
    emitBrowser({ event: "intents", data: DEFAULT_INTENTS });
    emitBrowser({
      event: "log",
      line: "Computer-Auto v2.5 initialized in preview mode",
      kind: "info",
    });
  }, 50);
}

export async function runCommand(text: string): Promise<void> {
  if (isTauriEnv()) {
    await invoke("run_command", { text });
    return;
  }

  const trimmed = text.trim();
  if (!trimmed) return;

  const lower = trimmed.toLowerCase();
  const isDestructive =
    lower.includes("delete") ||
    lower.includes("close window") ||
    lower.includes("shutdown") ||
    lower.includes("format");

  emitBrowser({
    event: "state",
    state: "processing",
    text: `Routing "${trimmed}"...`,
    detail: "Analyzing intent",
  });

  setTimeout(() => {
    if (isDestructive) {
      browserState = "guardrail";
      emitBrowser({
        event: "state",
        state: "guardrail",
        text: `Confirm destructive action: "${trimmed}"`,
        detail: "Guardrail triggered — awaiting approval",
      });
      emitBrowser({
        event: "log",
        line: `Guardrail: Approval required for "${trimmed}"`,
        kind: "guardrail",
      });
      return;
    }

    const isTier1 =
      lower.startsWith("open ") ||
      lower.includes("volume") ||
      lower.includes("mute") ||
      lower.includes("tab") ||
      lower.includes("snap") ||
      lower.includes("screenshot") ||
      lower.includes("minimize") ||
      lower.includes("maximize");

    emitBrowser({
      event: "state",
      state: "executing",
      text: isTier1 ? `Executing "${trimmed}"` : `Vision agent running "${trimmed}"`,
      detail: isTier1 ? "Tier-1 Deterministic Router" : "Tier-2 AI Vision Loop",
    });

    setTimeout(() => {
      browserState = "ready";
      emitBrowser({
        event: "log",
        line: isTier1
          ? `[Tier-1 Router] Executed: ${trimmed}`
          : `[Tier-2 Vision] Completed: ${trimmed}`,
        kind: isTier1 ? "action" : "vision",
      });
      emitBrowser({
        event: "state",
        state: "ready",
        text: `Done: "${trimmed}"`,
        detail: "Ready for next command",
      });
    }, 850);
  }, 450);
}

export async function toggleMic(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("toggle_mic");
    return;
  }

  if (browserState === "listening") {
    browserState = "ready";
    if (browserMicTimer) {
      window.clearInterval(browserMicTimer);
      browserMicTimer = null;
    }
    emitBrowser({ event: "audio_level", level: 0 });
    emitBrowser({
      event: "state",
      state: "ready",
      text: "Microphone stopped.",
      detail: "Idle",
    });
  } else {
    browserState = "listening";
    emitBrowser({
      event: "state",
      state: "listening",
      text: "Listening... speak your command",
      detail: "Audio capture active",
    });
    browserMicTimer = window.setInterval(() => {
      const level = Math.min(1, Math.max(0.08, Math.random() * 0.85));
      emitBrowser({ event: "audio_level", level });
    }, 90);
  }
}

export async function setContinuous(enabled: boolean): Promise<void> {
  if (isTauriEnv()) {
    await invoke("set_continuous", { enabled });
    return;
  }
  emitBrowser({
    event: "log",
    line: `Continuous voice mode ${enabled ? "enabled" : "disabled"}`,
    kind: "info",
  });
}

export async function triggerPanic(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("trigger_panic");
    return;
  }
  if (browserMicTimer) {
    window.clearInterval(browserMicTimer);
    browserMicTimer = null;
  }
  browserState = "ready";
  emitBrowser({ event: "audio_level", level: 0 });
  emitBrowser({
    event: "log",
    line: "PANIC STOP triggered — all active actions aborted",
    kind: "error",
  });
  emitBrowser({
    event: "state",
    state: "ready",
    text: "Aborted by Panic Stop (Esc)",
    detail: "Ready",
  });
}

export async function confirmGuardrail(approved: boolean): Promise<void> {
  if (isTauriEnv()) {
    await invoke("confirm_guardrail", { approved });
    return;
  }
  browserState = "ready";
  emitBrowser({
    event: "log",
    line: approved
      ? "Guardrail approved — action executed"
      : "Guardrail cancelled — action aborted",
    kind: approved ? "action" : "info",
  });
  emitBrowser({
    event: "state",
    state: "ready",
    text: approved ? "Action approved and completed." : "Action cancelled.",
    detail: "Ready",
  });
}

export async function saveSettings(
  settings: Partial<AppSettings>
): Promise<void> {
  if (isTauriEnv()) {
    await invoke("save_settings", { settings });
    return;
  }
  const rawKey = settings.vision_api_key || settings.openrouter_api_key || "";
  const hasNewKey = Boolean(rawKey.trim());
  browserSettings = {
    ...browserSettings,
    ...settings,
    has_api_key: hasNewKey || browserSettings.has_api_key,
    masked_key: hasNewKey
      ? `sk-or-••••••${rawKey.trim().slice(-4)}`
      : browserSettings.masked_key,
  };
  emitBrowser({ event: "settings", data: { ...browserSettings } });
  emitBrowser({
    event: "log",
    line: "Settings saved",
    kind: "info",
  });
}

export async function downloadModel(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("download_model");
    return;
  }
  if (browserDownloadTimer) return;
  let pct = 0;
  browserDownloadTimer = window.setInterval(() => {
    pct += 10;
    emitBrowser({
      event: "download_progress",
      done: pct,
      total: 100,
      stage: pct < 100 ? `Downloading Parakeet INT8 (${pct}%)...` : "Complete",
    });
    if (pct >= 100 && browserDownloadTimer) {
      window.clearInterval(browserDownloadTimer);
      browserDownloadTimer = null;
      browserSettings = { ...browserSettings, has_local_model: true };
      emitBrowser({ event: "settings", data: { ...browserSettings } });
    }
  }, 220);
}

export async function cancelDownload(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("cancel_download");
    return;
  }
  if (browserDownloadTimer) {
    window.clearInterval(browserDownloadTimer);
    browserDownloadTimer = null;
  }
  emitBrowser({
    event: "download_progress",
    done: 0,
    total: 0,
    stage: "Cancelled",
  });
}

export async function checkUpdate(): Promise<UpdateStatus> {
  if (isTauriEnv()) {
    const res = await invoke<Record<string, unknown>>("check_update");
    const available = Boolean(res?.available ?? res?.update_available);
    const version =
      (res?.latest_version as string) || (res?.version as string) || undefined;
    const error = res?.error as string | undefined;
    if (error) return { status: "error", error };
    if (available && version) {
      return {
        status: "available",
        version,
        notes: (res?.notes as string) || undefined,
      };
    }
    return { status: "up_to_date", version: version || "2.5.0" };
  }
  return { status: "up_to_date", version: "2.5.0" };
}

export async function installUpdate(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("install_update");
    return;
  }
  emitBrowser({
    event: "log",
    line: "Update installer is only available in the desktop app",
    kind: "info",
  });
}

export async function setAlwaysOnTop(pinned: boolean): Promise<void> {
  if (isTauriEnv()) {
    await invoke("set_always_on_top", { pinned });
  }
}

export async function setCompactMode(compact: boolean): Promise<void> {
  if (isTauriEnv()) {
    await invoke("set_compact_mode", { compact });
  }
}

export async function minimizeWin(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("minimize_win");
  }
}

export async function closeWin(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("close_win");
  }
}

export async function listModels(
  baseUrl?: string,
  apiKey?: string
): Promise<{ base_url: string; models: ModelInfo[] }> {
  if (isTauriEnv()) {
    return invoke<{ base_url: string; models: ModelInfo[] }>("list_models", {
      baseUrl: baseUrl ?? null,
      apiKey: apiKey ?? null,
    });
  }
  return {
    base_url:
      baseUrl ||
      browserSettings.vision_api_base ||
      "https://openrouter.ai/api/v1",
    models: [],
  };
}

export async function testConnection(
  baseUrl?: string,
  apiKey?: string,
  model?: string
): Promise<ConnectionTestResult> {
  if (isTauriEnv()) {
    return invoke<ConnectionTestResult>("test_connection", {
      baseUrl: baseUrl ?? null,
      apiKey: apiKey ?? null,
      model: model ?? null,
    });
  }
  const hasKey = Boolean((apiKey || "").trim() || browserSettings.has_api_key);
  return hasKey
    ? { ok: true, message: "Preview mode: API key format looks valid.", models_count: 0 }
    : { ok: false, message: "Enter an API key first." };
}

let browserQueuePending: QueueItem[] = [];
let browserQueueRunning: QueueItem | null = null;

export async function removeQueued(id: string): Promise<void> {
  if (isTauriEnv()) {
    await invoke("remove_queued", { id });
    return;
  }
  browserQueuePending = browserQueuePending.filter((item) => item.id !== id);
  emitBrowser({
    event: "queue",
    pending: browserQueuePending,
    running: browserQueueRunning,
  });
}

export async function clearQueue(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("clear_queue");
    return;
  }
  browserQueuePending = [];
  emitBrowser({
    event: "queue",
    pending: [],
    running: browserQueueRunning,
  });
}

let browserLearned: LearnedCommand[] = [];

export async function listLearned(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("list_learned");
    return;
  }
  emitBrowser({ event: "learned", data: [...browserLearned] });
}

export async function approveLearned(id: string): Promise<void> {
  if (isTauriEnv()) {
    await invoke("approve_learned", { id });
    return;
  }
  browserLearned = browserLearned.map((cmd) =>
    cmd.id === id ? { ...cmd, suggested: false, enabled: true } : cmd
  );
  emitBrowser({ event: "learned", data: [...browserLearned] });
}

export async function toggleLearned(
  id: string,
  enabled: boolean
): Promise<void> {
  if (isTauriEnv()) {
    await invoke("toggle_learned", { id, enabled });
    return;
  }
  browserLearned = browserLearned.map((cmd) =>
    cmd.id === id ? { ...cmd, enabled } : cmd
  );
  emitBrowser({ event: "learned", data: [...browserLearned] });
}

export async function deleteLearned(id: string): Promise<void> {
  if (isTauriEnv()) {
    await invoke("delete_learned", { id });
    return;
  }
  browserLearned = browserLearned.filter((cmd) => cmd.id !== id);
  emitBrowser({ event: "learned", data: [...browserLearned] });
}

export async function getMcpConfig(): Promise<void> {
  if (isTauriEnv()) {
    await invoke("get_mcp_config");
    return;
  }
  emitBrowser({
    event: "mcp_config",
    data: JSON.stringify(
      {
        mcpServers: {
          "computer-auto": {
            command: "python",
            args: ["-m", "src.mcp_server"],
          },
        },
      },
      null,
      2
    ),
  });
}
