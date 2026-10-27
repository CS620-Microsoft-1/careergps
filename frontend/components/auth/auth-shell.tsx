import { cn } from "@/lib/utils";

type AuthShellProps = {
  children: React.ReactNode;
  /** Below the card, e.g. "New to CareerGPS? Create an account". */
  footer?: React.ReactNode;
  className?: string;
};

/**
 * Log in, sign up and email confirmation: the wordmark over one centered card, with the route-map
 * shapes behind it on wide screens. The card column scrolls on short screens.
 */
export function AuthShell({ children, footer, className }: AuthShellProps) {
  return (
    <div className="relative min-h-dvh overflow-hidden">
      <Shapes />
      <main className="relative mx-auto grid min-h-dvh w-full max-w-105 content-center px-4 py-12">
        <div className="mb-7 text-center">
          <p className="text-display font-extrabold tracking-[-0.02em]">CareerGPS</p>
          <p className="mt-2 text-lg text-muted-foreground">Where you are, where you’re going, and your next turn.</p>
        </div>
        <div className={cn("rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8", className)}>{children}</div>
        {footer && <div className="mt-8 text-center">{footer}</div>}
      </main>
    </div>
  );
}

export function AuthHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6 text-center">
      <h1 className="text-[1.75rem]/9">{title}</h1>
      {subtitle && <p className="mt-2 text-muted-foreground">{subtitle}</p>}
    </div>
  );
}

/** Decorative: a stop-dotted route, a destination pin and color blocks. Hidden below lg. */
function Shapes() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 hidden lg:block">
      <div className="absolute -top-6 left-[5%] h-[28rem] w-[21rem] rounded-b-[2rem] bg-deep">
        <div className="absolute top-8 left-20 grid gap-6">
          {Array.from({ length: 6 }, (_, i) => <span key={i} className="size-5 rounded-full bg-background" />)}
        </div>
        <div className="absolute bottom-28 left-32 flex gap-6">
          {Array.from({ length: 4 }, (_, i) => <span key={i} className="size-5 rounded-full bg-background" />)}
        </div>
      </div>
      <div className="absolute top-[32rem] left-[10%] grid size-56 place-items-center rounded-full bg-accent">
        <span className="size-11 rounded-full bg-deep" />
      </div>
      <div className="absolute top-24 right-[15%] h-44 w-56 rounded-[2rem] bg-tint-blue" />
      <div className="absolute top-80 -right-8 h-[32rem] w-80 rounded-[2rem] bg-tint-mint" />
    </div>
  );
}
