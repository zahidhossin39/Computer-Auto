import React, { useMemo, useState } from "react";
import {
  Activity,
  Check,
  Cpu,
  Eye,
  Mic,
  MicOff,
  Radio,
  Send,
  ShieldAlert,
  Square,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import { RobotMascot3D } from "./RobotMascot3D";
import type { ActivityEntry, MascotState } from "../types";

interface StudioViewProps {
  state: MascotState;
  statusText: string;
  statusDetail: string;
  audioLevel: number;
  continuous: boolean;
  theme: "dark" | "light";
  activities: ActivityEntry[];
  onToggleMic: () => void;
  onToggleContinuous: () => void;
  onPanic: () => void;
  onRunCommand: (text: string) => void;
  onConfirmGuardrail: (approved: boolean) => void;
}

const STATE_BADGE: Record<
  MascotState,
  { label: string; dot: string; pill: string }
> = {
  ready: {
    label: "Ready",
    dot: "bg-sky-400",
    pill: "bg-sky-500/15 text-sky-600 dark:text-sky-300 border-sky-500/30",
  },
  listening: {
    label: "Listening",
    dot: "bg-emerald-400 animate-ping",
    pill: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30",
  },
  processing: {
    label: "Thinking",
    dot: "bg-violet-400 animate-pulse",
    pill: "bg-violet-500/15 text-violet-600 dark:text-violet-300 border-violet-500/30",
  },
  executing: {
    label: "Executing",
    dot: "bg-fuchsia-400 animate-pulse",
    pill: "bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-300 border-fuchsia-500/30",
  },
  guardrail: {
    label: "Guardrail",
    dot: "bg-amber-400 animate-pulse",
    pill: "bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30",
  },
  error: {
    label: "Error",
    dot: "bg-rose-400",
    pill: "bg-rose-500/15 text-rose-600 dark:text-rose-300 border-rose-500/30",
  },
};

const QUICK_CHIPS = [
  "Open Notepad",
  "New Browser Tab",
  "Volume Up",
  "Mute Audio",
  "Snap Window Left",
  "Take Screenshot",
];

const BAR_WEIGHTS = [
  0.28, 0.42, 0.56, 0.72, 0.64, 0.85, 0.94, 0.78, 0.9, 1.0, 0.88, 0.96, 0.96,
  0.88, 1.0, 0.9, 0.78, 0.94, 0.85, 0.64, 0.72, 0.56, 0.42, 0.28,
];

export const StudioView: React.FC<StudioViewProps> = ({
  state,
  statusText,
  statusDetail,
  audioLevel,
  continuous,
  theme,
  activities,
  onToggleMic,
  onToggleContinuous,
  onPanic,
  onRunCommand,
  onConfirmGuardrail,
}) => {
  const [commandInput, setCommandInput] = useState("");
  const badge = STATE_BADGE[state] || STATE_BADGE.ready;
  const isListening = state === "listening";

  const spectrumBars = useMemo(() => {
    return BAR_WEIGHTS.map((w, idx) => {
      const base = isListening ? 0.16 + audioLevel * w * 0.84 : state === "processing" || state === "executing" ? 0.22 + ((idx % 3) * 0.12) : 0.1;
      return Math.min(1, Math.max(0.08, base));
    });
  }, [audioLevel, isListening, state]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = commandInput.trim();
    if (!trimmed) return;
    onRunCommand(trimmed);
    setCommandInput("");
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
      {/* Hero Mascot Stage */}
      <section className="relative rounded-2xl glass-panel p-4 overflow-hidden">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
          {/* 3D Mascot */}
          <div className="md:col-span-5 h-52 sm:h-56 relative flex items-center justify-center">
            <div className="absolute inset-0 bg-gradient-to-b from-sky-500/5 via-transparent to-violet-500/5 rounded-xl pointer-events-none" />
            <RobotMascot3D
              state={state}
              audioLevel={audioLevel}
              theme={theme}
              onClick={onToggleMic}
            />
          </div>

          {/* Status, Spectrum & Primary Controls */}
          <div className="md:col-span-7 flex flex-col justify-between space-y-3.5">
            <div className="space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badge.pill}`}
                >
                  <span className={`w-2 h-2 rounded-full ${badge.dot}`} />
                  {badge.label}
                </span>
                {statusDetail && (
                  <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                    {statusDetail}
                  </span>
                )}
              </div>

              <h2 className="text-base sm:text-lg font-semibold text-slate-900 dark:text-slate-100 leading-snug line-clamp-2">
                {statusText || "Nova is ready for your command."}
              </h2>
            </div>

            {/* 24-Bar Audio Spectrum Visualizer */}
            <div
              aria-label="Audio spectrum"
              className="h-9 px-3 rounded-xl bg-slate-100/80 dark:bg-slate-950/60 border border-slate-200/70 dark:border-slate-800/80 flex items-center justify-between gap-1"
            >
              {spectrumBars.map((val, i) => (
                <div
                  key={i}
                  className={`flex-1 rounded-full transition-all duration-75 ${
                    isListening
                      ? "bg-gradient-to-t from-emerald-500 to-teal-300"
                      : state === "processing" || state === "executing"
                      ? "bg-gradient-to-t from-violet-500 to-fuchsia-400"
                      : state === "guardrail"
                      ? "bg-amber-400/70"
                      : "bg-sky-400/40 dark:bg-sky-500/35"
                  }`}
                  style={{ height: `${Math.round(val * 100)}%` }}
                />
              ))}
            </div>

            {/* Primary Control Dock */}
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={onToggleMic}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-lg ${
                  isListening
                    ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/30 ring-2 ring-emerald-400/50"
                    : "bg-gradient-to-r from-sky-500 to-violet-600 hover:from-sky-400 hover:to-violet-500 text-white shadow-sky-500/25"
                }`}
              >
                {isListening ? (
                  <>
                    <MicOff className="w-4 h-4" />
                    <span>Stop Listening</span>
                  </>
                ) : (
                  <>
                    <Mic className="w-4 h-4" />
                    <span>Hold Left Ctrl or Click</span>
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={onToggleContinuous}
                className={`flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-semibold border transition-all ${
                  continuous
                    ? "bg-teal-500/15 text-teal-600 dark:text-teal-300 border-teal-500/40"
                    : "bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-200/70 dark:hover:bg-slate-800"
                }`}
              >
                <Radio className="w-3.5 h-3.5" />
                <span>Continuous</span>
              </button>

              <button
                type="button"
                onClick={onPanic}
                className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-semibold bg-rose-500/15 hover:bg-rose-500 text-rose-600 dark:text-rose-300 hover:text-white border border-rose-500/30 transition-all ml-auto"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Panic Stop (Esc)</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Inline Guardrail Confirmation Card */}
      {state === "guardrail" && (
        <section className="rounded-2xl p-4 bg-amber-500/10 border-2 border-amber-500/40 backdrop-blur-md flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg shadow-amber-500/10">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-amber-500/20 text-amber-500 shrink-0">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-300">
                Safety Guardrail Confirmation
              </h3>
              <p className="text-xs text-slate-700 dark:text-slate-300 mt-0.5">
                {statusText || "A potentially destructive action requires your approval."}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => onConfirmGuardrail(true)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 transition-colors"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Approve & Execute</span>
            </button>
            <button
              type="button"
              onClick={() => onConfirmGuardrail(false)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              <span>Cancel</span>
            </button>
          </div>
        </section>
      )}

      {/* Spotlight Command Input Bar + Quick Action Chips */}
      <section className="space-y-2.5">
        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-2 p-1.5 rounded-2xl glass-panel focus-within:ring-2 focus-within:ring-sky-500/40 transition-all"
        >
          <div className="pl-3 text-slate-400">
            <Terminal className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={commandInput}
            onChange={(e) => setCommandInput(e.target.value)}
            placeholder='Try "open calculator", "search youtube for lofi hip hop", or "click the sign in button"...'
            className="flex-1 bg-transparent text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none py-2"
          />
          <button
            type="submit"
            disabled={!commandInput.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-sky-500 hover:bg-sky-400 disabled:opacity-40 disabled:pointer-events-none text-white transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Run</span>
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mr-1 flex items-center gap-1">
            <Zap className="w-3 h-3 text-sky-400" /> Quick:
          </span>
          {QUICK_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => onRunCommand(chip)}
              className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-slate-100 dark:bg-slate-900/70 hover:bg-sky-500/15 text-slate-700 dark:text-slate-300 hover:text-sky-600 dark:hover:text-sky-300 border border-slate-200/80 dark:border-slate-800 transition-colors"
            >
              {chip}
            </button>
          ))}
        </div>
      </section>

      {/* Live Activity & Vision Feed */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" />
            Live Activity & Vision Feed
          </h3>
          <span className="text-[11px] font-mono text-slate-400">
            {activities.length} events
          </span>
        </div>

        <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
          {activities.length === 0 ? (
            <div className="rounded-xl glass-card p-4 text-center text-xs text-slate-500 dark:text-slate-400">
              No commands executed yet. Speak or type a command above to see live Tier-1 Router & Tier-2 Vision logs.
            </div>
          ) : (
            activities.map((item) => (
              <div
                key={item.id}
                className="rounded-xl glass-card px-3.5 py-2.5 flex items-start justify-between gap-3"
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <div
                    className={`mt-0.5 p-1 rounded-md shrink-0 ${
                      item.kind === "vision"
                        ? "bg-violet-500/15 text-violet-500 dark:text-violet-300"
                        : item.kind === "action"
                        ? "bg-emerald-500/15 text-emerald-500 dark:text-emerald-300"
                        : item.kind === "guardrail"
                        ? "bg-amber-500/15 text-amber-500"
                        : item.kind === "error"
                        ? "bg-rose-500/15 text-rose-500"
                        : "bg-sky-500/15 text-sky-500"
                    }`}
                  >
                    {item.kind === "vision" ? (
                      <Eye className="w-3.5 h-3.5" />
                    ) : (
                      <Cpu className="w-3.5 h-3.5" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {item.tier && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-200/70 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                          {item.tier}
                        </span>
                      )}
                      <span className="text-xs text-slate-800 dark:text-slate-200 break-words">
                        {item.line}
                      </span>
                    </div>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-slate-400 shrink-0">
                  {item.timestamp}
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
};
