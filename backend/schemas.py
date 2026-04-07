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
    cta_token: str = Field(default="", max_length=40)
    ctaToken: str = Field(default="", max_length=40)
    request_id: str = Field(default="", max_length=64)
    requestId: str = Field(default="", max_length=64)


class GenerateCardRequest(BaseModel):
    raw_input: str = Field(default="", max_length=12000)
    optional_title: str = Field(default="", max_length=80)
    file_text: str = Field(default="", max_length=12000)
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


class ApiEnvelope(BaseModel):
    used_fallback: Optional[bool] = None
    warning: Optional[str] = None
    data: Dict[str, Any]
