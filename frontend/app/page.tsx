import { redirect } from "next/navigation";

// Without sessions yet, every visit starts at sign-in.
export default function Home() {
  redirect("/login");
}
