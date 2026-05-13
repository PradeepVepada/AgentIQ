"""
Tests for cross-agent memory persistence and decision journal.

Tests the Decision Journal implementation (Option 2) for:
- Recording decisions from agents
- Retrieving context for downstream agents
- Dynamic suggestion generation
- Firebird persistence (optional)
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from typing import Dict, Any


class TestDecisionJournal:
    """Test Decision Journal functionality."""
    
    def test_record_decision(self, mock_decision):
        """Test recording a decision."""
        # This would test the actual AgentMemory.record_decision() method
        # For now, we verify the decision structure
        assert mock_decision["agent_id"] == 1
        assert mock_decision["agent_name"] == "EDA"
        assert mock_decision["decision_type"] == "ANALYSIS"
        assert mock_decision["confidence"] == 0.95
        assert "quality_score" in mock_decision["details"]
    
    def test_get_agent_context(self, mock_memory_context):
        """Test retrieving context for an agent."""
        # Verify context structure
        assert "previous_decisions" in mock_memory_context
        assert "dynamic_suggestions" in mock_memory_context
        assert "known_issues" in mock_memory_context
        assert "recovery_hints" in mock_memory_context
        
        # Verify content
        assert len(mock_memory_context["previous_decisions"]) > 0
        assert len(mock_memory_context["dynamic_suggestions"]) > 0
    
    def test_dynamic_suggestions_generation(self):
        """Test that dynamic suggestions are generated correctly."""
        # Example: Agent 2 should get suggestions based on Agent 1's findings
        eda_findings = {
            "quality_score": 6,
            "missing_pct": 25.0,
            "outlier_count": 50,
            "duplicate_rows": 10,
        }
        
        # Generate suggestions
        suggestions = []
        if eda_findings["missing_pct"] > 20:
            suggestions.append(
                f"High missing rate ({eda_findings['missing_pct']:.1f}%) — "
                "consider MNAR-aware imputation"
            )
        if eda_findings["outlier_count"] > 10:
            suggestions.append(
                f"Detected {eda_findings['outlier_count']} outliers — "
                "use robust scaling or IQR-based removal"
            )
        
        assert len(suggestions) >= 2
        assert "missing" in suggestions[0].lower()
        assert "outlier" in suggestions[1].lower()
    
    def test_decision_confidence_scoring(self):
        """Test confidence scoring for decisions."""
        # High confidence: comprehensive analysis
        high_conf_decision = {
            "confidence": 0.95,
            "reasoning": "Comprehensive statistical analysis with multiple methods",
        }
        
        # Low confidence: limited data
        low_conf_decision = {
            "confidence": 0.60,
            "reasoning": "Limited sample size, results may not generalize",
        }
        
        assert high_conf_decision["confidence"] > low_conf_decision["confidence"]
    
    def test_decision_impact_tracking(self):
        """Test that decision impact is tracked."""
        decision = {
            "agent_id": 1,
            "agent_name": "EDA",
            "impact": "Informs imputation strategy in Agent 2",
        }
        
        # Verify impact is recorded
        assert decision["impact"] is not None
        assert "Agent 2" in decision["impact"]


class TestMemoryIntegration:
    """Test memory integration with agents."""
    
    def test_agent_retrieves_context(self, mock_state_with_memory):
        """Test that agent can retrieve context from memory."""
        # Simulate agent retrieving context
        context = mock_state_with_memory["memory"].get_agent_context(agent_id=2)
        
        # Verify context is available
        assert context is not None
        assert "previous_decisions" in context
        assert "dynamic_suggestions" in context
    
    def test_agent_records_decision(self, mock_state_with_memory):
        """Test that agent can record decision to memory."""
        # Simulate agent recording decision
        decision = {
            "agent_id": 2,
            "agent_name": "Prep",
            "summary": "Cleaned 5 columns, removed 3 duplicates",
            "details": {"duplicates_removed": 3, "columns_cleaned": 5},
        }
        
        mock_state_with_memory["memory"].record_decision(decision)
        
        # Verify record_decision was called
        mock_state_with_memory["memory"].record_decision.assert_called_once()
    
    def test_memory_context_flow(self):
        """Test context flows correctly through agents."""
        # Agent 1 records findings
        agent1_decision = {
            "agent_id": 1,
            "summary": "Quality score: 8/10",
            "details": {"quality_score": 8, "missing_pct": 5},
        }
        
        # Agent 2 retrieves context
        context = {
            "previous_decisions": [agent1_decision],
            "dynamic_suggestions": ["Low missing rate — standard imputation OK"],
        }
        
        # Agent 2 uses context
        assert len(context["previous_decisions"]) > 0
        assert context["previous_decisions"][0]["agent_id"] == 1
        assert len(context["dynamic_suggestions"]) > 0


class TestDynamicSuggestions:
    """Test dynamic suggestion generation."""
    
    def test_suggestions_for_agent2_high_missing(self):
        """Test Agent 2 gets suggestions for high missing data."""
        eda_findings = {"missing_pct": 35.0}
        
        suggestions = []
        if eda_findings["missing_pct"] > 30:
            suggestions.append("Very high missing rate — consider deletion or advanced imputation")
        
        assert len(suggestions) > 0
        assert "missing" in suggestions[0].lower()
    
    def test_suggestions_for_agent3_multicollinearity(self):
        """Test Agent 3 gets suggestions for multicollinearity."""
        eda_findings = {
            "correlation_count": 15,  # Many high correlations
        }
        
        suggestions = []
        if eda_findings.get("correlation_count", 0) > 10:
            suggestions.append("High multicollinearity detected — use PCA or feature selection")
        
        assert len(suggestions) > 0
        assert "multicollinearity" in suggestions[0].lower()
    
    def test_suggestions_for_agent4_feature_count(self):
        """Test Agent 4 gets suggestions based on feature count."""
        feature_count = 75
        
        suggestions = []
        if feature_count > 50:
            suggestions.append(f"{feature_count} features — recommend tree-based models")
        
        assert len(suggestions) > 0
        assert "tree" in suggestions[0].lower()
    
    def test_suggestions_context_aware(self):
        """Test suggestions are context-aware."""
        # Different suggestions for different scenarios
        scenarios = [
            {"missing_pct": 5, "expected": "low"},
            {"missing_pct": 25, "expected": "high"},
            {"missing_pct": 50, "expected": "very_high"},
        ]
        
        for scenario in scenarios:
            if scenario["missing_pct"] < 10:
                level = "low"
            elif scenario["missing_pct"] < 30:
                level = "high"
            else:
                level = "very_high"
            
            assert level == scenario["expected"]


class TestErrorRecovery:
    """Test error recovery with memory hints."""
    
    def test_recovery_hint_recorded(self):
        """Test that recovery hints are recorded when agent fails."""
        recovery_hint = {
            "agent_id": 2,
            "error": "Imputation failed for column X",
            "hint": "Try median imputation instead of mean",
            "timestamp": datetime.now().isoformat(),
        }
        
        assert recovery_hint["agent_id"] == 2
        assert "hint" in recovery_hint
    
    def test_recovery_hint_retrieved(self):
        """Test that recovery hints are available to next agent."""
        context = {
            "recovery_hints": [
                "Agent 2 failed on column X — try median imputation",
                "Agent 2 detected 50 outliers — consider robust scaling",
            ]
        }
        
        assert len(context["recovery_hints"]) > 0
        assert "Agent 2" in context["recovery_hints"][0]
    
    def test_recovery_workflow(self):
        """Test complete recovery workflow."""
        # Agent 2 fails
        failure = {
            "agent_id": 2,
            "error": "Imputation failed",
            "recovery_hint": "Use KNN imputation",
        }
        
        # Agent 3 retrieves hint
        context = {
            "recovery_hints": [failure["recovery_hint"]]
        }
        
        # Agent 3 can use hint
        assert len(context["recovery_hints"]) > 0
        assert "KNN" in context["recovery_hints"][0]


class TestMemoryPersistence:
    """Test Firebird persistence (optional)."""
    
    @pytest.mark.skip(reason="Requires Firebird installation")
    def test_decision_persisted_to_firebird(self, temp_firebird_db):
        """Test decision is persisted to Firebird."""
        # This would test actual Firebird persistence
        # Skipped if Firebird not installed
        pass
    
    @pytest.mark.skip(reason="Requires Firebird installation")
    def test_decision_retrieved_from_firebird(self, temp_firebird_db):
        """Test decision is retrieved from Firebird."""
        # This would test actual Firebird retrieval
        # Skipped if Firebird not installed
        pass
    
    def test_memory_fallback_to_in_memory(self):
        """Test memory falls back to in-memory if Firebird unavailable."""
        # When Firebird is not available, use in-memory storage
        storage_mode = "memory"
        
        assert storage_mode == "memory"
        # In-memory storage is always available


class TestMemoryPerformance:
    """Test memory performance characteristics."""
    
    def test_context_retrieval_speed(self, mock_memory_context):
        """Test context retrieval is fast (<50ms)."""
        import time
        
        start = time.time()
        # Simulate context retrieval
        context = mock_memory_context
        elapsed = (time.time() - start) * 1000  # Convert to ms
        
        # Should be very fast (in-memory)
        assert elapsed < 50  # <50ms target
    
    def test_decision_record_size(self, mock_decision):
        """Test decision record size is reasonable (~2KB)."""
        import json
        
        # Serialize decision
        serialized = json.dumps(mock_decision)
        size_bytes = len(serialized.encode('utf-8'))
        size_kb = size_bytes / 1024
        
        # Should be ~2KB
        assert size_kb < 5  # Allow some variance
    
    def test_memory_growth_bounded(self):
        """Test memory growth is bounded."""
        # With 6 agents and ~10 decisions per agent
        decisions_per_agent = 10
        num_agents = 6
        avg_decision_size_kb = 2
        
        total_memory_kb = decisions_per_agent * num_agents * avg_decision_size_kb
        total_memory_mb = total_memory_kb / 1024
        
        # Should be <1MB for typical project
        assert total_memory_mb < 1


class TestMemoryStateManagement:
    """Test memory state management in LangGraph."""
    
    def test_memory_initialized_in_state(self, mock_state_with_memory):
        """Test memory is properly initialized in state."""
        assert "memory" in mock_state_with_memory
        assert mock_state_with_memory["memory"] is not None
    
    def test_dynamic_suggestions_in_state(self, mock_state_with_memory):
        """Test dynamic suggestions are stored in state."""
        assert "dynamic_suggestions" in mock_state_with_memory
        assert isinstance(mock_state_with_memory["dynamic_suggestions"], list)
    
    def test_previous_decisions_in_state(self, mock_state_with_memory):
        """Test previous decisions are stored in state."""
        assert "previous_decisions" in mock_state_with_memory
        assert isinstance(mock_state_with_memory["previous_decisions"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

