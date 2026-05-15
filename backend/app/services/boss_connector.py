from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import re
import socket
import ssl
import struct
import threading
import time
from typing import Any
from urllib import error, parse, request

# Python 3.8 on Windows raises UNEXPECTED_EOF_WHILE_READING for TLS connections
# where the server closes without sending a proper close_notify alert.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

from app.core.logging import get_logger
from app.models.domain import CandidateAnalysis, CandidateCard, CandidateDetail, JobOption, ResumeDetailSection
from app.services.mock_data import build_analysis

JOB_LIST_URL = "https://www.zhipin.com/wapi/zpjob/job/chatted/jobList"
RECOMMEND_LIST_URL = (
    "https://www.zhipin.com/wapi/zpjob/rec/geek/list?"
    "age=16,-1&gender=0&activation=0&recentNotView=0&keyword1=-1&major=0&"
    "exchangeResumeWithColleague=0&school=0&switchJobFrequency=0&degree=0&"
    "experience=0&intention=0&salary=0&coverScreenMemory=0&cardType=0"
)
RESUME_DETAIL_URL = "https://www.zhipin.com/wapi/zpjob/view/geek/info"
RESUME_COLLECT_URL = "https://www.zhipin.com/wapi/zprelation/userMark/add"
RESUME_GREET_URL = "https://www.zhipin.com/wapi/zpjob/chat/start"

logger = get_logger(__name__)


class BossConnectorError(RuntimeError):
    pass


