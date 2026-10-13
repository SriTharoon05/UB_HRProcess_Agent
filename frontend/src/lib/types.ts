export interface LinkedInProfile {
  sub: string;
  issuer: string;
  name?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  email?: string | null;
  email_verified?: boolean | null;
  picture?: string | null;
  locale?: string | null;
}
export interface User {
  sub: string;
  name: string;
  email: string;
  role: "candidate" | "hr";
  issuer: string;
  linkedin_profile?: LinkedInProfile | null;
}
export interface AuthSession {
  user: User | null;
  csrf_token: string;
  demo_mode: boolean;
  consent_version?: string;
}
export interface Job {
  requirement_id: string;
  title: string;
  description: string;
  responsibilities: string;
  required_skills: string[];
  preferred_skills: string[];
  qualifications: string;
  department: string;
  location: string;
  work_mode: string;
  employment_type: string;
  min_experience: number | null;
  max_experience: number | null;
  openings: number | null;
  status: string;
  published_date: string | null;
  deadline: string | null;
}
export interface Application {
  application_id: string;
  requirement_id: string;
  job_title: string;
  candidate_name: string;
  email: string;
  applied_date: string | null;
  hr_status: string;
  ai_status: string;
  resume_file_name: string;
  demo_fixture?: boolean;
}
export interface Evidence {
  requirement: string;
  resume_section: string;
  project_name: string;
  evidence: string;
  reason: string;
  evidence_strength: string;
}
export interface Gap {
  requirement: string;
  reason: string;
}
export interface Evaluation {
  score: number;
  meets_minimum_criteria: boolean;
  match_label: string;
  score_justification: string;
  summary: string;
  matched_requirements: Evidence[];
  partially_matched_requirements: Evidence[];
  not_evidenced_requirements: Gap[];
  evaluation_confidence: string;
  relevant_evidence: Evidence[];
  model_deployment: string;
  prompt_version: string;
  rubric_version: string;
}
export interface Candidate extends Application {
  candidate_id: string;
  linkedin_url: string;
  evaluation: Evaluation | null;
  evaluation_date: string | null;
  demo_fixture: boolean;
}
export interface CandidateResponse {
  candidates: Candidate[];
  limit: number;
  returned_count: number;
}
export interface SubmissionResult {
  success: boolean;
  application_id: string;
  ai_status: string;
  message: string;
}
