export type ApiError = {
  error: string;
  message: string;
};

export type ProjectObjectField = {
  key: string;
  label: string;
  value: string;
};

export type ProjectObject = {
  external_judgment_line: string;
  project_identity: {
    title: string;
    stage: string;
    stage_label: string;
    audience?: string;
    category?: string;
    status_tag?: string;
  };
  project_description: string;
  key_browse_fields: ProjectObjectField[];
  current_status: {
    stage: string;
    stage_label: string;
    recent_update: string;
    validation_signal?: string;
  };
  next_step: {
    text: string;
    status: string;
    status_label?: string;
  };
};

export type OneFileProject = {
  id: string;
  title: string;
  summary?: string;
  project_object?: ProjectObject;
  entity_type?: "temporary_card" | "claimed_project" | string;
  claim_status?: "unclaimed" | "claimed" | string;
  visible_in_library?: boolean;
  claimed_by_user_id?: string;
  stage?: string;
  stage_label?: string;
  form_type?: string;
  form_type_label?: string;
  business_model_type?: string;
  business_model_type_label?: string;
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
    status?: string;
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
  idempotent_replay?: boolean;
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

export type OpsInboxItem = {
  id: string;
  raw_text: string;
  capture_type: string;
  who: string;
  source_channel: string;
  source_detail: string;
  does_what: string;
  can_offer: string;
  currently_needs: string;
  status: string;
  routed_to_type: string;
  routed_to_id: string;
  private_notes: string;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type OpsPerson = {
  id: string;
  name?: string;
  alias?: string;
  display_name: string;
  wechat_name: string;
  phone: string;
  email: string;
  city: string;
  roles: string[];
  role_tags?: string[];
  organization_ids: string[];
  associated_organizations?: string[];
  associated_opportunities?: string[];
  source_channel: string;
  relationship_temperature: string;
  trust_level: string;
  can_offer_summary: string;
  currently_needs_summary: string;
  can_offer?: string;
  currently_needs?: string;
  decision_power?: string;
  budget_signal?: string;
  trust_notes?: string;
  public_notes: string;
  private_notes: string;
  last_contacted_at: string;
  next_action: string;
  next_action_at: string;
  priority?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type OpsOrganization = {
  id: string;
  name: string;
  type: string;
  city: string;
  key_people_ids: string[];
  key_people?: string[];
  offers: string;
  needs: string;
  can_offer?: string;
  currently_needs?: string;
  what_they_do?: string;
  potential_value_to_me?: string;
  risks?: string;
  suitable_project_types: string[];
  cooperation_status: string;
  relationship_status?: string;
  relationship_temperature: string;
  notes: string;
  next_action: string;
  next_action_at: string;
  priority?: string;
  created_at: string;
  updated_at: string;
};

export type OpsProject = {
  id: string;
  name: string;
  founder_people_ids: string[];
  public_project_id: string;
  one_liner: string;
  target_customer: string;
  problem: string;
  solution: string;
  current_stage: string;
  evidence_level: string;
  has_customer: boolean;
  has_order: boolean;
  has_revenue: boolean;
  has_delivery: boolean;
  business_loop_summary: string;
  needs_compute: boolean;
  needs_private_deployment: boolean;
  needs_tech: boolean;
  needs_ops: boolean;
  needs_capital: boolean;
  suitable_for_parks: boolean;
  suitable_for_interview: boolean;
  suitable_for_recommendation: boolean;
  recommended_org_ids: string[];
  sensitive_notes: string;
  share_permission: string;
  next_action: string;
  next_action_at: string;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type OpsNeed = {
  id: string;
  owner_type: "person" | "project" | "organization" | string;
  owner_id: string;
  owner?: string;
  category: string;
  need_type?: string;
  description: string;
  urgency: string;
  status: string;
  matched_offer_ids: string[];
  possible_matches?: string[];
  next_action: string;
  next_action_at: string;
  created_at: string;
  updated_at: string;
};

export type OpsOffer = {
  id: string;
  owner_type: "person" | "organization" | string;
  owner_id: string;
  owner?: string;
  category: string;
  offer_type?: string;
  description: string;
  constraints: string;
  available_for: string[];
  matched_need_ids: string[];
  suitable_for?: string;
  proof_or_cases?: string;
  needs_verification?: string;
  next_action?: string;
  created_at: string;
  updated_at: string;
};

export type OpsInteraction = {
  id: string;
  date: string;
  title?: string;
  channel: string;
  participants?: string[];
  people_ids: string[];
  organization_ids: string[];
  project_ids: string[];
  summary: string;
  key_points?: string[];
  decisions_or_consensus?: string[];
  open_questions?: string[];
  commitments: string;
  next_action: string;
  next_actions?: string[];
  next_action_at: string;
  confidentiality_level: string;
  raw_notes: string;
  private_notes?: string;
  created_at: string;
  updated_at: string;
};

export type OpsContent = {
  id: string;
  platform: string;
  content_title?: string;
  title: string;
  topic_tags: string[];
  published_at: string;
  related_people_ids: string[];
  related_org_ids: string[];
  related_project_ids: string[];
  related_opportunity?: string;
  metrics: {
    views: number;
    likes: number;
    comments: number;
    saves: number;
    shares: number;
    follows: number;
    dms: number;
  };
  content_angle?: string;
  key_message?: string;
  target_audience?: string;
  possible_followup?: string;
  publish_priority?: string;
  insights: string;
  followup_content_ideas: string;
  private_notes?: string;
  created_at: string;
  updated_at: string;
};

export type OpsOpportunity = {
  id: string;
  opportunity_name: string;
  source: string;
  related_people: string[];
  related_organizations: string[];
  stage: string;
  current_stage: string;
  core_need: string;
  why_it_matters: string;
  my_possible_role: string;
  my_role: string;
  required_partners_or_resources: string;
  possible_revenue_model: string;
  budget_signal: string;
  decision_process: string;
  decision_power_status: string;
  next_action: string;
  next_action_at: string;
  why_now: string;
  priority: "high" | "medium" | "low" | string;
  risks: string;
  risk: string;
  recommended_action_this_week: string;
  private_notes: string;
  created_at: string;
  updated_at: string;
};

export type OpsNextAction = {
  id: string;
  action: string;
  related_person_or_opportunity: string;
  related_person: string;
  expected_outcome: string;
  deadline_or_timing: string;
  priority: "high" | "medium" | "low" | string;
  reason: string;
  message_needed: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type OpsFollowup = {
  id: string;
  entity_type: string;
  entity_id: string;
  label: string;
  next_action: string;
  next_action_at: string;
  bucket: string;
  updated_at: string;
};

export type OpsSummaryResponse = {
  summary: {
    inbox_count: number;
    people_count: number;
    organization_count: number;
    project_count: number;
    opportunity_count: number;
    high_priority_opportunity_count: number;
    need_count: number;
    offer_count: number;
    interaction_count: number;
    content_count: number;
    next_action_count: number;
    high_priority_next_action_count: number;
    followup_count: number;
    overdue_followup_count: number;
    today_followup_count: number;
    this_week_followup_count: number;
  };
};