class BossConnector:
    def __init__(self, cdp_url: str | None = None) -> None:
        self.cdp_url = cdp_url or os.getenv("BOSS_CDP_URL", "http://127.0.0.1:9222")

    def fetch_job_options(self) -> list[JobOption]:
        payload = self._fetch_json_in_browser(
            JOB_LIST_URL,
            referer="https://www.zhipin.com/web/geek/job",
        )
        logger.info("Boss jobList raw payload: %s", self._summarize_payload(payload))
        zp_data = self._extract_zpdata_list(payload, "job list")
        jobs: list[JobOption] = []
        for item in zp_data:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("encryptJobId") or item.get("jobId") or "").strip()
            if not job_id:
                continue
            jobs.append(self._normalize_job(item, job_id))
        logger.info("Fetched %s job options from Boss.", len(jobs))
        return jobs

    def fetch_recommended_candidates(self, job_id: str, page: int = 1) -> list[CandidateDetail]:
        url = f"{RECOMMEND_LIST_URL}&jobId={job_id}&page={page}"
        payload = self._fetch_json_in_browser(
            url,
            referer=f"https://www.zhipin.com/web/frame/recommend/?jobid={job_id}&version=9609",
        )
        logger.info(
            "Boss recommend raw payload job=%s page=%s: %s",
            job_id,
            page,
            self._summarize_payload(payload),
        )
        zp_data = payload.get("zpData") or {}
        geek_list = zp_data.get("geekList") or []
        if not isinstance(geek_list, list):
            raise BossConnectorError("Boss candidate list format is invalid.")

        details: list[CandidateDetail] = []
        for item in geek_list:
            if not isinstance(item, dict):
                continue
            card = item.get("geekCard") or {}
            if not isinstance(card, dict):
                continue
            merged_card = dict(item)
            merged_card.update(card)
            details.append(self._build_candidate_from_card(job_id, merged_card))
        logger.info("Fetched %s Boss candidates for job %s page %s", len(details), job_id, page)
        return details

    def find_candidate_card_fields(self, job_id: str, security_id: str, lid: str, max_pages: int = 10) -> dict[str, str | None]:
        fallback_match: dict[str, str | None] | None = None
        for page in range(1, max_pages + 1):
            try:
                candidates = self.fetch_recommended_candidates(job_id, page=page)
            except BossConnectorError as exc:
                logger.warning(
                    "Failed to refresh Boss candidate card fields from list job=%s page=%s: %s",
                    job_id,
                    page,
                    exc,
                )
                continue

            for candidate in candidates:
                card = candidate.card
                if card.security_id != security_id:
                    continue
                matched_fields = {
                    "security_id": card.security_id,
                    "lid": card.lid,
                    "encrypt_geek_id": card.encrypt_geek_id,
                    "encrypt_job_id": card.encrypt_job_id,
                    "expect_id": card.expect_id,
                }
                if card.lid == lid:
                    return matched_fields
                if fallback_match is None:
                    fallback_match = matched_fields
        return fallback_match or {}

    def build_candidate_card_field_index(self, job_id: str, max_pages: int = 10) -> dict[str, dict[str, str | None]]:
        field_index: dict[str, dict[str, str | None]] = {}
        for page in range(1, max_pages + 1):
            try:
                candidates = self.fetch_recommended_candidates(job_id, page=page)
            except BossConnectorError as exc:
                logger.warning(
                    "Failed to build Boss candidate field index job=%s page=%s: %s",
                    job_id,
                    page,
                    exc,
                )
                continue

            for candidate in candidates:
                card = candidate.card
                if not card.security_id:
                    continue
                field_index[card.security_id] = {
                    "security_id": card.security_id,
                    "lid": card.lid,
                    "encrypt_geek_id": card.encrypt_geek_id,
                    "encrypt_job_id": card.encrypt_job_id,
                    "expect_id": card.expect_id,
                }
        return field_index

    def fetch_candidate_detail(self, job_id: str, security_id: str, lid: str) -> CandidateDetail:
        url = f"{RESUME_DETAIL_URL}?securityId={security_id}&lid={lid}"
        payload = self._fetch_json_in_browser(
            url,
            referer=f"https://www.zhipin.com/web/frame/recommend/?jobid={job_id}&version=9609",
        )
        logger.info(
            "Boss resume detail raw payload job=%s security_id=%s lid=%s: %s",
            job_id,
            security_id,
            lid,
            self._summarize_payload(payload),
        )
        if payload.get("code") != 0:
            raise BossConnectorError(str(payload.get("message") or "Boss candidate detail request failed."))

        zp_data = payload.get("zpData") or {}
        
        # Check if Boss returned a limit/block dialog
        block_dialog = zp_data.get("blockDialog")
        if block_dialog:
            title = block_dialog.get("title", "")
            content = block_dialog.get("content", "")
            logger.warning("Boss returned block dialog: %s - %s", title, content)
            # Return a candidate with limited info, indicating the limit was hit
            candidate_id = self._build_candidate_id(security_id, lid)
            placeholder_analysis = build_analysis(
                0,
                "C",
                f"Boss 查看限制：{title}。{content}",
                candidate_id,
            )
            card = CandidateCard(
                id=candidate_id,
                name="Unknown (查看受限)",
                age=0,
                education="Unknown",
                work_years=0,
                current_company="Unknown",
                current_position="Unknown",
                grade="C",
                score=0,
                summary=placeholder_analysis.summary,
                risk_tags=[],
                collected=False,
                greeted=False,
                source="boss",
                security_id=security_id,
                lid=lid,
            )
            return CandidateDetail(
                card=card,
                timeline=[f"Boss 限制：{title}"],
                original_resume="无法获取完整简历：已达到 Boss 直聘查看上限。",
                analysis=placeholder_analysis,
            )

        detail_info = zp_data.get("geekDetailInfo") or {}
        base = detail_info.get("geekBaseInfo") or {}
        work_list = detail_info.get("geekWorkExpList") or []
        edu_list = detail_info.get("geekEduExpList") or []
        project_list = detail_info.get("geekProjExpList") or detail_info.get("geekProjectExpList") or []
        certificate_list = (
            detail_info.get("geekCertificateList")
            or detail_info.get("geekCredentialList")
            or detail_info.get("geekSkillList")
            or []
        )

        # Log the structure for debugging
        logger.info(
            "Boss detail structure - base keys: %s, work count: %s, edu count: %s",
            list(base.keys()) if isinstance(base, dict) else "not a dict",
            len(work_list) if isinstance(work_list, list) else "not a list",
            len(edu_list) if isinstance(edu_list, list) else "not a list",
        )

        name = str(base.get("name") or "Unknown")
        education = str(base.get("degreeCategory") or "Unknown")
        work_years = self._parse_work_year(base.get("workYearDesc") or "")
        age = self._parse_age(base.get("ageDesc") or "")
        current_company = "Unknown"
        current_position = "Unknown"
        if work_list and isinstance(work_list[0], dict):
            current_company = str(work_list[0].get("company") or "Unknown")
            current_position = str(work_list[0].get("positionName") or "Unknown")

        timeline = self._build_timeline(work_list, edu_list)
        original_resume = self._build_resume_summary(base, work_list)
        hr_resume_sections = self._build_hr_resume_sections(
            base=base,
            work_list=work_list,
            edu_list=edu_list,
            project_list=project_list,
            certificate_list=certificate_list,
        )
        encrypt_geek_id = str(base.get("encryptGeekId") or "")
        encrypt_job_id = str(base.get("encryptJobId") or job_id)
        expect_id = str(base.get("expectId") or "")
        design_greeting = str(base.get("designGreeting") or "") or None

        candidate_id = self._build_candidate_id(security_id, lid)
        placeholder_analysis: CandidateAnalysis = build_analysis(
            72,
            "B",
            "Waiting for profile-based screening.",
            candidate_id,
        )
        card = CandidateCard(
            id=candidate_id,
            name=name,
            age=age,
            education=education,
            work_years=work_years,
            current_company=current_company,
            current_position=current_position,
            grade=placeholder_analysis.grade,
            score=placeholder_analysis.score,
            summary=placeholder_analysis.summary,
            risk_tags=[],
            collected=False,
            greeted=False,
            source="boss",
            security_id=security_id,
            lid=lid,
            encrypt_geek_id=encrypt_geek_id or None,
            encrypt_job_id=encrypt_job_id or None,
            expect_id=expect_id or None,
            design_greeting=design_greeting,
        )
        logger.info(
            "Fetched Boss candidate detail for security_id=%s lid=%s - name=%s company=%s position=%s",
            security_id, lid, name, current_company, current_position,
        )
        return CandidateDetail(
            card=card,
            timeline=timeline,
            original_resume=original_resume,
            hr_resume_sections=hr_resume_sections,
            analysis=placeholder_analysis,
        )

    def collect_candidate(self, job_id: str, *, security_id: str, encrypt_geek_id: str) -> dict[str, Any]:
        payload = {
            "markType": 5,
            "encryptMarkId": encrypt_geek_id,
            "securityId": security_id,
        }
        result = self._post_form_in_browser(RESUME_COLLECT_URL, payload, job_id)
        logger.info("Boss collect action succeeded for job %s security_id=%s", job_id, security_id)
        return result

    def greet_candidate(
        self,
        job_id: str,
        *,
        lid: str,
        security_id: str,
        encrypt_geek_id: str,
        encrypt_job_id: str,
        expect_id: str,
        design_greeting: str | None = None,
    ) -> dict[str, Any]:
        greet_text = design_greeting or ""
        # If no greeting text cached on the card, fetch candidate detail to get it
        if not greet_text and security_id and lid:
            try:
                detail = self.fetch_candidate_detail(job_id, security_id, lid)
                greet_text = detail.card.design_greeting or ""
                logger.info(
                    "Fetched design_greeting for greet action: security_id=%s greet_len=%s",
                    security_id, len(greet_text),
                )
            except BossConnectorError as exc:
                logger.warning("Failed to fetch design_greeting for greet: %s", exc)

        payload = {
            "gid": encrypt_geek_id,
            "suid": "",
            "jid": encrypt_job_id,
            "expectId": expect_id,
            "lid": lid,
            "greet": greet_text,
            "from": "",
            "securityId": security_id,
            "customGreetingGuide": -1,
        }
        result = self._post_form_in_browser(RESUME_GREET_URL, payload, job_id)
        zp_data = result.get("zpData") or {}
        if zp_data.get("chat") == 0:
            logger.warning(
                "Boss greet opened channel but sent no message (chat=0, greet_len=%s). "
                "Configure a greeting template in Boss job settings. security_id=%s job=%s",
                len(greet_text), security_id, job_id,
            )
        logger.info("Boss greet action succeeded for job %s security_id=%s lid=%s chat=%s", job_id, security_id, lid, zp_data.get("chat"))
        return result

    def get_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "cdp_url": self.cdp_url,
            "cdp_reachable": False,
            "browser_connected": False,
            "boss_page_detected": False,
            "login_cookie_detected": False,
            "job_list_available": False,
            "job_count": 0,
            "message": "",
        }

        try:
            status["cdp_reachable"] = self._probe_cdp()
        except BossConnectorError as exc:
            status["message"] = str(exc)
            return status

        try:
            tabs = self._cdp_list_tabs()
            connected = bool(tabs)
            boss_tab = next((t for t in tabs if "zhipin.com" in (t.get("url") or "")), None)
            boss_page_detected = boss_tab is not None

            login_cookie_detected = False
            if boss_tab and boss_tab.get("webSocketDebuggerUrl"):
                ws_path = parse.urlparse(boss_tab["webSocketDebuggerUrl"]).path
                result = self._cdp_ws_command(
                    ws_path, "Network.getCookies",
                    {"urls": ["https://www.zhipin.com", "https://zhipin.com"]},
                )
                login_names = {"bst", "__zp_stoken__", "wt2"}
                login_cookie_detected = any(
                    c.get("name") in login_names for c in result.get("cookies", [])
                )

            status["browser_connected"] = connected
            status["boss_page_detected"] = boss_page_detected
            status["login_cookie_detected"] = login_cookie_detected
        except Exception as exc:
            status["message"] = f"Failed to connect Boss browser: {exc}"
            return status

        status["job_list_available"] = connected and login_cookie_detected
        status["job_count"] = 0
        if connected and login_cookie_detected:
            status["message"] = "Connected. Browser and Boss login detected."
        elif connected:
            status["message"] = "Browser connected, but Boss login was not detected."
        else:
            status["message"] = "Boss browser is not connected."

        return status

    def _build_candidate_from_card(self, job_id: str, card: dict[str, Any]) -> CandidateDetail:
        security_id = str(card.get("securityId") or "")
        lid = str(card.get("lid") or "")
        geek_name = str(card.get("geekName") or "Unknown")
        age = self._parse_age(card.get("ageDesc") or "")
        education = str(card.get("geekDegree") or "Unknown")
        work_years = self._parse_work_year(card.get("geekWorkYear") or card.get("workYearDesc") or "")
        summary_parts = [
            self._normalize_resume_text(str(card.get("geekDesc") or "")),
            self._normalize_resume_text(str(card.get("applyStatusDesc") or "")),
        ]
        original_resume = " ".join(part for part in summary_parts if part).strip() or "Boss card summary only."
        candidate_id = self._build_candidate_id(security_id, lid)
        placeholder_analysis = build_analysis(
            72,
            "B",
            "Waiting for profile-based screening.",
            candidate_id,
        )

        card_model = CandidateCard(
            id=candidate_id,
            name=geek_name,
            age=age,
            education=education,
            work_years=work_years,
            current_company=str(card.get("geekCompany") or "Unknown"),
            current_position=str(card.get("geekPosition") or "Unknown"),
            grade=placeholder_analysis.grade,
            score=placeholder_analysis.score,
            summary=placeholder_analysis.summary,
            risk_tags=[],
            collected=False,
            greeted=False,
            source="boss",
            security_id=security_id or None,
            lid=lid or None,
            encrypt_geek_id=str(card.get("encryptGeekId") or "") or None,
            encrypt_job_id=str(card.get("encryptJobId") or job_id) or None,
            expect_id=str(card.get("expectId") or "") or None,
            design_greeting=str(card.get("designGreeting") or "") or None,
        )
        timeline = [
            "Boss card only. Open detail to load full work history.",
        ]
        return CandidateDetail(card=card_model, timeline=timeline, original_resume=original_resume, analysis=placeholder_analysis)

    def _build_hr_resume_sections(
        self,
        *,
        base: dict[str, Any],
        work_list: list[Any],
        edu_list: list[Any],
        project_list: list[Any],
        certificate_list: list[Any],
    ) -> list[ResumeDetailSection]:
        sections: list[ResumeDetailSection] = []

        profile_items = self._collect_labeled_values(
            base,
            [
                ("姓名", ["name"]),
                ("性别", ["genderDesc", "gender"]),
                ("年龄", ["ageDesc"]),
                ("学历", ["degreeCategory", "degreeName"]),
                ("工作年限", ["workYearDesc"]),
                ("所在城市", ["cityName", "city", "locationName"]),
                ("最近状态", ["applyStatusDesc", "jobStatusDesc"]),
                ("当前职位", ["positionName", "recentPositionName"]),
                ("当前公司", ["companyName", "recentCompanyName"]),
            ],
        )
        if profile_items:
            sections.append(ResumeDetailSection(title="个人概况", items=profile_items))

        expectation_items = self._collect_labeled_values(
            base,
            [
                ("期望职位", ["expectPositionName", "expectJobName"]),
                ("期望城市", ["expectCityNames", "expectLocationName", "expectAreaName"]),
                ("期望薪资", ["expectSalaryDesc", "salaryDesc"]),
                ("期望行业", ["expectIndustryNames", "industryName"]),
                ("求职状态", ["applyStatusDesc", "jobStatusDesc"]),
            ],
        )
        if expectation_items:
            sections.append(ResumeDetailSection(title="求职意向", items=expectation_items))

        intro_items = self._collect_labeled_values(
            base,
            [
                ("个人优势", ["advantage", "advantageDesc", "highlight"]),
                ("自我介绍", ["userDescription", "personalRemark", "selfDescription"]),
            ],
        )
        if intro_items:
            sections.append(ResumeDetailSection(title="个人亮点", items=intro_items))

        work_items = self._build_work_section_items(work_list)
        if work_items:
            sections.append(ResumeDetailSection(title="工作经历", items=work_items))

        project_items = self._build_project_section_items(project_list)
        if project_items:
            sections.append(ResumeDetailSection(title="项目经历", items=project_items))

        education_items = self._build_education_section_items(edu_list)
        if education_items:
            sections.append(ResumeDetailSection(title="教育经历", items=education_items))

        certificate_items = self._build_generic_list_section_items(certificate_list)
        if certificate_items:
            sections.append(ResumeDetailSection(title="证书/技能", items=certificate_items))

        return sections

    def _build_work_section_items(self, work_list: list[Any]) -> list[str]:
        items: list[str] = []
        for work in work_list:
            if not isinstance(work, dict):
                continue
            period = self._join_parts(
                [
                    str(work.get("startYearMonStr") or work.get("startDateDesc") or "").strip(),
                    str(work.get("endYearMonStr") or work.get("endDateDesc") or "至今").strip(),
                ],
                " - ",
            )
            headline = self._join_parts(
                [
                    period,
                    str(work.get("company") or "").strip(),
                    str(work.get("positionName") or "").strip(),
                ],
                " | ",
            )
            responsibility = self._normalize_resume_text(str(work.get("responsibility") or "").strip())
            achievement = self._normalize_resume_text(
                str(work.get("workPerformance") or work.get("achievement") or "").strip()
            )
            entry_parts = [part for part in [headline, responsibility, achievement] if part]
            if entry_parts:
                items.append("\n".join(entry_parts))
        return items

    def _build_project_section_items(self, project_list: list[Any]) -> list[str]:
        items: list[str] = []
        for project in project_list:
            if not isinstance(project, dict):
                continue
            period = self._join_parts(
                [
                    str(project.get("startYearMonStr") or project.get("startDateDesc") or "").strip(),
                    str(project.get("endYearMonStr") or project.get("endDateDesc") or "").strip(),
                ],
                " - ",
            )
            headline = self._join_parts(
                [
                    period,
                    str(project.get("projectName") or project.get("name") or "").strip(),
                    str(project.get("roleName") or project.get("role") or "").strip(),
                ],
                " | ",
            )
            description = self._normalize_resume_text(
                str(project.get("projectDescription") or project.get("description") or "").strip()
            )
            responsibility = self._normalize_resume_text(str(project.get("responsibility") or "").strip())
            entry_parts = [part for part in [headline, description, responsibility] if part]
            if entry_parts:
                items.append("\n".join(entry_parts))
        return items

    def _build_education_section_items(self, edu_list: list[Any]) -> list[str]:
        items: list[str] = []
        for edu in edu_list:
            if not isinstance(edu, dict):
                continue
            period = self._join_parts(
                [
                    str(edu.get("startYearMonStr") or edu.get("startDateDesc") or "").strip(),
                    str(edu.get("endYearMonStr") or edu.get("endDateDesc") or "").strip(),
                ],
                " - ",
            )
            headline = self._join_parts(
                [
                    period,
                    str(edu.get("school") or "").strip(),
                    str(edu.get("major") or "").strip(),
                    str(edu.get("degreeName") or edu.get("degree") or "").strip(),
                ],
                " | ",
            )
            summary = self._normalize_resume_text(str(edu.get("experience") or edu.get("summary") or "").strip())
            entry_parts = [part for part in [headline, summary] if part]
            if entry_parts:
                items.append("\n".join(entry_parts))
        return items

    def _build_generic_list_section_items(self, raw_list: list[Any]) -> list[str]:
        items: list[str] = []
        for item in raw_list:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    items.append(text)
                continue
            if not isinstance(item, dict):
                continue
            preferred = [
                item.get("name"),
                item.get("certificateName"),
                item.get("skillName"),
                item.get("title"),
                item.get("description"),
            ]
            line = self._join_parts([self._normalize_resume_text(str(value or "").strip()) for value in preferred], " | ")
            if line:
                items.append(line)
        return items

    def _collect_labeled_values(self, payload: dict[str, Any], mapping: list[tuple[str, list[str]]]) -> list[str]:
        items: list[str] = []
        for label, keys in mapping:
            for key in keys:
                value = payload.get(key)
                rendered = self._stringify_detail_value(value)
                if rendered:
                    items.append(f"{label}: {rendered}")
                    break
        return items

    def _stringify_detail_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            parts = [self._stringify_detail_value(item) for item in value]
            return " | ".join(part for part in parts if part)
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                rendered = self._stringify_detail_value(item)
                if rendered:
                    parts.append(f"{key}: {rendered}")
            return " | ".join(parts)
        text = self._normalize_resume_text(str(value).strip())
        return "" if text.lower() in {"unknown", "none", "null"} else text

    @staticmethod
    def _join_parts(parts: list[str], separator: str) -> str:
        return separator.join(part for part in parts if part)

    def _build_timeline(self, work_list: list[Any], edu_list: list[Any]) -> list[str]:
        timeline: list[str] = []
        for work in work_list:
            if not isinstance(work, dict):
                continue
            start = str(work.get("startYearMonStr") or work.get("startDateDesc") or "")
            end = str(work.get("endYearMonStr") or work.get("endDateDesc") or "")
            company = str(work.get("company") or "Unknown")
            position = str(work.get("positionName") or "Unknown")
            responsibility = self._normalize_resume_text(str(work.get("responsibility") or "").strip())
            line = f"{start}-{end} {company} | {position}"
            if responsibility:
                line += f" | {responsibility}"
            timeline.append(line)
        for edu in edu_list:
            if not isinstance(edu, dict):
                continue
            start = str(edu.get("startYearMonStr") or edu.get("startDateDesc") or "")
            end = str(edu.get("endYearMonStr") or edu.get("endDateDesc") or "")
            school = str(edu.get("school") or "Unknown school")
            major = str(edu.get("major") or "").strip()
            degree = str(edu.get("degreeName") or edu.get("degree") or "Unknown degree")
            detail = " | ".join(part for part in [major, degree] if part)
            timeline.append(f"{start}-{end} {school} | {detail or degree}")
        return timeline or ["No structured timeline was returned from Boss."]

    def _build_resume_summary(self, base: dict[str, Any], work_list: list[Any]) -> str:
        parts = [
            self._normalize_resume_text(str(base.get("userDescription") or "").strip()),
            self._normalize_resume_text(str(base.get("applyStatusDesc") or "").strip()),
        ]
        for work in work_list[:4]:
            if not isinstance(work, dict):
                continue
            responsibility = self._normalize_resume_text(str(work.get("responsibility") or "").strip())
            if responsibility:
                parts.append(responsibility)
        return "\n".join(part for part in parts if part) or "No resume text was extracted."

    def _normalize_resume_text(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        dict_match = re.search(r"'content'\s*:\s*'([^']+)'", cleaned)
        if dict_match:
            return dict_match.group(1).strip()

        json_match = re.search(r'"content"\s*:\s*"([^"]+)"', cleaned)
        if json_match:
            return json_match.group(1).strip()

        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _fetch_json_in_browser(self, url: str, *, referer: str) -> dict[str, Any]:
        cookies, user_agent = self._get_browser_session()
        headers = self._build_request_headers(cookies, user_agent, referer=referer)
        req = request.Request(url, headers=headers, method="GET")

        last_exc: Exception | None = None
        opener = request.build_opener(request.HTTPSHandler(context=_SSL_CTX))
        for attempt in range(3):
            try:
                with opener.open(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break  # 成功，跳出重试循环
            except error.HTTPError as exc:
                # HTTP 错误不重试（4xx/5xx 是明确拒绝）
                raise BossConnectorError(f"Boss HTTP error: {exc.code} {exc.reason}") from exc
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt + random.uniform(0, 1)  # 1-2s → 2-3s → 4-5s
                logger.warning(
                    "Boss fetch network error (attempt %s/3), retry in %.1fs: %s",
                    attempt + 1, wait, exc,
                )
                if attempt < 2:
                    time.sleep(wait)
        else:
            logger.error("Failed to fetch Boss URL %s after 3 attempts: %s", url, last_exc)
            raise BossConnectorError(f"Failed to fetch Boss URL: {last_exc}") from last_exc

        if not isinstance(payload, dict):
            raise BossConnectorError("Boss response payload is invalid.")
        logger.info("Boss GET %s returned: %s", url, self._summarize_payload(payload))
        if payload.get("code") != 0:
            raise BossConnectorError(str(payload.get("message") or "Boss request failed."))
        return payload

    def _post_form_in_browser(self, url: str, data: dict[str, Any], job_id: str) -> dict[str, Any]:
        cookies, user_agent = self._get_browser_session()
        referer = f"https://www.zhipin.com/web/frame/recommend/?jobid={job_id}&version=9609"
        headers = self._build_request_headers(
            cookies, user_agent, referer=referer,
            extra={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://www.zhipin.com"},
        )
        form_data = parse.urlencode(
            {k: "" if v is None else str(v) for k, v in data.items()}
        ).encode("utf-8")
        req = request.Request(url, data=form_data, headers=headers, method="POST")
        try:
            opener = request.build_opener(request.HTTPSHandler(context=_SSL_CTX))
            with opener.open(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise BossConnectorError(f"Boss HTTP error: {exc.code} {exc.reason}") from exc
        except Exception as exc:
            logger.exception("Failed to post Boss URL %s: %s", url, exc)
            raise BossConnectorError(f"Failed to post Boss action: {exc}") from exc

        if not isinstance(payload, dict):
            raise BossConnectorError("Boss action response is invalid.")
        logger.info("Boss POST %s returned: %s", url, self._summarize_payload(payload))
        if payload.get("code") != 0:
            raise BossConnectorError(str(payload.get("message") or "Boss action failed."))
        return payload

    def _get_browser_session(self) -> tuple[list[dict[str, Any]], str]:
        """Get cookies from the browser via CDP WebSocket (no Playwright required)."""
        try:
            tabs = self._cdp_list_tabs()
        except BossConnectorError:
            raise
        except Exception as exc:
            raise BossConnectorError(f"Cannot list CDP tabs: {exc}") from exc

        if not tabs:
            raise BossConnectorError("No browser tabs found. Please launch Boss login browser first.")

        # Prefer a zhipin.com tab; fall back to the first available tab.
        target = next(
            (t for t in tabs if "zhipin.com" in (t.get("url") or "")),
            tabs[0],
        )
        ws_url = target.get("webSocketDebuggerUrl") or ""
        if not ws_url:
            raise BossConnectorError("No inspectable tab found. Please launch Boss login browser first.")

        ws_path = parse.urlparse(ws_url).path
        try:
            result = self._cdp_ws_command(
                ws_path, "Network.getCookies",
                {"urls": ["https://www.zhipin.com", "https://zhipin.com"]},
            )
        except Exception as exc:
            logger.exception("Failed to get browser cookies via CDP: %s", exc)
            raise BossConnectorError(f"Failed to connect Boss browser: {exc}") from exc

        raw_cookies = result.get("cookies", [])
        if not raw_cookies:
            raise BossConnectorError("No cookies found. Please log in to Boss 直聘 in the browser first.")

        cookies = [
            {"name": c["name"], "value": c["value"],
             "domain": c.get("domain", ""), "path": c.get("path", "/")}
            for c in raw_cookies
        ]
        user_agent = self._get_user_agent_from_cdp()
        return cookies, user_agent

    def _get_user_agent_from_cdp(self) -> str:
        probe_url = f"{self.cdp_url}/json/version"
        req = request.Request(probe_url, method="GET")
        try:
            with request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return str(data.get("User-Agent") or "")
        except Exception:
            return ""

    @staticmethod
    def _build_request_headers(
        cookies: list[dict[str, Any]],
        user_agent: str,
        *,
        referer: str,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        bst_cookie = next((c for c in cookies if c["name"] == "bst"), None)
        zp_token = parse.unquote(bst_cookie["value"]) if bst_cookie else ""
        headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "zp_token": zp_token,
            "Referer": referer,
            "Cookie": cookie_header,
        }
        if user_agent:
            headers["User-Agent"] = user_agent
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _summarize_payload(payload: Any, limit: int = 1800) -> str:
        try:
            text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            text = str(payload)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > limit:
            return f"{text[:limit]}...<truncated>"
        return text

    @staticmethod
    def _extract_zpdata_list(payload: dict[str, Any], label: str) -> list[Any]:
        if payload.get("code") != 0:
            raise BossConnectorError(str(payload.get("message") or f"Boss {label} request failed."))
        zp_data = payload.get("zpData") or []
        if not isinstance(zp_data, list):
            raise BossConnectorError(f"Boss {label} zpData format is invalid.")
        return zp_data

    @staticmethod
    def _parse_age(age_text: str) -> int:
        match = re.search(r"(\d+)", age_text or "")
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_work_year(text: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
        return float(match.group(1)) if match else 0.0

    @staticmethod
    def _build_candidate_id(security_id: str, lid: str) -> str:
        return f"boss::{security_id or 'unknown'}::{lid or 'unknown'}"

    def _cdp_ws_command(self, ws_path: str, method: str, params: dict | None = None) -> dict:
        """Execute a single CDP command over a raw WebSocket connection.

        Returns the 'result' dict from the CDP response, or {} on error.
        No third-party deps — uses only stdlib socket/struct/base64.
        """
        port = int(self.cdp_url.rstrip("/").rsplit(":", 1)[-1])
        host = "127.0.0.1"
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {ws_path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock = socket.create_connection((host, port), timeout=5)
        try:
            sock.sendall(handshake.encode())
            # Consume HTTP upgrade response
            buf = b""
            while b"\r\n\r\n" not in buf:
                buf += sock.recv(4096)

            # Build masked WebSocket text frame
            cmd = json.dumps({"id": 1, "method": method, "params": params or {}}).encode()
            mask = os.urandom(4)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(cmd))
            n = len(cmd)
            if n <= 125:
                header = bytes([0x81, 0x80 | n]) + mask
            elif n <= 65535:
                header = bytes([0x81, 0xFE]) + struct.pack(">H", n) + mask
            else:
                header = bytes([0x81, 0xFF]) + struct.pack(">Q", n) + mask
            sock.sendall(header + masked)

            # Read response frame (server-to-client frames are never masked)
            raw = b""
            while True:
                raw += sock.recv(65536)
                if len(raw) < 2:
                    continue
                pl = raw[1] & 0x7F
                off = 2
                if pl == 126:
                    if len(raw) < 4:
                        continue
                    pl = struct.unpack(">H", raw[2:4])[0]
                    off = 4
                elif pl == 127:
                    if len(raw) < 10:
                        continue
                    pl = struct.unpack(">Q", raw[2:10])[0]
                    off = 10
                if len(raw) >= off + pl:
                    return json.loads(raw[off : off + pl].decode()).get("result", {})
        finally:
            sock.close()
        return {}

    def _cdp_list_tabs(self) -> list[dict]:
        tabs_url = f"{self.cdp_url}/json/list"
        req = request.Request(tabs_url, method="GET")
        try:
            with request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise BossConnectorError(f"Cannot list CDP tabs: {exc}") from exc

    def _probe_cdp(self) -> bool:
        probe_url = f"{self.cdp_url}/json/version"
        req = request.Request(probe_url, method="GET")
        try:
            with request.urlopen(req, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise BossConnectorError("Debug port 9222 is not reachable. Please launch Boss login browser first.") from exc
        except json.JSONDecodeError as exc:
            raise BossConnectorError("Debug port 9222 returned invalid data.") from exc

        return isinstance(payload, dict) and bool(payload.get("Browser"))

    def _normalize_job(self, item: dict[str, Any], job_id: str) -> JobOption:
        raw_status = item.get("jobOnlineStatus")
        status = "active" if raw_status == 1 else "paused"
        city = item.get("cityName") or item.get("city") or item.get("locationName") or item.get("jobArea") or item.get("address") or "Unknown"
        salary_desc = item.get("salaryDesc") or item.get("salary") or None
        return JobOption(
            id=job_id,
            name=str(item.get("jobName") or "Untitled Job"),
            city=str(city),
            salary_desc=str(salary_desc).strip() if salary_desc else None,
            status=status,
            profile_version_name="No profile yet",
        )

    @staticmethod
    def _get_playwright():
        BossConnector._ensure_windows_loop_policy()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BossConnectorError("Playwright is not installed, cannot connect to Boss browser.") from exc
        return sync_playwright

    @staticmethod
    def _ensure_windows_loop_policy() -> None:
        if os.name != "nt":
            return
        policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if policy_cls is None:
            return
        if not isinstance(asyncio.get_event_loop_policy(), policy_cls):
            asyncio.set_event_loop_policy(policy_cls())

    @staticmethod
    def _run_playwright_sync(func):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return func()

        result: dict[str, Any] = {}
        failure: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result["value"] = func()
            except BaseException as exc:  # noqa: BLE001
                failure["error"] = exc

        thread = threading.Thread(target=runner, name="boss-playwright-sync", daemon=True)
        thread.start()
        thread.join()

        if "error" in failure:
            raise failure["error"]
        return result.get("value")


boss_connector = BossConnector()
