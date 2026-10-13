"""Explicitly fictional fixtures, isolated from production integrations."""

import secrets
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException

from app.models import Candidate, Evaluation, Evidence, Gap, Job, LinkedInProfile, User


def now():
    return datetime.now(timezone.utc).isoformat()


def sample_evaluation(score=88):
    evidence = Evidence(
        requirement="Build accessible React applications",
        resume_section="Projects",
        project_name="Fictional Meridian dashboard",
        evidence="Built a React dashboard with accessible keyboard navigation.",
        reason="The sample project explicitly describes React and accessibility.",
        evidence_strength="Strong",
    )
    partial = Evidence(
        requirement="Lead cross-functional delivery",
        resume_section="Employment",
        project_name="Fictional team collaboration",
        evidence="Collaborated with designers and engineers to launch a dashboard.",
        reason="Collaboration is evidenced, but leadership scope is unclear.",
        evidence_strength="Partial",
    )
    return Evaluation(
        score=score,
        meets_minimum_criteria=True,
        match_label="Strong evidence alignment",
        score_justification="FICTIONAL DEMO FIXTURE. This sample score illustrates evidence review and is not an evaluation of the uploaded resume.",
        summary="Fictional sample: relevant product delivery and React experience. Human review is required.",
        matched_requirements=[evidence],
        partially_matched_requirements=[partial],
        not_evidenced_requirements=[
            Gap(
                requirement="Enterprise-scale performance optimization",
                reason="The fictional sample does not demonstrate this requirement; absence of evidence is not absence of ability.",
            )
        ],
        evaluation_confidence="Demo fixture",
        relevant_evidence=[evidence, partial],
        model_deployment="fictional-demo",
        prompt_version="demo-v1",
        rubric_version="demo-v1",
    )


