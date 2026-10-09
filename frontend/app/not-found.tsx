import Link from "next/link";

import { Logo } from "@/components/common/logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="grid max-w-100 justify-items-center gap-4 text-center">
        <Logo />
        <h1 className="text-page-title tracking-[-0.02em]">Page not found</h1>
        <p className="text-muted-foreground">
          The page you&apos;re looking for doesn&apos;t exist or has moved.
        </p>
        <Button asChild size="lg">
          <Link href="/dashboard">Go to dashboard</Link>
        </Button>
      </div>
    </main>
  );
}
