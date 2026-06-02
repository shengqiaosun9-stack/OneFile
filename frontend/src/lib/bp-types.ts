export type BpProject = {
  id: string;
  name: string;
  founder_name?: string;
  tagline: string;
  industry?: string;
  stage: string;
  target_customer?: string;
  current_resource_need: string[];
  visibility?: string;
  share_card_requested?: boolean;
  readiness_score: number;
  recommended_path: string;
  submission_source?: string;
  user_visible_token: string;
  internal_status?: string;
  priority?: string;
  budget_signal?: string;
  decision_power?: string;
  service_quote?: string;
  internal_notes?: string;
  private_feedback?: string;
  next_action?: string;
  next_action_at?: string;
  created_at: string;
  updated_at: string;
};

export type BpRawMaterial = {
  id: string;
  project_id: string;
  type: string;
  title: string;
  content: string;
  related_page_number?: number;
  created_at: string;
};

export type BpProjectInsight = {
  id: string;
  project_id: string;
  problem: string;
  solution: string;
  business_model: string;
  ai_relevance: string;
  traction: string;
  key_data: string;
  resource_needs: string;
  material_gaps: string[];
  recommended_path: string;
  readiness_score: number;
  score_breakdown?: Record<string, number>;
  resource_readiness?: Array<{
    path: string;
    level: string;
    reason: string;
    missing: string;
    next_step: string;
  }>;
  likely_questions?: string[];
  next_actions?: string[];
  bp_structure_preview?: Array<{
    module: string;
    question_to_answer: string;
    current_status: string;
    missing_material: string;
  }>;
  share_card?: {
    title: string;
    one_line: string;
    stage: string;
    category?: string;
    scenario?: string;
    target_user?: string;
    core_problem?: string;
    solution?: string;
    ai_role?: string;
    current_progress?: string;
    evidence?: string;
    business_model_status?: string;
    current_needs?: string[];
    can_provide?: string[];
    suitable_for?: string[];
    sensitive_info_boundary?: string;
    contact_visibility?: "hidden" | "public" | "via_owner" | string;
    contact_method?: string;
    target_customer: string;
    resource_ask: string;
    recommended_path: string;
    highlights: string[];
    gaps: string[];
  };
  created_at: string;
  updated_at: string;
};

export type BpPage = {
  id: string;
  project_id: string;
  page_number: number;
  title: string;
  question: string;
  core_judgement: string;
  suggested_content: string;
  existing_materials: string[];
  missing_materials: string[];
  draft_copy: string;
  likely_questions: string[];
  is_locked?: boolean;
  is_delivery_ready?: boolean;
  internal_notes?: string;
  created_at: string;
  updated_at: string;
};

export type BpGapItem = {
  gap_name: string;
  severity: string;
  why_it_matters: string;
  recommended_fix: string;
  page_number: number;
  page_title: string;
};

export type BpGapReport = {
  id: string;
  project_id: string;
  summary: string;
  items: BpGapItem[];
  updated_at: string;
};

export type BpServiceRequest = {
  id: string;
  project_id: string;
  service_type: string;
  contact_name?: string;
  contact_wechat?: string;
  contact_phone?: string;
  contact_email?: string;
  contact_preference?: string;
  urgent_problem?: string;
  budget_signal?: string;
  authorized_material_review?: boolean;
  user_message: string;
  status: string;
  internal_notes?: string;
  service_quote?: string;
  created_at: string;
  updated_at?: string;
};

export type BpNextAction = {
  id: string;
  project_id: string;
  action: string;
  owner: string;
  due_date: string;
  status: string;
  priority: string;
  created_at: string;
  updated_at: string;
};

export type BpVersion = {
  id: string;
  project_id: string;
  version_name: string;
  change_summary: string;
  created_at: string;
};

export type BpBundle = {
  project: BpProject;
  raw_materials: BpRawMaterial[];
  insight: BpProjectInsight;
  pages: BpPage[];
  gap_report: BpGapReport;
  service_requests: BpServiceRequest[];
  next_actions: BpNextAction[];
  versions: BpVersion[];
};
