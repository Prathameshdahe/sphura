import { useId, useState, type ReactNode } from "react";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface FieldProps {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  autoComplete?: string;
  autoFocus?: boolean;
  hint?: ReactNode;
}

export function Field({ label, type = "text", value, onChange, error, autoComplete, autoFocus, hint }: FieldProps) {
  const id = useId();
  const [reveal, setReveal] = useState(false);
  const isPassword = type === "password";
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={isPassword && reveal ? "text" : type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          aria-invalid={!!error || undefined}
          aria-describedby={error ? `${id}-err` : undefined}
          className={cn("h-10 bg-card", isPassword && "pr-10")}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setReveal((v) => !v)}
            aria-label={reveal ? "Hide password" : "Show password"}
            className="absolute top-1/2 right-2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:text-foreground"
          >
            {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
      </div>
      {error ? (
        <p id={`${id}-err`} className="text-xs text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      {message}
    </div>
  );
}

export function SubmitButton({ loading, children }: { loading: boolean; children: ReactNode }) {
  return (
    <Button type="submit" size="lg" className="h-10 w-full text-sm" disabled={loading}>
      {loading && <LoaderCircle className="animate-spin" />}
      {children}
    </Button>
  );
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
