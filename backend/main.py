from typing import Any, Dict

from fastapi import FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.schemas import (
    CreateProjectRequest,
    EditProjectRequest,
    GenerateCardRequest,
    GenerateProjectRequest,
    LoginStartRequest,
    LoginVerifyRequest,
    LoginRequest,
    OpsContentRequest,
    OpsInboxItemRequest,
    OpsInboxRouteRequest,
    OpsInteractionRequest,
    OpsNeedRequest,
    OpsOfferRequest,
    OpsOrganizationRequest,
    OpsPersonRequest,
    OpsProfileRequest,
    OpsProfileSuggestRequest,
    OpsProjectRequest,
    ShareCTARequest,
    ToggleShareRequest,
    UpdateProgressRequest,
    EditProgressItemRequest,
    WeeklyReportRequest,
)
from backend.pdf_extract import extract_pdf_text
from backend.service import (
    ServiceError,
    create_project,
    claim_card,
    generate_project,
    generate_card,
    delete_project,
    edit_project,
    export_user_backup,
    generate_weekly_report,
    get_growth_metrics,
    get_growth_projects_dashboard,
    get_intervention_learning,
    get_portfolio,
    get_project_growth_metrics,
    get_project_detail,
    get_session_user,
    get_card,
    get_share,
    get_visible_projects,
    logout_session,
    start_login,
    track_share_cta,
    toggle_share,
    update_project_progress,
    edit_project_progress_item,
    delete_project_progress_item,
    create_ops_item,
    create_bp_diagnosis,
    create_bp_service_request,
    export_ops_crm,
    get_bp_diagnosis,
    get_local_ops_user,
    get_ops_followups,
    get_ops_bp_followups,
    get_ops_bp_project,
    get_ops_relationship_map,
    import_ops_crm,
    verify_login,
    get_ops_summary,
    list_ops_bp_projects,
    list_ops_items,
    route_ops_inbox_item,
    supplement_bp_diagnosis,
    update_ops_bp_page,
    update_ops_bp_project,
    update_ops_item,
    get_ops_profile,
    require_ops_admin,
    suggest_ops_profile,
    update_ops_profile,
)

app = FastAPI(title="OneFile Backend API", version="0.1.0")
SESSION_COOKIE_KEY = "onefile_session"


def _request_is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    proto = (request.headers.get("x-forwarded-proto") or "").lower()
    return proto.startswith("https")


def _extract_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def _set_session_cookie(response: Response, session_token: str, request: Request) -> None:
    max_age = int(get_settings().auth_session_ttl_days * 24 * 60 * 60)
    secure_cookie = bool(get_settings().session_cookie_secure or _request_is_https(request))
    response.set_cookie(
        key=SESSION_COOKIE_KEY,
        value=session_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_KEY, path="/", samesite="lax")


def _optional_user(request: Request) -> Dict[str, Any]:
    session_token = request.cookies.get(SESSION_COOKIE_KEY, "")
    user = get_session_user(session_token) if session_token else None
    return user or {}


def _require_user(request: Request) -> Dict[str, Any]:
    user = _optional_user(request)
    if not user:
        raise ServiceError(401, "unauthorized", "请先登录后再执行该操作。")
    return user


def _require_ops_user(request: Request) -> Dict[str, Any]:
    if get_settings().local_mode:
        return get_local_ops_user()
    return _require_user(request)


