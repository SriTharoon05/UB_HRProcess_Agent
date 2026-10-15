import {
  AlertCircle,
  ArrowRight,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  FolderOpen,
  LoaderCircle,
  MapPin,
  RefreshCw,
  Star,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { Button } from "./ui/button";
import { appName } from "../lib/config";
import { cn, dateLabel, experience, humanize, initials } from "../lib/utils";
import type { Job } from "../lib/types";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="brand" aria-label={`${appName} home`}>
      <span className="brand-mark">
        <span aria-hidden="true">UB</span>
      </span>
      {!compact && <span>{appName}</span>}
    </Link>
  );
}
export function Avatar({
  name,
  size = "md",
  color = 0,
}: {
  name: string;
  size?: "sm" | "md" | "lg";
  color?: number;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("avatar", `avatar-${size}`, `avatar-color-${color % 5}`)}
    >
      {initials(name)}
    </span>
  );
}
export function Badge({
  children,
  tone = "purple",
  className,
}: {
  children: ReactNode;
  tone?: "purple" | "green" | "orange" | "blue" | "gray";
  className?: string;
}) {
  return (
    <span className={cn("badge", `badge-${tone}`, className)}>{children}</span>
  );
}
export function StatusBadge({ status }: { status: string }) {
  const lower = status.toLowerCase();
  const tone = ["completed", "open", "evaluated", "submitted"].includes(lower)
    ? "green"
    : ["failed", "error"].includes(lower)
      ? "orange"
      : ["pending", "queued", "processing"].includes(lower)
        ? "blue"
        : "gray";
  return (
    <Badge tone={tone}>
      <span className="status-dot" />
      {humanize(status || "Unknown")}
    </Badge>
  );
}
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="loading-state" role="status" aria-label="Loading">
      <span className="sr-only">Loading, please wait</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton" />
      ))}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  return (
    <div className="empty-state error-state" role="alert">
      <span className="empty-icon">
        <AlertCircle />
      </span>
      <h3>We couldn’t load this information</h3>
      <p>{error?.message || "Please check your connection and try again."}</p>
      {retry && (
        <Button variant="outline" onClick={retry}>
          <RefreshCw size={15} />
          Try again
        </Button>
      )}
    </div>
  );
}
export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon || <FolderOpen />}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function SectionHeading({
  title,
  description,
  link,
  linkText = "View all",
}: {
  title: string;
  description?: string;
  link?: string;
  linkText?: string;
}) {
  return (
    <div className="section-heading">
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {link && (
        <Link to={link} className="text-link">
          {linkText}
          <ArrowRight size={14} />
        </Link>
      )}
    </div>
  );
}
export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          {index > 0 && <ChevronRight size={12} />}
          {item.to ? (
            <Link to={item.to}>{item.label}</Link>
          ) : (
            <span aria-current="page">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
export function HumanReviewNotice() {
  return (
    <div className="review-notice">
      <CircleHelp size={17} />
      <p>
        AI highlights resume evidence to support your review. Scores are
        contextual and never make hiring decisions. A person makes the final
        call.
      </p>
    </div>
  );
}
export function JobIcon({
  department,
  index = 0,
}: {
  department: string;
  index?: number;
}) {
  const type = /design/i.test(department)
    ? "design"
    : /data|analytics/i.test(department)
      ? "data"
      : /human|people/i.test(department)
        ? "people"
        : /product/i.test(department)
          ? "product"
          : "engineering";
  return (
    <span
      className={cn(
        "job-icon",
        `job-icon-${type}`,
        index % 2 && "job-icon-alt",
      )}
    >
      <span className="job-symbol">
        <span />
        <span />
        <span />
      </span>
    </span>
  );
}
export function JobCard({
  job,
  index = 0,
  hr = false,
}: {
  job: Job;
  index?: number;
  hr?: boolean;
}) {
  return (
    <article className="job-card">
      <div className="job-card-art">
        <JobIcon department={job.department} index={index} />
        <span className="job-art-grid" />
        <span className="job-card-mode">
          {job.work_mode || job.employment_type || "Opportunity"}
        </span>
        <Star className="job-art-star" size={54} strokeWidth={1} />
      </div>
      <div className="job-card-body">
        <div className="job-card-category">
          {job.department && (
            <Badge
              tone={
                index % 3 === 0 ? "blue" : index % 3 === 1 ? "purple" : "orange"
              }
            >
              {job.department}
            </Badge>
          )}
          <span className="job-id">{job.requirement_id}</span>
        </div>
        <Link
          className="job-card-title"
          to={
            hr
              ? `/hr/jobs/${job.requirement_id}/candidates`
              : `/jobs/${job.requirement_id}`
          }
        >
          {job.title}
        </Link>
        <div className="job-card-meta">
          {job.location && (
            <span>
              <MapPin size={12} />
              {job.location}
            </span>
          )}
          {experience(job) && (
            <span>
              <BriefcaseBusiness size={12} />
              {experience(job)}
            </span>
          )}
        </div>
        <div className="job-card-footer">
          <span>{job.employment_type || humanize(job.status)}</span>
          <Link
            to={
              hr
                ? `/hr/jobs/${job.requirement_id}/candidates`
                : `/jobs/${job.requirement_id}`
            }
            aria-label={`${hr ? "View candidates for" : "View"} ${job.title}`}
            className="round-link"
          >
            <ArrowRight size={15} />
          </Link>
        </div>
      </div>
    </article>
  );
}
export function ScoreRing({
  score,
  size = 132,
  label = "Evidence alignment",
}: {
  score: number;
  size?: number;
  label?: string;
}) {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div
      className="score-ring"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${score} out of 100 ${label}`}
    >
      <svg viewBox="0 0 110 110">
        <circle cx="55" cy="55" r={radius} className="score-track" />
        <circle
          cx="55"
          cy="55"
          r={radius}
          className="score-progress"
          strokeDasharray={`${(clamped / 100) * circumference} ${circumference}`}
          transform="rotate(-90 55 55)"
        />
      </svg>
      <div>
        <strong>
          {score}
          <small>/100</small>
        </strong>
        <span>{label}</span>
      </div>
    </div>
  );
}
export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="inline-spinner">
      <LoaderCircle size={16} className="spin" />
      {label}
    </span>
  );
}
export function DateMeta({ value }: { value: string | null }) {
  return (
    <span className="date-meta">
      <Clock3 size={13} />
      {dateLabel(value)}
    </span>
  );
}
export function CheckList({ items }: { items: string[] }) {
  return (
    <ul className="check-list">
      {items.map((item) => (
        <li key={item}>
          <span>
            <Check size={13} />
          </span>
          {item}
        </li>
      ))}
    </ul>
  );
}
