"use client";

import { useParams } from "next/navigation";

import { CardPage } from "@/components/onefile/card-page";

export default function CardRoutePage() {
  const params = useParams<{ id: string }>();
  return <CardPage projectId={String(params.id || "")} />;
}
