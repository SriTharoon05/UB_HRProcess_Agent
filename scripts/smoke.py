"""Exercise the demo UI against a running API, including a real resume upload.

Start `bash scripts/dev.sh` first. From backend:
  uv run --frozen --extra e2e python ../scripts/smoke.py
Set CHROMIUM_PATH if using a system browser; otherwise install Playwright Chromium.
This test creates a fictional application in the demo adapter and no external records.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pymupdf as fitz
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import get_settings  # noqa: E402


def verify_collection_layout(page, base, requirement_id, candidate, job):
    """Read-only browser fixtures exercise full rows without changing demo records."""
    candidates_path = re.compile(rf"/api/hr/jobs/{re.escape(requirement_id)}/candidates$")
    job_path = re.compile(rf"/api/jobs/{re.escape(requirement_id)}$")
    fixture = {}

    def candidates_route(route):
        route.fulfill(json=fixture)

    long_job = {
        **job,
        "department": "Enterprise Applications",
        "location": "Chennai, Tamil Nadu, India",
        "work_mode": "Hybrid",
        "employment_type": "Permanent",
        "min_experience": 3,
        "max_experience": 6,
        "openings": 2,
        "published_date": "2026-10-13",
        "deadline": "2026-10-23",
        "description": "\n\n".join(["Review requirements and deliver maintainable business applications."] * 60),
    }

    def job_route(route):
        route.fulfill(json=long_job)

    page.route(candidates_path, candidates_route)
    page.route(job_path, job_route)
    try:
        page.set_viewport_size({"width": 1440, "height": 768})
        for count in (4, 9):
            fixture = {
                "limit": 25,
                "returned_count": count,
                "candidates": [
                    {
                        **candidate,
                        "application_id": f"APP-layout-{index:02d}-failed-candidate",
                        "candidate_name": f"Layout Candidate {index:02d}",
                        "email": f"layout-{index:02d}@example.test",
                        "ai_status": "Failed",
                        "evaluation": None,
                        "demo_fixture": False,
                    }
                    for index in range(count)
                ],
            }
            page.goto(f"{base}/hr/jobs/{requirement_id}/candidates")
            region = page.get_by_role("region", name="Candidate records", exact=True)
            expect(region.locator("tbody tr")).to_have_count(count)
            expect(region.get_by_role("button", name="Retry evaluation", exact=True)).to_have_count(count)
            # Wait for ResizeObserver measurement; assert the cap contains the
            # entire sixth row rather than merely an arbitrary viewport slice.
            page.wait_for_function(
                """count => {
                    const r = document.querySelector('[aria-label="Candidate records"]');
                    const rows = r?.querySelectorAll('tbody tr');
                    if (!r || rows?.length !== count || r.scrollTop !== 0) return false;
                    if (count <= 6) return !r.style.maxHeight && r.scrollHeight <= r.clientHeight + 1;
                    const bottom = r.getBoundingClientRect().top + r.clientTop + r.clientHeight;
                    return !!r.style.maxHeight && r.scrollHeight > r.clientHeight + 20 &&
                        rows[5].getBoundingClientRect().bottom <= bottom + 2 &&
                        rows[6].getBoundingClientRect().top >= bottom - 3;
                }""",
                arg=count,
            )
            assert page.evaluate("document.documentElement.scrollHeight > window.innerHeight + 50")
            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            page.wait_for_function("window.scrollY > 0")
            if count > 6:
                region.evaluate("element => { element.scrollTop = 100; }")
                page.wait_for_function(
                    """() => {
                        const r = document.querySelector('[aria-label="Candidate records"]');
                        const header = r.querySelector('th');
                        return r.scrollTop > 0 && getComputedStyle(header).position === 'sticky' &&
                            Math.abs(header.getBoundingClientRect().top - r.getBoundingClientRect().top) < 3;
                    }"""
                )
        for viewport in ({"width": 1440, "height": 768}, {"width": 390, "height": 844}):
            page.set_viewport_size(viewport)
            page.goto(f"{base}/jobs/{requirement_id}")
            overview = page.locator(".role-summary dl")
            expect(overview.locator(":scope > div")).to_have_count(9)
            assert overview.evaluate("element => element.scrollHeight <= element.clientHeight + 1"), "Role overview must show all fields without a nested scrollbar"
            assert page.evaluate("document.documentElement.scrollHeight > window.innerHeight + 50")
    finally:
        page.unroute(candidates_path, candidates_route)
        page.unroute(job_path, job_route)
        page.set_viewport_size({"width": 1440, "height": 1000})


def main():
    settings = get_settings()
    assert settings.hr_username and settings.hr_password, "Set HR_USERNAME and HR_PASSWORD for the running demo API and smoke process"
    base = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5173")
    browser_path = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
    with tempfile.TemporaryDirectory(prefix="talentmatch-smoke-") as temp, sync_playwright() as playwright:
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (50, 60),
            "Avery Sample\navery@example.test\nProfessional Experience\n"
            "Developed a frontend application using React and TypeScript.\n"
            "Projects\nEmployee Management System\n"
            "Integrated REST APIs developed using FastAPI and Python.\n"
            "Education\nBachelor of Computer Science.\n",
        )
        resume_path = Path(temp) / "avery-resume.pdf"
        document.save(resume_path)
        document.close()
        browser = playwright.chromium.launch(
            headless=True,
            **({"executable_path": browser_path} if browser_path else {}),
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        health = context.request.get(f"{base}/api/health")
        assert health.ok and health.json()["demo_mode"], "Smoke test requires explicit demo mode"
        jobs = context.request.get(f"{base}/api/jobs").json()
        assert jobs, "Expected demo job fixtures"
        requirement_id = jobs[0]["requirement_id"]
        page.goto(f"{base}/jobs")
        expect(page.get_by_text(jobs[0]["title"], exact=True).first).to_be_visible()

        page.goto(f"{base}/login")
        page.get_by_test_id("demo-candidate-login").click()
        page.wait_for_url(re.compile(r"/candidate/applications/?$"))
        expect(page.get_by_text("Demo workspace", exact=True).first).to_be_visible()
        page.goto(f"{base}/jobs/{requirement_id}")
        page.get_by_role("link", name="Apply now", exact=True).first.click()
        page.get_by_role("textbox", name="Full name", exact=True).fill("Avery Sample")
        page.get_by_role("textbox", name="Email address", exact=True).fill("avery@example.test")
        page.get_by_test_id("resume-input").set_input_files(str(resume_path))
        page.get_by_test_id("application-consent").check()
        with page.expect_response(
            lambda response: response.request.method == "POST" and response.url.endswith("/api/applications")
        ) as submitted:
            page.get_by_test_id("submit-application").click()
        assert submitted.value.ok, submitted.value.text()
        application_id = submitted.value.json()["application_id"]
        confirmation = page.get_by_test_id("application-success")
        expect(confirmation).to_be_visible(timeout=15000)
        expect(confirmation).to_contain_text(application_id)

        applications_response = context.request.get(f"{base}/api/me/applications")
        assert applications_response.ok, applications_response.text()
        application = next(
            item
            for item in applications_response.json()
            if item["application_id"] == application_id
        )
        assert application["requirement_id"] == requirement_id and application["resume_file_name"] == resume_path.name
        assert application["candidate_name"] == "Avery Sample" and application["email"] == "avery@example.test"
        assert "evaluation" not in application, "Candidate responses must omit internal AI analysis"
        page.goto(f"{base}/candidate/applications")
        expect(page.get_by_text(application_id, exact=False).first).to_be_visible()
        assert context.request.get(f"{base}/api/hr/jobs").status == 403

        page.goto(f"{base}/hr/login")
        page.get_by_role("textbox", name="Username", exact=True).fill(settings.hr_username)
        page.get_by_label("Password", exact=True).fill(settings.hr_password)
        page.get_by_role("button", name="Sign in to HR", exact=True).click()
        page.wait_for_url(re.compile(r"/hr/?$"))
        page.goto(f"{base}/hr/jobs/{requirement_id}/candidates")
        expect(page.get_by_text(application["candidate_name"], exact=True).first).to_be_visible()
        page.goto(f"{base}/hr/jobs/{requirement_id}/candidates/{application_id}")
        expect(page.get_by_text(application_id, exact=False).first).to_be_visible()
        candidate_response = context.request.get(f"{base}/api/hr/jobs/{requirement_id}/candidates/{application_id}")
        assert candidate_response.ok, candidate_response.text()
        candidate = candidate_response.json()
        assert candidate["demo_fixture"] and candidate["evaluation"]
        downloaded = context.request.get(f"{base}/api/hr/applications/{application_id}/resume")
        assert downloaded.ok and downloaded.body() == resume_path.read_bytes()

        verify_collection_layout(page, base, requirement_id, candidate, jobs[0])

        # Responsive navigation should remain usable without horizontal overflow.
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{base}/hr")
        expect(page.get_by_role("button", name="Open navigation")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert not js_errors, f"Browser errors: {js_errors}"
        print(
            json.dumps(
                {
                    "result": "passed",
                    "application_id": application_id,
                    "checks": [
                        "job listing",
                        "demo login",
                        "PDF form upload",
                        "application contact capture",
                        "application history",
                        "HR authorization",
                        "candidate evidence",
                        "private resume download",
                        "full failed-candidate rows and six-record scroll cap",
                        "natural document scrolling and complete role overview",
                        "mobile layout",
                        "no browser exceptions",
                    ],
                }
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
