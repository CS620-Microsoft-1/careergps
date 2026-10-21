"use client";

import { Plus, RotateCcw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type {
  ResumeAnalysis,
  ResumeClassification,
  ResumeRecord,
} from "@/types/api";

type ResumeReviewProps = {
  result: ResumeAnalysis;
  classification: ResumeClassification;
  onChange: (classification: ResumeClassification) => void;
  onStartOver: () => void;
  onConfirm: () => void;
  /** True while the confirmed result is being saved. */
  confirming?: boolean;
  /** Why saving failed, shown above the buttons. */
  confirmError?: string;
  /** The student's university, pre-filled from the résumé; they confirm or change it here. */
  university: string;
  onUniversityChange: (university: string) => void;
};

type StringListKey = "research_interests" | "technical_skills";
type ObjectListKey = Exclude<keyof ResumeClassification, "personal_information" | StringListKey>;
type FieldDefinition = {
  key: string;
  label: string;
  type?: "text" | "lines" | "list" | "month";
  itemLabel?: string;
  allowPresent?: boolean;
};

const PERSONAL_FIELDS: FieldDefinition[] = [
  { key: "name", label: "Name" },
  { key: "emails", label: "Emails", type: "list", itemLabel: "email" },
  { key: "phones", label: "Phones", type: "list", itemLabel: "phone" },
  { key: "location", label: "Location" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "github", label: "GitHub" },
  { key: "website", label: "Website" },
];

const STRING_SECTIONS: Record<StringListKey, string> = {
  research_interests: "Research Interests",
  technical_skills: "Technical Skills",
};

const OBJECT_SECTIONS: Record<
  ObjectListKey,
  { label: string; itemLabel: string; fields: FieldDefinition[] }
> = {
  education: {
    label: "Education",
    itemLabel: "education record",
    fields: [
      { key: "institution", label: "Institution" },
      { key: "degree", label: "Degree" },
      { key: "major", label: "Major" },
      { key: "start_date", label: "Start date", type: "month" },
      { key: "end_date", label: "End date", type: "month" },
      { key: "gpa", label: "GPA" },
      { key: "content", label: "Coursework and additional details", type: "lines" },
    ],
  },
  work_experience: {
    label: "Work Experience",
    itemLabel: "work entry",
    fields: [
      { key: "company", label: "Company" },
      { key: "title", label: "Title" },
      { key: "start_date", label: "Start date", type: "month" },
      { key: "end_date", label: "End date", type: "month", allowPresent: true },
      { key: "location", label: "Location" },
      { key: "content", label: "Responsibilities and achievements", type: "lines" },
    ],
  },
  research_experience: {
    label: "Research Experience",
    itemLabel: "research entry",
    fields: [
      { key: "organization", label: "Organization or laboratory" },
      { key: "title", label: "Title" },
      { key: "start_date", label: "Start date", type: "month" },
      { key: "end_date", label: "End date", type: "month", allowPresent: true },
      { key: "location", label: "Location" },
      { key: "content", label: "Research contributions", type: "lines" },
    ],
  },
  projects: {
    label: "Projects",
    itemLabel: "project",
    fields: [
      { key: "name", label: "Project name" },
      { key: "url", label: "Project URL" },
      { key: "technologies", label: "Technologies", type: "lines" },
      { key: "content", label: "Project details", type: "lines" },
    ],
  },
  languages: {
    label: "Languages",
    itemLabel: "language",
    fields: [
      { key: "name", label: "Language" },
      { key: "proficiency", label: "Proficiency" },
    ],
  },
  publications: {
    label: "Publications",
    itemLabel: "publication",
    fields: [
      { key: "title", label: "Title" },
      { key: "authors", label: "Authors" },
      { key: "venue", label: "Venue" },
      { key: "date", label: "Date" },
      { key: "url", label: "Publication URL" },
      { key: "content", label: "Additional details", type: "lines" },
    ],
  },
  awards_honors: {
    label: "Awards and Honors",
    itemLabel: "award or honor",
    fields: [
      { key: "name", label: "Name" },
      { key: "issuer", label: "Issuer" },
      { key: "date", label: "Date" },
      { key: "content", label: "Additional details", type: "lines" },
    ],
  },
  certifications: {
    label: "Certifications",
    itemLabel: "certification",
    fields: [
      { key: "name", label: "Certification name" },
      { key: "issuer", label: "Issuer" },
      { key: "date", label: "Date" },
      { key: "url", label: "Credential URL" },
      { key: "content", label: "Additional details", type: "lines" },
    ],
  },
  leadership_activities: {
    label: "Leadership and Activities",
    itemLabel: "activity",
    fields: [
      { key: "organization", label: "Organization" },
      { key: "role", label: "Role" },
      { key: "start_date", label: "Start date", type: "month" },
      { key: "end_date", label: "End date", type: "month", allowPresent: true },
      { key: "location", label: "Location" },
      { key: "content", label: "Activity details", type: "lines" },
    ],
  },
  other: {
    label: "Other",
    itemLabel: "other item",
    fields: [{ key: "content", label: "Content" }],
  },
};

const SECTION_ORDER: Array<StringListKey | ObjectListKey> = [
  "research_interests",
  "education",
  "work_experience",
  "research_experience",
  "projects",
  "technical_skills",
  "languages",
  "publications",
  "awards_honors",
  "certifications",
  "leadership_activities",
  "other",
];

function lines(value: string) {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

function formatUsPhone(value: string) {
  const digits = value.replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "").slice(0, 10);
  if (digits.length <= 3) return digits ? `(${digits}` : "";
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function blankRecord(section: ObjectListKey): ResumeRecord {
  return Object.fromEntries(
    // other.content is a required string in the contract (app/schemas/resume.py), not nullable.
    OBJECT_SECTIONS[section].fields.map((field) => [
      field.key,
      field.type === "lines" ? [] : section === "other" ? "" : null,
    ]),
  );
}

function isStringSection(section: StringListKey | ObjectListKey): section is StringListKey {
  return section === "research_interests" || section === "technical_skills";
}

export function ResumeReview({
  result,
  classification,
  onChange,
  onStartOver,
  onConfirm,
  confirming = false,
  confirmError,
  university,
  onUniversityChange,
}: ResumeReviewProps) {
  const updatePersonal = (field: string, value: string | string[]) => {
    onChange({
      ...classification,
      personal_information: { ...classification.personal_information, [field]: value },
    });
  };

  const updateStringItem = (section: StringListKey, index: number, value: string) => {
    const next = classification[section].map((item, itemIndex) =>
      itemIndex === index ? value : item,
    );
    onChange({ ...classification, [section]: next });
  };

  const addStringItem = (section: StringListKey) => {
    onChange({ ...classification, [section]: [...classification[section], ""] });
  };

  const removeStringItem = (section: StringListKey, index: number) => {
    onChange({
      ...classification,
      [section]: classification[section].filter((_, itemIndex) => itemIndex !== index),
    });
  };

  const updateRecord = (
    section: ObjectListKey,
    index: number,
    field: string,
    value: string | string[],
  ) => {
    const next = classification[section].map((item, itemIndex) =>
      itemIndex === index ? { ...item, [field]: value } : item,
    );
    onChange({ ...classification, [section]: next });
  };

  const addRecord = (section: ObjectListKey) => {
    onChange({
      ...classification,
      [section]: [...classification[section], blankRecord(section)],
    });
  };

  const removeRecord = (section: ObjectListKey, index: number) => {
    onChange({
      ...classification,
      [section]: classification[section].filter((_, itemIndex) => itemIndex !== index),
    });
  };

  const emptySections = SECTION_ORDER.filter((section) => classification[section].length === 0);

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-page-title tracking-[-0.02em]">Review the extracted résumé</h2>
        <p className="mt-1.5 text-muted-foreground">
          Check and edit the Agent&apos;s classification. Empty categories are hidden below. When you
          continue, the result is saved to your account and shown on your profile.
        </p>
      </div>

      <Field className="max-w-100">
        <FieldLabel htmlFor="university">University</FieldLabel>
        <Input
          id="university"
          value={university}
          onChange={(event) => onUniversityChange(event.target.value)}
          maxLength={150}
          autoComplete="organization"
          aria-describedby="university-hint"
        />
        <p id="university-hint" className="text-xs text-muted-foreground">
          From your résumé. Change it if this isn&apos;t the school you attend now.
        </p>
      </Field>

      <Card size="sm">
        <CardHeader>
          <CardTitle>{result.filename}</CardTitle>
          <CardDescription>
            {result.extraction.parser} · {result.extraction.characters.toLocaleString()} characters ·
            extraction {result.extraction.seconds.toFixed(4)}s · Agent {result.agent.seconds.toFixed(4)}s
            {result.extraction.ocr_pages.length > 0 &&
              ` · OCR page${result.extraction.ocr_pages.length === 1 ? "" : "s"} ${result.extraction.ocr_pages.join(", ")}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <details className="rounded-lg border border-border bg-background p-3">
            <summary className="cursor-pointer text-control font-semibold">
              View actual extracted text
            </summary>
            <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-ink-2">
              {result.extraction.text}
            </pre>
          </details>
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle>Personal Information</CardTitle>
          <CardDescription>Contact details explicitly found in the résumé</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {PERSONAL_FIELDS.map((field) => {
            const value = classification.personal_information[field.key];
            return field.type === "list" ? (
              <PersonalListField
                key={field.key}
                label={field.label}
                itemLabel={field.itemLabel ?? "item"}
                values={Array.isArray(value) ? value : []}
                onChange={(next) => updatePersonal(field.key, next)}
              />
            ) : field.type === "lines" ? (
              <TextAreaField
                key={field.key}
                label={field.label}
                value={Array.isArray(value) ? value.join("\n") : ""}
                onChange={(next) => updatePersonal(field.key, lines(next))}
              />
            ) : (
              <TextInputField
                key={field.key}
                label={field.label}
                value={typeof value === "string" ? value : ""}
                onChange={(next) => updatePersonal(field.key, next)}
              />
            );
          })}
        </CardContent>
      </Card>

      {SECTION_ORDER.map((section) => {
        const values = classification[section];
        if (values.length === 0) return null;
        return isStringSection(section) ? (
          <StringListSection
            key={section}
            label={STRING_SECTIONS[section]}
            values={classification[section]}
            onAdd={() => addStringItem(section)}
            onChange={(index, value) => updateStringItem(section, index, value)}
            onRemove={(index) => removeStringItem(section, index)}
          />
        ) : (
          <ObjectListSection
            key={section}
            definition={OBJECT_SECTIONS[section]}
            values={classification[section]}
            onAdd={() => addRecord(section)}
            onChange={(index, field, value) => updateRecord(section, index, field, value)}
            onRemove={(index) => removeRecord(section, index)}
          />
        );
      })}

      {emptySections.length > 0 && (
        <details className="rounded-xl border border-dashed border-border bg-card p-4">
          <summary className="cursor-pointer font-semibold">
            Add missing information ({emptySections.length} empty categories)
          </summary>
          <div className="mt-4 flex flex-wrap gap-2">
            {emptySections.map((section) => (
              <Button
                key={section}
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  isStringSection(section) ? addStringItem(section) : addRecord(section)
                }
              >
                <Plus data-icon="inline-start" />
                {isStringSection(section) ? STRING_SECTIONS[section] : OBJECT_SECTIONS[section].label}
              </Button>
            ))}
          </div>
        </details>
      )}

      {confirmError && (
        <p role="alert" className="text-control text-destructive">
          {confirmError}
        </p>
      )}
      <div className="grid gap-3 border-t border-border pt-5 sm:grid-cols-[auto_1fr]">
        <Button type="button" variant="outline" size="lg" onClick={onStartOver}>
          <RotateCcw data-icon="inline-start" /> Choose another résumé
        </Button>
        <Button type="button" size="lg" onClick={onConfirm} disabled={confirming}>
          {confirming ? "Saving…" : "Looks right, continue"}
        </Button>
      </div>
    </div>
  );
}

function StringListSection({
  label,
  values,
  onAdd,
  onChange,
  onRemove,
}: {
  label: string;
  values: string[];
  onAdd: () => void;
  onChange: (index: number, value: string) => void;
  onRemove: (index: number) => void;
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardDescription>{values.length} identified</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {values.map((value, index) => (
          <div key={index} className="flex gap-2">
            <Input
              value={value}
              aria-label={`${label} item ${index + 1}`}
              onChange={(event) => onChange(index, event.target.value)}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Remove ${label} item ${index + 1}`}
              onClick={() => onRemove(index)}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={onAdd}>
          <Plus data-icon="inline-start" /> Add item
        </Button>
      </CardContent>
    </Card>
  );
}

function ObjectListSection({
  definition,
  values,
  onAdd,
  onChange,
  onRemove,
}: {
  definition: { label: string; itemLabel: string; fields: FieldDefinition[] };
  values: ResumeRecord[];
  onAdd: () => void;
  onChange: (index: number, field: string, value: string | string[]) => void;
  onRemove: (index: number) => void;
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{definition.label}</CardTitle>
        <CardDescription>{values.length} identified</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {values.map((record, index) => (
          <div key={index} className="relative grid gap-4 rounded-lg border border-border p-4 pr-12 sm:grid-cols-2">
            {definition.fields.map((field) => {
              const value = record[field.key];
              return field.type === "month" ? (
                <MonthInputField
                  key={field.key}
                  label={field.label}
                  value={typeof value === "string" ? value : ""}
                  allowPresent={field.allowPresent}
                  onChange={(next) => onChange(index, field.key, next)}
                />
              ) : field.type === "lines" ? (
                <TextAreaField
                  key={field.key}
                  label={field.label}
                  value={Array.isArray(value) ? value.join("\n") : ""}
                  onChange={(next) => onChange(index, field.key, lines(next))}
                />
              ) : (
                <TextInputField
                  key={field.key}
                  label={field.label}
                  value={typeof value === "string" ? value : ""}
                  onChange={(next) => onChange(index, field.key, next)}
                />
              );
            })}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Remove ${definition.itemLabel} ${index + 1}`}
              onClick={() => onRemove(index)}
              className="absolute top-3 right-3"
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={onAdd}>
          <Plus data-icon="inline-start" /> Add {definition.itemLabel}
        </Button>
      </CardContent>
    </Card>
  );
}

function TextInputField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field>
      <FieldLabel>{label}</FieldLabel>
      <Input value={value} onChange={(event) => onChange(event.target.value)} />
    </Field>
  );
}

function PersonalListField({
  label,
  itemLabel,
  values,
  onChange,
}: {
  label: string;
  itemLabel: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <Field>
      <FieldLabel>{label}</FieldLabel>
      <div className="grid gap-2">
        {values.map((value, index) => (
          <div key={index} className="flex gap-2">
            <Input
              value={itemLabel === "phone" ? formatUsPhone(value) : value}
              type={itemLabel === "phone" ? "tel" : itemLabel === "email" ? "email" : "text"}
              inputMode={itemLabel === "phone" ? "numeric" : undefined}
              placeholder={itemLabel === "phone" ? "(###) ###-####" : undefined}
              aria-label={`${label} ${index + 1}`}
              onChange={(event) =>
                onChange(values.map((item, itemIndex) =>
                  itemIndex === index
                    ? itemLabel === "phone"
                      ? formatUsPhone(event.target.value)
                      : event.target.value
                    : item,
                ))
              }
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Remove ${itemLabel} ${index + 1}`}
              onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="justify-self-start"
          onClick={() => onChange([...values, ""])}
        >
          <Plus data-icon="inline-start" /> Add {itemLabel}
        </Button>
      </div>
    </Field>
  );
}

function MonthInputField({
  label,
  value,
  allowPresent = false,
  onChange,
}: {
  label: string;
  value: string;
  allowPresent?: boolean;
  onChange: (value: string) => void;
}) {
  const isPresent = value === "Present";
  const isYearOnly = /^\d{4}$/.test(value);
  const monthValue = /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? value : "";

  return (
    <Field>
      <FieldLabel>{label}</FieldLabel>
      <div className="flex gap-2">
        {isYearOnly ? (
          <Input
            type="number"
            min="1900"
            max="2100"
            value={value}
            aria-label={`${label} year`}
            onChange={(event) => onChange(event.target.value)}
          />
        ) : (
          <Input
            type="month"
            value={monthValue}
            disabled={isPresent}
            aria-label={`${label} month and year`}
            onChange={(event) => onChange(event.target.value)}
          />
        )}
        {allowPresent && (
          <Button
            type="button"
            variant={isPresent ? "secondary" : "outline"}
            onClick={() => onChange(isPresent ? "" : "Present")}
          >
            Present
          </Button>
        )}
      </div>
    </Field>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field className="sm:col-span-2">
      <FieldLabel>{label} (one per line)</FieldLabel>
      <textarea
        value={value}
        rows={Math.max(3, value.split("\n").length + 1)}
        onChange={(event) => onChange(event.target.value)}
        className="w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-sm outline-none focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-accent"
      />
    </Field>
  );
}
