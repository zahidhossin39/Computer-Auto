import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  Download,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Mic,
  PlugZap,
  RefreshCw,
  Search,
  Sparkles,
  Volume2,
  XCircle,
} from "lucide-react";
import { listModels, testConnection } from "../lib/bridge";
import { McpCard } from "./McpCard";
import type {
  AppSettings,
  ConnectionTestResult,
  DownloadProgress,
  LearnedCommand,
  ModelInfo,
  UpdateStatus,
} from "../types";

interface SettingsViewProps {
  settings: AppSettings;
  downloadProgress: DownloadProgress;
  updateStatus: UpdateStatus;
  learnedCommands: LearnedCommand[];
  mcpConfig: string;
  onSaveSettings: (next: Partial<AppSettings>) => Promise<void>;
  onDownloadModel: () => void;
  onCancelDownload: () => void;
  onCheckUpdate: () => void;
  onInstallUpdate: () => void;
  onApproveLearned: (id: string) => void;
  onToggleLearned: (id: string, enabled: boolean) => void;
  onDeleteLearned: (id: string) => void;
  onRefreshMcp: () => void;
}

type ProviderPresetId = "openrouter" | "google" | "anthropic" | "openai" | "custom";

interface ProviderPreset {
  id: ProviderPresetId;
  label: string;
  baseUrl: string;
  defaultModel?: string;
  hint: string;
}

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "openrouter",
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "google/gemini-2.5-flash",
    hint: "Unified API for Gemini, Claude, GPT, Grok, Qwen & Llama",
  },
  {
    id: "google",
    label: "Google AI Studio",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    defaultModel: "gemini-2.5-flash",
    hint: "Direct Gemini API (OpenAI-compatible endpoint)",
  },
  {
    id: "anthropic",
    label: "Anthropic (via OpenRouter)",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "anthropic/claude-sonnet-4.5",
    hint: "Claude Sonnet / Opus / Haiku routed via OpenRouter",
  },
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4o",
    hint: "Direct OpenAI GPT-5 / GPT-4.1 / GPT-4o API",
  },
  {
    id: "custom",
    label: "Custom / Local",
    baseUrl: "",
    hint: "Ollama, LM Studio, vLLM, or any OpenAI-compatible server",
  },
];

