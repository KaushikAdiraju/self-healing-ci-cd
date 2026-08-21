# agent/server.py
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from agent.graph import healing_app

app = FastAPI(title="Self-Healing CI/CD Agent")

class GitHubWebhookPayload(BaseModel):
    repo: str
    run_id: str
    commit: str

def run_agent_workflow(payload_data: dict):
    print(f"\n[Agent] Starting remediation workflow for run_id: {payload_data['run_id']}...")
    try:
        final_state = healing_app.invoke({
            "repo": payload_data["repo"],
            "run_id": payload_data["run_id"],
            "commit": payload_data["commit"]
        })
        print(f"[Agent] Successfully healed! Created branch: {final_state.get('branch_name')}")
    except Exception as e:
        print(f"[Agent] Error during self-healing workflow: {e}")

@app.post("/webhook")
async def handle_ci_failure(payload: GitHubWebhookPayload, background_tasks: BackgroundTasks):
    # Process in the background so GitHub Action doesn't hang waiting for the LLM
    background_tasks.add_task(run_agent_workflow, payload.model_dump())
    return {"status": "received", "message": "Self-healing triggered"}

if __name__ == "__main__":
    uvicorn.run("agent.server:app", host="0.0.0.0", port=8000, reload=True)