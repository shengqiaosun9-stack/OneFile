import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { copyZh } from "@/lib/copy-zh";
import type { OneFileProject } from "@/lib/types";

type Props = {
  project: OneFileProject;
  isOwner?: boolean;
};

export function ProjectCard({ project, isOwner = false }: Props) {
  const t = copyZh.projectCard;
  const summary = project.summary || project.problem_statement || t.noSummary;
  const stageText = project.stage_label || project.stage || t.stageFallback;
  const formText = project.form_type_label || project.form_type || t.valueFallback;
  const usersText = project.users || t.usersFallback;
  const businessModelText = project.business_model_type_label || project.business_model_type || t.valueFallback;
  const profitModelText = project.model_type_label || project.model_type || t.valueFallback;

  return (
    <Card className="project-card-surface project-card-surface--interactive h-full border-0">
      <CardHeader className="space-y-3">
        <p className="line-clamp-3 text-sm content-subtle">{summary}</p>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="line-clamp-1 text-sm font-medium text-[var(--landing-title)]/90">{project.title}</CardTitle>
          <Badge className="stage-badge">{stageText}</Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs content-caption">{t.form}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{formText}</p>
          </div>
          <div>
            <p className="text-xs content-caption">{t.users}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{usersText}</p>
          </div>
          <div className="col-span-2">
            <p className="text-xs content-caption">{t.businessModel}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{businessModelText}</p>
          </div>
          <div className="col-span-2">
            <p className="text-xs content-caption">{t.profitModel}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{profitModelText}</p>
          </div>
          <div className="col-span-2 border-t border-white/10 pt-2">
            <p className="text-xs content-caption">{t.latest}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]/85">{project.latest_update || t.noUpdates}</p>
          </div>
        </div>
      </CardContent>

      <CardFooter className="flex gap-2">
        <Link
          href={`/card/${project.id}?from=library`}
          className={buttonVariants({ variant: "default", className: isOwner ? "action-primary-btn flex-1" : "action-primary-btn w-full" })}
        >
          {t.viewDetails}
        </Link>
        {isOwner ? (
          <Link
            href={`/edit/${project.id}`}
            className={buttonVariants({ variant: "ghost", className: "action-secondary-btn flex-1" })}
          >
            {t.editCard}
          </Link>
        ) : null}
      </CardFooter>
    </Card>
  );
}
