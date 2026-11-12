import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  Download,
  Eye,
  EyeOff,
  KeyRound,
  Mic,
  RefreshCw,
  Save,
  Sparkles,
  XCircle,
} from "lucide-react";
import type { AppSettings, DownloadProgress, UpdateStatus } from "../types";

interface SettingsViewProps {
  settings: AppSettings;
  downloadProgress: DownloadProgress;
  updateStatus: UpdateStatus;
  onSaveSettings: (next: Partial<AppSettings>) => Promise<void>;
  onDownloadModel: () => void;
  onCancelDownload: () => void;
  onCheckUpdate: () => void;
  onInstallUpdate: () => void;
}

const VISION_MODELS = [
  "google/gemini-2.5-flash",
  "google/gemini-2.5-pro",
  "anthropic/claude-3.7-sonnet",
  "openai/gpt-4o",
];

export const SettingsView: React.FC<SettingsViewProps> = ({
  settings,
  downloadProgress,
  updateStatus,
  onSaveSettings,
  onDownloadModel,
  onCancelDownload,
  onCheckUpdate,
  onInstallUpdate,
}) => {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState(
    settings.base_url || "https://openrouter.ai/api/v1"
  );
  const [visionModel, setVisionModel] = useState(
    settings.vision_model || "google/gemini-2.5-flash"
  );
  const [maxSteps, setMaxSteps] = useState(settings.max_vision_steps || 8);
  const [sttEngine, setSttEngine] = useState<"parakeet" | "cloud">(
    settings.stt_engine || "parakeet"
  );
  const [alwaysOnTop, setAlwaysOnTop] = useState(Boolean(settings.always_on_top));
  const [useJev, setUseJev] = useState(settings.use_jev ?? true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    setBaseUrl(settings.base_url || "https://openrouter.ai/api/v1");
    setVisionModel(settings.vision_model || "google/gemini-2.5-flash");
    setMaxSteps(settings.max_vision_steps || 8);
    setSttEngine(settings.stt_engine || "parakeet");
    setAlwaysOnTop(Boolean(settings.always_on_top));
    setUseJev(settings.use_jev ?? true);
  }, [settings]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Partial<AppSettings> = {
        base_url: baseUrl.trim() || "https://openrouter.ai/api/v1",
        vision_model: visionModel,
        max_vision_steps: maxSteps,
        stt_engine: sttEngine,
        always_on_top: alwaysOnTop,
        use_jev: useJev,
      };
      if (apiKey.trim()) {
        payload.openrouter_api_key = apiKey.trim();
      }
      await onSaveSettings(payload);
      setApiKey("");
      setToast("Settings saved successfully");
      setTimeout(() => setToast(null), 2600);
    } finally {
      setSaving(false);
    }
  };

  const downloadPct =
    downloadProgress.total > 0
      ? Math.min(
          100,
          Math.round((downloadProgress.done / downloadProgress.total) * 100)
        )
      : 0;

  return (
    <form
      onSubmit={handleSave}
      className="flex-1 overflow-y-auto px-5 py-4 space-y-4"
    >
      {/* Toast Feedback */}
      {toast && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 text-slate-950 text-xs font-semibold shadow-xl">
          <CheckCircle2 className="w-4 h-4" />
          <span>{toast}</span>
        </div>
      )}

      {/* Card 1: AI & Vision */}
      <section className="rounded-2xl glass-panel p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-violet-400" />
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              AI & Vision
            </h3>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
              settings.has_api_key
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"
                : "bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30"
            }`}
          >
            {settings.has_api_key ? "Connected" : "Key Required"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5" />
              OpenRouter API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  settings.has_api_key
                    ? settings.masked_key || "•••••••••••• (saved)"
                    : "sk-or-v1-..."
                }
                className="w-full pr-9 pl-3 py-2 rounded-xl text-xs bg-slate-100/80 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
              />
              <button
                type="button"
                onClick={() => setShowKey((s) => !s)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              >
                {showKey ? (
                  <EyeOff className="w-3.5 h-3.5" />
                ) : (
                  <Eye className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
              API Base URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full px-3 py-2 rounded-xl text-xs bg-slate-100/80 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Vision Model
            </label>
            <select
              value={visionModel}
              onChange={(e) => setVisionModel(e.target.value)}
              className="w-full px-3 py-2 rounded-xl text-xs bg-slate-100/80 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
            >
              {VISION_MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                Max Vision Steps
              </label>
              <span className="text-xs font-mono font-semibold text-sky-500">
                {maxSteps}
              </span>
            </div>
            <input
              type="range"
              min={3}
              max={20}
              value={maxSteps}
              onChange={(e) => setMaxSteps(Number(e.target.value))}
              className="w-full accent-sky-500 cursor-pointer"
            />
          </div>
        </div>
      </section>

      {/* Card 2: Voice & Speech (STT) */}
      <section className="rounded-2xl glass-panel p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Voice & Speech (STT)
            </h3>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
              settings.has_local_model
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"
                : "bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30"
            }`}
          >
            {settings.has_local_model ? "Parakeet Ready" : "Not Downloaded"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 items-end">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Voice Engine
            </label>
            <select
              value={sttEngine}
              onChange={(e) =>
                setSttEngine(e.target.value as "parakeet" | "cloud")
              }
              className="w-full px-3 py-2 rounded-xl text-xs bg-slate-100/80 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
            >
              <option value="parakeet">
                On-Device Parakeet INT8 + Cloud Fallback
              </option>
              <option value="cloud">Cloud Gemini 2.5 Flash Audio</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            {downloadProgress.active ? (
              <button
                type="button"
                onClick={onCancelDownload}
                className="flex-1 flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-rose-500/15 hover:bg-rose-500 text-rose-500 hover:text-white border border-rose-500/30 transition-all"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Cancel Download ({downloadPct}%)</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onDownloadModel}
                className="flex-1 flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-emerald-500/15 hover:bg-emerald-500 text-emerald-600 dark:text-emerald-300 hover:text-slate-950 border border-emerald-500/30 transition-all"
              >
                <Download className="w-3.5 h-3.5" />
                <span>
                  {settings.has_local_model
                    ? "Re-download Offline Model"
                    : "Download Offline Model"}
                </span>
              </button>
            )}
          </div>
        </div>

        {downloadProgress.active && (
          <div className="space-y-1.5">
            <div className="flex justify-between text-[11px] font-mono text-slate-500 dark:text-slate-400">
              <span>{downloadProgress.stage || "Downloading..."}</span>
              <span>{downloadPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-sky-500 transition-all duration-200"
                style={{ width: `${downloadPct}%` }}
              />
            </div>
          </div>
        )}
      </section>

      {/* Card 3: App & Updates */}
      <section className="rounded-2xl glass-panel p-4 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              App & Updates
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Current version: v{settings.app_version || "2.0.0"}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {updateStatus.status === "available" ? (
              <button
                type="button"
                onClick={onInstallUpdate}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Install Update ({updateStatus.version})</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onCheckUpdate}
                disabled={updateStatus.status === "checking"}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 transition-colors"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${
                    updateStatus.status === "checking" ? "animate-spin" : ""
                  }`}
                />
                <span>
                  {updateStatus.status === "checking"
                    ? "Checking..."
                    : updateStatus.status === "up_to_date"
                    ? "Up to Date"
                    : "Check for Updates"}
                </span>
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          <label className="flex items-center justify-between p-3 rounded-xl bg-slate-100/70 dark:bg-slate-950/60 border border-slate-200/70 dark:border-slate-800 cursor-pointer">
            <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
              Always-on-Top Window
            </span>
            <input
              type="checkbox"
              checked={alwaysOnTop}
              onChange={(e) => setAlwaysOnTop(e.target.checked)}
              className="w-4 h-4 accent-sky-500 rounded cursor-pointer"
            />
          </label>

          <label className="flex items-center justify-between p-3 rounded-xl bg-slate-100/70 dark:bg-slate-950/60 border border-slate-200/70 dark:border-slate-800 cursor-pointer">
            <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
              JEV Voice Feedback
            </span>
            <input
              type="checkbox"
              checked={useJev}
              onChange={(e) => setUseJev(e.target.checked)}
              className="w-4 h-4 accent-sky-500 rounded cursor-pointer"
            />
          </label>
        </div>

        {updateStatus.status === "error" && updateStatus.error && (
          <p className="text-xs text-rose-500">{updateStatus.error}</p>
        )}
      </section>

      {/* Save Button */}
      <div className="flex justify-end pb-2">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-gradient-to-r from-sky-500 to-violet-600 hover:from-sky-400 hover:to-violet-500 text-white shadow-lg shadow-sky-500/20 transition-all disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          <span>{saving ? "Saving..." : "Save Settings"}</span>
        </button>
      </div>
    </form>
  );
};
