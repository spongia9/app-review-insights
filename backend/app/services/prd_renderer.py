from typing import List

from app.models import AnalysisOutputLanguage, StructuredPRD


def render_prd_markdown(
    prd: StructuredPRD,
    output_language: AnalysisOutputLanguage,
) -> str:
    chinese = output_language == AnalysisOutputLanguage.ZH_CN
    labels = {
        "goal": "产品目标" if chinese else "Product Goal",
        "background": "背景" if chinese else "Background",
        "scope": "分析范围" if chinese else "Analysis Scope",
        "problems": "用户问题" if chinese else "User Problems",
        "findings": "洞察摘要" if chinese else "Findings Summary",
        "requirements": "产品需求" if chinese else "Product Requirements",
        "release": "版本规划" if chinese else "Release Plan",
        "criteria": "验收标准" if chinese else "Acceptance Criteria",
        "evidence": "证据摘要" if chinese else "Evidence Summary",
        "assumptions": "假设项" if chinese else "Assumptions",
        "limitations": "已知限制" if chinese else "Known Limitations",
        "references": "来源" if chinese else "Sources",
        "none": "无" if chinese else "None",
    }
    reference_separator = "：" if chinese else ":"
    lines: List[str] = [f"# {prd.title}", "", f"## {labels['goal']}", "", prd.product_goal]
    lines.extend(["", f"## {labels['background']}", "", prd.background])
    lines.extend(["", f"## {labels['scope']}", "", prd.analysis_scope])

    def append_sections(label: str, sections: list) -> None:
        lines.extend(["", f"## {label}", ""])
        for section in sections:
            lines.extend([f"### {section.title}", "", section.content])
            references = [
                *section.finding_ids,
                *section.requirement_ids,
                *section.version_item_ids,
            ]
            if references:
                lines.extend(["", f"**{labels['references']}{reference_separator}** {', '.join(references)}"])
            lines.append("")

    append_sections(labels["problems"], prd.user_problems)
    append_sections(labels["findings"], prd.findings_summary)
    append_sections(labels["requirements"], prd.requirements)
    append_sections(labels["release"], prd.release_plan)
    append_sections(labels["criteria"], prd.acceptance_criteria)
    append_sections(labels["evidence"], [prd.evidence_summary])

    lines.extend([f"## {labels['assumptions']}", ""])
    lines.extend(
        [f"- {item}" for item in prd.assumptions]
        or [f"- {labels['none']}"]
    )
    lines.extend(["", f"## {labels['limitations']}", ""])
    lines.extend(
        [f"- {item}" for item in prd.limitations]
        or [f"- {labels['none']}"]
    )
    return "\n".join(lines).strip() + "\n"
