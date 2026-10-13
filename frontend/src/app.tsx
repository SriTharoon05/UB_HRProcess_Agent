import { Route, Routes, Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { AppShell } from "./components/app-shell";
import { EmptyState } from "./components/common";
import { Button } from "./components/ui/button";
import { Protected } from "./lib/auth";
import { lazy } from "react";
const ApplicationDetailPage = lazy(() =>
  import("./pages/candidate").then((module) => ({
    default: module.ApplicationDetailPage,
  })),
);
const ApplicationsPage = lazy(() =>
  import("./pages/candidate").then((module) => ({
    default: module.ApplicationsPage,
  })),
);
const ApplyPage = lazy(() =>
  import("./pages/candidate").then((module) => ({ default: module.ApplyPage })),
);
const HomePage = lazy(() =>
  import("./pages/candidate").then((module) => ({ default: module.HomePage })),
);
const JobDetailsPage = lazy(() =>
  import("./pages/candidate").then((module) => ({
    default: module.JobDetailsPage,
  })),
);
const JobsPage = lazy(() =>
  import("./pages/candidate").then((module) => ({ default: module.JobsPage })),
);
const LoginPage = lazy(() =>
  import("./pages/candidate").then((module) => ({ default: module.LoginPage })),
);
const CandidateDetailPage = lazy(() =>
  import("./pages/hr").then((module) => ({
    default: module.CandidateDetailPage,
  })),
);
const CandidateRankingPage = lazy(() =>
  import("./pages/hr").then((module) => ({
    default: module.CandidateRankingPage,
  })),
);
const HRDashboardPage = lazy(() =>
  import("./pages/hr").then((module) => ({ default: module.HRDashboardPage })),
);
const HRJobsPage = lazy(() =>
  import("./pages/hr").then((module) => ({ default: module.HRJobsPage })),
);

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:requirementId" element={<JobDetailsPage />} />
        <Route
          path="/jobs/:requirementId/apply"
          element={
            <Protected role="candidate">
              <ApplyPage />
            </Protected>
          }
        />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/candidate/applications"
          element={
            <Protected role="candidate">
              <ApplicationsPage />
            </Protected>
          }
        />
        <Route
          path="/candidate/applications/:applicationId"
          element={
            <Protected role="candidate">
              <ApplicationDetailPage />
            </Protected>
          }
        />
        <Route path="/hr/login" element={<LoginPage hr />} />
        <Route
          path="/hr"
          element={
            <Protected role="hr">
              <HRDashboardPage />
            </Protected>
          }
        />
        <Route
          path="/hr/jobs"
          element={
            <Protected role="hr">
              <HRJobsPage />
            </Protected>
          }
        />
        <Route
          path="/hr/jobs/:requirementId/candidates"
          element={
            <Protected role="hr">
              <CandidateRankingPage />
            </Protected>
          }
        />
        <Route
          path="/hr/jobs/:requirementId/candidates/:applicationId"
          element={
            <Protected role="hr">
              <CandidateDetailPage />
            </Protected>
          }
        />
        <Route
          path="*"
          element={
            <div className="page">
              <EmptyState
                title="This possibility took a different path"
                description="We couldn’t find that page. Let’s get you back to a fresh start."
                action={
                  <Button asChild>
                    <Link to="/">
                      Back to home
                      <ArrowRight size={15} />
                    </Link>
                  </Button>
                }
              />
            </div>
          }
        />
      </Route>
    </Routes>
  );
}
