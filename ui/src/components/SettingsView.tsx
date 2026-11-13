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
  { id: "google/gemini-2.5-flash", name: "Gemini 2.5 Flash", badge: "Fastest • Multimodal" },
  { id: "google/gemini-2.5-pro", name: "Gemini 2.5 Pro", badge: "Highest Reasoning" },
  { id: "anthropic/claude-3.7-sonnet", name: "Claude 3.7 Sonnet", badge: "Agentic Specialist" },
  { id: "openai/gpt-4o", name: "GPT-4o", badge: "Universal" },
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
    settings.vision_api_base ||
      settings.base_url ||
      "https://openrouter.ai/api/v1"
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
    setBaseUrl(
      settings.vision_api_base ||
        settings.base_url ||
        "https://openrouter.ai/api/v1"
    );
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
        vision_api_base: baseUrl.trim() || "https://openrouter.ai/api/v1",
        vision_model: visionModel,
        max_vision_steps: maxSteps,
        stt_engine: sttEngine,
        always_on_top: alwaysOnTop,
        use_jev: useJev,
      };
      if (apiKey.trim()) {
        payload.vision_api_key = apiKey.trim();
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
      className="flex-1 overflow-y-auto px-5 py-4 space-y-5 max-w-5xl mx-auto w-full"
    >
      {/* Toast Feedback */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-5 py-3 rounded-full bg-emerald-500 text-slate-950 text-xs font-bold shadow-2xl shadow-emerald-500/30 animate-bounce-subtle">
          <CheckCircle2 className="w-4 h-4" />
          <span>{toast}</span>
        </div>
      )}

      {/* Card 1: OpenRouter API & Vision Intelligence (M3 Container) */}
      <section className="rounded-3xl bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-[#D0BCFF]/15 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-[#6750A4] dark:text-[#D0BCFF]" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-[#E6E0E9]">
                AI Vision & Reasoning
              </h3>
              <p className="text-xs text-slate-500 dark:text-[#CAC4D0]">
                Configure OpenRouter neural models for desktop GUI automation
              </p>
            </div>
          </div>

          <span
            className={`px-3 py-1 rounded-full text-[11px] font-bold border ${
              settings.has_api_key
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"
                : "bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30"
            }`}
          >
            {settings.has_api_key ? "API Key Connected" : "API Key Required"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0] flex items-center gap-1.5">
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
                className="w-full pr-10 pl-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all"
              />
              <button
                type="button"
                onClick={() => setShowKey((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 p-1 rounded-full"
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
            <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0]">
              API Base URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all font-mono"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0]">
              Multimodal Vision Model
            </label>
            <select
              value={visionModel}
              onChange={(e) => setVisionModel(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all cursor-pointer"
            >
              {VISION_MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.badge})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0]">
                Max Vision Execution Steps
              </label>
              <span className="text-xs font-mono font-bold text-[#6750A4] dark:text-[#D0BCFF]">
                {maxSteps} steps
              </span>
            </div>
            <input
              type="range"
              min={3}
              max={20}
              value={maxSteps}
              onChange={(e) => setMaxSteps(Number(e.target.value))}
              className="w-full accent-[#6750A4] dark:accent-[#D0BCFF] cursor-pointer mt-2"
            />
          </div>
        </div>
      </section>

      {/* Card 2: Voice & Speech Engine (M3 Container) */}
      <section className="rounded-3xl bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-emerald-500/15 flex items-center justify-center">
              <Mic className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-[#E6E0E9]">
                Speech & Recognition Engine (STT)
              </h3>
              <p className="text-xs text-slate-500 dark:text-[#CAC4D0]">
                Choose between On-Device Fast Parakeet Neural weights or Cloud Multimodal STT
              </p>
            </div>
          </div>

          <span
            className={`px-3 py-1 rounded-full text-[11px] font-bold border ${
              settings.has_local_model
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"
                : "bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30"
            }`}
          >
            {settings.has_local_model ? "Local Weights Ready" : "Local Model Missing"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end pt-1">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0]">
              Speech Engine Mode
            </label>
            <select
              value={sttEngine}
              onChange={(e) =>
                setSttEngine(e.target.value as "parakeet" | "cloud")
              }
              className="w-full px-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all cursor-pointer"
            >
              <option value="parakeet">
                ⚡ On-Device Parakeet INT8 + Cloud Fallback
              </option>
              <option value="cloud">
                ☁️ Cloud Gemini 2.5 Flash Speech (High Accuracy)
              </option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            {downloadProgress.active ? (
              <button
                type="button"
                onClick={onCancelDownload}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-full text-xs font-bold bg-rose-500/15 hover:bg-rose-500 text-rose-500 hover:text-white border border-rose-500/30 transition-all"
              >
                <XCircle className="w-4 h-4" />
                <span>Cancel Download ({downloadPct}%)</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onDownloadModel}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-full text-xs font-bold bg-[#D0BCFF]/15 hover:bg-[#D0BCFF] text-[#6750A4] dark:text-[#D0BCFF] hover:text-[#381E72] border border-[#D0BCFF]/30 transition-all shadow-sm"
              >
                <Download className="w-4 h-4" />
                <span>
                  {settings.has_local_model
                    ? "Re-download Offline Model (~600MB)"
                    : "Download Offline Model (~600MB)"}
                </span>
              </button>
            )}
          </div>
        </div>

        {downloadProgress.active && (
          <div className="space-y-1.5 pt-1">
            <div className="flex justify-between text-[11px] font-mono text-slate-500 dark:text-[#CAC4D0]">
              <span>{downloadProgress.stage || "Downloading neural weights..."}</span>
              <span>{downloadPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-slate-200 dark:bg-[#141218] overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-[#D0BCFF] transition-all duration-300"
                style={{ width: `${downloadPct}%` }}
              />
            </div>
          </div>
        )}
      </section>

      {/* Card 3: App Experience & Updates (M3 Container) */}
      <section className="rounded-3xl bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-[#E6E0E9]">
              Application Experience & Updates
            </h3>
            <p className="text-xs text-slate-500 dark:text-[#CAC4D0]">
              Installed version: v{settings.app_version || "2.1.0"}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {updateStatus.status === "available" ? (
              <button
                type="button"
                onClick={onInstallUpdate}
                className="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] shadow-sm transition-all"
              >
                <Download className="w-4 h-4" />
                <span>Install Update ({updateStatus.version})</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onCheckUpdate}
                disabled={updateStatus.status === "checking"}
                className="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-semibold bg-slate-200/70 dark:bg-[#2B2833] hover:bg-slate-300 dark:hover:bg-[#36333F] text-slate-800 dark:text-[#E6E0E9] border border-black/5 dark:border-white/5 transition-all"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${
                    updateStatus.status === "checking" ? "animate-spin text-[#D0BCFF]" : ""
                  }`}
                />
                <span>
                  {updateStatus.status === "checking"
                    ? "Checking GitHub..."
                    : updateStatus.status === "up_to_date"
                    ? "Up to Date"
                    : "Check for Updates"}
                </span>
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 pt-1">
          <label className="flex items-center justify-between p-4 rounded-2xl bg-slate-200/60 dark:bg-[#141218] border border-black/5 dark:border-white/5 cursor-pointer hover:border-[#D0BCFF]/30 transition-all">
            <div className="space-y-0.5">
              <span className="text-xs font-semibold text-slate-800 dark:text-[#E6E0E9]">
                Always-on-Top Mode
              </span>
              <p className="text-[11px] text-slate-500 dark:text-[#938F99]">
                Keep Nova window visible above active desktop apps
              </p>
            </div>
            <input
              type="checkbox"
              checked={alwaysOnTop}
              onChange={(e) => setAlwaysOnTop(e.target.checked)}
              className="w-4 h-4 accent-[#6750A4] dark:accent-[#D0BCFF] rounded cursor-pointer ml-3"
            />
          </label>

          <label className="flex items-center justify-between p-4 rounded-2xl bg-slate-200/60 dark:bg-[#141218] border border-black/5 dark:border-white/5 cursor-pointer hover:border-[#D0BCFF]/30 transition-all">
            <div className="space-y-0.5">
              <span className="text-xs font-semibold text-slate-800 dark:text-[#E6E0E9]">
                JEV Semantic Routing
              </span>
              <p className="text-[11px] text-slate-500 dark:text-[#938F99]">
                Use smart language model to parse natural paraphrases
              </p>
            </div>
            <input
              type="checkbox"
              checked={useJev}
              onChange={(e) => setUseJev(e.target.checked)}
              className="w-4 h-4 accent-[#6750A4] dark:accent-[#D0BCFF] rounded cursor-pointer ml-3"
            />
          </label>
        </div>

        {updateStatus.status === "error" && updateStatus.error && (
          <p className="text-xs text-rose-500">{updateStatus.error}</p>
        )}
      </section>

      {/* Floating Save Button */}
      <div className="flex justify-end pb-4 pt-1">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-full text-xs font-bold bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] hover:brightness-110 shadow-lg shadow-purple-500/25 transition-all disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          <span>{saving ? "Saving Changes..." : "Save Settings"}</span>
        </button>
      </div>
    </form>
  );
};
