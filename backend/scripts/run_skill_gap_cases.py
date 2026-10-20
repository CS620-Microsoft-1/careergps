"""Create an organized three-résumé bundle and obtain actual Agent results, without a DB."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import BACKEND_ROOT
from app.schemas.skill_gap_extraction import ReviewedResume
from app.services.skill_gap_agent import SkillGapAgentError, call_foundry
from scripts.test_skill_gap_local import FIXTURES, save_json
from scripts.test_skill_gap_pipeline import run as run_pipeline

CASES = [
    ("01_foundational_student", "基础阶段应届生", "Jamie Example"),
    ("02_frontend_developer", "前端项目型应届生", "Morgan Example"),
    ("03_backend_developer", "后端与部署型应届生", "Riley Example"),
]
COMPLEX_CASES = [
    ("01_backend_data", "复杂后端与数据工程", "Avery Example"),
    ("02_frontend_fullstack", "复杂前端与全栈", "Taylor Example"),
    ("03_systems_research", "复杂系统与研究开发", "Casey Example"),
]


def readable_resume(reviewed: ReviewedResume) -> str:
    resume = reviewed.classification
    lines = [f"# {resume.personal_information.name}", "",
             "Fictional résumé for local Skill Gap testing. All experiences are invented.", "",
             resume.personal_information.location or "", "", "## Education", ""]
    for entry in resume.education:
        lines += [f"### {entry.institution}", "",
                  f"{entry.degree} — {entry.major} ({entry.start_date} to {entry.end_date})", ""]
        lines += [f"- {line}" for line in entry.content]
        lines += [""]
    lines += ["## Work experience", ""]
    if not resume.work_experience:
        lines += ["No work experience supplied.", ""]
    for entry in resume.work_experience:
        lines += [f"### {entry.title} — {entry.company}", "",
                  f"{entry.start_date} to {entry.end_date}", ""]
        lines += [f"- {line}" for line in entry.content]
        lines += [""]
    if resume.research_experience:
        lines += ["## Research experience", ""]
        for entry in resume.research_experience:
            lines += [f"### {entry.title} — {entry.organization}", "",
                      f"{entry.start_date} to {entry.end_date}", ""]
            lines += [f"- {line}" for line in entry.content]
            lines += [""]
    lines += ["## Projects", ""]
    for entry in resume.projects:
        lines += [f"### {entry.name}", "", f"Technologies: {', '.join(entry.technologies)}", ""]
        lines += [f"- {line}" for line in entry.content]
        lines += [""]
    lines += ["## Technical skills", "", ", ".join(resume.technical_skills), ""]
    if resume.research_interests:
        lines += ["## Research interests", "", "; ".join(resume.research_interests), ""]
    if resume.publications:
        lines += ["## Publications", ""]
        for entry in resume.publications:
            lines += [f"### {entry.title}", "", f"{entry.authors} — {entry.venue}, {entry.date}", ""]
            lines += [f"- {line}" for line in entry.content]
            lines += [""]
    for title, entries in (("Certifications", resume.certifications), ("Awards and honors", resume.awards_honors)):
        if entries:
            lines += [f"## {title}", ""]
            for entry in entries:
                lines += [f"### {entry.name}", "", f"{entry.issuer}, {entry.date}", ""]
                lines += [f"- {line}" for line in entry.content]
                lines += [""]
    if resume.leadership_activities:
        lines += ["## Leadership activities", ""]
        for entry in resume.leadership_activities:
            lines += [f"### {entry.role} — {entry.organization}", "",
                      f"{entry.start_date} to {entry.end_date}", ""]
            lines += [f"- {line}" for line in entry.content]
            lines += [""]
    if resume.languages:
        lines += ["## Languages", ""]
        lines += [f"- {entry.name}: {entry.proficiency}" for entry in resume.languages]
        lines += [""]
    if resume.other:
        lines += ["## Additional information", ""]
        lines += [entry.content for entry in resume.other]
        lines += [""]
    return "\n".join(lines)


def summarize(root: Path, outcomes: list[dict], expected_count: int = 3) -> bool:
    successes = [row for row in outcomes if row["passed"]]
    for row in successes:
        source = Path(row["run_dir"])
        destination = root / row["case_id"]
        for name, alias in (
            ("extract_job_requirements_raw.txt", "agent_job_requirements.json"),
            ("extract_resume_evidence_raw.txt", "agent_resume_evidence.json"),
            ("explain_skill_gaps_raw.txt", "agent_final_response.json"),
            ("result.json", "result.json"), ("report.md", "report.md"),
        ):
            shutil.copyfile(source / name, destination / alias)
        for name in ("job_descriptions.json", "target_scope.json", "resume_evidence_audit.json", "market_skill_counts.json"):
            shutil.copyfile(source / name, destination / name)
    market_signatures = set()
    for row in successes:
        run_dir = Path(row["run_dir"])
        market = json.loads((run_dir / "market_profile.json").read_text(encoding="utf-8"))
        counts = json.loads((run_dir / "market_skill_counts.json").read_text(encoding="utf-8"))["skills"]
        # Quote selection may vary without changing statistics. Compare the actual counts, not prose.
        signature = {key: market[key] for key in (
            "target_role", "seniority", "window_days", "sample_size", "company_count", "low_confidence",
        )}
        signature["skills"] = sorted([
            {key: item[key] for key in ("skill", "postings", "denominator", "required_postings",
                                        "preferred_only_postings", "frequency")}
            for item in counts if item["postings"] > 0
        ], key=lambda item: item["skill"].casefold())
        market_signatures.add(json.dumps(signature, sort_keys=True))
    comparable = len(successes) == expected_count and len(market_signatures) == 1
    summary = {"database_used": False, "data_source": "synthetic", "agent_calls": "actual Azure calls",
               "all_passed": len(successes) == expected_count, "market_statistics_identical": comparable,
               "cases": outcomes}
    save_json(root / "comparison.json", summary)
    lines = ["# 三份虚拟简历：Skill Gap Agent 返回对比", "",
             "全部简历和招聘内容均为虚构。每个案例均通过完整三阶段流程实际调用 Azure Agent，结果只保存本地。", "",
             "## 运行状态", "", "| 案例 | 虚拟姓名 | 状态 |", "|---|---|---|"]
    for row in outcomes:
        lines += [f"| {row['label']} | {row['name']} | {'通过' if row['passed'] else '失败，查看运行目录'} |"]
    lines += ["", f"市场统计一致性：{'三个案例的市场统计相同，可在相同需求基准下比较。' if comparable else '未通过一致性检查；不要把差异全部归因于简历。'}", ""]
    if successes:
        lines += ["## 需求、证据分和缺口分", "",
                  "每格为：简历证据分 / 缺口分 / 优先级。排名不代表用户的真实能力。", ""]
        labels = [row["label"] for row in successes]
        lines += ["| 技能 | 需求比例 | " + " | ".join(labels) + " |",
                  "|---|---:|" + "---|" * len(labels)]
        results = [row["result"] for row in successes]
        skills = sorted({g["skill"] for result in results for g in result["gaps"]}, key=str.casefold)
        for skill in skills:
            cells = []
            frequencies = set()
            for result in results:
                item = next((g for g in result["gaps"] if g["skill"] == skill), None)
                if item:
                    frequencies.add(item["market_frequency"])
                    cells.append(f"{item['user_evidence_score']:.2f} / {item['gap_score']:.2f} / {item['priority']}")
                else:
                    cells.append("未返回")
            frequency = f"{next(iter(frequencies)):.0%}" if len(frequencies) == 1 else "各运行不同"
            lines += [f"| {skill} | {frequency} | " + " | ".join(cells) + " |"]
    for row in successes:
        result = row["result"]
        lines += ["", f"## {row['label']} — {row['name']}", "", result["summary"], "",
                  "前三项返回建议：", ""]
        for gap in result["gaps"][:3]:
            lines += [f"- **{gap['skill']}**（{gap['priority']}，{gap['gap_score']}）：{gap['recommended_action']}",
                      f"  完成证明：{gap['completion_evidence']}"]
    lines += ["", "## 解读边界", "",
              "- 输入岗位混合前端、后端、平台和全栈，统一目标为入门级 Software Engineer。前端或后端简历的跨方向缺口不等于其目标方向上的不胜任。",
              "- 样本筛选后仅五个岗位，所有结果应为低样本置信度。",
              "- 当前需求比例合并必需与加分项；例如 Docker 的 80% 中只有 20% 为必需，其余为加分项。",
              "- Agent 类别判断和原文引用可能随调用变化；数值由 Python 映射、统计并校验。",
              "- 评分不是能力测验。不同条目重复验证文字可能触发满分的已知规则问题仍未修改。", ""]
    (root / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    return summary["all_passed"] and comparable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--case-set", choices=("basic", "complex"))
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--resume-bundle", type=Path, help="Continue a previously created bundle, preserving all attempts.")
    args = parser.parse_args()
    saved_config = None
    if args.resume_bundle and (args.resume_bundle / "bundle_config.json").exists():
        saved_config = json.loads((args.resume_bundle / "bundle_config.json").read_text(encoding="utf-8"))
    case_set = args.case_set or (saved_config["case_set"] if saved_config else "basic")
    if saved_config and saved_config["case_set"] != case_set:
        raise ValueError("The selected case set does not match the existing bundle.")
    cases = COMPLEX_CASES if case_set == "complex" else CASES
    fixture_dir = "complex_resume_cases" if case_set == "complex" else "resume_cases"
    output_dir = args.output_dir or BACKEND_ROOT / "local_results" / "skill_gap" / fixture_dir
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = (args.resume_bundle.resolve() if args.resume_bundle else
            output_dir.resolve() / f"{stamp}_{uuid4().hex[:8]}")
    if args.resume_bundle:
        if not root.is_dir():
            raise ValueError("The bundle to resume does not exist.")
    else:
        root.mkdir(parents=True, exist_ok=False)
    save_json(root / "bundle_config.json", {"case_set": case_set, "case_ids": [row[0] for row in cases]})
    shared = root / "shared_inputs"
    shared.mkdir(exist_ok=True)
    for name in ("job_descriptions.json", "target_scope.json"):
        if not args.resume_bundle:
            shutil.copyfile(FIXTURES / name, shared / name)
        shutil.copyfile(shared / name, root / name)
    jobs = []
    for case_id, label, name in cases:
        source = (root / case_id / "reviewed_resume.json" if args.resume_bundle else
                  FIXTURES / fixture_dir / case_id / "reviewed_resume.json")
        reviewed = ReviewedResume.model_validate_json(source.read_text(encoding="utf-8"))
        folder = root / case_id
        folder.mkdir(exist_ok=True)
        if not args.resume_bundle:
            shutil.copyfile(source, folder / "reviewed_resume.json")
        (folder / "resume.md").write_text(readable_resume(reviewed), encoding="utf-8")
        jobs.append((case_id, label, name, folder))
    readme = """# 三份虚拟简历与实际 Agent 返回

