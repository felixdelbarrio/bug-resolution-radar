import type { CorporateBrandContract } from "../lib/api";
import { cn } from "../lib/cn";

export function CorporateLockup({
  brand,
  className
}: {
  brand?: CorporateBrandContract;
  className?: string;
}) {
  if (!brand?.wordmark || brand.descriptorLines.length === 0) return null;
  return (
    <div className={cn("corporate-lockup", className)} aria-label={brand.name}>
      <strong>{brand.wordmark}</strong>
      <span>
        {brand.descriptorLines.map((line, index) => (
          <span key={line}>
            {line}
            {index < brand.descriptorLines.length - 1 ? <br /> : null}
          </span>
        ))}
      </span>
    </div>
  );
}
