import React, { useCallback, useEffect, useState } from "react";
import { Mic, MicOff, Send, ShieldAlert, Square } from "lucide-react";
import { HeaderBar } from "./components/HeaderBar";
import { StudioView } from "./components/StudioView";
import { CommandsView } from "./components/CommandsView";
import { SettingsView } from "./components/SettingsView";
import { RobotMascot3D } from "./components/RobotMascot3D";
import {
  approveLearned,
  cancelDownload,
  checkUpdate,
  clearQueue,
  closeWin,
  confirmGuardrail,
  deleteLearned,
  downloadModel,
  getInitialState,
  getMcpConfig,
  installUpdate,
  listLearned,
  minimizeWin,
  removeQueued,
  runCommand,
  saveSettings,
  setAlwaysOnTop,
  setCompactMode,
  setContinuous,
  subscribeBridgeEvents,
  toggleLearned,
  toggleMic,
  triggerPanic,
} from "./lib/bridge";
import type {
  ActivityEntry,
  AppSettings,
  BridgeEvent,
  DownloadProgress,
  IntentCommand,
  LearnedCommand,
  LogKind,
  MascotState,
  NavTab,
  QueueState,
  UpdateStatus,
} from "./types";

function formatTime(): string {
  const now = new Date();
  return now.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function inferTier(line: string, kind: LogKind): ActivityEntry["tier"] {
  if (kind === "guardrail") return "Guardrail";
  if (kind === "vision" || line.toLowerCase().includes("vision")) {
    return "Tier-2 Vision";
  }
  if (kind === "action" || line.toLowerCase().includes("router")) {
    return "Tier-1 Router";
  }
  return "System";
}

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("studio");
  const [mascotState, setMascotState] = useState<MascotState>("ready");
  const [statusText, setStatusText] = useState(
    "Nova is ready. Hold Left Ctrl or type a command."
  );
  const [statusDetail, setStatusDetail] = useState("Ready");
  const [audioLevel, setAudioLevel] = useState(0);
  const [continuous, setContinuousState] = useState(false);
  const [compact, setCompact] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  const [activities, setActivities] = useState<ActivityEntry[]>([]);
  const [intents, setIntents] = useState<IntentCommand[]>([]);
  const [queue, setQueue] = useState<QueueState>({ pending: [], running: null });
  const [learnedCommands, setLearnedCommands] = useState<LearnedCommand[]>([]);
  const [mcpConfig, setMcpConfig] = useState<string>("");
  const [settings, setSettings] = useState<AppSettings>({
    vision_model: "google/gemini-2.5-flash",
    stt_cloud_model: "google/gemini-2.5-flash",
    theme: "dark",
    max_vision_steps: 8,
    use_jev: true,
    has_api_key: false,
    has_local_model: false,
    app_version: "2.5.1",
  });
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress>({
    active: false,
    done: 0,
    total: 0,
    stage: "",
  });
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus>({
    status: "idle",
  });
  const [miniInput, setMiniInput] = useState("");

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [theme]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        void triggerPanic();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleBridgeEvent = useCallback((ev: BridgeEvent) => {
    switch (ev.event) {
      case "state": {
        setMascotState(ev.state || "ready");
        if (typeof ev.text === "string") setStatusText(ev.text);
        if (typeof ev.detail === "string") setStatusDetail(ev.detail);
        if (typeof ev.continuous === "boolean") {
          setContinuousState(ev.continuous);
        }
        break;
      }
      case "audio_level": {
        setAudioLevel(typeof ev.level === "number" ? ev.level : 0);
        break;
      }
      case "log": {
        const kind: LogKind = ev.kind || "info";
        const entry: ActivityEntry = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          timestamp: formatTime(),
          line: ev.line,
          kind,
          tier: inferTier(ev.line, kind),
        };
        setActivities((prev) => [entry, ...prev].slice(0, 60));
        break;
      }
      case "settings": {
        if (ev.data) {
          setSettings((prev) => ({ ...prev, ...ev.data }));
          if (ev.data.theme === "light" || ev.data.theme === "dark") {
            setTheme(ev.data.theme);
          }
          if (typeof ev.data.always_on_top === "boolean") {
            setPinned(ev.data.always_on_top);
          }
        }
        break;
      }
      case "intents": {
        if (Array.isArray(ev.data)) {
          setIntents(ev.data);
        }
        break;
      }
      case "queue": {
        setQueue({
          pending: Array.isArray(ev.pending) ? ev.pending : [],
          running: ev.running ?? null,
        });
        break;
      }
      case "learned": {
        if (Array.isArray(ev.data)) {
          setLearnedCommands(ev.data);
        }
        break;
      }
      case "mcp_config": {
        if (typeof ev.data === "string") {
          setMcpConfig(ev.data);
        }
        break;
      }
      case "download_progress": {
        const done = ev.done ?? 0;
        const total = ev.total ?? 0;
        const stage = ev.stage ?? "";
        const isDone =
          (total > 0 && done >= total) ||
          stage.toLowerCase().includes("complete") ||
          stage.toLowerCase().includes("cancelled");
        setDownloadProgress({
          active: !isDone && total > 0,
          done,
          total,
          stage,
        });
        break;
      }
    }
  }, []);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void (async () => {
      unlisten = await subscribeBridgeEvents(handleBridgeEvent);
      await getInitialState();
      void listLearned();
      void getMcpConfig();
    })();
    return () => {
      unlisten?.();
    };
  }, [handleBridgeEvent]);

  const handleToggleCompact = async () => {
    const next = !compact;
    setCompact(next);
    await setCompactMode(next);
  };

  const handleTogglePin = async () => {
    const next = !pinned;
    setPinned(next);
    await setAlwaysOnTop(next);
  };

  const handleToggleTheme = async () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    await saveSettings({ theme: next });
  };

  const handleToggleContinuous = async () => {
    const next = !continuous;
    setContinuousState(next);
    await setContinuous(next);
  };

  const handleRunCommand = async (text: string) => {
    if (activeTab === "commands") {
      setActiveTab("studio");
    }
    await runCommand(text);
  };

  const handleCheckUpdate = async () => {
    setUpdateStatus({ status: "checking" });
    try {
      const res = await checkUpdate();
      setUpdateStatus(res);
    } catch (err) {
      const msg =
        typeof err === "string"
          ? err
          : err instanceof Error
          ? err.message
          : "Failed to check updates";
      setUpdateStatus({
        status: "error",
        error: msg,
      });
    }
  };

  const handleInstallUpdate = async () => {
    setUpdateStatus((prev) => ({ ...prev, status: "downloading", error: undefined }));
    try {
      await installUpdate();
    } catch (err) {
      const msg =
        typeof err === "string"
          ? err
          : err instanceof Error
          ? err.message
          : "Failed to install update";
      setUpdateStatus((prev) => ({
        ...prev,
        status: "error",
        error: msg,
      }));
    }
  };

  const handleMiniSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = miniInput.trim();
    if (!trimmed) return;
    setMiniInput("");
    await runCommand(trimmed);
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-[#FEF7FF] dark:bg-[#0F0D14] text-slate-900 dark:text-[#E6E0E9] overflow-hidden relative select-none font-sans">
      {/* Ambient M3 Background Glows */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-32 -left-28 w-96 h-96 rounded-full bg-[#6750A4]/10 dark:bg-[#D0BCFF]/8 blur-3xl" />
        <div className="absolute -bottom-32 -right-28 w-96 h-96 rounded-full bg-[#0284C7]/10 dark:bg-[#7DD3FC]/8 blur-3xl" />
      </div>

      {/* Custom M3 Frameless Header */}
      <HeaderBar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        aiReady={settings.has_api_key}
        offlineReady={settings.has_local_model}
        compact={compact}
        onToggleCompact={() => void handleToggleCompact()}
        alwaysOnTop={pinned}
        onTogglePin={() => void handleTogglePin()}
        theme={theme}
        onToggleTheme={() => void handleToggleTheme()}
        onMinimize={() => void minimizeWin()}
        onClose={() => void closeWin()}
        version={settings.app_version || "2.5.1"}
      />

      {/* Main Content */}
      {compact ? (
        <main className="flex-1 flex flex-col items-center justify-between p-4 gap-3 relative z-10">
          <div className="w-40 h-40 relative flex items-center justify-center rounded-2xl">
            <div className="pointer-events-none absolute inset-0 rounded-2xl bg-[radial-gradient(circle_at_50%_48%,rgba(208,188,255,0.24),transparent_72%)] dark:bg-[radial-gradient(circle_at_50%_48%,rgba(208,188,255,0.14),transparent_72%)]" />
            <RobotMascot3D
              state={mascotState}
              audioLevel={audioLevel}
              theme={theme}
              compact
              onClick={() => void toggleMic()}
            />
          </div>

          <p className="text-xs font-semibold text-center text-slate-700 dark:text-[#CAC4D0] line-clamp-2 px-2">
            {statusText}
          </p>

          {mascotState === "guardrail" && (
            <div className="w-full flex items-center justify-center gap-2 p-2.5 rounded-full bg-amber-500/15 border border-amber-500/40">
              <ShieldAlert className="w-4 h-4 text-amber-500 shrink-0" />
              <button
                type="button"
                onClick={() => void confirmGuardrail(true)}
                className="px-3 py-1 rounded-full text-xs font-bold bg-amber-500 text-slate-950"
              >
                Approve
              </button>
              <button
                type="button"
                onClick={() => void confirmGuardrail(false)}
                className="px-3 py-1 rounded-full text-xs font-semibold bg-slate-200 dark:bg-[#2B2833] text-slate-800 dark:text-[#E6E0E9]"
              >
                Cancel
              </button>
            </div>
          )}

          <div className="w-full space-y-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void toggleMic()}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-full text-xs font-bold transition-all ${
                  mascotState === "listening"
                    ? "bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/25"
                    : "bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] shadow-md shadow-purple-500/25"
                }`}
              >
                {mascotState === "listening" ? (
                  <>
                    <MicOff className="w-3.5 h-3.5" />
                    <span>Stop</span>
                  </>
                ) : (
                  <>
                    <Mic className="w-3.5 h-3.5" />
                    <span>Speak</span>
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => void triggerPanic()}
                title="Panic Stop (Esc)"
                className="p-2.5 rounded-full bg-rose-500/15 text-rose-500 hover:bg-rose-500 hover:text-white border border-rose-500/30 transition-colors"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            </div>

            <form
              onSubmit={(e) => void handleMiniSubmit(e)}
              className="flex items-center gap-1.5 p-1 rounded-full bg-slate-200/70 dark:bg-[#1F1D26] border border-black/5 dark:border-white/10"
            >
              <input
                type="text"
                value={miniInput}
                onChange={(e) => setMiniInput(e.target.value)}
                placeholder="Type command..."
                className="flex-1 bg-transparent px-3 py-1 text-xs focus:outline-none text-slate-900 dark:text-[#E6E0E9]"
              />
              <button
                type="submit"
                className="p-1.5 rounded-full bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72]"
              >
                <Send className="w-3 h-3" />
              </button>
            </form>
          </div>
        </main>
      ) : (
        <main className="flex-1 flex flex-col min-h-0 relative z-10">
          {activeTab === "studio" && (
            <StudioView
              state={mascotState}
              statusText={statusText}
              statusDetail={statusDetail}
              audioLevel={audioLevel}
              continuous={continuous}
              theme={theme}
              activities={activities}
              queue={queue}
              onToggleMic={() => void toggleMic()}
              onToggleContinuous={() => void handleToggleContinuous()}
              onPanic={() => void triggerPanic()}
              onRunCommand={(text) => void handleRunCommand(text)}
              onConfirmGuardrail={(approved) =>
                void confirmGuardrail(approved)
              }
              onRemoveQueued={(id) => void removeQueued(id)}
              onClearQueue={() => void clearQueue()}
            />
          )}

          {activeTab === "commands" && (
            <CommandsView
              intents={intents}
              onRunCommand={(text) => void handleRunCommand(text)}
            />
          )}

          {activeTab === "settings" && (
            <SettingsView
              settings={settings}
              downloadProgress={downloadProgress}
              updateStatus={updateStatus}
              learnedCommands={learnedCommands}
              mcpConfig={mcpConfig}
              onSaveSettings={async (next) => {
                await saveSettings(next);
                if (typeof next.always_on_top === "boolean") {
                  setPinned(next.always_on_top);
                  await setAlwaysOnTop(next.always_on_top);
                }
              }}
              onDownloadModel={() => void downloadModel()}
              onCancelDownload={() => void cancelDownload()}
              onCheckUpdate={() => void handleCheckUpdate()}
              onInstallUpdate={() => void handleInstallUpdate()}
              onApproveLearned={(id) => void approveLearned(id)}
              onToggleLearned={(id, enabled) => void toggleLearned(id, enabled)}
              onDeleteLearned={(id) => void deleteLearned(id)}
              onRefreshMcp={() => {
                void listLearned();
                void getMcpConfig();
              }}
            />
          )}
        </main>
      )}
    </div>
  );
}

export default App;
