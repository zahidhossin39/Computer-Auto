export type MascotState =
  | "ready"
  | "listening"
  | "processing"
  | "executing"
  | "guardrail"
  | "error";

export type NavTab = "studio" | "commands" | "settings";

export type LogKind = "info" | "action" | "vision" | "error" | "guardrail";

export interface ActivityEntry {
  id: string;
  timestamp: string;
  line: string;
  kind: LogKind;
  tier?: "Tier-1 Router" | "Tier-2 Vision" | "Guardrail" | "System";
}

export interface IntentCommand {
  name: string;
  description?: string;
  phrases: string[];
  category: string;
  destructive?: boolean;
}

export interface AppSettings {
  openrouter_api_key?: string;
  base_url?: string;
  vision_model: string;
  stt_engine?: "parakeet" | "cloud";
  stt_cloud_model: string;
  theme: "dark" | "light";
  max_vision_steps: number;
  use_jev: boolean;
  always_on_top?: boolean;
  has_api_key: boolean;
  masked_key?: string;
  has_local_model: boolean;
  app_version?: string;
}

export interface DownloadProgress {
  active: boolean;
  done: number;
  total: number;
  stage: string;
}

export interface UpdateStatus {
  status: "idle" | "checking" | "available" | "up_to_date" | "downloading" | "error";
  version?: string;
  notes?: string;
  error?: string;
}

export interface BridgeStateEvent {
  event: "state";
  state: MascotState;
  text?: string;
  detail?: string;
  continuous?: boolean;
}

export interface BridgeAudioLevelEvent {
  event: "audio_level";
  level: number;
}

export interface BridgeLogEvent {
  event: "log";
  line: string;
  kind?: LogKind;
}

export interface BridgeSettingsEvent {
  event: "settings";
  data: AppSettings;
}

export interface BridgeIntentsEvent {
  event: "intents";
  data: IntentCommand[];
}

export interface BridgeDownloadProgressEvent {
  event: "download_progress";
  done: number;
  total: number;
  stage: string;
}

export type BridgeEvent =
  | BridgeStateEvent
  | BridgeAudioLevelEvent
  | BridgeLogEvent
  | BridgeSettingsEvent
  | BridgeIntentsEvent
  | BridgeDownloadProgressEvent;
