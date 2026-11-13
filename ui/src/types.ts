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
  vision_api_key?: string;
  openrouter_api_key?: string;
  vision_api_base?: string;
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

export interface QueueItem {
  id: string;
  text: string;
}

export interface QueueState {
  running: QueueItem | null;
  pending: QueueItem[];
}

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

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  context_length?: number | null;
  input_modalities?: string[];
  pricing_prompt?: string | null;
  pricing_completion?: string | null;
  supports_vision: boolean;
  supports_audio: boolean;
  modalities_inferred?: boolean;
}

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  models_count?: number;
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

export interface BridgeQueueEvent {
  event: "queue";
  pending: QueueItem[];
  running: QueueItem | null;
}

export interface BridgeLearnedEvent {
  event: "learned";
  data: LearnedCommand[];
}

export interface BridgeMcpConfigEvent {
  event: "mcp_config";
  data: string;
}

export type BridgeEvent =
  | BridgeStateEvent
  | BridgeAudioLevelEvent
  | BridgeLogEvent
  | BridgeSettingsEvent
  | BridgeIntentsEvent
  | BridgeDownloadProgressEvent
  | BridgeQueueEvent
  | BridgeLearnedEvent
  | BridgeMcpConfigEvent;
