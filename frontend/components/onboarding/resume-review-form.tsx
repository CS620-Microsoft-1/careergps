"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, X } from "lucide-react";
import { Controller, useFieldArray, useForm, type Control } from "react-hook-form";
import { z } from "zod";

import { TextField } from "@/components/common/form-fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/client";
import { confirmResume } from "@/lib/api/resumes";
import type { Resume, ResumeData, SkillCategory } from "@/types/api";

// Mirrors backend/app/schemas/resume.py (ResumeConfirm); the backend re-checks everything.
const date = z
  .string()
  .trim()
  .regex(/^(\d{4}(-(0[1-9]|1[0-2]))?)?$/, "Use YYYY or YYYY-MM.");
const optional = (max: number) => z.string().trim().max(max);
const required = (max: number, message: string) => z.string().trim().min(1, message).max(max);

const formSchema = z.object({
  contact: z.object({
    full_name: optional(100),
    email: optional(255),
    phone: optional(50),
    location: optional(100),
    links: z.string(), // one per line
  }),
  education: z.array(
    z.object({
      school: required(200, "Enter the school."),
      degree: optional(200),
      field_of_study: optional(200),
      start_date: date,
      end_date: date,
      gpa: optional(20),
    }),
  ),
  experience: z.array(
    z.object({
      company: required(200, "Enter the company."),
      title: optional(200),
      location: optional(200),
      start_date: date,
      end_date: date,
      is_current: z.boolean(),
      bullets: z.string(), // one per line
    }),
  ),
  projects: z.array(
    z.object({
      name: required(200, "Enter the project name."),
      description: optional(2000),
      url: optional(500),
      technologies: z.string(), // comma-separated
    }),
  ),
  skills: z.array(z.object({ name: z.string(), category: z.string() })),
});
type FormValues = z.infer<typeof formSchema>;

const lines = (text: string) => text.split("\n").map((s) => s.trim()).filter(Boolean);
const commaList = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);
const orNull = (text: string) => text.trim() || null;

function toForm(data: ResumeData): FormValues {
  return {
    contact: {
      full_name: data.contact.full_name ?? "",
      email: data.contact.email ?? "",
      phone: data.contact.phone ?? "",
      location: data.contact.location ?? "",
      links: data.contact.links.join("\n"),
    },
    education: data.education.map((e) => ({
      school: e.school,
      degree: e.degree ?? "",
      field_of_study: e.field_of_study ?? "",
      start_date: e.start_date ?? "",
      end_date: e.end_date ?? "",
      gpa: e.gpa ?? "",
    })),
    experience: data.experience.map((e) => ({
      company: e.company,
      title: e.title ?? "",
      location: e.location ?? "",
      start_date: e.start_date ?? "",
      end_date: e.end_date ?? "",
      is_current: e.is_current,
      bullets: e.bullets.join("\n"),
    })),
    projects: data.projects.map((p) => ({
      name: p.name,
      description: p.description ?? "",
      url: p.url ?? "",
      technologies: p.technologies.join(", "),
    })),
    skills: data.skills,
  };
}

function fromForm(values: FormValues): ResumeData {
  return {
    contact: {
      full_name: orNull(values.contact.full_name),
      email: orNull(values.contact.email),
      phone: orNull(values.contact.phone),
      location: orNull(values.contact.location),
      links: lines(values.contact.links),
    },
    education: values.education.map((e) => ({
      school: e.school.trim(),
      degree: orNull(e.degree),
      field_of_study: orNull(e.field_of_study),
      start_date: orNull(e.start_date),
      end_date: orNull(e.end_date),
      gpa: orNull(e.gpa),
    })),
    experience: values.experience.map((e) => ({
      company: e.company.trim(),
      title: orNull(e.title),
      location: orNull(e.location),
      start_date: orNull(e.start_date),
      end_date: e.is_current ? null : orNull(e.end_date),
      is_current: e.is_current,
      bullets: lines(e.bullets),
    })),
    projects: values.projects.map((p) => ({
      name: p.name.trim(),
      description: orNull(p.description),
      url: orNull(p.url),
      technologies: commaList(p.technologies),
    })),
    skills: values.skills.map((s) => ({ name: s.name, category: s.category as SkillCategory })),
  };
}

