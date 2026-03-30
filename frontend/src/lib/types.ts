export type ApiError = {
  error: string;
  message: string;
};

export type OneFileProject = {
  id: string;
  title: string;
  summary?: string;
  stage?: string;
  stage_label?: string;
  form_type?: string;
  form_type_label?: string;
  model_type?: string;
  model_type_label?: string;
  users?: string;
  model_desc?: string;
  problem_statement?: string;
  solution_approach?: string;
  use_cases?: string;
  latest_update?: string;
  stage_metric?: string;
  updated_at?: string;
  owner_user_id?: string;
  share?: {
    is_public?: boolean;
    slug?: string;
  };
  updates?: Array<{
    id?: string;
    kind?: string;
    content?: string;
    created_at?: string;
    evidence_score?: number;
    action_alignment?: number;
    completion_signal?: boolean;
  }>;
  next_action?: {
    text?: string;
  };
};

export type AuthResponse = {
  user: {
    id: string;
    email: string;
  };
  projects: OneFileProject[];
};

export type AuthStartResponse = {
  ok: boolean;
  challenge_id: string;
  expires_in_seconds: number;
  debug_code?: string;
};

export type AuthMeResponse = {
  authenticated: boolean;
  user: {
    id: string;
    email: string;
  };
  projects?: OneFileProject[];
};

export type ListResponse = {
  user: {
    id: string;
    email: string;
  };
  projects: OneFileProject[];
};

export type ShareResponse = {
  project: OneFileProject;
  access_granted: boolean;
  owner_preview: boolean;
};

export type CtaResponse = {
  ok: boolean;
  access_granted: boolean;
  cta_token: string;
  expires_in_days: number;
  expires_at: string;
};

export type MutationResponse = {
  project: OneFileProject;
  used_fallback?: boolean;
  warning?: string;
};

export type BpExtractResponse = {
  extracted_text: string;
  page_count: number;
  text_chars: number;
  truncated: boolean;
};

export type BackupExportResponse = {
  exported_at: string;
  user: {
    id: string;
    email: string;
  };
  projects: OneFileProject[];
  events: Array<Record<string, unknown>>;
};
