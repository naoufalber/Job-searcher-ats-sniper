import { z } from "zod";

export const passwordSchema = z.string()
  .min(8, "Password must be at least 8 characters.")
  .max(128, "Password must be 128 characters or fewer.")
  .regex(/[a-z]/, "Password must include a lowercase letter.")
  .regex(/[A-Z]/, "Password must include an uppercase letter.")
  .regex(/[0-9]/, "Password must include a number.");

export const profileInputSchema = z.object({
  firstName: z.string().trim().min(1, "First name is required.").max(80, "First name is too long."),
  lastName: z.string().trim().min(1, "Last name is required.").max(80, "Last name is too long."),
});

export const signupSchema = z.object({
  firstName: profileInputSchema.shape.firstName,
  lastName: profileInputSchema.shape.lastName,
  email: z.string().trim().email("Enter a valid email address."),
  password: passwordSchema,
  confirmPassword: z.string(),
}).superRefine((value, context) => {
  if (value.password !== value.confirmPassword) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["confirmPassword"], message: "Passwords do not match." });
  }
});

export const passwordChangeSchema = z.object({
  currentPassword: z.string().min(1, "Current password is required."),
  newPassword: passwordSchema,
  confirmNewPassword: z.string(),
}).superRefine((value, context) => {
  if (value.newPassword !== value.confirmNewPassword) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ["confirmNewPassword"], message: "Passwords do not match." });
  }
});

export const jobIngestionSchema = z.object({
  source: z.string().trim().min(1).max(80),
  external_job_id: z.string().trim().min(1).max(300),
  company_name: z.string().trim().min(1).max(240),
  title: z.string().trim().min(1).max(300),
  location: z.string().trim().max(300).nullable().optional(),
  country: z.string().trim().max(120).nullable().optional(),
  contract_type: z.string().trim().max(120).nullable().optional(),
  remote_type: z.string().trim().max(120).nullable().optional(),
  canonical_url: z.string().url().refine((value) => value.startsWith("http://") || value.startsWith("https://"), "Only HTTP(S) URLs are allowed."),
  description: z.string().max(200000).nullable().optional(),
  first_seen_at: z.string().datetime().optional(),
  publication_date: z.string().datetime().nullable().optional(),
  metadata: z.record(z.unknown()).default({}),
});

export type ProfileInput = z.infer<typeof profileInputSchema>;
