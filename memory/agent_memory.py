"""Cross-Agent Memory & Context Management (Decision Journal)

Lightweight decision journal for sharing context across the 6-agent LangGraph pipeline.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Classification of agent decisions."""
    # Agent 1
    ANALYSIS = "analysis"
    # Agent 2
    CLEANING = "cleaning"
    IMPUTATION = "imputation"
    # Agent 3
    FEATURE_ENGINEERING = "feature_engineering"
    SELECTION = "selection"
    # Agent 4
    MODEL_SELECTION = "model_selection"
    ARCHITECTURE = "architecture"
    # Agent 5
    TRAINING = "training"
    # Agent 6
    EVALUATION = "evaluation"
    # General
    FAILURE = "failure"
    APPROVAL = "approval"


@dataclass
class Decision:
    """Atomic decision made by an agent."""
    agent_id: int
    agent_name: str
    decision_type: DecisionType
    timestamp: str
    summary: str
    details: Dict[str, Any]
    confidence: float = 0.5
    reasoning: str = ""
    impact: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "decision_type": self.decision_type.value,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "details": self.details,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "impact": self.impact,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        return cls(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            decision_type=DecisionType(data["decision_type"]),
            timestamp=data["timestamp"],
            summary=data["summary"],
            details=data.get("details", {}),
            confidence=data.get("confidence", 0.5),
            reasoning=data.get("reasoning", ""),
            impact=data.get("impact", ""),
        )


class AgentMemory:
    """Lightweight in-memory + Firebird-backed memory store."""

    def __init__(self, project_id: str, db_client: Optional[Any] = None):
        self.project_id = project_id
        self.db = db_client
        self._decisions: List[Decision] = []
        self._context_cache: Dict[str, Any] = {}
        self._failure_hints: Dict[str, str] = {}
        logger.info("[Memory] Initialized for project %s", project_id)

    def record_decision(self, decision: Decision) -> None:
        self._decisions.append(decision)
        logger.info("[Memory] Agent %s recorded: %s", decision.agent_id, decision.summary)
        if self.db and hasattr(self.db, "log_decision"):
            try:
                self.db.log_decision(self.project_id, decision.to_dict())
            except Exception as e:
                logger.warning("[Memory] Failed to persist decision: %s", e)

    def get_agent_context(self, agent_id: int) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "current_agent_id": agent_id,
            "previous_decisions": self._get_decisions_before(agent_id),
            "data_quality_summary": self._get_quality_summary(),
            "known_issues": self._get_known_issues(),
            "dynamic_suggestions": self._get_suggestions_for_agent(agent_id),
            "context_retrieved_at": datetime.now().isoformat(),
        }

    def _get_decisions_before(self, agent_id: int) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._decisions if d.agent_id < agent_id]

    def _get_quality_summary(self) -> Dict[str, Any]:
        agent1 = [d for d in self._decisions if d.agent_id == 1]
        if not agent1:
            return {"note": "Agent 1 EDA not yet executed"}
        d = agent1[-1]
        return {
            "data_quality_score": d.details.get("quality_score"),
            "total_missing_pct": d.details.get("total_missing_pct"),
            "duplicate_count": d.details.get("duplicate_rows"),
            "multicollinearity_risk": d.details.get("multicollinearity_risk"),
            "critical_missing_cols": d.details.get("critical_missing_cols", []),
            "outlier_columns": d.details.get("outlier_columns", []),
        }

    def _get_known_issues(self) -> List[str]:
        return [
            f"[Agent {d.agent_id}] {d.summary}"
            for d in self._decisions
            if d.decision_type == DecisionType.FAILURE
        ]

    def _get_suggestions_for_agent(self, agent_id: int) -> List[str]:
        suggestions = []
        if agent_id == 2:
            quality = self._get_quality_summary()
            missing_pct = quality.get("total_missing_pct") or 0
            if missing_pct > 10:
                suggestions.append(
                    f"High missing rate ({missing_pct:.1f}%). Consider MNAR-aware imputation."
                )
        elif agent_id == 4:
            agent3 = [d for d in self._decisions if d.agent_id == 3]
            if agent3:
                fc = agent3[-1].details.get("feature_count", 0)
                if fc > 50:
                    suggestions.append(
                        f"{fc} features — prefer tree-based models (RF, XGBoost)."
                    )
        return suggestions

    def record_failure(self, agent_id: int, step: str, error: str, recovery_hint: str) -> None:
        self._failure_hints[f"agent_{agent_id}_{step}"] = recovery_hint
        self.record_decision(Decision(
            agent_id=agent_id,
            agent_name=f"Agent {agent_id}",
            decision_type=DecisionType.FAILURE,
            timestamp=datetime.now().isoformat(),
            summary=f"Failed at step: {step}",
            details={"error": error, "step": step, "recovery_hint": recovery_hint},
            confidence=0.0,
        ))

    def clear_session(self) -> None:
        self._decisions.clear()
        self._context_cache.clear()

    def restore_from_firebird(self, decisions_json: List[Dict[str, Any]]) -> None:
        self._decisions.clear()
        for d in decisions_json:
            try:
                self._decisions.append(Decision.from_dict(d))
            except Exception as e:
                logger.warning("[Memory] Failed to restore decision: %s", e)


class DynamicSuggestionEngine:
    """Generate contextual suggestions for each agent."""

    @staticmethod
    def suggest_for_agent1(df_shape: tuple, col_types: Dict[str, List[str]]) -> List[str]:
        suggestions = []
        rows, cols = df_shape
        if rows < 100:
            suggestions.append(f"Small dataset ({rows} rows). Results may have high variance.")
        if cols > 100:
            suggestions.append(f"High dimensionality ({cols} columns). Plan for feature selection.")
        return suggestions
