import { ComingSoon } from "@/components/common/coming-soon";
import { GoogleIcon, MicrosoftIcon, UwBadge } from "@/components/common/provider-icons";
import { Button } from "@/components/ui/button";

// Single sign-on is not implemented yet; buttons keep the prototype layout.
export function SsoButtons() {
  return (
    <div className="grid grid-cols-1 gap-2 min-[22rem]:grid-cols-2">
      <ComingSoon>
        <Button type="button" variant="outline" size="lg" disabled className="w-full">
          <GoogleIcon className="size-5" />
          Google
        </Button>
      </ComingSoon>
      <ComingSoon>
        <Button type="button" variant="outline" size="lg" disabled className="w-full">
          <MicrosoftIcon className="size-5" />
          Microsoft
        </Button>
      </ComingSoon>
      <ComingSoon className="min-[22rem]:col-span-2">
        <Button type="button" variant="outline" size="lg" disabled className="w-full">
          <UwBadge />
          Continue with UW–Madison
        </Button>
      </ComingSoon>
    </div>
  );
}
