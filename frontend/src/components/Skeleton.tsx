import { useI18n } from "../lib/i18n";

// Loading placeholder: shows the shape of the coming content without faking values (Grundregel 6).
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function CardSkeleton() {
  const { t } = useI18n();
  return (
    <div className="card space-y-3" role="status" aria-label={t("common.loadingContent")}>
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}
