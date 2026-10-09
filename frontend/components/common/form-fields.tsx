"use client";

import { Controller, type Control, type FieldPath, type FieldValues } from "react-hook-form";
import { RadioGroup as RadioGroupPrimitive } from "radix-ui";

import { Field, FieldError, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// react-hook-form + shadcn Field wiring, so each form only lists its fields.

type BaseProps<T extends FieldValues> = {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
};

export function TextField<T extends FieldValues>({
  control,
  name,
  label,
  ...inputProps
}: BaseProps<T> &
  Pick<
    React.ComponentProps<"input">,
    "type" | "placeholder" | "autoComplete" | "inputMode"
  >) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Input
            {...field}
            {...inputProps}
            id={name}
            value={field.value ?? ""}
            aria-invalid={fieldState.invalid}
          />
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  );
}

export function SelectField<T extends FieldValues>({
  control,
  name,
  label,
  placeholder,
  options,
}: BaseProps<T> & { placeholder: string; options: readonly string[] }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Select
            name={field.name}
            value={field.value ?? ""}
            onValueChange={field.onChange}
          >
            <SelectTrigger
              id={name}
              ref={field.ref}
              onBlur={field.onBlur}
              aria-invalid={fieldState.invalid}
              className="w-full"
            >
              <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent>
              {options.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  );
}

/** Two-or-more option toggle styled like the prototype's segmented control. */
export function SegmentedField<T extends FieldValues>({
  control,
  name,
  label,
  options,
}: BaseProps<T> & { options: readonly string[] }) {
  const labelId = `${name}-label`;
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldTitle id={labelId}>{label}</FieldTitle>
          <RadioGroupPrimitive.Root
            ref={field.ref}
            name={field.name}
            value={field.value ?? ""}
            onValueChange={field.onChange}
            aria-labelledby={labelId}
            aria-invalid={fieldState.invalid}
            className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg bg-line-soft p-1 aria-invalid:ring-1 aria-invalid:ring-destructive"
          >
            {options.map((option) => (
              <RadioGroupPrimitive.Item
                key={option}
                value={option}
                onBlur={field.onBlur}
                className="h-8.5 rounded-md text-control font-semibold text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-primary data-[state=checked]:bg-card data-[state=checked]:text-foreground data-[state=checked]:shadow-[0_1px_3px_rgb(0_0_0/0.08)]"
              >
                {option}
              </RadioGroupPrimitive.Item>
            ))}
          </RadioGroupPrimitive.Root>
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  );
}
