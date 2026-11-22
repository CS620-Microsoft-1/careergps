import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountDeletedNotice } from "@/components/auth/account-deleted-notice";

let search = "";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search) }));

describe("AccountDeletedNotice", () => {
  it("confirms the deletion on /login?deleted=1", () => {
    search = "deleted=1";
    render(<AccountDeletedNotice />);
    expect(screen.getByRole("status")).toHaveTextContent("Your account has been deleted.");
  });

  it("shows nothing otherwise", () => {
    for (const value of ["", "deleted=0", "deleted=true", "next=%2Fprofile"]) {
      search = value;
      const { unmount } = render(<AccountDeletedNotice />);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
      unmount();
    }
  });
});
