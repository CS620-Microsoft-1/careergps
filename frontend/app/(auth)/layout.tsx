// /login and /signup each render their own AuthShell, since the text under the card differs.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return children;
}
