"""Tests for Agent Memory (Decision Journal) - Cross-Agent Context Sharing.

These tests verify:
- AgentMemory initialization and context retrieval
- Decision recording and serialization
- Dynamic suggestion generation for each agent
- Failure recording and recovery hints
- Context restoration from Firebird (mocked)
"""
from __future__ import annotations

import pytest
from datetime import datetime

from memory.agent_memory import (
    AgentMemory,
    Decision,
    DecisionType,
    DynamicSuggestionEngine,
)


class TestDecision:
    """Tests for Decision dataclass."""

    def test_decision_creation(self):
        decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp=datetime.now().isoformat(),
            summary="Quality score: 8.5/10",
            details={"quality_score": 8.5},
            confidence=0.9,
            reasoning="Comprehensive statistical analysis",
            impact="Informs imputation strategy in Agent 2"
        )
        assert decision.agent_id == 1
        assert decision.decision_type == DecisionType.ANALYSIS
        assert decision.confidence == 0.9

    def test_to_dict(self):
        decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp="2026-05-02T10:00:00",
            summary="Test",
            details={"score": 8},
            confidence=0.9
        )
        d = decision.to_dict()
        assert d["agent_id"] == 1
        assert d["decision_type"] == "analysis"
        assert d["details"]["score"] == 8

    def test_from_dict(self):
        data = {
            "agent_id": 1,
            "agent_name": "EDA",
            "decision_type": "analysis",
            "timestamp": "2026-05-02T10:00:00",
            "summary": "Test",
            "details": {"score": 8},
            "confidence": 0.9,
            "reasoning": "Test reason",
            "impact": "Test impact"
        }
        decision = Decision.from_dict(data)
        assert decision.agent_id == 1
        assert decision.decision_type == DecisionType.ANALYSIS
        assert decision.summary == "Test"