class DemoAdapter:
    def __init__(self):
        titles = [
            "Senior Frontend Engineer",
            "Product Designer",
            "Data Engineer",
            "People Operations Partner",
            "Full Stack Engineer",
            "Machine Learning Engineer",
        ]
        skills = [
            ["React", "TypeScript", "Accessibility"],
            ["Figma", "User research", "Design systems"],
            ["Python", "SQL", "Data pipelines"],
            ["Recruiting", "Employee experience", "Communication"],
            ["React", "Python", "API design"],
            ["Python", "Machine learning", "Model evaluation"],
        ]
        self.jobs = [
            Job(
                requirement_id=f"REQ-2026-{i + 1:03}",
                title=title,
                description=f"Join our fictional demo team as a {title}. Build thoughtful products that help people do their best work. Collaborate with a supportive cross-functional team, own meaningful work, and document your decisions.",
                responsibilities="Deliver reliable solutions; collaborate with design and engineering; communicate clearly; support continuous improvement.",
                required_skills=skills[i],
                preferred_skills=["Mentoring", "Agile delivery"],
                qualifications="Relevant professional experience or equivalent demonstrated projects.",
                department=["Engineering", "Design", "Engineering", "People", "Engineering", "Data & AI"][i],
                location=[
                    "Bengaluru, India",
                    "Remote",
                    "Hyderabad, India",
                    "Chennai, India",
                    "Remote",
                    "Bengaluru, India",
                ][i],
                work_mode=["Hybrid", "Remote", "Hybrid", "Onsite", "Remote", "Hybrid"][i],
                employment_type="FullTime",
                min_experience=3 if i != 3 else 2,
                max_experience=7,
                openings=2 if i == 0 else 1,
                status="Open",
                published_date="2026-10-01T09:00:00Z",
                deadline="2027-01-31T23:59:59Z",
            )
            for i, title in enumerate(titles)
        ]
        self.records: dict[str, Candidate] = {}
        for i, name in enumerate(
            ["Jordan Rivera", "Alex Morgan", "Sam Taylor", "Jamie Park", "Robin Ellis", "Casey Avery"]
        ):
            aid = f"DEMO-APP-{i + 1:03}"
            job = self.jobs[i % 3]
            self.records[aid] = Candidate(
                application_id=aid,
                candidate_id=f"DEMO-CAND-{i + 1:03}",
                requirement_id=job.requirement_id,
                job_title=job.title,
                candidate_name=name,
                email=f"candidate{i + 1}@example.test",
                applied_date="2026-10-06T10:00:00Z",
                hr_status="Under review",
                ai_status="Completed",
                resume_file_name="fictional-sample.pdf",
                demo_fixture=True,
                linkedin_url="",
                evaluation=sample_evaluation(94 - i * 4),
                evaluation_date="2026-10-06T10:05:00Z",
                owner_sub=f"fictional-{i + 1}",
                owner_issuer="demo",
            )
        self.idempotency: dict[str, dict] = {}
        # Explicit local-demo stand-ins for the candidate/application tables.
        # They are private, process-local records, never connected D365 writes.
        self.candidate_information: dict[tuple[str, str], dict] = {}
        self.application_information: dict[str, dict] = {}

    async def get_open_requirements(self):
        return self.jobs

    async def submit_application(self, payload):
        key = payload["idempotency_key"]
        if key in self.idempotency:
            return self.idempotency[key]
        job = next(j for j in self.jobs if j.requirement_id == payload["requirement_id"])
        identity = (payload["owner_issuer"], payload["owner_sub"])
        previous = self.candidate_information.get(identity)
        candidate_id = previous["candidate_id"] if previous else f"DEMO-CAND-{secrets.token_hex(5).upper()}"
        contact = {
            "candidate_id": candidate_id,
            **{field: payload.get(field, "") for field in (
                "owner_issuer", "owner_sub", "candidate_name", "email", "phone", "linkedin_url",
                "consent_version", "consent_date",
            )},
            "consent_accepted": payload["consent_accepted"],
        }
        if payload.get("linkedin_profile") is not None:
            contact["linkedin_profile"] = LinkedInProfile.model_validate(payload["linkedin_profile"]).model_dump(
                mode="json", exclude_none=True,
            )
        aid = f"DEMO-APP-{secrets.token_hex(6).upper()}"
        record = Candidate(
            application_id=aid,
            candidate_id=candidate_id,
            requirement_id=job.requirement_id,
            job_title=job.title,
            candidate_name=payload["candidate_name"],
            email=payload["email"],
            applied_date=now(),
            hr_status="Submitted",
            ai_status="Completed",
            resume_file_name=payload["resume_file_name"],
            demo_fixture=True,
            linkedin_url=payload["linkedin_url"],
            evaluation=sample_evaluation(),
            evaluation_date=now(),
            owner_sub=payload["owner_sub"],
            owner_issuer=payload["owner_issuer"],
            resume_ref=payload["resume_ref"],
        )
        # Save contact before acknowledging application creation. Each
        # application keeps its own snapshot when this identity applies again.
        self.candidate_information[identity] = deepcopy(contact)
        self.application_information[aid] = {
            "application_id": aid,
            **deepcopy(contact),
            **{field: payload.get(field, "") for field in (
                "requirement_id", "resume_ref", "resume_file_name", "resume_sha256",
                "job_description_hash", "idempotency_key",
            )},
        }
        self.records[aid] = record
        result = {"application_id": aid, "candidate_id": candidate_id}
        self.idempotency[key] = result
        return result

    async def get_my_applications(self, user: User):
        return [c for c in self.records.values() if c.owner_sub == user.sub and c.owner_issuer == user.issuer]

    async def get_application(self, application_id):
        record = self.records.get(application_id)
        if not record:
            raise HTTPException(404, "Application not found")
        return record

    async def get_top_candidates(self, requirement_id, limit):
        records = [c for c in self.records.values() if c.requirement_id == requirement_id]
        return sorted(records, key=lambda c: c.evaluation.score if c.evaluation else -1, reverse=True)[:limit]

    async def save_candidate_evaluation(self, payload):
        record = await self.get_application(payload["application_id"])
        record.evaluation = Evaluation.model_validate(payload["evaluation"])
        record.evaluation_date, record.ai_status = now(), "Completed"
        return {"success": True}
