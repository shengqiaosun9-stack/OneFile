from typing import Any, Dict

from fastapi import FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.schemas import (
    CreateProjectRequest,
    EditProjectRequest,
    GenerateProjectRequest,
    LoginStartRequest,
    LoginVerifyRequest,
    LoginRequest,
    ShareCTARequest,
    ToggleShareRequest,
    UpdateProgressRequest,
    WeeklyReportRequest,
)
from backend.pdf_extract import extract_pdf_text
from backend.service import (
    ServiceError,
    create_project,
    generate_project,
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
    get_share,
    get_visible_projects,
    logout_session,
    start_login,
    track_share_cta,
    toggle_share,
    update_project_progress,
    verify_login,
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
