import React, { useState } from "react";
import {
  Bot,
  Check,
  CheckCircle2,
  Copy,
  RefreshCw,
  Sparkles,
  Terminal,
  Trash2,
  Zap,
} from "lucide-react";

export interface LearnedCommandStep {
  type: string;
  command?: string | null;
  target?: string | null;
  fallback_target?: string | null;
  args?: string[];
  keys?: string[];
  text?: string | null;
  wait_ms?: number | null;
}

export interface LearnedCommand {
  id: string;
  name: string;
  description: string;
  triggers: string[];
  steps: LearnedCommandStep[];
  source_event_ids: string[];
  created_at: string;
  uses: number;
  enabled: boolean;
  suggested?: boolean;
}

export interface McpCardProps {
  config: string;
  commands: LearnedCommand[];
  onApprove: (id: string) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

const DEFAULT_MCP_CONFIG = JSON.stringify(
  {
    mcpServers: {
      "computer-auto": {
        command: "python",
        args: ["-m", "src.mcp_server"],
        cwd: "D:\\Vibe-coding\\Computer-Auto",
      },
    },
  },
  null,
  2
);

function formatStepSummary(step: LearnedCommandStep): string {
  if (step.type === "hotkey" && step.keys && step.keys.length > 0) {
    return `hotkey: ${step.keys.join("+")}`;
  }
  if (step.type === "click_element") {
    return `click_element: "${step.target || step.command || ""}"`;
  }
  if (step.type === "wait") {
    return `wait: ${step.command || step.target || 500}ms`;
  }
  const detail = step.target || step.command || "";
  return detail ? `${step.type}: ${detail}` : step.type;
}

export const McpCard: React.FC<McpCardProps> = ({
  config,
  commands,
  onApprove,
  onToggle,
  onDelete,
  onRefresh,
}) => {
  const [copied, setCopied] = useState(false);

  const effectiveConfig = (config || "").trim() || DEFAULT_MCP_CONFIG;
  const safeCommands = Array.isArray(commands) ? commands : [];
  const activeCount = safeCommands.filter((c) => c.enabled).length;
  const suggestedCount = safeCommands.filter((c) => !c.enabled).length;

  const handleCopyConfig = async () => {
    try {
      await navigator.clipboard.writeText(effectiveConfig);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard fallback ignored in restricted contexts
    }
  };

  return (
    <section className="m3-card rounded-3xl bg-slate-100/90 dark:bg-[#1F1D26] border border-black/5 dark:border-white/[0.08] p-5 space-y-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-[#D0BCFF]/15 flex items-center justify-center">
            <Bot className="w-4 h-4 text-[#6750A4] dark:text-[#D0BCFF]" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-[#E6E0E9]">
              MCP Server — Connect an AI agent
            </h3>
            <p className="text-xs text-slate-500 dark:text-[#CAC4D0]">
              Let Claude Desktop, Cursor, or any MCP agent analyze execution history and turn slow Vision tasks into fast commands
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full text-[11px] font-bold bg-[#D0BCFF]/15 text-[#6750A4] dark:text-[#D0BCFF] border border-[#D0BCFF]/30">
            {activeCount} Active • {suggestedCount} Suggested
          </span>
          <button
            type="button"
            onClick={onRefresh}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-200/70 dark:bg-[#2B2833] hover:bg-slate-300 dark:hover:bg-[#36333F] text-slate-800 dark:text-[#E6E0E9] border border-black/5 dark:border-white/5 transition-all"
            title="Refresh learned commands & scan history for suggestions"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Copyable MCP Config Snippet */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0] flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5" />
            <span>Claude Desktop / Cursor / MCP Client Config</span>
          </label>
          <button
            type="button"
            onClick={handleCopyConfig}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold bg-[#6750A4]/15 dark:bg-[#D0BCFF]/15 hover:bg-[#6750A4] dark:hover:bg-[#D0BCFF] text-[#6750A4] dark:text-[#D0BCFF] hover:text-white dark:hover:text-[#381E72] border border-[#D0BCFF]/30 transition-all"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>Copied JSON</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy Config</span>
              </>
            )}
          </button>
        </div>
        <pre className="w-full p-3.5 rounded-2xl text-[11px] leading-relaxed font-mono bg-slate-200/70 dark:bg-[#141218] border border-black/5 dark:border-white/10 text-slate-800 dark:text-[#E6E0E9] overflow-x-auto select-all">
          {effectiveConfig}
        </pre>
      </div>

      {/* Learned & Suggested Commands List */}
      <div className="space-y-2.5 pt-1">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-700 dark:text-[#CAC4D0] flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Learned & Suggested Commands ({safeCommands.length})</span>
          </span>
        </div>

        {safeCommands.length === 0 ? (
          <div className="p-4 rounded-2xl bg-slate-200/50 dark:bg-[#141218] border border-black/5 dark:border-white/5 text-center space-y-1">
            <p className="text-xs font-semibold text-slate-700 dark:text-[#E6E0E9]">
              No learned or suggested commands yet
            </p>
            <p className="text-[11px] text-slate-500 dark:text-[#938F99]">
              Repeated Vision tasks are automatically suggested here, or connect an MCP agent above to synthesize custom commands from history.
            </p>
          </div>
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {safeCommands.map((cmd) => {
              const isSuggested = !cmd.enabled && cmd.suggested !== false;
              return (
                <div
                  key={cmd.id}
                  className="p-3.5 rounded-2xl bg-slate-200/60 dark:bg-[#141218] border border-black/5 dark:border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-[#D0BCFF]/30 transition-all"
                >
                  <div className="space-y-1.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-slate-900 dark:text-[#E6E0E9] font-mono">
                        {cmd.name}
                      </span>
                      {isSuggested ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-300 border border-amber-500/30">
                          <Sparkles className="w-3 h-3" />
                          Suggested
                        </span>
                      ) : cmd.enabled ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border border-emerald-500/30">
                          <CheckCircle2 className="w-3 h-3" />
                          Enabled
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-500/15 text-slate-500 dark:text-slate-400 border border-slate-500/30">
                          Disabled
                        </span>
                      )}
                      <span className="text-[10px] font-mono text-slate-500 dark:text-[#938F99]">
                        {cmd.uses ?? 0} uses
                      </span>
                    </div>

                    {cmd.description && (
                      <p className="text-[11px] text-slate-600 dark:text-[#CAC4D0]">
                        {cmd.description}
                      </p>
                    )}

                    {/* Triggers */}
                    {Array.isArray(cmd.triggers) && cmd.triggers.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {cmd.triggers.map((trig, idx) => (
                          <span
                            key={`${cmd.id}-trig-${idx}`}
                            className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#D0BCFF]/10 text-[#6750A4] dark:text-[#D0BCFF] border border-[#D0BCFF]/20"
                          >
                            &ldquo;{trig}&rdquo;
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Steps preview */}
                    {Array.isArray(cmd.steps) && cmd.steps.length > 0 && (
                      <div className="text-[10px] font-mono text-slate-500 dark:text-[#938F99] truncate">
                        Steps: {cmd.steps.map(formatStepSummary).join(" → ")}
                      </div>
                    )}
                  </div>

                  {/* Actions: Approve / Enable toggle / Delete */}
                  <div className="flex items-center gap-2 shrink-0">
                    {!cmd.enabled && (
                      <button
                        type="button"
                        onClick={() => onApprove(cmd.id)}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-bold bg-emerald-500/15 hover:bg-emerald-500 text-emerald-600 dark:text-emerald-300 hover:text-slate-950 border border-emerald-500/30 transition-all"
                        title="Approve and enable this command"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Approve</span>
                      </button>
                    )}

                    <label
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-semibold bg-slate-200/80 dark:bg-[#2B2833] text-slate-700 dark:text-[#E6E0E9] cursor-pointer select-none"
                      title="Toggle command enabled state"
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(cmd.enabled)}
                        onChange={(e) => onToggle(cmd.id, e.target.checked)}
                        className="w-3.5 h-3.5 accent-[#6750A4] dark:accent-[#D0BCFF] rounded cursor-pointer"
                      />
                      <span>{cmd.enabled ? "On" : "Off"}</span>
                    </label>

                    <button
                      type="button"
                      onClick={() => onDelete(cmd.id)}
                      className="p-1.5 rounded-full text-rose-500 hover:bg-rose-500/15 transition-all"
                      title="Delete command"
                      aria-label={`Delete ${cmd.name}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
};

export default McpCard;
