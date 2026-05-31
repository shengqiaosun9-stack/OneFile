from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)


class LoginStartRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)


class LoginVerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    challenge_id: str = Field(min_length=8, max_length=24)
    code: str = Field(min_length=4, max_length=12)


class CreateProjectRequest(BaseModel):
    email: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=80)
    input_text: str = Field(default="", max_length=12000)
    inputText: str = Field(default="", max_length=12000)
    supplemental_text: str = Field(default="", max_length=12000)
    supplementalText: str = Field(default="", max_length=12000)
    cta_token: str = Field(default="", max_length=40)
    ctaToken: str = Field(default="", max_length=40)
    stage: str = Field(default="BUILDING", max_length=40)
    form_type: str = Field(default="OTHER", max_length=40)
    formType: str = Field(default="OTHER", max_length=40)
    business_model_type: str = Field(default="UNKNOWN", max_length=40)
    businessModelType: str = Field(default="UNKNOWN", max_length=40)
    model_type: str = Field(default="UNKNOWN", max_length=40)
    modelType: str = Field(default="UNKNOWN", max_length=40)
    request_id: str = Field(default="", max_length=64)
    requestId: str = Field(default="", max_length=64)


class GenerateProjectRequest(BaseModel):
    raw_input: str = Field(default="", max_length=12000)
    optional_title: str = Field(default="", max_length=80)
    file_text: str = Field(default="", max_length=12000)
    output_language: str = Field(default="", max_length=24)
    outputLanguage: str = Field(default="", max_length=24)
    cta_token: str = Field(default="", max_length=40)
    ctaToken: str = Field(default="", max_length=40)
    request_id: str = Field(default="", max_length=64)
    requestId: str = Field(default="", max_length=64)


class GenerateCardRequest(BaseModel):
    raw_input: str = Field(default="", max_length=12000)
    optional_title: str = Field(default="", max_length=80)
    file_text: str = Field(default="", max_length=12000)
    output_language: str = Field(default="", max_length=24)
    outputLanguage: str = Field(default="", max_length=24)
    cta_token: str = Field(default="", max_length=40)
    ctaToken: str = Field(default="", max_length=40)
    request_id: str = Field(default="", max_length=64)
    requestId: str = Field(default="", max_length=64)


class EditProjectRequest(BaseModel):
    email: str = Field(default="", max_length=120)
    title: Optional[str] = Field(default=None, max_length=80)
    summary: Optional[str] = Field(default=None, max_length=280)
    users: Optional[str] = Field(default=None, max_length=180)
    use_cases: Optional[str] = Field(default=None, max_length=280)
    problem_statement: Optional[str] = Field(default=None, max_length=280)
    solution_approach: Optional[str] = Field(default=None, max_length=280)
    model_desc: Optional[str] = Field(default=None, max_length=180)
    latest_update: Optional[str] = Field(default=None, max_length=300)
    stage_metric: Optional[str] = Field(default=None, max_length=120)
    next_action_text: Optional[str] = Field(default=None, max_length=200)
    next_action_status: Optional[str] = Field(default=None, max_length=24)
    stage: Optional[str] = Field(default=None, max_length=40)
    form_type: Optional[str] = Field(default=None, max_length=40)
    business_model_type: Optional[str] = Field(default=None, max_length=40)
    model_type: Optional[str] = Field(default=None, max_length=40)


class UpdateProgressRequest(BaseModel):
    email: str = Field(default="", max_length=120)
    update_text: str = Field(default="", max_length=12000)
    supplemental_text: str = Field(default="", max_length=12000)
    input_text: str = Field(default="", max_length=12000)
    cta_token: str = Field(default="", max_length=40)
    ctaToken: str = Field(default="", max_length=40)
    business_model_type: str = Field(default="", max_length=40)
    businessModelType: str = Field(default="", max_length=40)
    request_id: str = Field(default="", max_length=64)
    requestId: str = Field(default="", max_length=64)


class EditProgressItemRequest(BaseModel):
    content: str = Field(default="", max_length=12000)


class ToggleShareRequest(BaseModel):
    email: str = Field(default="", max_length=120)
    is_public: bool = False


class ShareCTARequest(BaseModel):
    email: str = Field(default="", max_length=120)
    cta: str = Field(default="start_project", max_length=40)
    source: str = Field(default="share_page_cta", max_length=40)
    ref: str = Field(default="", max_length=80)


class WeeklyReportRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    week_start: str = Field(default="", max_length=16)


class OpsLeadRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=80)
    source_channel: Optional[str] = Field(default=None, max_length=40)
    source_handle: Optional[str] = Field(default=None, max_length=80)
    wechat_status: Optional[str] = Field(default=None, max_length=40)
    city: Optional[str] = Field(default=None, max_length=40)
    direction: Optional[str] = Field(default=None, max_length=120)
    one_liner: Optional[str] = Field(default=None, max_length=240)
    stage: Optional[str] = Field(default=None, max_length=40)
    project_id: Optional[str] = Field(default=None, max_length=24)
    private_notes: Optional[str] = Field(default=None, max_length=1200)
    followup_status: Optional[str] = Field(default=None, max_length=40)


class OpsProfileRequest(BaseModel):
    core_need: Optional[str] = Field(default=None, max_length=500)
    need_tags: Optional[list[str]] = None
    target_people: Optional[str] = Field(default=None, max_length=500)
    offers: Optional[str] = Field(default=None, max_length=500)
    offer_tags: Optional[list[str]] = None
    cooperation_preferences: Optional[list[str]] = None
    has_budget: Optional[bool] = None
    accepts_paid_service: Optional[bool] = None
    accepts_equity_or_revenue_share: Optional[bool] = None
    seeking_cofounder: Optional[bool] = None
    needs_investment: Optional[bool] = None
    needs_customers: Optional[bool] = None
    needs_tech: Optional[bool] = None
    needs_content_growth: Optional[bool] = None
    needs_private_domain: Optional[bool] = None
    needs_industry_scene: Optional[bool] = None
    needs_school_scene: Optional[bool] = None
    needs_park_scene: Optional[bool] = None
    needs_medical_scene: Optional[bool] = None
    tech_need_type: Optional[str] = Field(default=None, max_length=24)
    tech_offer_type: Optional[str] = Field(default=None, max_length=24)
    suitable_offline_event: Optional[bool] = None
    suitable_remote_interview: Optional[bool] = None
    suitable_content_interview: Optional[bool] = None
    accepts_filming: Optional[bool] = None
    filming_boundary: Optional[str] = Field(default=None, max_length=500)
    internal_score: Optional[int] = None
    next_action: Optional[str] = Field(default=None, max_length=500)
    private_notes: Optional[str] = Field(default=None, max_length=1200)


class OpsProfileSuggestRequest(BaseModel):
    core_need: str = Field(default="", max_length=800)
    target_people: str = Field(default="", max_length=800)
    offers: str = Field(default="", max_length=800)
    direction: str = Field(default="", max_length=300)


class OpsActivityRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=24)
    title: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=40)
    format: Optional[str] = Field(default=None, max_length=40)
    date: Optional[str] = Field(default=None, max_length=40)
    status: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=1200)


class OpsActivityMembershipRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=24)
    activity_id: Optional[str] = Field(default=None, max_length=24)
    subject_type: Optional[str] = Field(default=None, max_length=16)
    subject_id: Optional[str] = Field(default=None, max_length=24)
    role: Optional[str] = Field(default=None, max_length=60)
    status: Optional[str] = Field(default=None, max_length=40)
    willing_one_minute_intro: Optional[bool] = None
    accepts_filming: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=1200)


class OpsRoutingRecordRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=24)
    subject_type: Optional[str] = Field(default=None, max_length=16)
    subject_id: Optional[str] = Field(default=None, max_length=24)
    target_type: Optional[str] = Field(default=None, max_length=60)
    target_name: Optional[str] = Field(default=None, max_length=100)
    reason: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = Field(default=None, max_length=40)
    next_action: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1200)


class OpsInboxItemRequest(BaseModel):
    raw_text: Optional[str] = Field(default=None, max_length=12000)
    capture_type: Optional[str] = Field(default=None, max_length=40)
    who: Optional[str] = Field(default=None, max_length=120)
    source_channel: Optional[str] = Field(default=None, max_length=40)
    source_detail: Optional[str] = Field(default=None, max_length=120)
    does_what: Optional[str] = Field(default=None, max_length=500)
    can_offer: Optional[str] = Field(default=None, max_length=500)
    currently_needs: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = Field(default=None, max_length=40)
    routed_to_type: Optional[str] = Field(default=None, max_length=40)
    routed_to_id: Optional[str] = Field(default=None, max_length=32)
    private_notes: Optional[str] = Field(default=None, max_length=1200)
    tags: Optional[list[str]] = None


class OpsInboxRouteRequest(BaseModel):
    target_type: str = Field(max_length=40)
    payload: Dict[str, Any] = Field(default_factory=dict)


class OpsPersonRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    wechat_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=80)
    email: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=60)
    roles: Optional[list[str]] = None
    organization_ids: Optional[list[str]] = None
    source_channel: Optional[str] = Field(default=None, max_length=60)
    relationship_temperature: Optional[str] = Field(default=None, max_length=24)
    trust_level: Optional[str] = Field(default=None, max_length=24)
    can_offer_summary: Optional[str] = Field(default=None, max_length=800)
    currently_needs_summary: Optional[str] = Field(default=None, max_length=800)
    public_notes: Optional[str] = Field(default=None, max_length=1200)
    private_notes: Optional[str] = Field(default=None, max_length=2400)
    last_contacted_at: Optional[str] = Field(default=None, max_length=24)
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_action_at: Optional[str] = Field(default=None, max_length=24)
    tags: Optional[list[str]] = None


class OpsOrganizationRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    type: Optional[str] = Field(default=None, max_length=40)
    city: Optional[str] = Field(default=None, max_length=60)
    key_people_ids: Optional[list[str]] = None
    offers: Optional[str] = Field(default=None, max_length=1000)
    needs: Optional[str] = Field(default=None, max_length=1000)
    suitable_project_types: Optional[list[str]] = None
    cooperation_status: Optional[str] = Field(default=None, max_length=80)
    relationship_temperature: Optional[str] = Field(default=None, max_length=24)
    notes: Optional[str] = Field(default=None, max_length=2400)
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_action_at: Optional[str] = Field(default=None, max_length=24)


class OpsProjectRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    founder_people_ids: Optional[list[str]] = None
    public_project_id: Optional[str] = Field(default=None, max_length=32)
    one_liner: Optional[str] = Field(default=None, max_length=500)
    target_customer: Optional[str] = Field(default=None, max_length=500)
    problem: Optional[str] = Field(default=None, max_length=800)
    solution: Optional[str] = Field(default=None, max_length=800)
    current_stage: Optional[str] = Field(default=None, max_length=40)
    evidence_level: Optional[str] = Field(default=None, max_length=40)
    has_customer: Optional[bool] = None
    has_order: Optional[bool] = None
    has_revenue: Optional[bool] = None
    has_delivery: Optional[bool] = None
    business_loop_summary: Optional[str] = Field(default=None, max_length=1000)
    needs_compute: Optional[bool] = None
    needs_private_deployment: Optional[bool] = None
    needs_tech: Optional[bool] = None
    needs_ops: Optional[bool] = None
    needs_capital: Optional[bool] = None
    suitable_for_parks: Optional[bool] = None
    suitable_for_interview: Optional[bool] = None
    suitable_for_recommendation: Optional[bool] = None
    recommended_org_ids: Optional[list[str]] = None
    sensitive_notes: Optional[str] = Field(default=None, max_length=2400)
    share_permission: Optional[str] = Field(default=None, max_length=40)
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_action_at: Optional[str] = Field(default=None, max_length=24)
    tags: Optional[list[str]] = None


class OpsNeedRequest(BaseModel):
    owner_type: Optional[str] = Field(default=None, max_length=24)
    owner_id: Optional[str] = Field(default=None, max_length=32)
    category: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = Field(default=None, max_length=1000)
    urgency: Optional[str] = Field(default=None, max_length=40)
    status: Optional[str] = Field(default=None, max_length=40)
    matched_offer_ids: Optional[list[str]] = None
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_action_at: Optional[str] = Field(default=None, max_length=24)


class OpsOfferRequest(BaseModel):
    owner_type: Optional[str] = Field(default=None, max_length=24)
    owner_id: Optional[str] = Field(default=None, max_length=32)
    category: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = Field(default=None, max_length=1000)
    constraints: Optional[str] = Field(default=None, max_length=1000)
    available_for: Optional[list[str]] = None
    matched_need_ids: Optional[list[str]] = None


class OpsInteractionRequest(BaseModel):
    date: Optional[str] = Field(default=None, max_length=24)
    channel: Optional[str] = Field(default=None, max_length=40)
    people_ids: Optional[list[str]] = None
    organization_ids: Optional[list[str]] = None
    project_ids: Optional[list[str]] = None
    summary: Optional[str] = Field(default=None, max_length=1200)
    commitments: Optional[str] = Field(default=None, max_length=1000)
    next_action: Optional[str] = Field(default=None, max_length=500)
    next_action_at: Optional[str] = Field(default=None, max_length=24)
    confidentiality_level: Optional[str] = Field(default=None, max_length=40)
    raw_notes: Optional[str] = Field(default=None, max_length=12000)


class OpsContentRequest(BaseModel):
    platform: Optional[str] = Field(default=None, max_length=40)
    title: Optional[str] = Field(default=None, max_length=160)
    topic_tags: Optional[list[str]] = None
    published_at: Optional[str] = Field(default=None, max_length=24)
    related_people_ids: Optional[list[str]] = None
    related_org_ids: Optional[list[str]] = None
    related_project_ids: Optional[list[str]] = None
    metrics: Optional[Dict[str, Any]] = None
    insights: Optional[str] = Field(default=None, max_length=2000)
    followup_content_ideas: Optional[str] = Field(default=None, max_length=2000)


class ApiEnvelope(BaseModel):
    used_fallback: Optional[bool] = None
    warning: Optional[str] = None
    data: Dict[str, Any]