type ReviewFormProps = { resume: Resume; onConfirmed: () => void };

/** "Here is what we identified": the parsed résumé, editable, saved only on confirm. */
export function ResumeReviewForm({ resume, onConfirmed }: ReviewFormProps) {
  const [submitError, setSubmitError] = useState<string>();
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: toForm(resume.parsed_data!),
  });
  const { control } = form;
  const education = useFieldArray({ control, name: "education" });
  const experience = useFieldArray({ control, name: "experience" });
  const projects = useFieldArray({ control, name: "projects" });

  const onSubmit = async (values: FormValues) => {
    setSubmitError(undefined);
    try {
      await confirmResume(resume.id, fromForm(values));
      onConfirmed();
    } catch (error) {
      setSubmitError(errorMessage(error));
    }
  };

  return (
    <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="grid gap-8">
      <div>
        <h1 className="text-page-title tracking-[-0.02em]">Here is what we identified</h1>
        <p className="mt-1.5 text-muted-foreground">
          From <span className="font-medium text-foreground">{resume.original_filename}</span>.
          Fix anything that&apos;s wrong. Nothing is saved until you confirm.
        </p>
      </div>

      <FieldSet>
        <FieldLegend>Contact</FieldLegend>
        <FieldGroup>
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField control={control} name="contact.full_name" label="Name" />
            <TextField control={control} name="contact.email" label="Email" type="email" />
            <TextField control={control} name="contact.phone" label="Phone" type="tel" />
            <TextField control={control} name="contact.location" label="Location" />
          </div>
          <TextArea control={control} name="contact.links" label="Links (one per line)" rows={2} />
        </FieldGroup>
      </FieldSet>

      <Section
        title="Education"
        addLabel="Add education"
        onAdd={() =>
          education.append({ school: "", degree: "", field_of_study: "", start_date: "", end_date: "", gpa: "" })
        }
      >
        {education.fields.map((item, i) => (
          <Item key={item.id} onRemove={() => education.remove(i)} label="Remove education">
            <TextField control={control} name={`education.${i}.school`} label="School" />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField control={control} name={`education.${i}.degree`} label="Degree" />
              <TextField control={control} name={`education.${i}.field_of_study`} label="Field of study" />
              <TextField control={control} name={`education.${i}.start_date`} label="Start (YYYY-MM)" />
              <TextField control={control} name={`education.${i}.end_date`} label="End (YYYY-MM)" />
              <TextField control={control} name={`education.${i}.gpa`} label="GPA" />
            </div>
          </Item>
        ))}
      </Section>

      <Section
        title="Experience"
        addLabel="Add experience"
        onAdd={() =>
          experience.append({
            company: "",
            title: "",
            location: "",
            start_date: "",
            end_date: "",
            is_current: false,
            bullets: "",
          })
        }
      >
        {experience.fields.map((item, i) => (
          <Item key={item.id} onRemove={() => experience.remove(i)} label="Remove experience">
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField control={control} name={`experience.${i}.company`} label="Company" />
              <TextField control={control} name={`experience.${i}.title`} label="Title" />
              <TextField control={control} name={`experience.${i}.location`} label="Location" />
              <TextField control={control} name={`experience.${i}.start_date`} label="Start (YYYY-MM)" />
              <TextField control={control} name={`experience.${i}.end_date`} label="End (YYYY-MM)" />
              <Controller
                control={control}
                name={`experience.${i}.is_current`}
                render={({ field }) => (
                  <label className="flex items-center gap-2 self-end pb-2.5 text-control">
                    <input
                      type="checkbox"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      className="size-4 accent-primary"
                    />
                    I currently work here
                  </label>
                )}
              />
            </div>
            <TextArea control={control} name={`experience.${i}.bullets`} label="What you did (one per line)" rows={4} />
          </Item>
        ))}
      </Section>

      <Section
        title="Projects"
        addLabel="Add project"
        onAdd={() => projects.append({ name: "", description: "", url: "", technologies: "" })}
      >
        {projects.fields.map((item, i) => (
          <Item key={item.id} onRemove={() => projects.remove(i)} label="Remove project">
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField control={control} name={`projects.${i}.name`} label="Name" />
              <TextField control={control} name={`projects.${i}.url`} label="Link" type="url" />
            </div>
            <TextArea control={control} name={`projects.${i}.description`} label="Description" rows={2} />
            <TextField control={control} name={`projects.${i}.technologies`} label="Technologies (comma-separated)" />
          </Item>
        ))}
      </Section>

      <Controller
        control={control}
        name="skills"
        render={({ field }) => <SkillsEditor value={field.value} onChange={field.onChange} />}
      />

      <div className="grid gap-3 border-t border-border pt-6">
        {submitError && (
          <p role="alert" className="text-control text-destructive">
            {submitError}
          </p>
        )}
        <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Saving…" : "Looks right, continue"}
        </Button>
      </div>
    </form>
  );
}

