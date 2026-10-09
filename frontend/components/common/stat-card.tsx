import { Card, CardContent } from "@/components/ui/card";

type StatCardProps = {
  label: string;
  value: React.ReactNode;
  /** Small line under the value; or pass children for richer content (e.g. a progress bar). */
  detail?: string;
  children?: React.ReactNode;
};

export function StatCard({ label, value, detail, children }: StatCardProps) {
  return (
    <Card>
      <CardContent>
        <p className="text-control font-medium text-muted-foreground">{label}</p>
        <p className="mt-1.5 text-3xl leading-tight font-semibold tracking-[-0.03em]">
          {value}
        </p>
        {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
        {children}
      </CardContent>
    </Card>
  );
}
