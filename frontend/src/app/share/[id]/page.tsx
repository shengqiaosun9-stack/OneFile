import { redirect } from "next/navigation";

export default async function LegacyShareRedirectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/card/${id}`);
}
