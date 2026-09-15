import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAMES = (
    "image-factory-use",
    "image-factory-run",
    "image-factory-judge",
    "image-factory-recover",
)


class ConversationWorkflowTests(unittest.TestCase):
    def body(self, name: str) -> str:
        return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")

    def test_every_workflow_skill_routes_to_one_conversation_contract(self) -> None:
        contract = SKILLS / "image-factory-use" / "references" / "conversation-workflow.md"
        self.assertTrue(contract.is_file())
        for name in NAMES:
            with self.subTest(skill=name):
                self.assertIn("conversation-workflow.md", self.body(name))

    def test_conversation_contract_covers_each_user_decision(self) -> None:
        text = (
            SKILLS
            / "image-factory-use"
            / "references"
            / "conversation-workflow.md"
        ).read_text(encoding="utf-8")
        for observable in (
            "创作目标",
            "最多三个方向",
            "创作确认卡",
            "生成调用数",
            "整组批准",
            "批准 1、2、4",
            "第 3 张",
            "全部换一种风格",
        ):
            with self.subTest(observable=observable):
                self.assertIn(observable, text)

    def test_confirmation_happens_before_every_spending_round(self) -> None:
        contract = (
            SKILLS
            / "image-factory-use"
            / "references"
            / "conversation-workflow.md"
        ).read_text(encoding="utf-8")
        self.assertIn("每个会消耗额度的新轮次", contract)
        self.assertIn("用户明确同意", contract)
        self.assertIn("不得把上一轮批准沿用到下一轮", contract)

    def test_approval_is_bound_to_the_displayed_transaction(self) -> None:
        contract = (
            SKILLS
            / "image-factory-use"
            / "references"
            / "conversation-workflow.md"
        ).read_text(encoding="utf-8")
        for observable in (
            "当前轮次",
            "剩余生成调用数",
            "只对这张确认卡",
            "计划发生变化",
            "批准立即失效",
        ):
            with self.subTest(observable=observable):
                self.assertIn(observable, contract)

    def test_conversation_names_transactional_result_and_recovery_states(self) -> None:
        contract = (
            SKILLS
            / "image-factory-use"
            / "references"
            / "conversation-workflow.md"
        ).read_text(encoding="utf-8")
        for state in ("PendingApproval", "Accepted", "Unknown"):
            with self.subTest(state=state):
                self.assertIn(state, contract)
        self.assertIn("恢复本身产生 0 次生成调用", contract)
        self.assertIn("不得为了判断结果而重新生成", contract)

    def test_examples_cover_partial_rewrite_invalidation_and_unknown_recovery(self) -> None:
        examples = (
            SKILLS
            / "image-factory-use"
            / "references"
            / "conversation-examples.md"
        ).read_text(encoding="utf-8")
        for observable in (
            "第 1 轮",
            "整组批准",
            "第 3 张改成更温暖",
            "原批准立即失效",
            "Unknown",
            "恢复本身产生 0 次生成调用",
        ):
            with self.subTest(observable=observable):
                self.assertIn(observable, examples)

    def test_conversation_is_the_product_surface(self) -> None:
        text = self.body("image-factory-use")
        self.assertIn("conversation is the product surface", text.lower())
        self.assertNotRegex(text.lower(), re.compile(r"start .*web|open .*workbench"))
        self.assertIn("推荐方案", text)
        self.assertIn("不能只回复问题", text)
        self.assertIn("按推荐继续", text)

    def test_conversation_contract_routes_to_progressive_examples_and_safety(self) -> None:
        references = SKILLS / "image-factory-use" / "references"
        contract = (references / "conversation-workflow.md").read_text(encoding="utf-8")
        for filename in (
            "conversation-examples.md",
            "conversation-anti-patterns.md",
            "conversation-faq.md",
        ):
            with self.subTest(reference=filename):
                self.assertTrue((references / filename).is_file())
                self.assertIn(filename, contract)

        examples = (references / "conversation-examples.md").read_text(encoding="utf-8")
        for opening in (
            "帮我做一组小红书产后康复知识卡",
            "把这个产品做成 4 张电商系列图",
            "继续上次中断的图片批次",
        ):
            self.assertIn(opening, examples)

        anti_patterns = (references / "conversation-anti-patterns.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(anti_patterns.count("错误："), 4)
        self.assertGreaterEqual(anti_patterns.count("正确："), 4)

        faq = (references / "conversation-faq.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(faq.count("## Q"), 8)
        self.assertIn("敏感", faq)
        self.assertIn("团队", faq)


if __name__ == "__main__":
    unittest.main()
