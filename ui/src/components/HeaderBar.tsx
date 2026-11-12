import React from "react";
import {
  Bot,
  Command,
  Maximize2,
  Minimize2,
  Minus,
  Moon,
  Pin,
  PinOff,
  Settings,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import type { NavTab } from "../types";

interface HeaderBarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  aiReady: boolean;
  offlineReady: boolean;
  compact: boolean;
  onToggleCompact: () => void;
  alwaysOnTop: boolean;
  onTogglePin: () => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onMinimize: () => void;
  onClose: () => void;
  version?: string;
}

export const HeaderBar: React.FC<HeaderBarProps> = ({
  activeTab,
  onTabChange,
  aiReady,
  offlineReady,
  compact,
  onToggleCompact,
  alwaysOnTop,
  onTogglePin,
  theme,
  onToggleTheme,
  onMinimize,
  onClose,
  version = "2.0",
}) => {
  const statusLabel = aiReady
    ? "AI Ready"
    : offlineReady
    ? "Offline Ready"
    : "Key Required";

  const statusDotClass = aiReady
    ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"
    : offlineReady
    ? "bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.8)]"
    : "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]";

  return (
    <header
      data-tauri-drag-region
      className="h-12 px-3.5 flex items-center justify-between border-b border-slate-200/80 dark:border-slate-800/80 bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl shrink-0 z-20"
    >
      {/* Left: Brand & Status */}
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-sky-500 to-violet-600 flex items-center justify-center shadow-md shadow-sky-500/20 shrink-0">
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-sm tracking-tight text-slate-900 dark:text-slate-100 truncate">
            Computer-Auto
          </span>
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-semibold rounded-md bg-sky-500/15 text-sky-600 dark:text-sky-300 border border-sky-500/25">
            v{version.replace(/^v/, "").slice(0, 3)}
          </span>
          {!compact && (
            <div className="hidden sm:flex items-center gap-1.5 pl-2 ml-1 border-l border-slate-200 dark:border-slate-800">
              <span className={`w-2 h-2 rounded-full ${statusDotClass}`} />
              <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
                {statusLabel}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Center: Navigation Pills (Hidden in compact mode) */}
      {!compact && (
        <nav className="flex items-center gap-1 p-1 rounded-xl bg-slate-100/80 dark:bg-slate-900/90 border border-slate-200/70 dark:border-slate-800/80">
          {(
            [
              { id: "studio", label: "Studio", icon: Sparkles },
              { id: "commands", label: "Commands", icon: Command },
              { id: "settings", label: "Settings", icon: Settings },
            ] as const
          ).map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onTabChange(id)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  active
                    ? "bg-white dark:bg-slate-800 text-sky-600 dark:text-sky-300 shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>
      )}

      {/* Right: Window Controls */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onToggleCompact}
          title={compact ? "Expand to Studio View" : "Compact Mini-Mode"}
          className={`p-1.5 rounded-lg transition-colors ${
            compact
              ? "bg-sky-500/15 text-sky-500 dark:text-sky-300"
              : "text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800/80"
          }`}
        >
          {compact ? (
            <Maximize2 className="w-3.5 h-3.5" />
          ) : (
            <Minimize2 className="w-3.5 h-3.5" />
          )}
        </button>

        <button
          type="button"
          onClick={onTogglePin}
          title={alwaysOnTop ? "Unpin Always-on-Top" : "Pin Always-on-Top"}
          className={`p-1.5 rounded-lg transition-colors ${
            alwaysOnTop
              ? "bg-violet-500/15 text-violet-600 dark:text-violet-300"
              : "text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800/80"
          }`}
        >
          {alwaysOnTop ? (
            <Pin className="w-3.5 h-3.5" />
          ) : (
            <PinOff className="w-3.5 h-3.5" />
          )}
        </button>

        <button
          type="button"
          onClick={onToggleTheme}
          title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
          className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800/80 transition-colors"
        >
          {theme === "dark" ? (
            <Sun className="w-3.5 h-3.5" />
          ) : (
            <Moon className="w-3.5 h-3.5" />
          )}
        </button>

        <div className="w-px h-4 bg-slate-200 dark:bg-slate-800 mx-0.5" />

        <button
          type="button"
          onClick={onMinimize}
          title="Minimize"
          className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800/80 transition-colors"
        >
          <Minus className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={onClose}
          title="Close"
          className="p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-rose-500 hover:text-white transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </header>
  );
};
