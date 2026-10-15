import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  Linkedin,
  ListFilter,
  Mail,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api, resumeUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  dateLabel,
  experience,
  safeExternalUrl,
  sortCandidates,
} from "../lib/utils";
import type { Evidence, Gap } from "../lib/types";
import {
  Avatar,
  Badge,
  Breadcrumbs,
  EmptyState,
  ErrorState,
  HumanReviewNotice,
  JobCard,
  JobIcon,
  Loading,
  PageHeading,
  ScoreRing,
  SectionHeading,
  Spinner,
  StatusBadge,
} from "../components/common";
import { Button } from "../components/ui/button";
import { Dialog } from "../components/ui/dialog";

function RetryEvaluationButton({ requirementId, applicationId }: { requirementId: string; applicationId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const retry = useMutation({
    mutationFn: () => api.retryEvaluation(requirementId, applicationId),
    onMutate: () => setError(""),
    onSuccess: async () => {
      toast.success("Evaluation queued. You can continue reviewing.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["candidate", requirementId, applicationId] }),
        queryClient.invalidateQueries({ queryKey: ["candidates", requirementId] }),
      ]);
    },
    onError: (failure: Error) => {
      setError(failure.message);
      toast.error(failure.message);
    },
  });
  return (
    <div>
      <Button variant="secondary" size="sm" disabled={retry.isPending} onClick={() => retry.mutate()}>
        <RefreshCw size={14} />
        {retry.isPending ? "Queueing…" : "Retry evaluation"}
      </Button>
      {error && <p role="alert" className="small-note">{error}</p>}
    </div>
  );
}

