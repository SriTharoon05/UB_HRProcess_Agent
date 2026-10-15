import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Bell,
  BriefcaseBusiness,
  CircleHelp,
  Compass,
  ExternalLink,
  FileCheck2,
  LayoutGrid,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../lib/auth";
import { appName } from "../lib/config";
import { Avatar, Badge, Brand, Loading } from "./common";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";

export function AppShell() {
  const { session, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dialog, setDialog] = useState<"help" | "notifications" | null>(null);
  const [search, setSearch] = useState("");
  const hr = /^\/hr(?:\/|$)/.test(location.pathname);
  const user = session?.user;
  const displayName =
    user?.name.trim() || (user?.role === "hr" ? "HR team" : "Candidate");
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape") setMobileOpen(false);
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const nav = hr
    ? [
        { label: "Overview", icon: LayoutGrid, to: "/hr", end: true },
        {
          label: "Job requirements",
          icon: BriefcaseBusiness,
          to: "/hr/jobs",
          end: true,
        },
        {
          label: "Candidate workspace",
          icon: Users,
          to: "/hr/jobs",
          end: false,
        },
      ]
    : [
        { label: "Discover", icon: Compass, to: "/", end: true },
        {
          label: "Browse jobs",
          icon: BriefcaseBusiness,
          to: "/jobs",
          end: false,
        },
        {
          label: "My applications",
          icon: FileCheck2,
          to: "/candidate/applications",
          end: false,
        },
      ];
  async function handleLogout() {
    try {
      await logout();
      navigate("/");
      toast.success("You have been signed out.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Unable to sign out.",
      );
    }
  }
  return (
    <div className={`app-frame ${hr ? "workspace-frame" : "careers-frame"}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {!hr && (
        <header className="careers-masthead">
          <Brand />
          <nav aria-label="Careers navigation">
            <NavLink to="/" end>
              Discover
            </NavLink>
            <NavLink to="/jobs">Open roles</NavLink>
            <NavLink to="/candidate/applications">My applications</NavLink>
          </nav>
          <span className="careers-trust">
            <ShieldCheck size={15} /> Your next chapter, securely.
          </span>
        </header>
      )}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <Brand />
          <button
            className="mobile-close"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X size={19} />
          </button>
        </div>
        <div className="workspace-label">
          <span className="workspace-dot" />
          {hr ? "Recruitment workspace" : "Your next chapter"}
        </div>
        <div className="nav-label">{hr ? "WORKSPACE" : "EXPLORE"}</div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {nav.map(({ icon: Icon, label, to, end }, index) => (
            <NavLink
              key={`${label}-${index}`}
              to={to}
              end={end}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `nav-item ${hr && index === 2 ? (location.pathname.includes("/candidates") ? "nav-item-active" : "") : isActive ? "nav-item-active" : ""}`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
              {index === 0 && <span className="nav-active-dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-feature">
          <span className="feature-icon">
            <Sparkles size={19} />
          </span>
          <h3>{hr ? "Evidence, with context." : "Great work starts here."}</h3>
          <p>
            {hr
              ? "A little intelligence. A lot of human judgment."
              : "Find an opportunity that fits your next chapter."}
          </p>
          <LinkButton to={hr ? "/hr/jobs" : "/jobs"}>
            {hr ? "Explore requirements" : "Explore opportunities"}
            <ExternalLink size={12} />
          </LinkButton>
        </div>
        <div className="sidebar-bottom">
          <div className="nav-label">MORE</div>
          <button className="nav-item" onClick={() => setDialog("help")}>
            <CircleHelp size={18} />
            Help & guidance
          </button>
          {hr && (
            <NavLink className="nav-item" to="/">
              <ShieldCheck size={18} />
              Candidate portal
            </NavLink>
          )}
          {user && (
            <button
              className="nav-item logout-link"
              onClick={() => {
                void handleLogout();
              }}
            >
              <LogOut size={17} />
              Sign out
            </button>
          )}
          <div className="sidebar-bottom-note">
            <span className="brand-mini">✦</span> Thoughtfully connected.
          </div>
        </div>
      </aside>
      {mobileOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <div className="app-body">
        <header className="topbar">
          <button
            className="mobile-menu round-button"
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={20} />
          </button>
          <form
            className="global-search"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              navigate(
                `${hr ? "/hr/jobs" : "/jobs"}?search=${encodeURIComponent(search)}`,
              );
              setSearch("");
            }}
          >
            <Search size={16} />
            <input
              ref={searchRef}
              aria-label="Search job opportunities"
              placeholder={
                hr
                  ? "Search your job requirements…"
                  : "Search your next opportunity…"
              }
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <kbd>⌘ K</kbd>
          </form>
          <div className="topbar-actions">
            {session?.demo_mode && (
              <Badge className="demo-badge" tone="orange">
                <span className="status-dot" />
                Demo workspace
              </Badge>
            )}
            <button
              className="round-button notifications-button"
              aria-label="View notifications"
              onClick={() => setDialog("notifications")}
            >
              <Bell size={16} />
            </button>
            <span className="topbar-divider" />
            {!hr && user && (
              <button
                className="round-button"
                aria-label="Sign out"
                onClick={() => { void handleLogout(); }}
              >
                <LogOut size={16} />
              </button>
            )}
            {user ? (
              <div className="user-chip">
                <Avatar name={displayName} size="sm" />
                <div>
                  <strong>{displayName}</strong>
                  <span>
                    {hr ? "Recruitment team" : "Signed in"}
                  </span>
                </div>
              </div>
            ) : (
              <Button asChild variant="secondary" size="sm">
                <NavLink
                  to="/login"
                  state={{ from: `${location.pathname}${location.search}${location.hash}` }}
                >
                  Sign in
                  <ExternalLink size={13} />
                </NavLink>
              </Button>
            )}
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Suspense
            fallback={
              <div className="page">
                <Loading />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
        <footer className="app-footer">
          <span>
            © {new Date().getFullYear()} {appName}
          </span>
          <span>Talent. Opportunity. A thoughtful match.</span>
          <button onClick={() => setDialog("help")}>Privacy & support</button>
        </footer>
      </div>
      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        title={
          dialog === "notifications"
            ? "You’re all caught up"
            : "A little guidance"
        }
        description={
          dialog === "notifications"
            ? "Application updates are available in your workspace."
            : `${appName} connects your experience with opportunities to make a difference.`
        }
      >
        {dialog === "notifications" ? (
          <div className="dialog-empty">
            <Bell size={34} />
            <p>
              There are no in-app notifications. Check{" "}
              {hr ? "candidate evaluations" : "My applications"} for the latest
              status.
            </p>
            <Button
              onClick={() => {
                setDialog(null);
                navigate(hr ? "/hr/jobs" : "/candidate/applications");
              }}
            >
              Go to my workspace
            </Button>
          </div>
        ) : (
          <div className="help-copy">
            <h4>For candidates</h4>
            <p>
              Browse open roles, sign in with LinkedIn, and submit your resume
              with consent. Your application status stays in My applications.
            </p>
            {hr && (
              <>
                <h4>For recruitment teams</h4>
                <p>
                  Review job requirements and contextual resume evidence in your
                  authorized workspace. Hiring decisions remain with your team.
                </p>
              </>
            )}
            <h4>Your information</h4>
            <p>
              Your resume and application details are shared with the
              recruitment team for the role you choose. The application form
              explains the processing consent before you submit.
            </p>
            {session?.demo_mode && (
              <p className="demo-copy">
                Demo mode uses fictional jobs, candidates, and labeled sample
                evaluations. Uploaded documents are real and should contain only
                information you intend to share.
              </p>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
}
function LinkButton({
  to,
  children,
}: {
  to: string;
  children: React.ReactNode;
}) {
  return (
    <NavLink to={to} className="feature-link">
      {children}
    </NavLink>
  );
}