const FALLBACK_MODELS: ModelInfo[] = [
  {
    id: "google/gemini-2.5-flash",
    name: "Gemini 2.5 Flash",
    provider: "Google Gemini",
    context_length: 1048576,
    input_modalities: ["text", "image", "audio", "file"],
    pricing_prompt: "0.0000003",
    pricing_completion: "0.0000025",
    supports_vision: true,
    supports_audio: true,
  },
  {
    id: "google/gemini-2.5-pro",
    name: "Gemini 2.5 Pro",
    provider: "Google Gemini",
    context_length: 1048576,
    input_modalities: ["text", "image", "audio", "file"],
    pricing_prompt: "0.00000125",
    pricing_completion: "0.00001",
    supports_vision: true,
    supports_audio: true,
  },
  {
    id: "google/gemini-2.5-flash-lite",
    name: "Gemini 2.5 Flash Lite",
    provider: "Google Gemini",
    context_length: 1048576,
    input_modalities: ["text", "image", "audio", "file"],
    pricing_prompt: "0.0000001",
    pricing_completion: "0.0000004",
    supports_vision: true,
    supports_audio: true,
  },
  {
    id: "anthropic/claude-sonnet-4.5",
    name: "Claude Sonnet 4.5",
    provider: "Anthropic Claude",
    context_length: 1000000,
    input_modalities: ["text", "image", "file"],
    pricing_prompt: "0.000003",
    pricing_completion: "0.000015",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "anthropic/claude-opus-4.1",
    name: "Claude Opus 4.1",
    provider: "Anthropic Claude",
    context_length: 200000,
    input_modalities: ["text", "image"],
    pricing_prompt: "0.000015",
    pricing_completion: "0.000075",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "anthropic/claude-haiku-4.5",
    name: "Claude Haiku 4.5",
    provider: "Anthropic Claude",
    context_length: 200000,
    input_modalities: ["text", "image"],
    pricing_prompt: "0.000001",
    pricing_completion: "0.000005",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "openai/gpt-5",
    name: "OpenAI GPT-5",
    provider: "OpenAI",
    context_length: 400000,
    input_modalities: ["text", "image", "file"],
    pricing_prompt: "0.00000125",
    pricing_completion: "0.00001",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "openai/gpt-4.1",
    name: "OpenAI GPT-4.1",
    provider: "OpenAI",
    context_length: 1047576,
    input_modalities: ["text", "image"],
    pricing_prompt: "0.000002",
    pricing_completion: "0.000008",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "openai/gpt-4o",
    name: "OpenAI GPT-4o",
    provider: "OpenAI",
    context_length: 128000,
    input_modalities: ["text", "image"],
    pricing_prompt: "0.0000025",
    pricing_completion: "0.00001",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "openai/gpt-4o-mini",
    name: "OpenAI GPT-4o Mini",
    provider: "OpenAI",
    context_length: 128000,
    input_modalities: ["text", "image"],
    pricing_prompt: "0.00000015",
    pricing_completion: "0.0000006",
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "openai/gpt-audio",
    name: "OpenAI GPT Audio",
    provider: "OpenAI",
    context_length: 128000,
    input_modalities: ["text", "audio"],
    supports_vision: false,
    supports_audio: true,
  },
  {
    id: "openai/gpt-audio-mini",
    name: "OpenAI GPT Audio Mini",
    provider: "OpenAI",
    context_length: 128000,
    input_modalities: ["text", "audio"],
    supports_vision: false,
    supports_audio: true,
  },
  {
    id: "x-ai/grok-4.20",
    name: "xAI Grok 4.20",
    provider: "xAI",
    context_length: 2000000,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "x-ai/grok-4.5",
    name: "xAI Grok 4.5",
    provider: "xAI",
    context_length: 256000,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "qwen/qwen2.5-vl-72b-instruct",
    name: "Qwen 2.5 VL 72B Instruct",
    provider: "Qwen",
    context_length: 32768,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "qwen/qwen3-vl-30b-a3b-instruct",
    name: "Qwen 3 VL 30B A3B",
    provider: "Qwen",
    context_length: 262144,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "qwen/qwen3-vl-8b-instruct",
    name: "Qwen 3 VL 8B",
    provider: "Qwen",
    context_length: 131072,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "meta-llama/llama-4-maverick",
    name: "Meta Llama 4 Maverick",
    provider: "Meta",
    context_length: 1048576,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "meta-llama/llama-4-scout",
    name: "Meta Llama 4 Scout",
    provider: "Meta",
    context_length: 327680,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "mistralai/mistral-large-2512",
    name: "Mistral Large 3",
    provider: "Mistral",
    context_length: 262144,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "mistralai/mistral-medium-3-5",
    name: "Mistral Medium 3.5",
    provider: "Mistral",
    context_length: 131072,
    input_modalities: ["text", "image"],
    supports_vision: true,
    supports_audio: false,
  },
  {
    id: "mistralai/voxtral-small-24b-2507",
    name: "Mistral Voxtral Small 24B",
    provider: "Mistral",
    context_length: 32768,
    input_modalities: ["text", "audio"],
    supports_vision: false,
    supports_audio: true,
  },
  {
    id: "deepseek/deepseek-v4.1-flash",
    name: "DeepSeek V4.1 Flash",
    provider: "DeepSeek",
    context_length: 163840,
    input_modalities: ["text"],
    supports_vision: false,
    supports_audio: false,
  },
  {
    id: "deepseek/deepseek-chat-v3-0324",
    name: "DeepSeek Chat V3",
    provider: "DeepSeek",
    context_length: 163840,
    input_modalities: ["text"],
    supports_vision: false,
    supports_audio: false,
  },
];

const PROVIDER_ORDER = [
  "Google Gemini",
  "Anthropic Claude",
  "OpenAI",
  "xAI",
  "Qwen",
  "Meta",
  "Mistral",
  "DeepSeek",
];

function detectPreset(baseUrl: string, model: string): ProviderPresetId {
  const lower = (baseUrl || "").toLowerCase();
  if (lower.includes("generativelanguage.googleapis.com")) return "google";
  if (lower.includes("api.openai.com")) return "openai";
  if (lower.includes("openrouter.ai")) {
    return model.startsWith("anthropic/") ? "anthropic" : "openrouter";
  }
  return "custom";
}

