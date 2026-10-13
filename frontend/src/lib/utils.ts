import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Candidate, Job } from "./types";
export function cn(...values: ClassValue[]) {
  return twMerge(clsx(values));
}
export function initials(name: string) {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "?"
  );
}
export function dateLabel(value: string | null) {
  if (!value) return "Not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Not provided"
    : date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
}
export function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
export function experience(job: Job) {
  if (job.min_experience == null && job.max_experience == null) return null;
  if (job.min_experience != null && job.max_experience != null)
    return `${job.min_experience}–${job.max_experience} years`;
  return job.min_experience != null
    ? `${job.min_experience}+ years`
    : `Up to ${job.max_experience} years`;
}
export interface JobFilters {
  search: string;
  department: string;
  location: string;
  work_mode: string;
  employment_type: string;
}
export const emptyFilters: JobFilters = {
  search: "",
  department: "",
  location: "",
  work_mode: "",
  employment_type: "",
};
export function filterJobs(jobs: Job[], filters: JobFilters) {
  return jobs.filter(
    (job) =>
      (!filters.search ||
        `${job.title} ${job.department} ${job.required_skills.join(" ")}`
          .toLowerCase()
          .includes(filters.search.toLowerCase())) &&
      (
        ["department", "location", "work_mode", "employment_type"] as const
      ).every((key) => !filters[key] || job[key] === filters[key]),
  );
}
export function sortCandidates(candidates: Candidate[], descending = true) {
  return [...candidates].sort((a, b) => {
    if (!a.evaluation) return b.evaluation ? 1 : 0;
    if (!b.evaluation) return -1;
    return descending
      ? b.evaluation.score - a.evaluation.score
      : a.evaluation.score - b.evaluation.score;
  });
}
export function safeExternalUrl(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
