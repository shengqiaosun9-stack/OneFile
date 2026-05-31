import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { copyZh } from "@/lib/copy-zh";
import { getProjectObject } from "@/lib/project-object";
import type { OneFileProject } from "@/lib/types";

type Props = {
  project: OneFileProject;
  isOwner?: boolean;
};

export function ProjectCard({ project, isOwner = false }: Props) {
  const t = copyZh.projectCard;
  const projectObject = getProjectObject(project);
  const summary = projectObject.external_judgment_line || t.noSummary;
  const stageText = projectObject.project_identity.stage_label || t.stageFallback;
  const browseFields = projectObject.key_browse_fields.slice(0, 3);
  const profitField =
    projectObject.key_browse_fields.find((field) => field.key === "monetization" && !browseFields.some((item) => item.key === field.key)) ||
    projectObject.key_browse_fields.find((field) => !browseFields.some((item) => item.key === field.key)) ||
    null;
  const openHref = `/card/${project.id}?from=library`;
  const editHref = `/edit/${project.id}`;

  return (
    <Card className="project-card-surface project-card-surface--interactive project-card-index border-0">
      <Link href={openHref} className="project-card-open-hit" aria-label={`${t.viewDetails}：${project.title || t.stageFallback}`} />

      <CardHeader className="relative z-20 space-y-3">
        <p className="project-card-index-summary">{summary}</p>
        <div className="project-card-index-identity">
          <CardTitle className="line-clamp-1 text-[1.02rem] font-semibold tracking-[-0.01em] text-[var(--landing-title)]/94">
            {projectObject.project_identity.title}
          </CardTitle>
          <Badge className="stage-badge">{stageText}</Badge>
        </div>
      </CardHeader>

      <CardContent className="project-card-index-meta relative z-20 space-y-2.5 text-sm">
        <div className="project-card-index-meta-grid">
          {browseFields.map((field) => (
            <div key={field.key}>
              <p className="text-xs content-caption">{field.label}</p>
              <p className="line-clamp-1 text-[0.9rem] text-[var(--shell-text-secondary)]/82">{field.value}</p>
            </div>
          ))}
        </div>
        {profitField ? (
          <p className="project-card-index-profit">
            <span className="content-caption">{profitField.label}：</span>
            {profitField.value}
          </p>
        ) : null}
      </CardContent>

      <CardFooter className="project-card-index-footer relative z-30">
        <div className="project-card-index-recent">
          <p className="text-xs content-caption">{t.latest}</p>
          <p className="line-clamp-1 text-[0.86rem] text-[var(--shell-text-tertiary)]/88">
            {projectObject.current_status.recent_update || t.noUpdates}
          </p>
        </div>
        <div className="project-card-index-actions">
          <Link href={openHref} className="project-card-index-open-link">
            {t.viewDetails}
          </Link>
          {isOwner ? (
            <Link href={editHref} className="project-card-index-edit-link">
              {t.editCard}
            </Link>
          ) : null}
        </div>
      </CardFooter>
    </Card>
  );
}
