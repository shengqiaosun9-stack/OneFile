import type { OneFileProject, ProjectObject, ProjectObjectField } from "@/lib/types";

function nonEmpty(value: string | undefined, fallback: string): string {
  const cleaned = (value || "").trim();
  return cleaned || fallback;
}

function legacyProjectDescription(project: OneFileProject): string {
  return nonEmpty(project.solution_approach || project.problem_statement || project.model_desc || project.summary, "项目描述待补充");
}

function buildFallbackFields(project: OneFileProject): ProjectObjectField[] {
  return [
    {
      key: "form_type",
      label: "产品形态",
      value: nonEmpty(project.form_type_label || project.form_type, "待补充"),
    },
    {
      key: "target_user",
      label: "目标用户",
      value: nonEmpty(project.users, "待补充"),
    },
    {
      key: "business_model",
      label: "商业模式",
      value: nonEmpty(project.business_model_type_label || project.business_model_type, "待补充"),
    },
    {
      key: "monetization",
      label: "盈利模式",
      value: nonEmpty(project.model_type_label || project.model_type, "待补充"),
    },
  ];
}

export function getProjectObject(project: OneFileProject): ProjectObject {
  const current = project.project_object;
  return {
    external_judgment_line: nonEmpty(current?.external_judgment_line || project.summary, "项目摘要待补充"),
    project_identity: {
      title: nonEmpty(current?.project_identity?.title || project.title, "未命名项目"),
      stage: nonEmpty(current?.project_identity?.stage || project.stage, "BUILDING"),
      stage_label: nonEmpty(current?.project_identity?.stage_label || project.stage_label || project.stage, "待补充"),
      audience: nonEmpty(current?.project_identity?.audience || project.users, ""),
      category: nonEmpty(current?.project_identity?.category || project.form_type_label || project.form_type, ""),
      status_tag: nonEmpty(current?.project_identity?.status_tag, ""),
    },
    project_description: nonEmpty(current?.project_description, legacyProjectDescription(project)),
    key_browse_fields:
      current?.key_browse_fields?.filter((field) => field?.label && field?.value).length
        ? current.key_browse_fields.filter((field) => field?.label && field?.value)
        : buildFallbackFields(project),
    current_status: {
      stage: nonEmpty(current?.current_status?.stage || project.stage, "BUILDING"),
      stage_label: nonEmpty(current?.current_status?.stage_label || project.stage_label || project.stage, "待补充"),
      recent_update: nonEmpty(current?.current_status?.recent_update || project.latest_update, "暂无最近进展"),
      validation_signal: nonEmpty(current?.current_status?.validation_signal || project.stage_metric, ""),
    },
    next_step: {
      text: nonEmpty(current?.next_step?.text || project.next_action?.text || project.latest_update, "待补充"),
      status: nonEmpty(current?.next_step?.status || project.next_action?.status, "open"),
      status_label: nonEmpty(current?.next_step?.status_label, ""),
    },
  };
}
