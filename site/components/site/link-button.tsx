import { ArrowUpRight } from "@phosphor-icons/react/dist/ssr";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LINKS, type LinkKey } from "@/lib/links";

type Props = {
  to: LinkKey;
  children: React.ReactNode;
  icon?: React.ReactNode;
  variant?: "default" | "outline";
};

// A button for a link that may not be final yet: empty links show as unavailable instead of pointing nowhere.
export function LinkButton({ to, children, icon, variant = "default" }: Props) {
  const href = LINKS[to];
  if (!href) {
    return (
      <Button variant={variant} aria-disabled="true" className="!opacity-100" asChild>
        <span>
          <span className="inline-flex items-center gap-2 opacity-60">
            {icon}
            {children}
          </span>
          <Badge variant="outline" className={variant === "default" ? "border-background/50 text-background" : "border-foreground/40 text-foreground"}>Soon</Badge>
        </span>
      </Button>
    );
  }
  return (
    <Button variant={variant} asChild>
      <a href={href}>
        {icon}
        {children}
      </a>
    </Button>
  );
}

// A full-width row for the closing section.
export function LinkRow({ to, children, icon }: { to: LinkKey; children: React.ReactNode; icon: React.ReactNode }) {
  const href = LINKS[to];
  const dim = href ? "" : "opacity-60";
  const inner = (
    <>
      <span className={`text-2xl text-primary ${dim}`}>{icon}</span>
      <span className={`text-lg font-semibold ${dim}`}>{children}</span>
      <span className="ml-auto inline-flex items-center gap-2 text-sm text-muted-foreground">
        {!href && <Badge variant="outline" className="border-foreground/40 text-foreground">Soon</Badge>}
        <ArrowUpRight size={20} aria-hidden className={dim} />
      </span>
    </>
  );
  const base = "flex items-center gap-4 border-b border-border py-5 transition-all first:border-t";
  if (!href) return <div aria-disabled="true" className={base}>{inner}</div>;
  return (
    <a href={href} className={`${base} hover:pl-3 hover:text-primary focus-visible:rounded-lg focus-visible:ring-2 focus-visible:ring-ring`}>
      {inner}
    </a>
  );
}
