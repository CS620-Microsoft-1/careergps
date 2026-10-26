import { redirect } from "next/navigation";

// proxy.ts sends / to /dashboard or /login first; this is only a fallback.
export default function Home() {
  redirect("/login");
}
