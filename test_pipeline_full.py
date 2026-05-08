"""Test full pipeline from Agent 1-5 with error recovery."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from db.memory_storage import MemoryStorage
from agents.self_review_loop import OpenAIClientWrapper
from agents.unified_agent import AgentRunner
from app.orchestrator import PipelineOrchestrator
from agents.agent1_eda_with_review import run_agent_1_with_review
from agents.agent2_data_prep_with_review import run_agent_2_with_review
from agents.agent3_feature_eng_with_review import run_agent_3_with_review
from agents.agent4_model_arch_with_review import run_agent_4_with_review
from agents.agent5_training_with_review import run_agent_5_with_review
from openai import OpenAI
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_full_pipeline():
    """Test the full pipeline from Agent 1-5."""
    
    # Setup
    storage = MemoryStorage()
    raw_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    llm_client = OpenAIClientWrapper(raw_client)
    
    # Create orchestrator
    orchestrator = PipelineOrchestrator(storage, llm_client)
    
    # Register agents
    orchestrator.register_agent(1, AgentRunner(1, "EDA", run_agent_1_with_review))
    orchestrator.register_agent(2, AgentRunner(2, "Data Prep", run_agent_2_with_review))
    orchestrator.register_agent(3, AgentRunner(3, "Feature Eng", run_agent_3_with_review))
    orchestrator.register_agent(4, AgentRunner(4, "Model Arch", run_agent_4_with_review))
    orchestrator.register_agent(5, AgentRunner(5, "Training", run_agent_5_with_review))
    
    # Create test project
    project_id = "test_project_full"
    
    # Find a test dataset
    data_dir = Path(__file__).parent / "data" / "raw"
    test_files = list(data_dir.glob("*credit_risk*.csv"))
    
    if not test_files:
        logger.error("No test dataset found")
        return
    
    dataset_path = str(test_files[0])
    logger.info(f"Using dataset: {dataset_path}")
    
    # Create project
    await storage.create_project(
        project_id,
        "Test full pipeline with error recovery",
        dataset_path
    )
    
    await storage.update_state(
        project_id,
        DATASET_NAME=Path(dataset_path).name,
        ENABLE_REVISION_LOOP=False,  # Disable review for speed
    )
    
    # Run auto pipeline
    logger.info("=" * 80)
    logger.info("STARTING FULL PIPELINE TEST (Agents 1-5)")
    logger.info("=" * 80)
    
    result = await orchestrator.run_auto(project_id)
    
    logger.info("=" * 80)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Result: {result}")
    
    # Get final state
    final_state = await storage.get_state(project_id)
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 80)
    
    logger.info(f"Status: {final_state.get('APPROVAL_STATUS')}")
    logger.info(f"Current Step: {final_state.get('CURRENT_STEP')}")
    
    # Agent 1 results
    if final_state.get("EDA_REPORT"):
        eda = final_state["EDA_REPORT"]
        overview = eda.get("overview", {})
        logger.info(f"\n✓ Agent 1 (EDA):")
        logger.info(f"  - Rows: {overview.get('rows', 0)}")
        logger.info(f"  - Columns: {overview.get('columns', 0)}")
        logger.info(f"  - Task Type: {final_state.get('TASK_TYPE')}")
    
    # Agent 2 results
    if final_state.get("cleaning_report"):
        report = final_state["cleaning_report"]
        logger.info(f"\n✓ Agent 2 (Data Prep):")
        logger.info(f"  - Rows Processed: {report.get('rows_processed', 0)}")
        logger.info(f"  - Missing Handled: {report.get('missing_handled', 0)}")
        logger.info(f"  - Outliers Detected: {report.get('outliers_detected', 0)}")
    
    # Agent 3 results
    if final_state.get("feature_stats"):
        stats = final_state["feature_stats"]
        logger.info(f"\n✓ Agent 3 (Feature Eng):")
        logger.info(f"  - Total Features: {stats.get('total_features', 0)}")
        logger.info(f"  - Selected Features: {stats.get('selected_features', 0)}")
        logger.info(f"  - Top Features: {len(stats.get('top_features', []))}")
    
    # Agent 4 results
    if final_state.get("candidate_models"):
        models = final_state["candidate_models"]
        if isinstance(models, list):
            logger.info(f"\n✓ Agent 4 (Model Arch):")
            logger.info(f"  - Candidate Models: {len(models)}")
            for model in models[:3]:
                logger.info(f"    - {model.get('name')}")
        else:
            logger.info(f"\n✓ Agent 4 (Model Arch):")
            logger.info(f"  - Candidate Models: {len(models)}")
            for model_name in list(models.keys())[:3]:
                logger.info(f"    - {model_name}")
    
    # Agent 5 results
    if final_state.get("training_results"):
        results = final_state["training_results"]
        logger.info(f"\n✓ Agent 5 (Training):")
        logger.info(f"  - Models Trained: {len(results)}")
        for model_name, metrics in list(results.items())[:3]:
            cv_mean = metrics.get("cv_mean", 0)
            logger.info(f"    - {model_name}: {cv_mean:.4f}")
    
    # Error summary
    error_summary = await orchestrator.error_recovery.get_error_summary(project_id)
    if error_summary["total_errors"] > 0:
        logger.info(f"\n⚠ Errors Encountered: {error_summary['total_errors']}")
        logger.info(f"  - By Agent: {error_summary['by_agent']}")
        logger.info(f"  - By Type: {error_summary['by_type']}")
    else:
        logger.info(f"\n✓ No errors encountered")
    
    logger.info("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