@app.exception_handler(ServiceError)
async def service_error_handler(_: Any, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/auth/login")
def login_endpoint(payload: LoginRequest, response: Response, request: Request) -> Dict[str, Any]:
    # Legacy endpoint: only available when debug codes are enabled.
    if not get_settings().auth_debug_codes:
        raise ServiceError(410, "deprecated", "请改用 /v1/auth/login/start 与 /v1/auth/login/verify。")
    challenge = start_login(payload.email, client_ip=_extract_client_ip(request))
    result = verify_login(payload.email, str(challenge.get("challenge_id", "")), str(challenge.get("debug_code", "")))
    session_token = str(result.pop("session_token", ""))
    if session_token:
        _set_session_cookie(response, session_token, request)
    return result


@app.post("/v1/auth/login/start")
def login_start_endpoint(payload: LoginStartRequest, request: Request) -> Dict[str, Any]:
    return start_login(payload.email, client_ip=_extract_client_ip(request))


@app.post("/v1/auth/login/verify")
def login_verify_endpoint(payload: LoginVerifyRequest, response: Response, request: Request) -> Dict[str, Any]:
    result = verify_login(payload.email, payload.challenge_id, payload.code)
    session_token = str(result.pop("session_token", ""))
    if session_token:
        _set_session_cookie(response, session_token, request)
    return result


@app.get("/v1/auth/me")
def auth_me_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    projects = get_visible_projects(str(user.get("email", ""))).get("projects", [])
    return {"authenticated": True, "user": user, "projects": projects}


@app.post("/v1/auth/logout")
def auth_logout_endpoint(request: Request, response: Response) -> Dict[str, Any]:
    session_token = request.cookies.get(SESSION_COOKIE_KEY, "")
    logout_session(session_token)
    _clear_session_cookie(response)
    return {"ok": True}


@app.get("/v1/backup/export")
def backup_export_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    return export_user_backup(email=str(user.get("email", "")))


@app.post("/v1/bp/diagnoses")
def bp_diagnosis_create_endpoint(payload: Dict[str, Any]) -> Dict[str, Any]:
    return create_bp_diagnosis(payload)


@app.get("/v1/bp/diagnoses/{token}")
def bp_diagnosis_get_endpoint(token: str) -> Dict[str, Any]:
    return get_bp_diagnosis(token)


@app.post("/v1/bp/diagnoses/{token}/supplements")
def bp_diagnosis_supplement_endpoint(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return supplement_bp_diagnosis(token, payload)


@app.post("/v1/bp/diagnoses/{token}/service-requests")
def bp_service_request_create_endpoint(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return create_bp_service_request(token, payload)


@app.get("/v1/ops/bp/projects")
def ops_bp_projects_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_bp_projects(user)


@app.get("/v1/ops/bp/projects/{project_id}")
def ops_bp_project_get_endpoint(project_id: str, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return get_ops_bp_project(user, project_id)


@app.patch("/v1/ops/bp/projects/{project_id}")
def ops_bp_project_update_endpoint(project_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_bp_project(user, project_id, payload)


@app.patch("/v1/ops/bp/pages/{page_id}")
def ops_bp_page_update_endpoint(page_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_bp_page(user, page_id, payload)


@app.get("/v1/ops/bp/followups")
def ops_bp_followups_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return get_ops_bp_followups(user)


@app.get("/v1/ops/summary")
def ops_summary_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return get_ops_summary(user)


@app.post("/v1/ops/profiles/suggest")
def ops_profile_suggest_endpoint(payload: OpsProfileSuggestRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    require_ops_admin(user)
    return suggest_ops_profile(payload.model_dump())


@app.get("/v1/ops/profiles/{subject_type}/{subject_id}")
def ops_profile_get_endpoint(subject_type: str, subject_id: str, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return get_ops_profile(user, subject_type, subject_id)


@app.patch("/v1/ops/profiles/{subject_type}/{subject_id}")
def ops_profile_update_endpoint(subject_type: str, subject_id: str, payload: OpsProfileRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_profile(user, subject_type, subject_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/inbox")
def ops_inbox_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "inbox", dict(request.query_params))


@app.post("/v1/ops/inbox")
def ops_inbox_create_endpoint(payload: OpsInboxItemRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "inbox", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/inbox/{item_id}")
def ops_inbox_update_endpoint(item_id: str, payload: OpsInboxItemRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "inbox", item_id, payload.model_dump(exclude_none=True))


@app.post("/v1/ops/inbox/{item_id}/route")
def ops_inbox_route_endpoint(item_id: str, payload: OpsInboxRouteRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return route_ops_inbox_item(user, item_id, payload.target_type, payload.payload)


@app.get("/v1/ops/people")
def ops_people_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "people", dict(request.query_params))


@app.post("/v1/ops/people")
def ops_people_create_endpoint(payload: OpsPersonRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "people", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/people/{item_id}")
def ops_people_update_endpoint(item_id: str, payload: OpsPersonRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "people", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/organizations")
def ops_organizations_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "organizations", dict(request.query_params))


@app.post("/v1/ops/organizations")
def ops_organizations_create_endpoint(payload: OpsOrganizationRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "organizations", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/organizations/{item_id}")
def ops_organizations_update_endpoint(item_id: str, payload: OpsOrganizationRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "organizations", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/projects")
def ops_projects_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "projects", dict(request.query_params))


@app.post("/v1/ops/projects")
def ops_projects_create_endpoint(payload: OpsProjectRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "projects", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/projects/{item_id}")
def ops_projects_update_endpoint(item_id: str, payload: OpsProjectRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "projects", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/opportunities")
def ops_opportunities_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "opportunities", dict(request.query_params))


@app.post("/v1/ops/opportunities")
def ops_opportunities_create_endpoint(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "opportunities", payload)


@app.patch("/v1/ops/opportunities/{item_id}")
def ops_opportunities_update_endpoint(item_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "opportunities", item_id, payload)


@app.get("/v1/ops/needs")
def ops_needs_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "needs", dict(request.query_params))


@app.post("/v1/ops/needs")
def ops_needs_create_endpoint(payload: OpsNeedRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "needs", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/needs/{item_id}")
def ops_needs_update_endpoint(item_id: str, payload: OpsNeedRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "needs", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/offers")
def ops_offers_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "offers", dict(request.query_params))


@app.post("/v1/ops/offers")
def ops_offers_create_endpoint(payload: OpsOfferRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "offers", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/offers/{item_id}")
def ops_offers_update_endpoint(item_id: str, payload: OpsOfferRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "offers", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/interactions")
def ops_interactions_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "interactions", dict(request.query_params))


@app.post("/v1/ops/interactions")
def ops_interactions_create_endpoint(payload: OpsInteractionRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "interactions", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/interactions/{item_id}")
def ops_interactions_update_endpoint(item_id: str, payload: OpsInteractionRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "interactions", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/contents")
def ops_contents_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "contents", dict(request.query_params))


@app.post("/v1/ops/contents")
def ops_contents_create_endpoint(payload: OpsContentRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "contents", payload.model_dump(exclude_none=True))


@app.patch("/v1/ops/contents/{item_id}")
def ops_contents_update_endpoint(item_id: str, payload: OpsContentRequest, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "contents", item_id, payload.model_dump(exclude_none=True))


@app.get("/v1/ops/next-actions")
def ops_next_actions_list_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return list_ops_items(user, "next-actions", dict(request.query_params))


@app.post("/v1/ops/next-actions")
def ops_next_actions_create_endpoint(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return create_ops_item(user, "next-actions", payload)


@app.patch("/v1/ops/next-actions/{item_id}")
def ops_next_actions_update_endpoint(item_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return update_ops_item(user, "next-actions", item_id, payload)


@app.get("/v1/ops/followups")
def ops_followups_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return get_ops_followups(user)


@app.get("/v1/ops/relationship-map/{entity_type}/{entity_id}")
def ops_relationship_map_endpoint(entity_type: str, entity_id: str, request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return get_ops_relationship_map(user, entity_type, entity_id)


@app.get("/v1/ops/export")
def ops_export_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return export_ops_crm(user)


@app.post("/v1/ops/import")
def ops_import_endpoint(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    user = _require_ops_user(request)
    return import_ops_crm(user, payload)


@app.get("/v1/projects")
def list_projects(request: Request) -> Dict[str, Any]:
    user = _optional_user(request)
    effective_email = str(user.get("email", "")) or "guest@onefile.app"
    return get_visible_projects(effective_email)


@app.get("/v1/portfolio")
def portfolio_endpoint(request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    return get_portfolio(email=str(user.get("email", "")))


@app.post("/v1/projects")
def create_project_endpoint(payload: CreateProjectRequest, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    body = payload.model_dump()
    body["email"] = str(user.get("email", ""))
    return create_project(body)


@app.post("/v1/project/generate")
def generate_project_endpoint(payload: GenerateProjectRequest, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    body = payload.model_dump()
    body["email"] = str(user.get("email", ""))
    return generate_project(body)


@app.post("/v1/cards/generate")
def generate_card_endpoint(payload: GenerateCardRequest) -> Dict[str, Any]:
    return generate_card(payload.model_dump())


@app.get("/v1/cards/{project_id}")
def card_page_endpoint(project_id: str, request: Request) -> Dict[str, Any]:
    user = _optional_user(request)
    effective_email = str(user.get("email", ""))
    return get_card(project_id, email=effective_email)


@app.post("/v1/cards/{project_id}/claim")
def claim_card_endpoint(project_id: str, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    return claim_card(project_id, str(user.get("email", "")))


@app.get("/v1/projects/{project_id}")
def detail_project_endpoint(project_id: str, request: Request) -> Dict[str, Any]:
    user = _optional_user(request)
    effective_email = str(user.get("email", "")) or "guest@onefile.app"
    return get_project_detail(project_id, effective_email)


@app.patch("/v1/projects/{project_id}")
def edit_project_endpoint(project_id: str, payload: EditProjectRequest, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    body = payload.model_dump(exclude_none=True)
    body["email"] = str(user.get("email", ""))
    return edit_project(project_id, body)


@app.post("/v1/projects/{project_id}/update")
def update_project_endpoint(project_id: str, payload: UpdateProgressRequest, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    body = payload.model_dump()
    body["email"] = str(user.get("email", ""))
    return update_project_progress(project_id, body)


@app.patch("/v1/projects/{project_id}/updates/{update_id}")
def edit_project_update_item_endpoint(
    project_id: str,
    update_id: str,
    payload: EditProgressItemRequest,
    request: Request,
) -> Dict[str, Any]:
    user = _require_user(request)
    body = payload.model_dump()
    body["email"] = str(user.get("email", ""))
    return edit_project_progress_item(project_id, update_id, body)


@app.delete("/v1/projects/{project_id}/updates/{update_id}")
def delete_project_update_item_endpoint(project_id: str, update_id: str, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    return delete_project_progress_item(project_id, update_id, str(user.get("email", "")))


@app.patch("/v1/projects/{project_id}/share")
def share_project_endpoint(project_id: str, payload: ToggleShareRequest, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    body = payload.model_dump()
    body["email"] = str(user.get("email", ""))
    return toggle_share(project_id, body)


@app.delete("/v1/projects/{project_id}")
def delete_project_endpoint(project_id: str, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    return delete_project(project_id, str(user.get("email", "")))


@app.get("/v1/share/{project_id}")
def share_page_endpoint(project_id: str, request: Request) -> Dict[str, Any]:
    user = _optional_user(request)
    effective_email = str(user.get("email", ""))
    return get_share(project_id, email=effective_email)


@app.post("/v1/share/{project_id}/cta")
def share_cta_endpoint(project_id: str, payload: ShareCTARequest, request: Request) -> Dict[str, Any]:
    body = payload.model_dump()
    user = _optional_user(request)
    if user:
        body["email"] = str(user.get("email", ""))
    return track_share_cta(project_id, body)


@app.post("/v1/uploads/bp-extract")
async def bp_extract_endpoint(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    _require_user(request)
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if not filename.endswith(".pdf") and content_type != "application/pdf":
        raise ServiceError(400, "invalid_file_type", "仅支持 PDF 文件（.pdf）。")

    payload = await file.read()
    if len(payload) == 0:
        raise ServiceError(400, "invalid_file", "上传文件为空，请重新选择。")
    max_size = 10 * 1024 * 1024
    if len(payload) > max_size:
        raise ServiceError(400, "file_too_large", "文件过大，请上传 10MB 以内 PDF。")

    try:
        parsed = extract_pdf_text(payload)
    except Exception:
        raise ServiceError(400, "file_parse_failed", "文件解析失败，请确认 PDF 内容可读取。") from None
    extracted_text = str(parsed.get("extracted_text", "") or "").strip()
    if not extracted_text:
        raise ServiceError(400, "file_parse_empty", "未解析到有效文本，请上传可复制文本的 PDF。")
    return parsed


@app.get("/v1/metrics/growth")
def growth_metrics_endpoint(request: Request, days: int = Query(14, ge=1, le=365)) -> Dict[str, Any]:
    user = _require_user(request)
    return get_growth_metrics(email=str(user.get("email", "")), days=days)


@app.get("/v1/metrics/growth/projects/{project_id}")
def project_growth_metrics_endpoint(project_id: str, request: Request, days: int = Query(14, ge=1, le=365)) -> Dict[str, Any]:
    user = _require_user(request)
    return get_project_growth_metrics(project_id=project_id, email=str(user.get("email", "")), days=days)


@app.get("/v1/metrics/growth/projects")
def growth_projects_dashboard_endpoint(
    request: Request,
    days: int = Query(14, ge=1, le=365),
    limit: int = Query(10, ge=1, le=200),
) -> Dict[str, Any]:
    user = _require_user(request)
    return get_growth_projects_dashboard(email=str(user.get("email", "")), days=days, limit=limit)


@app.post("/v1/reports/weekly")
def weekly_report_endpoint(payload: WeeklyReportRequest, request: Request) -> Dict[str, Any]:
    user = _require_user(request)
    return generate_weekly_report(email=str(user.get("email", "")), week_start=payload.week_start)


@app.get("/v1/interventions/learning")
def intervention_learning_endpoint(request: Request, days: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    user = _require_user(request)
    return get_intervention_learning(email=str(user.get("email", "")), days=days)
