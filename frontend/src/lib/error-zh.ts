import type { ApiError } from "@/lib/types";

const API_ERROR_ZH: Record<string, string> = {
  invalid_email: "邮箱格式不正确，请检查后重试。",
  unauthorized: "你还未登录，请先登录后再继续。",
  invalid_title: "主体名称不符合要求，请调整后重试。",
  invalid_input: "输入内容不符合要求，请调整后重试。",
  invalid_code: "验证码无效或已过期，请重新获取。",
  invalid_update: "更新内容不符合要求，请调整后重试。",
  invalid_file_type: "仅支持 PDF 文件（.pdf）。",
  file_too_large: "文件过大，请上传 10MB 以内 PDF。",
  file_parse_failed: "文件解析失败，请确认 PDF 内容可读取。",
  file_parse_empty: "未解析到有效文本，请上传可复制文本的 PDF。",
  invalid_json: "请求体格式不正确，请检查后重试。",
  email_not_configured: "邮箱验证码服务尚未配置，请稍后再试。",
  email_send_failed: "验证码发送失败，请稍后重试。",
  forbidden: "仅项目所有者可执行该操作。",
  not_found: "目标内容不存在或已删除。",
  conflict: "请求冲突，请刷新后重试。",
  too_many_requests: "请求过于频繁，请稍后再试（建议 1 分钟后重试）。",
  too_many_attempts: "验证码尝试次数过多，请重新获取后再试。",
  backend_unreachable: "后端服务暂时不可用，请稍后重试。",
  backend_timeout: "后端响应超时，请稍后重试。",
  backend_not_configured: "后端服务尚未正确配置，请联系管理员。",
};

function hasChinese(text: string | undefined): boolean {
  return Boolean(text && /[\u4e00-\u9fff]/.test(text));
}

export function getApiErrorMessage(error: ApiError | null | undefined, fallback: string): string {
  if (!error) return fallback;
  if (error.error && API_ERROR_ZH[error.error]) return API_ERROR_ZH[error.error];
  if (hasChinese(error.message)) return error.message;
  return fallback;
}

export type ResolvedApiError = {
  status: number;
  code: string;
  message: string;
};

export async function resolveApiError(response: Response, fallback: string): Promise<ResolvedApiError> {
  let payload: ApiError | null = null;
  try {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      payload = (await response.json()) as ApiError;
    } else {
      const text = await response.text();
      payload = text
        ? {
            error: "",
            message: text,
          }
        : null;
    }
  } catch {
    payload = null;
  }

  return {
    status: response.status,
    code: payload?.error || "",
    message: getApiErrorMessage(payload, fallback),
  };
}
