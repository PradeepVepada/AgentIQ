"""Test script to run pipeline 1-4."""
import requests
import time
import json
import os

BASE_URL = "http://localhost:8000"

# Find a test CSV file
data_dir = "data/raw"
csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
print(f"Found {len(csv_files)} CSV files")

# Use the first test file
test_file = csv_files[0] if csv_files else None
if not test_file:
    print("No CSV files found!")
    exit(1)

print(f"Using: {test_file}")

# Step 1: Create project
print("\n=== Step 1: Create Project ===")
with open(f"{data_dir}/{test_file}", "rb") as f:
    files = {"file": (test_file, f, "text/csv")}
    data = {"project_goal": "Test pipeline run - Agents 1-4"}
    resp = requests.post(f"{BASE_URL}/projects", data=data, files=files)

print(f"Status: {resp.status_code}")
project_data = resp.json()
print(f"Project ID: {project_data.get('project_id')}")
project_id = project_data.get("project_id")

if not project_id:
    print(f"Error creating project: {project_data}")
    exit(1)

# Step 2: Run pipeline in AUTO mode (no human approval needed)
print("\n=== Step 2: Run Pipeline (Auto Mode) ===")
resp = requests.post(f"{BASE_URL}/projects/{project_id}/run?mode=auto")
print(f"Status: {resp.status_code}")
print(f"Response: {resp.json()}")

# Step 3: Poll for completion
print("\n=== Step 3: Poll for Completion ===")
max_wait = 300  # 5 minutes
interval = 5
elapsed = 0

while elapsed < max_wait:
    time.sleep(interval)
    elapsed += interval
    
    # Get state
    resp = requests.get(f"{BASE_URL}/projects/{project_id}/state")
    state = resp.json()
    current_step = state.get("CURRENT_STEP", "unknown")
    
    # Check agent outputs
    has_eda = bool(state.get("EDA_REPORT"))
    has_cleaning = bool(state.get("CLEANING_REPORT"))
    has_features = bool(state.get("FEATURE_ENGINEERING_PLAN"))
    has_models = bool(state.get("CANDIDATE_MODELS"))
    
    print(f"[{elapsed}s] Step: {current_step} | EDA: {has_eda} | Cleaning: {has_cleaning} | Features: {has_features} | Models: {has_models}")
    
    # Check if we're past agent 4
    if "agent_5" in current_step or "agent_4_complete" in str(state):
        print("\n=== Pipeline reached Agent 4! ===")
        break
    
    if "error" in current_step.lower() or state.get("ERROR"):
        print(f"\n!!! Error: {state.get('ERROR')}")
        break

# Final state
print("\n=== Final State ===")
resp = requests.get(f"{BASE_URL}/projects/{project_id}/state")
state = resp.json()
print(f"Current Step: {state.get('CURRENT_STEP')}")
print(f"EDA Report: {'YES' if state.get('EDA_REPORT') else 'NO'}")
print(f"Cleaning Report: {'YES' if state.get('CLEANING_REPORT') else 'NO'}")
print(f"Feature Plan: {'YES' if state.get('FEATURE_ENGINEERING_PLAN') else 'NO'}")
print(f"Candidate Models: {'YES' if state.get('CANDIDATE_MODELS') else 'NO'}")
print(f"Cleaned Data Path: {state.get('cleaned_data_path', 'N/A')}")
print(f"Engineered Data Path: {state.get('engineered_data_path', 'N/A')}")

# Check files exist
cleaned_path = state.get("cleaned_data_path")
engineered_path = state.get("engineered_data_path")

print(f"\nCleaned file exists: {os.path.exists(cleaned_path) if cleaned_path else 'N/A'}")
print(f"Engineered file exists: {os.path.exists(engineered_path) if engineered_path else 'N/A'}")

print("\n=== Test Complete ===")