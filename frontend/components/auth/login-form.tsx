"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ComingSoon } from "@/components/common/coming-soon";
import { TextField } from "@/components/common/form-fields";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { loginSchema, type LoginValues } from "@/lib/validation/auth";

export function LoginForm() {
  const router = useRouter();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  // No backend yet: a valid form simply continues into the app.
  const onSubmit = () => router.push("/dashboard");

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)}>
      <FieldGroup>
        <TextField
          control={form.control}
          name="email"
          label="Email"
          type="email"
          placeholder="student@wisc.edu"
          autoComplete="email"
        />
        <TextField
          control={form.control}
          name="password"
          label="Password"
          type="password"
          placeholder="Enter your password"
          autoComplete="current-password"
        />
        <div className="flex justify-end">
          <ComingSoon>
            <Button type="button" variant="link" disabled className="h-auto p-0">
              Forgot password?
            </Button>
          </ComingSoon>
        </div>
        <Button type="submit" size="lg" className="w-full">
          Sign In
        </Button>
      </FieldGroup>
      <p className="mt-6 text-center text-control text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="font-semibold text-primary hover:underline">
          Create Account
        </Link>
      </p>
    </form>
  );
}
