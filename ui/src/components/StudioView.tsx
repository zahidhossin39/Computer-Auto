import React, { useMemo, useState } from "react";
import {
  Activity,
  Check,
  Cpu,
  Eye,
  FileText,
  Globe,
  Layout,
  ListOrdered,
  Mic,
  MicOff,
  Minimize2,
  Radio,
  Search,
  Send,
  ShieldAlert,
  Square,
  Terminal,
  Trash2,
  Volume2,
  X,
  Zap,
} from "lucide-react";
import { RobotMascot3D } from "./RobotMascot3D";
import type { ActivityEntry, MascotState, QueueState } from "../types";

interface StudioViewProps {
  state: MascotState;
  statusText: string;
  statusDetail: string;
  audioLevel: number;
  continuous: boolean;
  theme: "dark" | "light";
  activities: ActivityEntry[];
  queue: QueueState;
  onToggleMic: () => void;
  onToggleContinuous: () => void;
  onPanic: () => void;
  onRunCommand: (text: string) => void;
  onConfirmGuardrail: (approved: boolean) => void;
  onRemoveQueued: (id: string) => void;
  onClearQueue: () => void;
}

const STATE_M3: Record<
  MascotState,
  { label: string; dot: string; container: string; text: string; subtitle: string }
> = {
  ready: {
    label: "Ready & Idle",
    dot: "bg-sky-400",
    container: "bg-sky-500/10 border-sky-500/25",
    text: "text-sky-400",
    subtitle: "Double-tap Left Ctrl or speak a desktop voice command",
  },
  listening: {
    label: "Listening...",
    dot: "bg-emerald-400 animate-ping",
    container: "bg-emerald-500/15 border-emerald-500/40",
    text: "text-emerald-400",
    subtitle: "Acoustics active — speak clearly into your microphone",
  },
  processing: {
    label: "Synthesizing",
    dot: "bg-purple-400 animate-pulse",
    container: "bg-purple-500/15 border-purple-500/40",
    text: "text-purple-400",
    subtitle: "Resolving intent through sub-millisecond neural router",
  },
  executing: {
    label: "Executing",
    dot: "bg-fuchsia-400 animate-pulse",
    container: "bg-fuchsia-500/15 border-fuchsia-500/40",
    text: "text-fuchsia-400",
    subtitle: "Desktop action successfully dispatched to Windows OS",
  },
  guardrail: {
    label: "Safety Confirmation",
    dot: "bg-amber-400 animate-bounce",
    container: "bg-amber-500/15 border-amber-500/40",
    text: "text-amber-400",
    subtitle: "Voice or click authorization required to proceed",
  },
  error: {
    label: "Attention Needed",
    dot: "bg-rose-400",
    container: "bg-rose-500/15 border-rose-500/30",
    text: "text-rose-400",
    subtitle: "Could not execute task — check command phrasing",
  },
};

const SUGGESTED_CHIPS = [
  { icon: FileText, text: "Open Notepad" },
  { icon: Globe, text: "New Browser Tab" },
  { icon: Search, text: "In search bar, type my website" },
  { icon: Volume2, text: "Volume Up" },
  { icon: Layout, text: "Snap Window Left" },
  { icon: Minimize2, text: "Minimize Window" },
];

const EQUALIZER_WEIGHTS = [
  0.25, 0.38, 0.52, 0.68, 0.62, 0.82, 0.95, 0.78, 0.88, 1.0, 0.92, 0.98,
  0.98, 0.92, 1.0, 0.88, 0.78, 0.95, 0.82, 0.62, 0.68, 0.52, 0.38, 0.25,
  0.4, 0.6, 0.85, 0.7, 0.5, 0.3, 0.2, 0.15
];

