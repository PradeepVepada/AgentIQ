"""Configuration for self-review loops."""
# Review loop settings per agent
REVIEW_CONFIG = {
    "agent_1_eda": {
        "max_iterations": 3,
        "approval_threshold": 0.8,  # How confident LLM must be
        "quality_check": True,
        "track_history": True,
    },
    "agent_2_prep": {
        "max_iterations": 2,  # Data prep usually simpler
        "approval_threshold": 0.85,
        "quality_check": True,
        "track_history": True,
    },
    "agent_3_features": {
        "max_iterations": 3,
        "approval_threshold": 0.8,
        "quality_check": True,
        "track_history": True,
    },
    "agent_4_architecture": {
        "max_iterations": 2,
        "approval_threshold": 0.85,
        "quality_check": True,
        "track_history": True,
    },
    "agent_5_training": {
        "max_iterations": 1,  # Training is deterministic, less need for review
        "approval_threshold": 0.9,
        "quality_check": True,
        "track_history": True,
    },
    "agent_6_evaluation": {
        "max_iterations": 2,
        "approval_threshold": 0.85,
        "quality_check": True,
        "track_history": True,
    },
}
