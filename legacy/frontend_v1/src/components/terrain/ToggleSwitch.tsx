import { useState } from "react";

interface ToggleSwitchProps {
  label: string;
  description?: string;
  defaultChecked?: boolean;
  colorDot?: string;
  checked?: boolean;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
}

export function ToggleSwitch({
  label,
  description,
  defaultChecked = false,
  colorDot,
  checked,
  onChange,
  disabled,
}: ToggleSwitchProps) {
  const [internal, setInternal] = useState(defaultChecked);
  const isControlled = checked !== undefined;
  const on = isControlled ? checked : internal;

  const handleClick = () => {
    if (disabled) return;
    if (isControlled) onChange?.(!on);
    else {
      setInternal(!on);
      onChange?.(!on);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className={`group flex w-full items-center justify-between gap-3 rounded-lg border border-transparent bg-secondary/40 px-3 py-2.5 text-left transition-all ${
        disabled
          ? "cursor-not-allowed opacity-50"
          : "hover:border-primary/30 hover:bg-secondary/70"
      }`}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        {colorDot && (
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-background/40"
            style={{ background: colorDot }}
          />
        )}
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-foreground">{label}</div>
          {description && (
            <div className="truncate text-[11px] text-muted-foreground">{description}</div>
          )}
        </div>
      </div>

      <span
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-300 ${
          on ? "bg-primary ring-glow" : "bg-input"
        }`}
        aria-hidden
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-background shadow transition-transform duration-300 ${
            on ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </span>
    </button>
  );
}
