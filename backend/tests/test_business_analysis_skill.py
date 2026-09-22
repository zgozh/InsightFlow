"""经营分析 skill 测试（Phase 3 任务 6）。

skill 只规定**顺序与证据要求**，不实现 SQL 策略、访问控制或凭证访问。这里固定：

- frontmatter 合法、名字与目录一致；
- 架构 §5 的九个步骤顺序都在（目录 → 单条查询 → Analyst → Reviewer → 一次修订 → artifact → 摘要）；
- Reviewer 被明确要求不查询数据库、不创建子 Agent；
- 不含固定表名、示例真实 SQL、凭据或 PII。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "public" / "business-analysis"
SKILL_PATH = SKILL_DIR / "SKILL.md"


def _text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_the_skill_file_exists_with_frontmatter():
    text = _text()

    assert text.startswith("---\n")
    frontmatter = text.split("---", 2)[1]
    assert re.search(r"^name:\s*business-analysis$", frontmatter, flags=re.MULTILINE)
    assert re.search(r"^description:\s*\S", frontmatter, flags=re.MULTILINE)


def test_the_frontmatter_matches_the_directory_name():
    from deerflow.skills.validation import _validate_skill_frontmatter

    valid, message, name = _validate_skill_frontmatter(SKILL_DIR)

    assert valid, message
    assert name == "business-analysis"


@pytest.mark.parametrize(
    "marker",
    [
        "inspect_business_catalog",
        "query_business_data",
        "publish_analysis_report",
        "general-purpose",
        "Data Analyst",
        "Reviewer",
        "evidence_id",
        "result_digest",
        "/mnt/user-data/outputs",
        "present_files",
    ],
)
def test_the_workflow_names_every_required_element(marker):
    assert marker in _text()


def test_the_workflow_orders_catalog_then_a_single_query_then_analysis_then_review():
    # 只看「步骤」正文：frontmatter 与「工具」小节里也会出现同样的名字。
    body = _text().split("## 步骤", 1)[1]
    positions = [body.index(token) for token in ("inspect_business_catalog", "每次只调用一次", "Data Analyst", "委派 Reviewer", "最多一次定向修订")]
    # Phase 4：报告索引登记必须排在 artifact 交付之后。
    positions.append(body.index("`present_files` 交付"))
    positions.append(body.index("**登记报告索引**"))
    positions.append(body.index("publish_analysis_report", body.index("**登记报告索引**")))

    assert positions == sorted(positions)


def test_the_skill_publishes_only_after_a_successful_presentation():
    text = _text()

    assert "只有** `present_files` 成功之后才调用 `publish_analysis_report`" in text
    # 发布失败不得被描述成"已保存"。
    assert "绝不能把未登记的报告说成" in text
    assert "report_conflict" in text and "existing" in text
    # 索引不含文件内容：工具不复制、不上传。
    assert "不读文件内容" in text or "不会复制或上传文件" in text


def test_the_skill_requires_serial_queries_and_forbids_automatic_retry():
    text = _text()

    assert "串行" in text
    assert "不要重试同一条" in text or "不要因为一次失败就自动重新查询" in text


def test_the_reviewer_is_explicitly_forbidden_from_querying_or_nesting():
    text = _text()

    assert "不要**查询数据库" in text or "不要**查询数据库、不要创建子 Agent" in text
    assert "不要创建子 Agent" in text


def test_the_skill_does_not_treat_its_own_rules_as_the_security_boundary():
    text = _text()

    assert "不实现任何 SQL 策略、访问控制或凭证访问" in text
    assert "由平台的受控查询工具执行" in text


def test_the_skill_carries_no_sql_table_names_credentials_or_pii():
    text = _text()

    for banned in ("SELECT ", "FROM ", "secret_ref", "password", "postgres://", "mysql://", "env://", "public.orders", "api_key"):
        assert banned not in text, banned
    # 没有内联代码块里塞真实 SQL 示例。
    assert "```sql" not in text


def test_the_skill_does_not_claim_tools_the_agent_does_not_have():
    text = _text()

    assert "token" not in text.lower() or "token 或任何凭据" in text