function Section({
  title,
  addLabel,
  onAdd,
  children,
}: {
  title: string;
  addLabel: string;
  onAdd: () => void;
  children: React.ReactNode;
}) {
  return (
    <FieldSet>
      <FieldLegend>{title}</FieldLegend>
      <div className="grid gap-3">
        {children}
        <Button type="button" variant="outline" size="sm" onClick={onAdd} className="justify-self-start">
          <Plus data-icon="inline-start" />
          {addLabel}
        </Button>
      </div>
    </FieldSet>
  );
}

function Item({
  label,
  onRemove,
  children,
}: {
  label: string;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="relative grid gap-4 rounded-xl border border-border p-4 pr-12">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={label}
        onClick={onRemove}
        className="absolute top-2 right-2"
      >
        <X />
      </Button>
      {children}
    </div>
  );
}

function TextArea({
  control,
  name,
  label,
  rows,
}: {
  control: Control<FormValues>;
  name: `contact.links` | `experience.${number}.bullets` | `projects.${number}.description`;
  label: string;
  rows: number;
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <textarea
            {...field}
            id={name}
            rows={rows}
            aria-invalid={fieldState.invalid}
            className="w-full rounded-lg border border-input bg-card px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-accent aria-invalid:border-destructive md:text-sm"
          />
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  );
}

type SkillValue = FormValues["skills"];

function SkillsEditor({ value, onChange }: { value: SkillValue; onChange: (skills: SkillValue) => void }) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const name = draft.trim();
    if (name && !value.some((s) => s.name.toLowerCase() === name.toLowerCase())) {
      onChange([...value, { name, category: "other" }]);
    }
    setDraft("");
  };

  return (
    <FieldSet>
      <FieldLegend>Skills</FieldLegend>
      <ul className="flex flex-wrap gap-2" aria-label="Skills">
        {value.map((skill) => (
          <li key={skill.name}>
            <Badge variant="brand" className="gap-1 pr-1">
              {skill.name}
              <button
                type="button"
                aria-label={`Remove ${skill.name}`}
                onClick={() => onChange(value.filter((s) => s.name !== skill.name))}
                className="rounded-full p-0.5 hover:bg-foreground/10"
              >
                <X className="size-3" />
              </button>
            </Badge>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Add a skill"
          aria-label="Add a skill"
          maxLength={100}
        />
        <Button type="button" variant="outline" onClick={add}>
          Add
        </Button>
      </div>
    </FieldSet>
  );
}