先打开 comparison.md 查看对比分析，comparison.json 提供完整机器可读对比。

每个案例文件夹包含：

- resume.md：可读英文虚拟简历。
- reviewed_resume.json：当前 Review 页面对应的完整输入格式，没有预填分数。
- agent_job_requirements.json、agent_resume_evidence.json、agent_final_response.json：成功运行的三次原始 Agent 返回，直接放在案例目录便于查看。
- result.json、report.md：成功运行的最终计算结果和可读报告，直接放在案例目录。
- job_descriptions.json、target_scope.json：与该简历一起分析的完整模拟岗位输入和目标条件，每个案例目录和总目录都保存一份。
- resume_evidence_audit.json、market_skill_counts.json：本次评分与统计所依据的原文引用。
- runs/<运行编号>/：完整三阶段流程的输入副本、Agent 请求、原始返回、证据审计及结果。
- 最常用的结果文件为 report.md（可读报告）和 result.json（最终结果）。
- extract_job_requirements_raw.txt：岗位技能提取原始返回。
- extract_resume_evidence_raw.txt：简历证据提取原始返回。
- explain_skill_gaps_raw.txt：最终解释原始返回。
- resume_evidence_audit.json、market_skill_counts.json：原文引用、证据评分和统计依据。

shared_inputs/ 保存三份简历共用的岗位原文与筛选条件。相同请求的岗位提取可以在同一批次中共享真实返回；comparison.md 会检查最终市场统计是否相同。

