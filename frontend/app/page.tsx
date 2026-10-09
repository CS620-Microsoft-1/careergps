// Temporary design-system preview for checking the ported prototype theme.
// Replaced by a redirect to /login once the real routes land (migration Step 3).
import { ChevronRight, LogOut, Sparkles, Target, User } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const SWATCHES = [
  ["background", "bg-background"],
  ["card", "bg-card"],
  ["primary", "bg-primary"],
  ["brand-dark", "bg-brand-dark"],
  ["deep", "bg-deep"],
  ["accent", "bg-accent"],
  ["line-soft", "bg-line-soft"],
  ["border", "bg-border"],
  ["foreground", "bg-foreground"],
  ["ink-2", "bg-ink-2"],
  ["muted-fg", "bg-muted-foreground"],
  ["success", "bg-success"],
  ["warning", "bg-warning"],
  ["warning-fill", "bg-warning-fill"],
  ["danger", "bg-danger"],
] as const;

export default function DesignPreview() {
  return (
    <main className="mx-auto grid max-w-[1160px] gap-6 px-4 py-8 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-3 flex items-center gap-2.5 text-lg font-bold tracking-[-0.01em]">
            <span className="grid size-8 place-items-center rounded-[9px] bg-primary text-primary-foreground">
              <Target className="size-[18px]" />
            </span>
            CareerGPS
          </div>
          <h1 className="text-[26px] tracking-[-0.02em]">Design system preview</h1>
          <p className="mt-1 text-muted-foreground">
            Prototype theme ported to Tailwind + shadcn/ui. Temporary page.
          </p>
        </div>
        <div className="flex items-center gap-2.5 rounded-lg border bg-card py-1.5 pr-1.5 pl-3 text-[13px]">
          <Target className="size-4" />
          <b className="font-semibold">AI Engineer · New Grad 2027</b>
          <Button size="sm" variant="secondary" className="bg-background">
            Change
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Colors</CardTitle>
          <CardDescription>Tokens from the prototype stylesheet</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {SWATCHES.map(([name, cls]) => (
            <div key={name} className="grid gap-1.5 text-xs text-muted-foreground">
              <div className={`h-12 rounded-lg border ${cls}`} />
              {name}
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {["Career readiness", "Jobs analyzed", "High-priority gaps", "Plan progress"].map(
          (label) => (
            <Card key={label}>
              <CardContent>
                <div className="text-[13px] font-medium text-muted-foreground">{label}</div>
                <div className="mt-1.5 text-3xl leading-tight font-semibold tracking-[-0.03em]">
                  —
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Available after your first analysis
                </div>
              </CardContent>
            </Card>
          ),
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 rounded-xl bg-deep px-5 py-[18px] text-deep-foreground">
        <span className="grid size-9 place-items-center rounded-lg bg-white/12">
          <Sparkles className="size-[18px]" />
        </span>
        <div className="flex-1">
          <small className="text-xs text-deep-muted">Recommended next step</small>
          <b className="block text-[15px] font-semibold">Deep surface (banner, auth panel, FAB)</b>
        </div>
        <Button variant="outline" className="border-0 text-foreground">
          View plan
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Buttons &amp; badges</CardTitle>
            <CardDescription>Default 36px, large 44px</CardDescription>
            <CardAction>
              <Button variant="link" className="h-auto p-0">
                View all <ChevronRight />
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex flex-wrap gap-2">
              <Button>Primary</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button size="lg">Large primary</Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Badge>Neutral</Badge>
              <Badge variant="brand">Brand</Badge>
              <Badge variant="success">Done</Badge>
              <Badge variant="warning">Medium</Badge>
              <Badge variant="danger">High</Badge>
            </div>
            <div className="grid gap-3.5">
              {[
                ["Technical skills", 78],
                ["Cloud / DevOps", 46],
              ].map(([label, value]) => (
                <div key={label}>
                  <div className="mb-1.5 flex justify-between text-[13px] text-ink-2">
                    <span>{label}</span>
                    <b className="font-semibold text-foreground">{value}%</b>
                  </div>
                  <Progress
                    value={Number(value)}
                    indicatorClassName={Number(value) < 60 ? "bg-warning-fill" : undefined}
                  />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Form controls</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="preview-email" className="text-[13px] font-semibold text-ink-2">
                Email
              </Label>
              <Input id="preview-email" type="email" placeholder="student@wisc.edu" />
            </div>
            <div className="grid gap-1.5">
              <Label className="text-[13px] font-semibold text-ink-2">Target role</Label>
              <Select defaultValue="ai">
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="swe">Software Engineer</SelectItem>
                  <SelectItem value="da">Data Analyst</SelectItem>
                  <SelectItem value="ai">AI Engineer</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <RadioGroup defaultValue="ft" className="flex gap-4">
              <Label className="font-normal">
                <RadioGroupItem value="intern" /> Internship
              </Label>
              <Label className="font-normal">
                <RadioGroupItem value="ft" /> Full-time
              </Label>
            </RadioGroup>
            <Label className="font-normal text-ink-2">
              <Checkbox defaultChecked /> Remember me
            </Label>
          </CardContent>
        </Card>
      </div>

      <div>
        <Tabs defaultValue="projects">
          <TabsList>
            <TabsTrigger value="projects">Projects</TabsTrigger>
            <TabsTrigger value="courses">Courses</TabsTrigger>
            <TabsTrigger value="clubs">Clubs</TabsTrigger>
          </TabsList>
          <TabsContent value="projects" className="pt-4 text-muted-foreground">
            Underline tabs, as on the Resources page.
          </TabsContent>
          <TabsContent value="courses" className="pt-4 text-muted-foreground">
            Courses tab.
          </TabsContent>
          <TabsContent value="clubs" className="pt-4 text-muted-foreground">
            Clubs tab.
          </TabsContent>
        </Tabs>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Avatar>
          <AvatarFallback>AJ</AvatarFallback>
        </Avatar>
        <Avatar size="lg">
          <AvatarFallback>AJ</AvatarFallback>
        </Avatar>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline">User menu</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem>
              <User /> My Profile
            </DropdownMenuItem>
            <DropdownMenuItem>
              <LogOut /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Sheet>
          <SheetTrigger asChild>
            <Button className="rounded-full bg-deep shadow-fab hover:bg-brand-dark">
              <Sparkles /> Ask CareerGPS
            </Button>
          </SheetTrigger>
          <SheetContent>
            <SheetHeader>
              <SheetTitle>CareerGPS Copilot</SheetTitle>
              <SheetDescription className="sr-only">Side panel preview</SheetDescription>
            </SheetHeader>
            <p className="p-5 text-muted-foreground">
              Side panels slide in from the right at 400px wide.
            </p>
          </SheetContent>
        </Sheet>
      </div>
    </main>
  );
}
