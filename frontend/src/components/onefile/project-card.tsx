import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { copyZh } from "@/lib/copy-zh";
import type { OneFileProject } from "@/lib/types";

type Props = {
  project: OneFileProject;
};

export function ProjectCard({ project }: Props) {
  const t = copyZh.projectCard;
  const summary = project.summary || project.problem_statement || t.noSummary;
  const stageText = project.stage_label || project.stage || t.stageFallback;
  const formText = project.form_type_label || project.form_type || t.valueFallback;
  const usersText = project.users || t.usersFallback;
  const modelText = project.model_type_label || project.model_type || t.valueFallback;

  return (
    <Card className="landing-card landing-hover-card h-full border-0 bg-white/92 shadow-[0_2px_8px_rgba(0,0,0,0.04)]">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="line-clamp-1 text-base text-[var(--landing-title)]">{project.title}</CardTitle>
          <Badge className="onefile-stage-badge">{stageText}</Badge>
        </div>
        <p className="line-clamp-3 text-sm onefile-subtle">{summary}</p>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs onefile-caption">{t.form}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{formText}</p>
          </div>
          <div>
            <p className="text-xs onefile-caption">{t.users}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{usersText}</p>
          </div>
          <div className="col-span-2">
            <p className="text-xs onefile-caption">{t.model}</p>
            <p className="line-clamp-2 text-[var(--landing-title)]">{modelText}</p>
          </div>
        </div>
        <p className="line-clamp-2 border-t border-slate-200/70 pt-2 text-xs onefile-caption">
          {t.latest}: {project.latest_update || t.noUpdates}
        </p>
      </CardContent>

      <CardFooter className="flex gap-2">
        <Link
          href={`/projects/${project.id}`}
          className={buttonVariants({ variant: "default", className: "landing-cta-btn flex-1" })}
        >
          {t.viewDetails}
        </Link>
        <Link
          href={`/share/${project.id}`}
          className={buttonVariants({ variant: "ghost", className: "landing-secondary-btn flex-1" })}
        >
          {t.sharePage}
        </Link>
      </CardFooter>
    </Card>
  );
}