export const StudioView: React.FC<StudioViewProps> = ({
  state,
  statusText,
  statusDetail,
  audioLevel,
  continuous,
  theme,
  activities,
  queue,
  onToggleMic,
  onToggleContinuous,
  onPanic,
  onRunCommand,
  onConfirmGuardrail,
  onRemoveQueued,
  onClearQueue,
}) => {
  const [commandInput, setCommandInput] = useState("");
  const m3State = STATE_M3[state] || STATE_M3.ready;
  const isListening = state === "listening";

  const spectrumBars = useMemo(() => {
    return EQUALIZER_WEIGHTS.map((w, idx) => {
      const base = isListening
        ? 0.18 + audioLevel * w * 0.82
        : state === "processing" || state === "executing"
        ? 0.25 + ((idx % 4) * 0.14)
        : 0.1;
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
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 max-w-5xl mx-auto w-full">
      {/* Hero Mascot Stage (M3 Elevated Container) */}
      <section className="relative rounded-3xl bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] p-5 overflow-hidden shadow-xl shadow-purple-950/5">
        <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-bl from-[#D0BCFF]/10 via-[#4F378B]/5 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="grid grid-cols-1 md:grid-cols-12 gap-5 items-center relative z-10">
          {/* Nova 3D Mascot Canvas */}
          <div className="md:col-span-5 h-56 sm:h-60 relative flex items-center justify-center rounded-2xl bg-gradient-to-b from-white/40 dark:from-white/[0.02] to-transparent">
            <RobotMascot3D
              state={state}
              audioLevel={audioLevel}
              theme={theme}
              onClick={onToggleMic}
            />
          </div>

          {/* Assistant Info & Interactive Controls */}
          <div className="md:col-span-7 flex flex-col justify-between space-y-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${m3State.container} ${m3State.text}`}
                >
                  <span className={`w-2 h-2 rounded-full ${m3State.dot}`} />
                  {m3State.label}
                </span>

                {statusDetail && (
                  <span className="text-xs font-mono text-slate-500 dark:text-[#938F99]">
                    {statusDetail}
                  </span>
                )}
              </div>

              <h2 className="text-lg sm:text-xl font-bold text-slate-900 dark:text-[#E6E0E9] leading-snug line-clamp-2">
                {statusText || "Nova is ready. Press Left Ctrl twice or speak."}
              </h2>

              <p className="text-xs text-slate-500 dark:text-[#CAC4D0]">
                {m3State.subtitle}
              </p>
            </div>

            {/* M3 Audio Waveform Visualizer */}
            <div
              aria-label="Audio waveform"
              className="h-10 px-3.5 rounded-full bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/5 flex items-center justify-between gap-1 shadow-inner"
            >
              {spectrumBars.map((val, i) => (
                <div
                  key={i}
                  className={`flex-1 rounded-full transition-all duration-100 ${
                    isListening
                      ? "bg-gradient-to-t from-emerald-500 to-teal-300"
                      : state === "processing" || state === "executing"
                      ? "bg-gradient-to-t from-[#6750A4] to-[#D0BCFF]"
                      : state === "guardrail"
                      ? "bg-amber-400"
                      : "bg-[#D0BCFF]/30 dark:bg-[#D0BCFF]/25"
                  }`}
                  style={{ height: `${Math.round(val * 100)}%` }}
                />
              ))}
            </div>

            {/* Primary Action Button Dock */}
            <div className="flex flex-wrap items-center gap-2.5 pt-1">
              {/* Main M3 Pill Mic Button */}
              <button
                type="button"
                onClick={onToggleMic}
                className={`flex items-center gap-2 px-5 py-3 rounded-full text-sm font-bold transition-all duration-200 shadow-md ${
                  isListening
                    ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/30 ring-4 ring-emerald-500/20"
                    : "bg-[#6750A4] dark:bg-[#D0BCFF] hover:brightness-110 text-white dark:text-[#381E72] shadow-purple-500/25"
                }`}
              >
                {isListening ? (
                  <>
                    <MicOff className="w-4 h-4 animate-spin-slow" />
                    <span>Stop Recording</span>
                  </>
                ) : (
                  <>
                    <Mic className="w-4 h-4" />
                    <span>Speak (Double-Tap Ctrl)</span>
                  </>
                )}
              </button>

              {/* Continuous Listening Pill Toggle */}
              <button
                type="button"
                onClick={onToggleContinuous}
                className={`flex items-center gap-2 px-4 py-3 rounded-full text-xs font-semibold border transition-all duration-200 ${
                  continuous
                    ? "bg-[#D0BCFF]/20 text-[#D0BCFF] border-[#D0BCFF]/40 shadow-sm"
                    : "bg-slate-200/70 dark:bg-[#2B2833] text-slate-700 dark:text-[#CAC4D0] border-transparent hover:border-black/10 dark:hover:border-white/10"
                }`}
              >
                <Radio className={`w-3.5 h-3.5 ${continuous ? "animate-pulse text-[#D0BCFF]" : ""}`} />
                <span>Continuous {continuous ? "ON" : "OFF"}</span>
              </button>

              {/* Emergency Panic Key */}
              <button
                type="button"
                onClick={onPanic}
                title="Immediately abort active execution (Panic Key: Escape)"
                className="flex items-center gap-1.5 px-4 py-3 rounded-full text-xs font-semibold bg-rose-500/15 hover:bg-rose-500 text-rose-600 dark:text-rose-300 hover:text-white border border-rose-500/30 transition-all ml-auto"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Panic (Esc)</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Safety Guardrail Alert Modal/Banner */}
      {state === "guardrail" && (
        <section className="rounded-3xl p-5 bg-gradient-to-r from-amber-500/20 to-orange-500/15 border-2 border-amber-500/50 backdrop-blur-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-xl shadow-amber-500/10 animate-fade-in">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 rounded-2xl bg-amber-500/20 text-amber-500 shrink-0">
              <ShieldAlert className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-amber-800 dark:text-amber-200">
                Action Requires Approval
              </h3>
              <p className="text-xs text-slate-700 dark:text-slate-300 mt-1 max-w-xl">
                {statusText || "A system-level or destructive command was detected. Approve to proceed or cancel to abort."}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <button
              type="button"
              onClick={() => onConfirmGuardrail(true)}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-full text-xs font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 transition-all shadow-md shadow-amber-500/20"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Approve & Run</span>
            </button>
            <button
              type="button"
              onClick={() => onConfirmGuardrail(false)}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-full text-xs font-semibold bg-slate-200 dark:bg-[#2B2833] hover:bg-slate-300 dark:hover:bg-[#36333F] text-slate-800 dark:text-[#E6E0E9] transition-all"
            >
              <X className="w-3.5 h-3.5" />
              <span>Cancel</span>
            </button>
          </div>
        </section>
      )}

      {/* M3 Spotlight Command Input & Quick Assist Chips */}
      <section className="space-y-3">
        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-2.5 p-2 rounded-full bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] focus-within:border-[#D0BCFF] focus-within:ring-2 focus-within:ring-[#D0BCFF]/30 transition-all shadow-sm"
        >
          <div className="pl-3 text-slate-400 dark:text-[#938F99]">
            <Terminal className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={commandInput}
            onChange={(e) => setCommandInput(e.target.value)}
            placeholder='Type a command: "open notepad", "in search bar type cats", "volume up"...'
            className="flex-1 bg-transparent text-sm text-slate-900 dark:text-[#E6E0E9] placeholder:text-slate-400 dark:placeholder:text-[#938F99] focus:outline-none py-1"
          />
          <button
            type="submit"
            disabled={!commandInput.trim()}
            className="flex items-center gap-1.5 px-5 py-2.5 rounded-full text-xs font-bold bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] hover:brightness-110 disabled:opacity-40 disabled:pointer-events-none transition-all shadow-sm"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Execute</span>
          </button>
        </form>

        {/* Suggestion Chips */}
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          <span className="text-[11px] font-semibold text-slate-500 dark:text-[#938F99] mr-1 flex items-center gap-1">
            <Zap className="w-3 h-3 text-[#D0BCFF]" /> Suggested:
          </span>
          {SUGGESTED_CHIPS.map((chip) => {
            const Icon = chip.icon;
            return (
              <button
                key={chip.text}
                type="button"
                onClick={() => onRunCommand(chip.text)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-slate-200/60 dark:bg-[#2B2833] hover:bg-[#D0BCFF]/20 text-slate-700 dark:text-[#CAC4D0] hover:text-[#D0BCFF] border border-black/5 dark:border-white/5 transition-all"
              >
                <Icon className="w-3.5 h-3.5 text-[#6750A4] dark:text-[#D0BCFF]" />
                <span>{chip.text}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* Task Queue */}
      {(queue.running || queue.pending.length > 0) && (
        <section className="rounded-3xl bg-white dark:bg-[#1F1D26] border border-black/10 dark:border-[#49454F]/40 p-4 space-y-2.5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <ListOrdered className="w-4 h-4 text-[#6750A4] dark:text-[#D0BCFF]" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-[#CAC4D0]">
                Task Queue
              </h3>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-[#6750A4]/10 dark:bg-[#D0BCFF]/15 text-[#6750A4] dark:text-[#D0BCFF]">
                {queue.pending.length} pending
              </span>
            </div>
            {queue.pending.length > 0 && (
              <button
                type="button"
                onClick={onClearQueue}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 dark:text-rose-300 border border-rose-500/20 transition-all"
              >
                <Trash2 className="w-3 h-3" />
                Clear queue
              </button>
            )}
          </div>

          {queue.running && (
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-2xl bg-violet-500/10 border border-violet-500/25">
              <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse shrink-0" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-violet-500 dark:text-violet-300 shrink-0">
                Running
              </span>
              <span className="text-xs font-medium text-slate-800 dark:text-[#E6E0E9] truncate">
                {queue.running.text}
              </span>
            </div>
          )}

          {queue.pending.length > 0 && (
            <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
              {queue.pending.map((item, idx) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-2xl bg-slate-100/80 dark:bg-[#141218]/60 border border-black/5 dark:border-[#49454F]/30"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[11px] font-mono text-slate-400 dark:text-[#938F99] w-4 shrink-0">
                      #{idx + 1}
                    </span>
                    <span className="text-xs text-slate-700 dark:text-[#CAC4D0] truncate">
                      {item.text}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRemoveQueued(item.id)}
                    aria-label={`Remove queued task ${item.text}`}
                    className="p-1 rounded-full text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors shrink-0"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Live Activity & Vision Execution Feed */}
      <section className="space-y-3 pt-1">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#938F99] flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#D0BCFF]" />
            Live Execution Feed
          </h3>
          <span className="text-xs font-mono text-slate-400 dark:text-[#938F99] bg-black/5 dark:bg-white/5 px-2.5 py-0.5 rounded-full">
            {activities.length} events
          </span>
        </div>

        <div className="space-y-2.5 max-h-60 overflow-y-auto pr-1">
          {activities.length === 0 ? (
            <div className="rounded-2xl bg-slate-100/60 dark:bg-[#1A1820] border border-black/5 dark:border-white/5 p-6 text-center text-xs text-slate-500 dark:text-[#938F99]">
              No actions run yet. Double-tap Left Ctrl or speak a command to see live Tier-1 Router and Tier-2 Vision events.
            </div>
          ) : (
            activities.map((item) => (
              <div
                key={item.id}
                className="rounded-2xl bg-slate-100/90 dark:bg-[#201E27] border border-black/5 dark:border-white/[0.06] px-4 py-3 flex items-start justify-between gap-3 hover:bg-slate-200/50 dark:hover:bg-[#2A2733] transition-colors"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div
                    className={`mt-0.5 p-1.5 rounded-xl shrink-0 ${
                      item.kind === "vision"
                        ? "bg-purple-500/20 text-purple-400"
                        : item.kind === "action"
                        ? "bg-emerald-500/20 text-emerald-400"
                        : item.kind === "guardrail"
                        ? "bg-amber-500/20 text-amber-400"
                        : item.kind === "error"
                        ? "bg-rose-500/20 text-rose-400"
                        : "bg-sky-500/20 text-sky-400"
                    }`}
                  >
                    {item.kind === "vision" ? (
                      <Eye className="w-4 h-4" />
                    ) : (
                      <Cpu className="w-4 h-4" />
                    )}
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {item.tier && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-200 dark:bg-[#36333F] text-slate-700 dark:text-[#EADDFF]">
                          {item.tier}
                        </span>
                      )}
                      <span className="text-xs text-slate-900 dark:text-[#E6E0E9] font-medium break-words">
                        {item.line}
                      </span>
                    </div>
                  </div>
                </div>

                <span className="text-[10px] font-mono text-slate-400 dark:text-[#938F99] shrink-0 mt-0.5">
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