运行遇到 Azure 限流时会串行等待并重试。继续已有 bundle 时，成功案例直接复用；已完成且请求内容完全一致的中间提取也可以复用真实返回。每个运行的 agent_call_audit.json 记录缓存来源和实际调用，失败记录保留在 runs/。

全部人物、公司和经历均为虚构；实际调用 Azure Agent。结果本地保存，不连接数据库。此目录受 backend/local_results/ 的 Git 忽略规则保护。
"""
    (root / "README.md").write_text(readme, encoding="utf-8")
    print(f"Bundle: {root}", flush=True)

    def execute(job):
        case_id, label, name, folder = job
        print(f"Starting {case_id}", flush=True)
        previous = sorted((folder / "runs").glob("*_pipeline_*"), reverse=True) if (folder / "runs").exists() else []
        for candidate in previous:
            metadata_path = candidate / "run.json"
            if metadata_path.exists() and (candidate / "result.json").exists():
                if json.loads(metadata_path.read_text(encoding="utf-8")).get("status") == "passed":
                    return {"case_id": case_id, "label": label, "name": name, "passed": True,
                            "run_dir": str(candidate), "reused_successful_run": True,
                            "result": json.loads((candidate / "result.json").read_text(encoding="utf-8"))}
        audit = []

        def live_agent(request, prompt, settings):
            task = request["task"]
            cache_candidates = list(previous)
            if task == "extract_job_requirements":
                cache_candidates.extend(sorted(root.glob("*/runs/*_pipeline_*"), reverse=True))
            for candidate in cache_candidates:
                request_path = candidate / f"{task}_request.json"
                raw_path = candidate / f"{task}_raw.txt"
                prior_prompt = candidate / "prompt.md"
                metadata_path = candidate / "run.json"
                if not all(p.exists() for p in (request_path, raw_path, prior_prompt, metadata_path)):
                    continue
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("failed_stage") == task:
                    continue
                if (json.loads(request_path.read_text(encoding="utf-8")) == request
                        and prior_prompt.read_text(encoding="utf-8") == prompt):
                    print(f"{case_id}: reusing completed {task}", flush=True)
                    audit.append({"task": task, "kind": "cached_actual_agent_response", "source": str(raw_path)})
                    return raw_path.read_text(encoding="utf-8")
            for attempt in range(4):
                audit.append({"task": task, "kind": "actual_agent_call", "attempt": attempt + 1,
                              "started_at": datetime.now(timezone.utc).isoformat()})
                try:
                    return call_foundry(request, prompt, settings)
                except SkillGapAgentError as error:
                    if "rate limit" not in str(error).lower() or attempt == 3:
                        raise
                    audit[-1]["error"] = "rate limited"
                    delay = min(30 * (attempt + 1), 60)
                    print(f"{case_id}: Azure rate limit; retrying {task} after {delay}s", flush=True)
                    time.sleep(delay)

        run_dir, passed = run_pipeline(argparse.Namespace(
            resume=folder / "reviewed_resume.json", postings=shared / "job_descriptions.json",
            scope=shared / "target_scope.json", output_dir=folder / "runs",
        ), live_agent, agent_mode="live")
        save_json(run_dir / "agent_call_audit.json", {"calls": audit})
        row = {"case_id": case_id, "label": label, "name": name,
               "passed": passed, "run_dir": str(run_dir)}
        if passed:
            row["result"] = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        return row

    outcomes = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(execute, job): job[0] for job in jobs}
        for future in as_completed(futures):
            row = future.result()
            outcomes.append(row)
            print(f"Finished {row['case_id']}: {row['passed']}", flush=True)
    outcomes.sort(key=lambda row: row["case_id"])
    passed = summarize(root, outcomes, expected_count=len(cases))
    print(f"Comparison: {root / 'comparison.md'}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
