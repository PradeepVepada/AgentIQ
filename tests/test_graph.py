"""Tests for LangGraph orchestration."""
from __future__ import annotations

import pytest

from workflows.graph import (
    build_pipeline_graph,
    route_eda_approval,
    route_prep_approval,
    route_feature_approval,
    route_model_approval,
    route_training_status,
    route_eval_approval,
)


class TestBuildGraph:
    def test_compiles_successfully(self):
        g = build_pipeline_graph()
        compiled = g.compile()
        assert compiled is not None

    def test_has_all_agent_nodes(self):
        g = build_pipeline_graph()
        nodes = list(g.nodes.keys())
        assert "agent_1_eda" in nodes
        assert "agent_2_prep" in nodes
        assert "agent_3_features" in nodes
        assert "agent_4_architecture" in nodes
        assert "agent_5_training" in nodes
        assert "agent_6_evaluation" in nodes

    def test_has_all_human_gates(self):
        g = build_pipeline_graph()
        nodes = list(g.nodes.keys())
        assert "human_gate_1" in nodes
        assert "human_gate_2" in nodes
        assert "human_gate_3" in nodes
        assert "human_gate_4" in nodes
        assert "human_gate_6" in nodes


class TestRoutingEDA:
    def test_approved_routes_to_agent2(self):
        state = {"approval_status": "approved"}
        assert route_eda_approval(state) == "agent_2_prep"

    def test_revision_routes_to_agent1(self):
        state = {"approval_status": "revision_requested"}
        assert route_eda_approval(state) == "agent_1_eda"

    def test_rejected_routes_to_end(self):
        state = {"approval_status": "rejected"}
        from langgraph.graph import END
        assert route_eda_approval(state) == END


class TestRoutingPrep:
    def test_approved_routes_to_agent3(self):
        state = {"approval_status": "approved"}
        assert route_prep_approval(state) == "agent_3_features"

    def test_revision_routes_to_agent2(self):
        state = {"approval_status": "revision_requested"}
        assert route_prep_approval(state) == "agent_2_prep"


class TestRoutingFeature:
    def test_approved_routes_to_agent4(self):
        state = {"approval_status": "approved"}
        assert route_feature_approval(state) == "agent_4_architecture"


class TestRoutingModel:
    def test_approved_routes_to_agent5(self):
        state = {"approval_status": "approved"}
        assert route_model_approval(state) == "agent_5_training"


class TestRoutingTraining:
    def test_no_error_routes_to_evaluation(self):
        state = {"error": None}
        assert route_training_status(state) == "agent_6_evaluation"

    def test_error_with_retry_routes_to_agent5(self):
        state = {"error": "some error", "retry_count": 1}
        assert route_training_status(state) == "agent_5_training"

    def test_max_retries_routes_to_end(self):
        state = {"error": "some error", "retry_count": 3}
        from langgraph.graph import END
        assert route_training_status(state) == END


class TestRoutingEval:
    def test_approved_routes_to_end(self):
        state = {"approval_status": "approved"}
        from langgraph.graph import END
        assert route_eval_approval(state) == END

    def test_revision_routes_to_agent3(self):
        state = {"approval_status": "revision_requested"}
        assert route_eval_approval(state) == "agent_3_features"