export function HRDashboardPage() {
  const { session } = useAuth();
  const [selectedJobId, setSelectedJobId] = useState("");
  const jobs = useQuery({
    queryKey: ["hr-jobs"],
    queryFn: () => api.jobs(true),
  });
  const candidateQueries = useQueries({
    queries: (jobs.data || []).map((job) => ({
      queryKey: ["candidates", job.requirement_id],
      queryFn: () => api.candidates(job.requirement_id),
      staleTime: 30_000,
    })),
  });
  const lists = candidateQueries.flatMap((query) =>
    query.data ? [query.data] : [],
  );
  const candidates = lists.flatMap((list) => list.candidates);
  const evaluated = candidates.filter((candidate) => candidate.evaluation);
  const pending = candidates.filter((candidate) =>
    ["pending", "queued", "processing"].includes(
      candidate.ai_status.toLowerCase(),
    ),
  );
  const candidatesLoading = candidateQueries.some((query) => query.isPending);
  const candidatesError = candidateQueries.find((query) => query.error)?.error;
  const recent = [...candidates]
    .sort(
      (a, b) =>
        new Date(b.evaluation_date || b.applied_date || 0).getTime() -
        new Date(a.evaluation_date || a.applied_date || 0).getTime(),
    )
    .slice(0, 4);
  const selectedJob =
    jobs.data?.find((job) => job.requirement_id === selectedJobId) ||
    jobs.data?.[0];
  const selectedJobCandidates = selectedJob
    ? candidateQueries[
        jobs.data!.findIndex(
          (job) => job.requirement_id === selectedJob.requirement_id,
        )
      ]?.data?.candidates || []
    : [];
  const selectedEvaluations = selectedJobCandidates.filter(
    (candidate) => candidate.evaluation,
  );
  const scoreData = [
    {
      range: "0–39",
      count: selectedEvaluations.filter((item) => item.evaluation!.score < 40)
        .length,
    },
    {
      range: "40–59",
      count: selectedEvaluations.filter(
        (item) => item.evaluation!.score >= 40 && item.evaluation!.score < 60,
      ).length,
    },
    {
      range: "60–79",
      count: selectedEvaluations.filter(
        (item) => item.evaluation!.score >= 60 && item.evaluation!.score < 80,
      ).length,
    },
    {
      range: "80–100",
      count: selectedEvaluations.filter((item) => item.evaluation!.score >= 80)
        .length,
    },
  ];
  const avg = selectedEvaluations.length
    ? Math.round(
        selectedEvaluations.reduce(
          (sum, item) => sum + item.evaluation!.score,
          0,
        ) / selectedEvaluations.length,
      )
    : null;
  return (
    <div className="page hr-dashboard">
      <PageHeading
        eyebrow="YOUR RECRUITMENT WORKSPACE"
        title="Good people. Great possibilities."
        description="A clear view of your opportunities and the talent behind them."
        action={
          <Badge tone="green">
            <span className="status-dot" />
            Human review
          </Badge>
        }
      />
      <div className="dashboard-grid">
        <div className="dashboard-main">
          <section className="hero dashboard-hero">
            <div className="hero-copy">
              <span className="hero-kicker">
                <span />
                MAKE ROOM FOR GREAT TALENT
              </span>
              <h2>
                The next great hire
                <br />
                starts with <span>good insight.</span>
              </h2>
              <p>
                See the experience behind every application.
                <br />
                Find your next conversation, thoughtfully.
              </p>
              <Button asChild variant="dark">
                <Link to="/hr/jobs">
                  Explore your opportunities
                  <span className="button-arrow">
                    <ArrowRight size={14} />
                  </span>
                </Link>
              </Button>
            </div>
            <div className="dashboard-hero-art" aria-hidden="true">
              <span className="hero-spark spark-one">✦</span>
              <span className="hero-spark spark-two">✦</span>
              <div className="talent-stack">
                <div className="stack-profile">
                  <Avatar name="People and potential" color={1} />
                  <div>
                    <span>PEOPLE & POTENTIAL</span>
                    <strong>The story behind the skills</strong>
                  </div>
                  <Sparkles size={16} />
                </div>
                <div className="stack-profile">
                  <Avatar name="Evidence with context" color={2} />
                  <div>
                    <span>EVIDENCE WITH CONTEXT</span>
                    <strong>A more thoughtful review</strong>
                  </div>
                  <CheckCircle2 size={16} />
                </div>
                <div className="stack-profile">
                  <Avatar name="Your next team" color={3} />
                  <div>
                    <span>YOUR NEXT TEAM</span>
                    <strong>Possibility starts here</strong>
                  </div>
                  <ArrowUpRight size={16} />
                </div>
              </div>
            </div>
          </section>
          <div className="dashboard-stats">
            <Metric
              icon={<BriefcaseBusiness size={20} />}
              value={
                jobs.data
                  ? jobs.data.filter(
                      (job) => job.status.toLowerCase() === "open",
                    ).length
                  : null
              }
              label="Open requirements"
              note="In available job records"
              color="purple"
            />
            <Metric
              icon={<Users size={20} />}
              value={
                lists.length ? candidates.length : candidatesLoading ? null : 0
              }
              label="Profiles returned"
              note="Across fetched candidate lists"
              color="pink"
            />
            <Metric
              icon={<FileSearch size={20} />}
              value={
                lists.length ? evaluated.length : candidatesLoading ? null : 0
              }
              label="Evidence evaluations"
              note={`${pending.length} processing in these lists`}
              color="blue"
            />
          </div>
          <SectionHeading
            title="Opportunities in focus"
            description="Build the next chapter of your team."
            link="/hr/jobs"
            linkText="All requirements"
          />
          {jobs.isPending ? (
            <Loading />
          ) : jobs.error ? (
            <ErrorState
              error={jobs.error}
              retry={() => {
                void jobs.refetch();
              }}
            />
          ) : jobs.data?.length ? (
            <div className="job-grid dashboard-job-grid">
              {jobs.data.slice(0, 3).map((job, index) => (
                <JobCard key={job.requirement_id} job={job} index={index} hr />
              ))}
            </div>
          ) : (
            <EmptyState
              title="A new opportunity starts in D365"
              description="Create and publish your requirements in Dynamics 365 to see them here."
            />
          )}
          <SectionHeading
            title="Recent candidate evidence"
            description="Recently evaluated profiles in the returned candidate lists."
          />
          {candidatesLoading ? (
            <Loading rows={2} />
          ) : candidatesError ? (
            <ErrorState
              error={candidatesError}
              retry={() => {
                candidateQueries.forEach((query) => {
                  void query.refetch();
                });
              }}
            />
          ) : recent.length ? (
            <div className="card recent-candidate-card">
              <div className="table-scroll scroll-region" role="region" aria-label="Recent candidates" tabIndex={0}>
                <table className="recent-table">
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th>Opportunity</th>
                      <th>Evidence score</th>
                      <th>
                        <span className="sr-only">Review</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((candidate, index) => (
                      <tr key={candidate.application_id}>
                        <td>
                          <div className="table-person">
                            <Avatar
                              name={candidate.candidate_name}
                              size="sm"
                              color={index}
                            />
                            <div>
                              <Link
                                to={`/hr/jobs/${candidate.requirement_id}/candidates/${candidate.application_id}`}
                              >
                                {candidate.candidate_name}
                              </Link>
                              <span>
                                {dateLabel(
                                  candidate.evaluation_date ||
                                    candidate.applied_date,
                                )}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className="table-job-title">
                            {candidate.job_title || candidate.requirement_id}
                          </span>
                          {candidate.demo_fixture && (
                            <span className="tiny-demo">
                              Fictional demo sample
                            </span>
                          )}
                        </td>
                        <td>
                          {candidate.evaluation ? (
                            <Badge tone="purple">
                              <Sparkles size={11} />
                              {candidate.evaluation.score}/100
                            </Badge>
                          ) : (
                            <StatusBadge status={candidate.ai_status} />
                          )}
                        </td>
                        <td>
                          <Link
                            className="round-link"
                            aria-label={`Review ${candidate.candidate_name}`}
                            to={`/hr/jobs/${candidate.requirement_id}/candidates/${candidate.application_id}`}
                          >
                            <ArrowUpRight size={15} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <EmptyState
              title="The next conversation is on its way"
              description="Candidate profiles will appear here as applications arrive."
            />
          )}
          <p className="data-scope-note">
            Showing up to {lists[0]?.limit || 25} profiles for each role. These
            counts describe the displayed applications, not organization-wide
            totals.
          </p>
        </div>
        <aside className="dashboard-rail">
          <section className="card reviewer-card">
            <div className="rail-heading">
              <h2>Your workspace</h2>
              <Sparkles size={15} />
            </div>
            <div className="reviewer-orbit">
              <Avatar
                name={session?.user?.name || "Recruitment team"}
                size="lg"
                color={0}
              />
              <span className="orbit-badge">
                <ShieldCheck size={13} />
              </span>
            </div>
            <h3>
              Hello, {session?.user?.name.split(" ")[0] || "team"}{" "}
              <span>✦</span>
            </h3>
            <p>Good insight. Thoughtful decisions.</p>
            <div className="evidence-chart">
              <div className="chart-title">
                <span>Evidence distribution</span>
                <Badge tone="purple">
                  {selectedEvaluations.length} profiles
                </Badge>
              </div>
              <select
                aria-label="Evidence overview job"
                value={selectedJob?.requirement_id || ""}
                onChange={(event) => setSelectedJobId(event.target.value)}
              >
                {jobs.data?.map((job) => (
                  <option key={job.requirement_id} value={job.requirement_id}>
                    {job.title}
                  </option>
                ))}
              </select>
              {selectedEvaluations.length ? (
                <>
                  <ResponsiveContainer width="100%" height={145}>
                    <BarChart
                      data={scoreData}
                      margin={{ top: 8, right: 0, left: -22, bottom: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        vertical={false}
                        stroke="#e0eaf1"
                      />
                      <XAxis
                        dataKey="range"
                        tick={{ fontSize: 10, fill: "#60788d" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 10, fill: "#60788d" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        cursor={{ fill: "#edf5fa" }}
                        contentStyle={{
                          borderRadius: 10,
                          border: "1px solid #dce7ef",
                          fontSize: 12,
                        }}
                      />
                      <Bar
                        isAnimationActive={false}
                        dataKey="count"
                        name="Returned profiles"
                        fill="#087db2"
                        radius={[5, 5, 0, 0]}
                        barSize={28}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                  <div className="average-score">
                    <strong>
                      {avg}
                      <small>/100</small>
                    </strong>
                    <span>
                      Average in {selectedEvaluations.length} returned job
                      profiles
                    </span>
                  </div>
                </>
              ) : (
                <div className="chart-empty">
                  Evidence distribution appears when evaluations are available.
                </div>
              )}
            </div>
          </section>
          <section className="card talent-rail-card">
            <div className="rail-heading">
              <h2>People in focus</h2>
              <Users size={16} />
            </div>
            {recent.slice(0, 3).map((candidate, index) => (
              <Link
                className="rail-person"
                key={candidate.application_id}
                to={`/hr/jobs/${candidate.requirement_id}/candidates/${candidate.application_id}`}
              >
                <Avatar
                  name={candidate.candidate_name}
                  size="sm"
                  color={index + 1}
                />
                <div>
                  <strong>{candidate.candidate_name}</strong>
                  <span>
                    {candidate.evaluation?.match_label || "Awaiting evaluation"}
                  </span>
                </div>
                <span className="mini-score">
                  {candidate.evaluation?.score ?? "—"}
                </span>
              </Link>
            ))}
            {!recent.length && (
              <p className="small-note">Profiles appear as candidates apply.</p>
            )}
            <Button
              asChild
              variant="secondary"
              size="sm"
              className="full-width"
            >
              <Link to="/hr/jobs">
                Explore candidate lists
                <ArrowRight size={13} />
              </Link>
            </Button>
          </section>
          <div className="human-review-card">
            <span className="review-card-icon">
              <ShieldCheck size={24} />
            </span>
            <h3>
              People first.
              <br />
              Always.
            </h3>
            <p>
              AI helps find the evidence.
              <br />
              You see the whole person.
            </p>
            <span className="review-card-decoration">✦</span>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Metric({
  icon,
  value,
  label,
  note,
  color,
}: {
  icon: React.ReactNode;
  value: number | null;
  label: string;
  note: string;
  color: string;
}) {
  return (
    <div className="metric-card">
      <span className={`stat-icon ${color}-icon`}>{icon}</span>
      <div>
        <span className="metric-label">{label}</span>
        <strong>{value ?? "—"}</strong>
        <span className="metric-note">{note}</span>
      </div>
    </div>
  );
}

export function HRJobsPage() {
  const query = useQuery({
    queryKey: ["hr-jobs"],
    queryFn: () => api.jobs(true),
  });
  const [params] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") || "");
  const urlSearch = params.get("search") || "";
  const [lastSearch, setLastSearch] = useState(urlSearch);
  if (lastSearch !== urlSearch) {
    setLastSearch(urlSearch);
    setSearch(urlSearch);
  }
  const [department, setDepartment] = useState("");
  const jobs = (query.data || []).filter(
    (job) =>
      `${job.title} ${job.requirement_id} ${job.department}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!department || department === job.department),
  );
  return (
    <div className="page page-records">
      <PageHeading
        eyebrow="RECRUITMENT OPPORTUNITIES"
        title="Great teams begin with a role."
        description="Published requirements from Dynamics 365, ready for a thoughtful match."
        action={
          <Badge tone="purple">
            <BriefcaseBusiness size={13} />
            {query.data?.length ?? "—"} available requirements
          </Badge>
        }
      />
      <div className="card list-toolbar">
        <div className="filter-search">
          <Search size={17} />
          <input
            aria-label="Search job requirements"
            placeholder="Search title, team, or requirement ID…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <select
          aria-label="Filter by department"
          value={department}
          onChange={(event) => setDepartment(event.target.value)}
        >
          <option value="">All teams</option>
          {Array.from(
            new Set(query.data?.map((job) => job.department).filter(Boolean)),
          ).map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      ) : jobs.length ? (
        <div className="card jobs-table-card record-card">
          <div className="table-scroll scroll-region" role="region" aria-label="Job requirements" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Job requirement</th>
                  <th>Team</th>
                  <th>Location</th>
                  <th>Experience</th>
                  <th>Status</th>
                  <th>Candidates</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job, index) => (
                  <tr key={job.requirement_id}>
                    <td>
                      <div className="table-role">
                        <JobIcon department={job.department} index={index} />
                        <div>
                          <Link
                            className="table-job-title"
                            to={`/hr/jobs/${job.requirement_id}/candidates`}
                          >
                            {job.title}
                          </Link>
                          <span className="mono">{job.requirement_id}</span>
                        </div>
                      </div>
                    </td>
                    <td>{job.department || "Not provided"}</td>
                    <td>
                      <div className="table-location">
                        {job.location || "Not provided"}
                        <span>{job.work_mode}</span>
                      </div>
                    </td>
                    <td>{experience(job) || "Not specified"}</td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td>
                      <Button asChild variant="secondary" size="sm">
                        <Link to={`/hr/jobs/${job.requirement_id}/candidates`}>
                          View candidates
                          <ArrowUpRight size={13} />
                        </Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>
              {jobs.length} {jobs.length === 1 ? "requirement" : "requirements"}
            </span>
            <span>
              <ShieldCheck size={12} />
              Dynamics 365 is the system of record
            </span>
          </div>
        </div>
      ) : (
        <EmptyState
          title="No requirements found"
          description="Try another search or department. New requirements are created and published in Dynamics 365."
          action={
            (search || department) && (
              <Button
                variant="secondary"
                onClick={() => {
                  setSearch("");
                  setDepartment("");
                }}
              >
                Clear filters
              </Button>
            )
          }
        />
      )}
    </div>
  );
}

export function CandidateRankingPage() {
  const { requirementId = "" } = useParams();
  const query = useQuery({
    queryKey: ["candidates", requirementId],
    queryFn: () => api.candidates(requirementId),
    refetchInterval: (value) => value.state.data?.candidates.some((item) => ["pending", "queued", "processing", "retrying"].includes(item.ai_status.toLowerCase())) ? 5_000 : false,
  });
  const job = useQuery({
    queryKey: ["job", requirementId],
    queryFn: () => api.job(requirementId),
  });
  const [search, setSearch] = useState("");
  const [match, setMatch] = useState("");
  const [status, setStatus] = useState("");
  const [descending, setDescending] = useState(true);
  const candidates = sortCandidates(
    query.data?.candidates || [],
    descending,
  ).filter(
    (item) =>
      `${item.candidate_name} ${item.email} ${item.application_id}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!match || item.evaluation?.match_label === match) &&
      (!status || item.ai_status === status),
  );
  return (
    <div className="page page-records ranking-page">
      <Breadcrumbs
        items={[
          { label: "Job requirements", to: "/hr/jobs" },
          { label: job.data?.title || requirementId },
          { label: "Candidate evidence" },
        ]}
      />
      <PageHeading
        eyebrow="CANDIDATE REVIEW WORKSPACE"
        title={job.data?.title || "Candidate evidence"}
        description={`${requirementId}${job.data?.department ? ` · ${job.data.department}` : ""}${job.data?.location ? ` · ${job.data.location}` : ""}`}
        action={
          <div className="heading-actions">
            <Button variant="secondary" disabled={query.isFetching} onClick={() => { void query.refetch(); }}>
              <RefreshCw size={14} /> Refresh list
            </Button>
            <Button asChild variant="outline">
              <Link to={`/jobs/${requirementId}`}>
                View job description
                <ExternalLink size={14} />
              </Link>
            </Button>
          </div>
        }
      />
      <HumanReviewNotice />
      <div className="ranking-summary">
        <div>
          <span className="stat-icon purple-icon">
            <Users size={19} />
          </span>
          <strong>{query.data?.returned_count ?? "—"}</strong>
          <span>profiles returned</span>
        </div>
        <div>
          <span className="stat-icon blue-icon">
            <Sparkles size={19} />
          </span>
          <strong>
            {query.data?.candidates.filter((item) => item.evaluation).length ??
              "—"}
          </strong>
          <span>with evidence evaluation</span>
        </div>
        <div className="ranking-scope">
          <ShieldCheck size={15} />
          Limited to {query.data?.limit || 25} profiles per job
        </div>
      </div>
      <div className="card ranking-toolbar">
        <div className="filter-search">
          <Search size={17} />
          <input
            aria-label="Search candidates"
            placeholder="Search candidate, email, or application ID…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="filter-row">
          <span className="filter-caption">
            <ListFilter size={14} />
            Filter
          </span>
          <select
            aria-label="Filter match label"
            value={match}
            onChange={(event) => setMatch(event.target.value)}
          >
            <option value="">All evidence</option>
            {Array.from(
              new Set(
                query.data?.candidates
                  .map((item) => item.evaluation?.match_label)
                  .filter(Boolean),
              ),
            ).map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <select
            aria-label="Filter AI status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            {Array.from(
              new Set(query.data?.candidates.map((item) => item.ai_status)),
            ).map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <button
            className="sort-button"
            onClick={() => setDescending((value) => !value)}
          >
            <ArrowDownUp size={14} />
            Score: {descending ? "highest first" : "lowest first"}
          </button>
          {(search || match || status) && (
            <button
              className="clear-filter"
              onClick={() => {
                setSearch("");
                setMatch("");
                setStatus("");
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      ) : candidates.length ? (
        <div className="card candidates-table-card record-card">
          <div className="table-scroll scroll-region" role="region" aria-label="Candidate records" tabIndex={0}>
            <table className="candidates-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Candidate</th>
                  <th>Application ID</th>
                  <th>Evidence score</th>
                  <th>Evidence label</th>
                  <th>AI status</th>
                  <th>Applied</th>
                  <th>Analysis</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate, index) => (
                  <tr key={candidate.application_id}>
                    <td>
                      <span className="rank-number">{index + 1}</span>
                    </td>
                    <td>
                      <div className="table-person">
                        <Avatar name={candidate.candidate_name} color={index} />
                        <div>
                          <Link
                            to={`/hr/jobs/${requirementId}/candidates/${candidate.application_id}`}
                          >
                            {candidate.candidate_name}
                          </Link>
                          <span>{candidate.email}</span>
                          {candidate.demo_fixture && (
                            <span className="tiny-demo">
                              Fictional demo sample
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="mono">{candidate.application_id}</td>
                    <td>
                      {candidate.evaluation ? (
                        <div className="table-score">
                          <strong>
                            {candidate.evaluation.score}
                            <small>/100</small>
                          </strong>
                          <span>
                            <i
                              style={{
                                width: `${candidate.evaluation.score}%`,
                              }}
                            />
                          </span>
                        </div>
                      ) : (
                        <span className="muted">Awaiting evidence</span>
                      )}
                    </td>
                    <td>
                      {candidate.evaluation ? (
                        <Badge tone="purple">
                          {candidate.evaluation.match_label}
                        </Badge>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <StatusBadge status={candidate.ai_status} />
                      {candidate.ai_status.toLowerCase() === "failed" && (
                        <RetryEvaluationButton requirementId={requirementId} applicationId={candidate.application_id} />
                      )}
                    </td>
                    <td>{dateLabel(candidate.applied_date)}</td>
                    <td>
                      <Button asChild variant="secondary" size="sm">
                        <Link
                          to={`/hr/jobs/${requirementId}/candidates/${candidate.application_id}`}
                        >
                          View analysis
                          <ArrowUpRight size={12} />
                        </Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>
              Showing {candidates.length} of {query.data?.returned_count}{" "}
              returned profiles
            </span>
            <span>Scores support human review</span>
          </div>
        </div>
      ) : (
        <EmptyState
          title={
            query.data?.candidates.length
              ? "No profiles match these filters"
              : "Your next conversation is on its way"
          }
          description={
            query.data?.candidates.length
              ? "Try a different search or evidence label."
              : "Applications for this role will appear here when candidates submit them."
          }
          action={
            (search || match || status) && (
              <Button
                variant="secondary"
                onClick={() => {
                  setSearch("");
                  setMatch("");
                  setStatus("");
                }}
              >
                Clear filters
              </Button>
            )
          }
        />
      )}
      <p className="data-scope-note">
        Rank indicates position in the displayed score ordering. The returned
        list may not include every application. Scores are contextual evidence
        assessments, not hiring verdicts.
      </p>
    </div>
  );
}

export function CandidateDetailPage() {
  const { requirementId = "", applicationId = "" } = useParams();
  const query = useQuery({
    queryKey: ["candidate", requirementId, applicationId],
    queryFn: () => api.candidate(requirementId, applicationId),
    refetchInterval: (value) => value.state.data && ["pending", "queued", "processing", "retrying"].includes(value.state.data.ai_status.toLowerCase()) ? 5_000 : false,
  });
  const [tab, setTab] = useState<
    "matched" | "partial" | "missing" | "evidence"
  >("matched");
  const [resumeOpen, setResumeOpen] = useState(false);
  const [resume, setResume] = useState<{
    url: string;
    type: string;
    filename: string;
  } | null>(null);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  useEffect(
    () => () => {
      if (resume) URL.revokeObjectURL(resume.url);
    },
    [resume],
  );
  async function openResume() {
    setResumeOpen(true);
    if (resume) return;
    setResumeLoading(true);
    setResumeError(null);
    try {
      const response = await fetch(resumeUrl(applicationId, requirementId), {
        credentials: "include",
      });
      if (!response.ok) {
        let message = "This resume is not currently available.";
        try {
          const body = await response.json();
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          /* Non-JSON upstream error. */
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      setResume({
        url: URL.createObjectURL(blob),
        type: blob.type,
        filename: query.data?.resume_file_name || "resume",
      });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to retrieve this resume.";
      setResumeError(message);
      toast.error(message);
    } finally {
      setResumeLoading(false);
    }
  }
  if (query.isPending)
    return (
      <div className="page">
        <Loading />
      </div>
    );
  if (query.error)
    return (
      <div className="page">
        <ErrorState
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  const candidate = query.data;
  const evaluation = candidate.evaluation;
  const linkedIn = safeExternalUrl(candidate.linkedin_url);
  const tabs = [
    {
      key: "matched" as const,
      label: "Supported",
      count: evaluation?.matched_requirements.length || 0,
    },
    {
      key: "partial" as const,
      label: "Partial evidence",
      count: evaluation?.partially_matched_requirements.length || 0,
    },
    {
      key: "missing" as const,
      label: "Not evidenced",
      count: evaluation?.not_evidenced_requirements.length || 0,
    },
    {
      key: "evidence" as const,
      label: "Resume evidence",
      count: evaluation?.relevant_evidence.length || 0,
    },
  ];
  return (
    <div className="page page-evaluation">
      <Breadcrumbs
        items={[
          { label: "Requirements", to: "/hr/jobs" },
          {
            label: candidate.job_title,
            to: `/hr/jobs/${requirementId}/candidates`,
          },
          { label: candidate.candidate_name },
        ]}
      />
      <PageHeading
        eyebrow="THE PERSON BEHIND THE RESUME"
        title="A clearer picture of potential."
        description="Resume evidence, context, and your informed judgment."
      />
      <HumanReviewNotice />
      <div className="evaluation-grid">
        <aside className="candidate-profile card">
          <div className="candidate-profile-content scroll-region" role="region" aria-label="Candidate information" tabIndex={0}>
            <div className="profile-top">
              <Avatar name={candidate.candidate_name} size="lg" color={1} />
              <h2>{candidate.candidate_name}</h2>
              <span>Candidate for</span>
              <strong>{candidate.job_title || candidate.requirement_id}</strong>
              {candidate.demo_fixture && (
                <Badge tone="orange">
                  <Sparkles size={11} />
                  Fictional demo profile
                </Badge>
              )}
            </div>
            <div className="profile-contact">
              <a href={`mailto:${candidate.email}`}>
                <Mail size={15} />
                {candidate.email}
              </a>
              {linkedIn && (
                <a href={linkedIn} target="_blank" rel="noopener noreferrer">
                  <Linkedin size={15} />
                  LinkedIn profile
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
            <dl className="profile-details">
              <div>
                <dt>Application reference</dt>
                <dd className="mono">{candidate.application_id}</dd>
              </div>
              <div>
                <dt>Candidate reference</dt>
                <dd className="mono">{candidate.candidate_id}</dd>
              </div>
              <div>
                <dt>Applied on</dt>
                <dd>{dateLabel(candidate.applied_date)}</dd>
              </div>
              <div>
                <dt>Application status</dt>
                <dd>
                  <StatusBadge status={candidate.hr_status} />
                </dd>
              </div>
              <div>
                <dt>AI processing</dt>
                <dd>
                  <StatusBadge status={candidate.ai_status} />
                </dd>
              </div>
              {candidate.evaluation_date && (
                <div>
                  <dt>Evaluated on</dt>
                  <dd>{dateLabel(candidate.evaluation_date)}</dd>
                </div>
              )}
            </dl>
          </div>
          <Button
            className="full-width"
            variant="secondary"
            onClick={() => {
              void openResume();
            }}
          >
            <FileText size={16} />
            View resume
            <ArrowUpRight size={14} />
          </Button>
          <p className="small-note">
            <ShieldCheck size={12} />
            Authorized access only
          </p>
        </aside>
        <div className="evaluation-main scroll-region" role="region" aria-label="Evaluation details" tabIndex={0}>
          {evaluation ? (
            <>
              <section className="card evaluation-summary">
                <div className="evaluation-summary-top">
                  <div>
                    <Badge tone="purple">
                      <Sparkles size={12} />
                      {candidate.demo_fixture
                        ? "FICTIONAL SAMPLE EVALUATION"
                        : "AI-GENERATED EVIDENCE ANALYSIS"}
                    </Badge>
                    <h2>Experience, with the context it deserves.</h2>
                    <p>{evaluation.summary}</p>
                    <div className="evaluation-meta">
                      <Badge>{evaluation.match_label}</Badge>
                      <span>
                        Confidence:{" "}
                        <strong>{evaluation.evaluation_confidence}</strong>
                      </span>
                    </div>
                  </div>
                  <ScoreRing score={evaluation.score} size={150} />
                </div>
                <div className="score-justification">
                  <h3>How the evidence supports this score</h3>
                  <p>{evaluation.score_justification}</p>
                </div>
                {candidate.demo_fixture && (
                  <div className="inline-demo-note">
                    <Sparkles size={16} />
                    <p>
                      This is a fictional sample evaluation for demonstration.
                      It is not a model’s analysis of an uploaded candidate
                      document.
                    </p>
                  </div>
                )}
              </section>
              <section className="card evidence-workspace">
                <div className="evidence-workspace-heading">
                  <div>
                    <h2>Follow the evidence</h2>
                    <p>Every requirement, connected to the submitted resume.</p>
                  </div>
                  <FileSearch size={21} />
                </div>
                <div
                  className="evidence-tabs"
                  role="tablist"
                  aria-label="Evaluation evidence"
                >
                  {tabs.map((item) => (
                    <button
                      key={item.key}
                      id={`tab-${item.key}`}
                      role="tab"
                      data-testid={`evidence-tab-${item.key}`}
                      aria-selected={tab === item.key}
                      aria-controls={`panel-${item.key}`}
                      tabIndex={tab === item.key ? 0 : -1}
                      onKeyDown={(event) => {
                        if (
                          event.key === "ArrowRight" ||
                          event.key === "ArrowLeft"
                        ) {
                          event.preventDefault();
                          const next =
                            (tabs.findIndex((value) => value.key === tab) +
                              (event.key === "ArrowRight" ? 1 : -1) +
                              tabs.length) %
                            tabs.length;
                          setTab(tabs[next].key);
                          document
                            .getElementById(`tab-${tabs[next].key}`)
                            ?.focus();
                        }
                      }}
                      onClick={() => setTab(item.key)}
                      className={tab === item.key ? "tab-active" : ""}
                    >
                      {item.label}
                      <span>{item.count}</span>
                    </button>
                  ))}
                </div>
                <div
                  className="evidence-tab-panel scroll-region"
                  tabIndex={0}
                  role="tabpanel"
                  id={`panel-${tab}`}
                  aria-labelledby={`tab-${tab}`}
                >
                  {tab === "matched" && (
                    <EvidenceList
                      items={evaluation.matched_requirements}
                      tone="matched"
                      empty="No requirements are fully supported in this evaluation."
                    />
                  )}
                  {tab === "partial" && (
                    <EvidenceList
                      items={evaluation.partially_matched_requirements}
                      tone="partial"
                      empty="No partially supported requirements were identified."
                    />
                  )}
                  {tab === "missing" && (
                    <GapList items={evaluation.not_evidenced_requirements} />
                  )}
                  {tab === "evidence" && (
                    <EvidenceList
                      items={evaluation.relevant_evidence}
                      tone="evidence"
                      empty="No additional supporting evidence was included."
                    />
                  )}
                </div>
              </section>
              <div className="evaluation-provenance">
                <ShieldCheck size={14} />
                <span>
                  Model: {evaluation.model_deployment || "Not provided"} ·
                  Prompt: {evaluation.prompt_version || "Not provided"} ·
                  Rubric: {evaluation.rubric_version || "Not provided"}
                </span>
              </div>
            </>
          ) : (
            <section className="card">
              <EmptyState
                title={candidate.ai_status.toLowerCase() === "failed" ? "Evaluation needs another attempt" : "The evidence is still coming together"}
                description={`Processing status: ${candidate.ai_status}. Your team can review the resume in the meantime. A score appears once the evaluation is verified and saved.`}
                icon={<Clock3 />}
                action={
                  candidate.ai_status.toLowerCase() === "failed" ? (
                    <RetryEvaluationButton requirementId={requirementId} applicationId={applicationId} />
                  ) : (
                    <Button variant="secondary" onClick={() => { void query.refetch(); }}>
                      Check for an update
                      <ArrowRight size={14} />
                    </Button>
                  )
                }
              />
            </section>
          )}
        </div>
      </div>
      <Dialog
        open={resumeOpen}
        onOpenChange={setResumeOpen}
        title="Candidate resume"
        description={`${candidate.candidate_name} · ${candidate.resume_file_name || "Submitted document"}`}
      >
        {resumeLoading ? (
          <div className="resume-loading">
            <Spinner label="Retrieving the authorized document…" />
          </div>
        ) : resumeError ? (
          <ErrorState
            error={new Error(resumeError)}
            retry={() => {
              void openResume();
            }}
          />
        ) : (
          resume && (
            <>
              <div className="resume-dialog-actions">
                <Button asChild variant="secondary" size="sm">
                  <a href={resume.url} download={resume.filename}>
                    <Download size={14} />
                    Download resume
                  </a>
                </Button>
              </div>
              {resume.type.includes("pdf") ? (
                <iframe
                  className="resume-preview"
                  title={`${candidate.candidate_name} resume preview`}
                  src={resume.url}
                />
              ) : (
                <div className="dialog-empty">
                  <FileText size={35} />
                  <p>
                    DOCX documents are available to download. Open the file in
                    your preferred document reader.
                  </p>
                </div>
              )}
            </>
          )
        )}
      </Dialog>
    </div>
  );
}

function EvidenceList({
  items,
  tone,
  empty,
}: {
  items: Evidence[];
  tone: "matched" | "partial" | "evidence";
  empty: string;
}) {
  return items.length ? (
    <div className="evidence-list">
      {items.map((item, index) => (
        <details
          className={`evidence-card evidence-${tone}`}
          key={`${item.requirement}-${index}`}
          open={index === 0}
        >
          <summary>
            <span className="evidence-status-icon">
              {tone === "matched" ? (
                <CheckCircle2 size={17} />
              ) : (
                <FileSearch size={17} />
              )}
            </span>
            <span>
              <strong>{item.requirement}</strong>
              <small>
                {item.resume_section || "Resume evidence"}
                {item.project_name ? ` · ${item.project_name}` : ""}
              </small>
            </span>
            <Badge tone={tone === "partial" ? "orange" : "purple"}>
              {item.evidence_strength || "Evidence"}
            </Badge>
            <ChevronDown className="evidence-chevron" size={16} />
          </summary>
          <div className="evidence-card-body">
            <span className="eyebrow">FROM THE SUBMITTED RESUME</span>
            <blockquote>{item.evidence}</blockquote>
            {item.project_name && (
              <p className="evidence-source">
                Project: <strong>{item.project_name}</strong>
              </p>
            )}
            <div className="evidence-explanation">
              <Sparkles size={14} />
              <div>
                <strong>AI explanation</strong>
                <p>{item.reason}</p>
              </div>
            </div>
          </div>
        </details>
      ))}
    </div>
  ) : (
    <EmptyState title="No evidence in this section" description={empty} />
  );
}
function GapList({ items }: { items: Gap[] }) {
  return items.length ? (
    <div className="evidence-list">
      {items.map((item, index) => (
        <article className="gap-card" key={`${item.requirement}-${index}`}>
          <div>
            <span className="evidence-status-icon">
              <FileSearch size={17} />
            </span>
            <h3>{item.requirement}</h3>
            <Badge tone="gray">Not documented</Badge>
          </div>
          <p>{item.reason}</p>
          <span className="gap-note">
            Not evidenced in the submitted resume. This does not establish that
            the candidate lacks the skill.
          </span>
        </article>
      ))}
    </div>
  ) : (
    <EmptyState
      title="No evidence gaps recorded"
      description="The evaluation did not list requirements without supporting evidence."
    />
  );
}
