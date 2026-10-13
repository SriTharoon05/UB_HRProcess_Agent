import { z } from "zod";

const contactEmailSchema = z.string().trim().max(320).email();

export function contactEmail(value: unknown): string {
  const result = contactEmailSchema.safeParse(value);
  return result.success ? result.data : "";
}

export function profilePhoto(value: string | null | undefined): string | null {
  // eslint-disable-next-line no-control-regex -- Reject malformed image URLs.
  if (!value || /[\x00-\x20\x7f\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password &&
      (!url.port || url.port === "443") &&
      (url.hostname === "licdn.com" || url.hostname.endsWith(".licdn.com"))
      ? url.href
      : null;
  } catch {
    return null;
  }
}
