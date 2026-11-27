// /login, /signup and /forgot-password each render their own AuthShell, since the text under the card differs.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return children;
}
