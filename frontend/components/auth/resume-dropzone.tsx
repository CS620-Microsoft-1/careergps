"use client";

import { useState } from "react";
import { CheckCircle2, Upload } from "lucide-react";

import { RESUME_ACCEPT } from "@/lib/options";
import { cn } from "@/lib/utils";

type ResumeDropzoneProps = {
  id: string;
  value: File | undefined;
  onChange: (file: File | undefined) => void;
  onBlur: () => void;
  invalid?: boolean;
};

/** Click or drop a résumé. Only keeps the File in form state; nothing is uploaded. */
export function ResumeDropzone({ id, value, onChange, onBlur, invalid }: ResumeDropzoneProps) {
  const [dragging, setDragging] = useState(false);

  return (
    <label
      htmlFor={id}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        onChange(e.dataTransfer.files[0]);
      }}
      className={cn(
        "grid cursor-pointer justify-items-center gap-0.5 rounded-xl border-[1.5px] border-dashed border-[#c7d6d2] bg-[#fbfcfc] px-4 py-5.5 text-center text-xs text-muted-foreground transition-colors hover:border-primary has-focus-visible:border-primary has-focus-visible:ring-3 has-focus-visible:ring-accent",
        dragging && "border-primary bg-accent",
        value && "border-solid border-success bg-success-soft",
        invalid && !value && "border-destructive",
      )}
    >
      {value ? (
        <CheckCircle2 aria-hidden className="mb-1 size-5 text-success" />
      ) : (
        <Upload aria-hidden className="mb-1 size-5 text-primary" />
      )}
      <b className="max-w-full truncate text-sm font-semibold text-foreground">
        {value ? value.name : "Upload your résumé"}
      </b>
      {value ? "Click to replace" : "PDF or DOCX, up to 10 MB"}
      <input
        id={id}
        type="file"
        accept={RESUME_ACCEPT}
        aria-invalid={invalid}
        className="sr-only"
        onBlur={onBlur}
        onChange={(e) => onChange(e.target.files?.[0])}
      />
    </label>
  );
}