class TestAgentMemory:
    """Tests for AgentMemory class."""

    def test_initialization(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        assert memory.project_id == "test-123"
        assert memory.db is None
        assert len(memory._decisions) == 0

    def test_record_decision(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp=datetime.now().isoformat(),
            summary="Test decision",
            details={"test": True},
            confidence=0.9
        )
        memory.record_decision(decision)
        assert len(memory._decisions) == 1
        assert memory._decisions[0].summary == "Test decision"

    def test_get_agent_context_agent1(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        context = memory.get_agent_context(agent_id=1)
        assert context["project_id"] == "test-123"
        assert context["current_agent_id"] == 1
        assert context["previous_decisions"] == []  # No prior agents for Agent 1
        assert "dynamic_suggestions" in context
        assert "data_quality_summary" in context

    def test_get_agent_context_agent2(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        # Record a decision from Agent 1
        decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp=datetime.now().isoformat(),
            summary="Quality: 8/10",
            details={"quality_score": 8, "total_missing_pct": 15},
            confidence=0.9
        )
        memory.record_decision(decision)

        # Get context for Agent 2
        context = memory.get_agent_context(agent_id=2)
        assert len(context["previous_decisions"]) == 1
        assert context["data_quality_summary"]["data_quality_score"] == 8
        # Should have suggestions for Agent 2 based on 15% missing
        assert len(context["dynamic_suggestions"]) > 0

    def test_suggestions_for_high_missing(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp=datetime.now().isoformat(),
            summary="Test",
            details={"quality_score": 5, "total_missing_pct": 25},
            confidence=0.9
        )
        memory.record_decision(decision)

        context = memory.get_agent_context(agent_id=2)
        suggestions = context["dynamic_suggestions"]
        # Should have suggestion about high missing rate
        assert any("missing" in s.lower() and "25" in s for s in suggestions)

    def test_record_failure(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        memory.record_failure(
            agent_id=2,
            step="imputation",
            error="Cannot impute column 'income'",
            recovery_hint="Try KNN imputation instead"
        )

        # Should have decision recorded
        assert len(memory._decisions) == 1
        assert memory._decisions[0].decision_type == DecisionType.FAILURE

        # Should have recovery hint
        hints = memory.get_recovery_suggestions(agent_id=2)
        assert len(hints) > 0
        assert "KNN" in hints[0]

    def test_clear_session(self):
        memory = AgentMemory(project_id="test-123", db_client=None)
        decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp=datetime.now().isoformat(),
            summary="Test",
            details={},
            confidence=0.9
        )
        memory.record_decision(decision)
        assert len(memory._decisions) == 1

        memory.clear_session()
        assert len(memory._decisions) == 0


class TestDynamicSuggestionEngine:
    """Tests for DynamicSuggestionEngine."""

    def test_suggest_for_small_dataset(self):
        suggestions = DynamicSuggestionEngine.suggest_for_agent1(
            df_shape=(50, 10),
            col_types={"numeric": ["a", "b"], "categorical": ["c", "d", "e"]}
        )
        assert any("Small dataset" in s for s in suggestions)

    def test_suggest_for_large_dataset(self):
        suggestions = DynamicSuggestionEngine.suggest_for_agent1(
            df_shape=(2_000_000, 20),
            col_types={"numeric": ["a", "b"], "categorical": ["c", "d"]}
        )
        assert any("Large dataset" in s for s in suggestions)

    def test_suggest_for_high_dimensionality(self):
        suggestions = DynamicSuggestionEngine.suggest_for_agent1(
            df_shape=(1000, 150),
            col_types={"numeric": ["a", "b"], "categorical": []}
        )
        assert any("High dimensionality" in s for s in suggestions)

    def test_suggest_for_agent2_high_missing(self):
        eda_report = {
            "missing_analysis": [
                {"column": "income", "missing_pct": 35},
                {"column": "age", "missing_pct": 5}
            ],
            "outlier_analysis": []
        }
        suggestions = DynamicSuggestionEngine.suggest_for_agent2(eda_report)
        assert any("High missing" in s for s in suggestions)

    def test_suggest_for_agent3_high_pn_ratio(self):
        suggestions = DynamicSuggestionEngine.suggest_for_agent3(
            cleaned_shape=(100, 50),
            feature_count=50
        )
        assert any("p/n ratio" in s.lower() or "overfitting" in s.lower() for s in suggestions)


class TestAgentMemoryIntegration:
    """Integration tests for multi-agent memory flow."""

    def test_full_pipeline_context_flow(self):
        """Test that context flows correctly from Agent 1 through Agent 6."""
        memory = AgentMemory(project_id="pipeline-test", db_client=None)

        # Agent 1 records EDA decision
        eda_decision = Decision(
            agent_id=1,
            agent_name="EDA",
            decision_type=DecisionType.ANALYSIS,
            timestamp=datetime.now().isoformat(),
            summary="Quality: 7.5/10",
            details={
                "quality_score": 7.5,
                "total_missing_pct": 12,
                "duplicate_rows": 50,
                "critical_missing_cols": [],
                "multicollinearity_risk": "medium",
            },
            confidence=0.95,
            reasoning="Full EDA analysis"
        )
        memory.record_decision(eda_decision)

        # Agent 2 gets context
        ctx2 = memory.get_agent_context(agent_id=2)
        assert len(ctx2["previous_decisions"]) == 1
        assert ctx2["data_quality_summary"]["total_missing_pct"] == 12
        assert any("missing" in s.lower() for s in ctx2["dynamic_suggestions"])

        # Agent 2 records cleaning decision
        prep_decision = Decision(
            agent_id=2,
            agent_name="Data Prep",
            decision_type=DecisionType.IMPUTATION,
            timestamp=datetime.now().isoformat(),
            summary="Cleaned 950 rows",
            details={
                "rows_before": 1000,
                "rows_after": 950,
                "rows_removed": 50,
            },
            confidence=0.9
        )
        memory.record_decision(prep_decision)

        # Agent 3 gets context from both
        ctx3 = memory.get_agent_context(agent_id=3)
        assert len(ctx3["previous_decisions"]) == 2
        assert ctx3["previous_decisions"][0]["agent_id"] == 1
        assert ctx3["previous_decisions"][1]["agent_id"] == 2

    def test_failure_recovery_flow(self):
        """Test that failures are recorded and recovery hints are available."""
        memory = AgentMemory(project_id="failure-test", db_client=None)

        # Agent 2 fails
        memory.record_failure(
            agent_id=2,
            step="imputation",
            error="Cannot impute column 'income' with mean",
            recovery_hint="Try KNN imputation instead of mean"
        )

        # Agent 6 can get recovery suggestions
        hints = memory.get_recovery_suggestions(agent_id=2)
        assert len(hints) > 0
        assert "KNN" in hints[0]

        # Known issues should include the failure
        ctx = memory.get_agent_context(agent_id=3)
        assert len(ctx["known_issues"]) > 0
        assert any("Agent 2" in issue for issue in ctx["known_issues"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])