function formatContext(ctx?: number | null): string | null {
  if (!ctx || ctx <= 0) return null;
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 === 0 ? 0 : 1)}M`;
  if (ctx >= 1_000) return `${Math.round(ctx / 1_000)}k`;
  return String(ctx);
}

function formatUsdPer1M(perToken?: string | null): string | null {
  if (perToken == null || perToken === "") return null;
  const num = Number(perToken);
  if (!Number.isFinite(num) || num < 0) return null;
  const perM = num * 1_000_000;
  if (perM === 0) return "$0";
  if (perM < 0.01) return `$${perM.toFixed(4).replace(/0+$/, "").replace(/\.$/, "")}`;
  if (perM < 1) return `$${perM.toFixed(2)}`;
  return `$${perM.toFixed(2).replace(/\.00$/, "")}`;
}

function formatModelCost(
  prompt?: string | null,
  completion?: string | null
): { label: string; isFree: boolean } | null {
  const p = formatUsdPer1M(prompt);
  const c = formatUsdPer1M(completion);
  if (!p && !c) return null;
  if (p === "$0" && (c === "$0" || !c)) {
    return { label: "Free", isFree: true };
  }
  if (p && c) {
    return { label: `${p} / ${c} per 1M`, isFree: false };
  }
  return { label: `${p || c}/1M`, isFree: false };
}

interface ModelPickerProps {
  label: string;
  value: string;
  models: ModelInfo[];
  mode: "vision" | "audio";
  loading?: boolean;
  isLive?: boolean;
  onChange: (id: string) => void;
  onRefresh?: () => void;
}

const ModelPicker: React.FC<ModelPickerProps> = ({
  label,
  value,
  models,
  mode,
  loading = false,
  isLive = false,
  onChange,
  onRefresh,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [capabilityOnly, setCapabilityOnly] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [open]);

  const selectedModel = useMemo(
    () => models.find((m) => m.id === value),
    [models, value]
  );

  const filteredModels = useMemo(() => {
    const q = query.trim().toLowerCase();
    return models.filter((m) => {
      if (capabilityOnly) {
        const capable = mode === "vision" ? m.supports_vision : m.supports_audio;
        if (!capable) return false;
      }
      if (!q) return true;
      return (
        m.id.toLowerCase().includes(q) ||
        m.name.toLowerCase().includes(q) ||
        m.provider.toLowerCase().includes(q)
      );
    });
  }, [models, query, capabilityOnly, mode]);

  const groupedModels = useMemo(() => {
    const groups = new Map<string, ModelInfo[]>();
    for (const m of filteredModels) {
      const list = groups.get(m.provider) || [];
      list.push(m);
      groups.set(m.provider, list);
    }
    const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
      const ia = PROVIDER_ORDER.indexOf(a);
      const ib = PROVIDER_ORDER.indexOf(b);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    });
    return sortedKeys.map((provider) => ({
      provider,
      items: groups.get(provider) || [],
    }));
  }, [filteredModels]);

  const trimmedQuery = query.trim();
  const hasExactMatch = models.some(
    (m) => m.id.toLowerCase() === trimmedQuery.toLowerCase()
  );

  return (
    <div ref={containerRef} className="space-y-1.5 relative">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0]">
          {label}
        </label>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-slate-500 dark:text-[#938F99]">
            {isLive ? `${models.length} live` : "Offline catalog"}
          </span>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              title="Refresh models from provider"
              className="p-1 rounded-full text-slate-400 hover:text-[#6750A4] dark:hover:text-[#D0BCFF] hover:bg-black/5 dark:hover:bg-white/5 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            </button>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 hover:border-[#D0BCFF]/50 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">
            {selectedModel ? selectedModel.name : value || "Select a model"}
          </div>
          <div className="text-[10px] font-mono text-slate-500 dark:text-[#938F99] truncate flex items-center gap-1.5">
            <span className="truncate">
              {selectedModel ? `${selectedModel.provider} • ${selectedModel.id}` : value}
            </span>
            {selectedModel &&
              (() => {
                const cost = formatModelCost(
                  selectedModel.pricing_prompt,
                  selectedModel.pricing_completion
                );
                return cost ? (
                  <span
                    className={`shrink-0 px-1.5 py-0.2 rounded font-sans font-semibold ${
                      cost.isFree
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                        : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                    }`}
                  >
                    {cost.label}
                  </span>
                ) : null;
              })()}
          </div>
        </div>
        <ChevronDown
          className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-40 rounded-2xl bg-white dark:bg-[#1A1822] border border-black/10 dark:border-[#49454F]/60 shadow-2xl p-2.5 space-y-2">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search models or paste custom ID..."
                autoFocus
                className="w-full pl-8 pr-3 py-1.5 rounded-xl text-xs bg-slate-100 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF]"
              />
            </div>
            <button
              type="button"
              onClick={() => setCapabilityOnly((c) => !c)}
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-[11px] font-semibold border transition-all shrink-0 ${
                capabilityOnly
                  ? "bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] border-transparent"
                  : "bg-slate-100 dark:bg-[#141218] text-slate-600 dark:text-[#CAC4D0] border-black/5 dark:border-white/10"
              }`}
            >
              {mode === "vision" ? (
                <Eye className="w-3 h-3" />
              ) : (
                <Volume2 className="w-3 h-3" />
              )}
              <span>{mode === "vision" ? "Vision" : "Audio"}</span>
            </button>
          </div>

          <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
            {trimmedQuery && !hasExactMatch && (
              <button
                type="button"
                onClick={() => {
                  onChange(trimmedQuery);
                  setOpen(false);
                  setQuery("");
                }}
                className="w-full text-left px-3 py-2 rounded-xl text-xs bg-[#D0BCFF]/15 hover:bg-[#D0BCFF]/25 text-[#6750A4] dark:text-[#D0BCFF] font-semibold"
              >
                Use custom model ID: <span className="font-mono">{trimmedQuery}</span>
              </button>
            )}

            {groupedModels.length === 0 ? (
              <div className="py-5 text-center text-xs text-slate-500 dark:text-[#938F99]">
                No matching {capabilityOnly ? `${mode}-capable ` : ""}models found.
              </div>
            ) : (
              groupedModels.map((group) => (
                <div key={group.provider} className="space-y-1">
                  <div className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-[#938F99] sticky top-0 bg-white/95 dark:bg-[#1A1822]/95 backdrop-blur-sm">
                    {group.provider} ({group.items.length})
                  </div>
                  {group.items.map((m) => {
                    const isSelected = m.id === value;
                    const ctx = formatContext(m.context_length);
                    const cost = formatModelCost(m.pricing_prompt, m.pricing_completion);
                    return (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => {
                          onChange(m.id);
                          setOpen(false);
                          setQuery("");
                        }}
                        className={`w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl text-left transition-colors ${
                          isSelected
                            ? "bg-[#6750A4]/15 dark:bg-[#D0BCFF]/15 text-[#6750A4] dark:text-[#D0BCFF]"
                            : "hover:bg-slate-100 dark:hover:bg-[#2B2833] text-slate-800 dark:text-[#E6E0E9]"
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold truncate">{m.name}</div>
                          <div className="text-[10px] font-mono text-slate-500 dark:text-[#938F99] truncate">
                            {m.id}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {cost && (
                            <span
                              title="Input / Output USD per 1M tokens"
                              className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-semibold ${
                                cost.isFree
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                                  : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                              }`}
                            >
                              {cost.label}
                            </span>
                          )}
                          {ctx && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/5 text-slate-500 dark:text-[#CAC4D0]">
                              {ctx}
                            </span>
                          )}
                          {m.supports_vision && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-600 dark:text-violet-300 font-semibold">
                              Vis
                            </span>
                          )}
                          {m.supports_audio && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 font-semibold">
                              Aud
                            </span>
                          )}
                          {isSelected && <Check className="w-3.5 h-3.5 shrink-0" />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export const SettingsView: React.FC<SettingsViewProps> = ({
  settings,
  downloadProgress,
  updateStatus,
  learnedCommands,
  mcpConfig,
  onSaveSettings,
  onDownloadModel,
  onCancelDownload,
  onCheckUpdate,
  onInstallUpdate,
  onApproveLearned,
  onToggleLearned,
  onDeleteLearned,
  onRefreshMcp,
}) => {
  const initialBase =
    settings.vision_api_base || settings.base_url || "https://openrouter.ai/api/v1";
  const initialModel = settings.vision_model || "google/gemini-2.5-flash";
  const initialKey = settings.vision_api_key || settings.openrouter_api_key || "";

  const [apiKey, setApiKey] = useState(initialKey);
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState(initialBase);
  const [presetId, setPresetId] = useState<ProviderPresetId>(() =>
    detectPreset(initialBase, initialModel)
  );
  const [visionModel, setVisionModel] = useState(initialModel);
  const [sttCloudModel, setSttCloudModel] = useState(
    settings.stt_cloud_model || "google/gemini-2.5-flash"
  );
  const [maxSteps, setMaxSteps] = useState(settings.max_vision_steps || 8);
  const [sttEngine, setSttEngine] = useState<"parakeet" | "cloud">(
    settings.stt_engine || "parakeet"
  );
  const [alwaysOnTop, setAlwaysOnTop] = useState(Boolean(settings.always_on_top));
  const [useJev, setUseJev] = useState(settings.use_jev ?? true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [liveModels, setLiveModels] = useState<ModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [testingConn, setTestingConn] = useState(false);
  const [connResult, setConnResult] = useState<ConnectionTestResult | null>(null);

  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editingKeyRef = useRef(false);
  const latestValuesRef = useRef({
    apiKey: initialKey,
    baseUrl: initialBase,
    visionModel: initialModel,
    sttCloudModel: settings.stt_cloud_model || "google/gemini-2.5-flash",
    maxSteps: settings.max_vision_steps || 8,
    sttEngine: (settings.stt_engine || "parakeet") as "parakeet" | "cloud",
    alwaysOnTop: Boolean(settings.always_on_top),
    useJev: settings.use_jev ?? true,
  });

  latestValuesRef.current = {
    apiKey,
    baseUrl,
    visionModel,
    sttCloudModel,
    maxSteps,
    sttEngine,
    alwaysOnTop,
    useJev,
  };

  const availableModels = liveModels.length > 0 ? liveModels : FALLBACK_MODELS;

  const fetchLiveModels = useCallback(
    async (targetBase: string, targetKey?: string) => {
      setLoadingModels(true);
      try {
        const res = await listModels(targetBase, targetKey || undefined);
        if (Array.isArray(res.models) && res.models.length > 0) {
          setLiveModels(res.models);
        } else {
          setLiveModels([]);
        }
      } catch {
        setLiveModels([]);
      } finally {
        setLoadingModels(false);
      }
    },
    []
  );

  useEffect(() => {
    const nextBase =
      settings.vision_api_base || settings.base_url || "https://openrouter.ai/api/v1";
    const nextModel = settings.vision_model || "google/gemini-2.5-flash";
    const incomingKey = settings.vision_api_key || settings.openrouter_api_key || "";
    if (!editingKeyRef.current && incomingKey) {
      setApiKey(incomingKey);
    }
    setBaseUrl(nextBase);
    setVisionModel(nextModel);
    setPresetId(detectPreset(nextBase, nextModel));
    setSttCloudModel(settings.stt_cloud_model || "google/gemini-2.5-flash");
    setMaxSteps(settings.max_vision_steps || 8);
    setSttEngine(settings.stt_engine || "parakeet");
    setAlwaysOnTop(Boolean(settings.always_on_top));
    setUseJev(settings.use_jev ?? true);
  }, [settings]);

  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (settings.has_api_key) {
      void fetchLiveModels(
        settings.vision_api_base || settings.base_url || "https://openrouter.ai/api/v1",
        settings.vision_api_key || settings.openrouter_api_key || undefined
      );
    }
  }, [
    settings.has_api_key,
    settings.vision_api_base,
    settings.base_url,
    settings.vision_api_key,
    settings.openrouter_api_key,
    fetchLiveModels,
  ]);

  const persistSettings = useCallback(
    async (overrides: Partial<AppSettings> = {}, refreshModels = false) => {
      const cur = latestValuesRef.current;
      const cleanBase =
        (overrides.vision_api_base ?? cur.baseUrl).trim() ||
        "https://openrouter.ai/api/v1";
      const nextKey = (
        overrides.vision_api_key ??
        overrides.openrouter_api_key ??
        cur.apiKey
      ).trim();

      const payload: Partial<AppSettings> = {
        vision_api_base: cleanBase,
        vision_model: overrides.vision_model ?? cur.visionModel,
        stt_cloud_model: overrides.stt_cloud_model ?? cur.sttCloudModel,
        max_vision_steps: overrides.max_vision_steps ?? cur.maxSteps,
        stt_engine: overrides.stt_engine ?? cur.sttEngine,
        always_on_top: overrides.always_on_top ?? cur.alwaysOnTop,
        use_jev: overrides.use_jev ?? cur.useJev,
      };
      if (nextKey) {
        payload.vision_api_key = nextKey;
        payload.openrouter_api_key = nextKey;
      }

      setSaving(true);
      try {
        await onSaveSettings(payload);
        if (refreshModels && nextKey) {
          void fetchLiveModels(cleanBase, nextKey);
        }
        setToast("Auto-saved");
        if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
        toastTimerRef.current = setTimeout(() => setToast(null), 1800);
      } finally {
        setSaving(false);
      }
    },
    [onSaveSettings, fetchLiveModels]
  );

  const scheduleAutoSave = useCallback(
    (overrides: Partial<AppSettings> = {}, refreshModels = false) => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
      autoSaveTimerRef.current = setTimeout(() => {
        autoSaveTimerRef.current = null;
        void persistSettings(overrides, refreshModels);
      }, 400);
    },
    [persistSettings]
  );

  const handleSelectPreset = (preset: ProviderPreset) => {
    setPresetId(preset.id);
    setConnResult(null);
    if (preset.id === "custom") {
      const nextCustom =
        !baseUrl ||
        baseUrl.includes("openrouter.ai") ||
        baseUrl.includes("googleapis.com") ||
        baseUrl.includes("api.openai.com")
          ? "http://localhost:11434/v1"
          : baseUrl;
      setBaseUrl(nextCustom);
      void persistSettings({ vision_api_base: nextCustom });
      return;
    }
    setBaseUrl(preset.baseUrl);
    const patch: Partial<AppSettings> = { vision_api_base: preset.baseUrl };
    if (preset.defaultModel) {
      setVisionModel(preset.defaultModel);
      patch.vision_model = preset.defaultModel;
    }
    void persistSettings(patch);
    if (apiKey.trim() || settings.has_api_key) {
      void fetchLiveModels(preset.baseUrl, apiKey.trim() || undefined);
    }
  };

  const handleTestConnection = async () => {
    setTestingConn(true);
    setConnResult(null);
    try {
      const res = await testConnection(
        baseUrl.trim() || "https://openrouter.ai/api/v1",
        apiKey.trim() || undefined,
        visionModel
      );
      setConnResult(res);
      if (res.ok) {
        void fetchLiveModels(
          baseUrl.trim() || "https://openrouter.ai/api/v1",
          apiKey.trim() || undefined
        );
      }
    } catch (err) {
      setConnResult({
        ok: false,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setTestingConn(false);
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
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5 max-w-5xl mx-auto w-full pb-8">
      {/* Auto-save Toast Feedback */}
      {(saving || toast) && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-500 text-slate-950 text-xs font-bold shadow-2xl shadow-emerald-500/30">
          {saving ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5" />
          )}
          <span>{saving ? "Auto-saving..." : toast}</span>
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

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testingConn}
              className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold bg-[#6750A4]/10 dark:bg-[#D0BCFF]/15 hover:bg-[#6750A4]/20 dark:hover:bg-[#D0BCFF]/25 text-[#6750A4] dark:text-[#D0BCFF] border border-[#6750A4]/20 dark:border-[#D0BCFF]/30 transition-all disabled:opacity-50"
            >
              {testingConn ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <PlugZap className="w-3 h-3" />
              )}
              <span>{testingConn ? "Testing..." : "Test connection"}</span>
            </button>

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
        </div>

        {/* Provider Presets */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0]">
            AI Provider Preset
          </label>
          <div className="flex flex-wrap gap-1.5">
            {PROVIDER_PRESETS.map((preset) => {
              const active = presetId === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSelectPreset(preset)}
                  title={preset.hint}
                  className={`px-3 py-1.5 rounded-full text-[11px] font-semibold border transition-all ${
                    active
                      ? "bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] border-transparent shadow-sm"
                      : "bg-slate-200/60 dark:bg-[#141218] text-slate-700 dark:text-[#CAC4D0] border-black/5 dark:border-white/10 hover:border-[#D0BCFF]/40"
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </div>

        {connResult && (
          <div
            className={`flex items-center gap-2 px-3.5 py-2 rounded-2xl text-xs border ${
              connResult.ok
                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30"
                : "bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30"
            }`}
          >
            {connResult.ok ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <XCircle className="w-4 h-4 shrink-0" />
            )}
            <span className="truncate">{connResult.message}</span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0] flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5" />
              API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onFocus={() => {
                  editingKeyRef.current = true;
                }}
                onChange={(e) => {
                  const val = e.target.value;
                  setApiKey(val);
                  if (val.trim()) {
                    scheduleAutoSave(
                      { vision_api_key: val.trim(), openrouter_api_key: val.trim() },
                      true
                    );
                  }
                }}
                onBlur={() => {
                  editingKeyRef.current = false;
                  const val = apiKey.trim();
                  if (val) {
                    void persistSettings(
                      { vision_api_key: val, openrouter_api_key: val },
                      true
                    );
                  }
                }}
                placeholder={
                  settings.has_api_key
                    ? settings.masked_key || "•••••••••••• (saved)"
                    : "sk-or-v1-... or provider key"
                }
                className="w-full pr-10 pl-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all"
              />
              <button
                type="button"
                title={showKey ? "Hide API key" : "Show API key"}
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
              onChange={(e) => {
                const nextBase = e.target.value;
                setBaseUrl(nextBase);
                setPresetId(detectPreset(nextBase, visionModel));
                scheduleAutoSave({ vision_api_base: nextBase });
              }}
              onBlur={() => {
                void persistSettings({ vision_api_base: baseUrl });
              }}
              className="w-full px-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all font-mono"
            />
          </div>

          <ModelPicker
            label="Multimodal Vision Model"
            value={visionModel}
            models={availableModels}
            mode="vision"
            loading={loadingModels}
            isLive={liveModels.length > 0}
            onChange={(id) => {
              setVisionModel(id);
              setPresetId(detectPreset(baseUrl, id));
              void persistSettings({ vision_model: id });
            }}
            onRefresh={() =>
              void fetchLiveModels(
                baseUrl.trim() || "https://openrouter.ai/api/v1",
                apiKey.trim() || undefined
              )
            }
          />

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
              onChange={(e) => {
                const val = Number(e.target.value);
                setMaxSteps(val);
                scheduleAutoSave({ max_vision_steps: val });
              }}
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
              onChange={(e) => {
                const mode = e.target.value as "parakeet" | "cloud";
                setSttEngine(mode);
                void persistSettings({ stt_engine: mode });
              }}
              className="w-full px-3.5 py-2.5 rounded-2xl text-xs bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-900 dark:text-[#E6E0E9] focus:outline-none focus:border-[#D0BCFF] focus:ring-2 focus:ring-[#D0BCFF]/30 transition-all cursor-pointer"
            >
              <option value="parakeet">
                ⚡ On-Device Parakeet INT8 + Cloud Fallback
              </option>
              <option value="cloud">
                ☁️ Cloud Multimodal Speech (High Accuracy)
              </option>
            </select>
          </div>

          <ModelPicker
            label="Cloud STT Model (Audio-Capable)"
            value={sttCloudModel}
            models={availableModels}
            mode="audio"
            loading={loadingModels}
            isLive={liveModels.length > 0}
            onChange={(id) => {
              setSttCloudModel(id);
              void persistSettings({ stt_cloud_model: id });
            }}
            onRefresh={() =>
              void fetchLiveModels(
                baseUrl.trim() || "https://openrouter.ai/api/v1",
                apiKey.trim() || undefined
              )
            }
          />
        </div>

        <div className="flex items-center gap-2 pt-1">
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
              Installed version: v{settings.app_version || "2.5.1"}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {updateStatus.status === "available" || updateStatus.status === "downloading" ? (
              <button
                type="button"
                onClick={onInstallUpdate}
                disabled={updateStatus.status === "downloading"}
                className="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] shadow-sm transition-all disabled:opacity-60"
              >
                {updateStatus.status === "downloading" ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                <span>
                  {updateStatus.status === "downloading"
                    ? "Downloading & Installing..."
                    : `Install Update (${updateStatus.version})`}
                </span>
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
              onChange={(e) => {
                const checked = e.target.checked;
                setAlwaysOnTop(checked);
                void persistSettings({ always_on_top: checked });
              }}
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
              onChange={(e) => {
                const checked = e.target.checked;
                setUseJev(checked);
                void persistSettings({ use_jev: checked });
              }}
              className="w-4 h-4 accent-[#6750A4] dark:accent-[#D0BCFF] rounded cursor-pointer ml-3"
            />
          </label>
        </div>

        {updateStatus.status === "error" && updateStatus.error && (
          <p className="text-xs text-rose-500">{updateStatus.error}</p>
        )}
      </section>

      {/* Card 4: Learned Workflows & MCP Server */}
      <McpCard
        config={mcpConfig}
        commands={learnedCommands}
        onApprove={onApproveLearned}
        onToggle={onToggleLearned}
        onDelete={onDeleteLearned}
        onRefresh={onRefreshMcp}
      />
    </div>
  );
};
