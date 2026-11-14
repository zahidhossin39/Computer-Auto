import React from "react";
import {
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
  Zap,
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
  version = "2.5.1",
}) => {
  const statusLabel = aiReady
    ? "AI Cloud Ready"
    : offlineReady
    ? "Neural Local"
    : "Key Needed";

  const statusColor = aiReady
    ? "text-emerald-400 bg-emerald-500/15 border-emerald-500/30"
    : offlineReady
    ? "text-sky-400 bg-sky-500/15 border-sky-500/30"
    : "text-amber-400 bg-amber-500/15 border-amber-500/30";

  return (
    <header
      data-tauri-drag-region
      className="h-14 px-4 flex items-center justify-between border-b border-white/[0.08] dark:border-white/[0.06] bg-slate-50/90 dark:bg-[#141218]/90 backdrop-blur-2xl shrink-0 z-30 transition-colors"
    >
      {/* Left: Brand Identity & Version */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="relative group flex items-center justify-center">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#6750A4] to-[#D0BCFF] dark:from-[#4F378B] dark:to-[#D0BCFF] flex items-center justify-center shadow-lg shadow-purple-500/20 shrink-0 transition-transform group-hover:scale-105">
            <Sparkles className="w-4 h-4 text-white dark:text-[#381E72]" />
          </div>
          <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-[#141218] animate-pulse" />
        </div>

        <div className="flex items-center gap-2 min-w-0">
          <div className="flex flex-col">
            <span className="font-semibold text-sm tracking-tight text-slate-900 dark:text-[#E6E0E9] truncate">
              Computer-Auto
            </span>
            <span className="text-[10px] text-slate-500 dark:text-[#938F99] leading-tight">
              Nova Co-Pilot
            </span>
          </div>

          {!compact && (
            <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-full bg-[#EADDFF] dark:bg-[#4F378B] text-[#21005D] dark:text-[#EADDFF] tracking-wider ml-1">
              v{version.replace(/^v/, "")}
            </span>
          )}

          {!compact && (
            <div className={`hidden sm:flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${statusColor} ml-1`}>
              <Zap className="w-3 h-3" />
              <span>{statusLabel}</span>
            </div>
          )}
        </div>
      </div>

      {/* Center: M3 Segmented Tabs (Hidden in compact mode) */}
      {!compact && (
        <nav className="flex items-center gap-1 p-1 rounded-full bg-slate-200/60 dark:bg-[#201E27] border border-black/5 dark:border-white/5 shadow-inner">
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
                className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                  active
                    ? "bg-[#6750A4] dark:bg-[#D0BCFF] text-white dark:text-[#381E72] shadow-sm shadow-purple-500/25"
                    : "text-slate-600 dark:text-[#CAC4D0] hover:text-slate-900 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${active ? "animate-bounce-subtle" : ""}`} />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>
      )}

      {/* Right: Window Controls & Quick Toggles */}
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={onToggleCompact}
          title={compact ? "Expand Window" : "Compact Mode"}
          className={`p-2 rounded-full transition-colors ${
            compact
              ? "bg-[#D0BCFF]/20 text-[#D0BCFF]"
              : "text-slate-500 dark:text-[#CAC4D0] hover:bg-black/5 dark:hover:bg-white/10"
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
          title={alwaysOnTop ? "Unpin Window" : "Keep Window Always-On-Top"}
          className={`p-2 rounded-full transition-colors ${
            alwaysOnTop
              ? "bg-[#D0BCFF]/20 text-[#D0BCFF]"
              : "text-slate-500 dark:text-[#CAC4D0] hover:bg-black/5 dark:hover:bg-white/10"
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
          title={theme === "dark" ? "Light Mode" : "Dark Mode"}
          className="p-2 rounded-full text-slate-500 dark:text-[#CAC4D0] hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
        >
          {theme === "dark" ? (
            <Sun className="w-3.5 h-3.5 text-amber-300" />
          ) : (
            <Moon className="w-3.5 h-3.5 text-slate-700" />
          )}
        </button>

        <div className="w-px h-5 bg-black/10 dark:bg-white/10 mx-1" />

        <button
          type="button"
          onClick={onMinimize}
          title="Minimize Window"
          className="p-2 rounded-full text-slate-500 dark:text-[#CAC4D0] hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
        >
          <Minus className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={onClose}
          title="Close Window"
          className="p-2 rounded-full text-slate-500 dark:text-[#CAC4D0] hover:bg-rose-500 hover:text-white transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </header>
  );
};
