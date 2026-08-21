# agent/graph.py
import os
import requests
import base64
from typing import TypedDict, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

load_dotenv()

# --- 1. State Definition ---
class AgentState(TypedDict):
    repo: str
    run_id: str
    commit: str
    logs: Optional[str]
    target_file: Optional[str]
    file_content: Optional[str]
    file_sha: Optional[str]
    fixed_code: Optional[str]
    branch_name: Optional[str]
    pr_title: Optional[str]
    pr_body: Optional[str]

# --- 2. Structured Output Schema ---
class FixSchema(BaseModel):
    branch_name: str = Field(description="Unique branch name, e.g., fix/calculator-bug-1")
    file_path: str = Field(description="Relative path of file to fix, e.g., app/calculator.py")
    fixed_code: str = Field(description="Complete, fully corrected source code for the file")
    pr_title: str = Field(description="Concise PR title")
    pr_body: str = Field(description="Markdown formatted explanation of the bug and fix applied")

GH_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# --- 3. Node Definitions ---

def fetch_context_node(state: AgentState) -> dict:
    repo, run_id = state["repo"], state["run_id"]
    
    # 1. Fetch failing job logs
    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    jobs_resp = requests.get(jobs_url, headers=HEADERS)
    jobs_resp.raise_for_status()
    jobs_data = jobs_resp.json()
    job_id = jobs_data["jobs"][0]["id"]
    
    log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    log_resp = requests.get(log_url, headers=HEADERS)
    logs = log_resp.text if log_resp.status_code == 200 else "No logs retrieved."
    
    # 2. Fetch the target file content (app/calculator.py)
    file_path = "app/calculator.py"
    content_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    file_resp = requests.get(content_url, headers=HEADERS)
    file_resp.raise_for_status()
    file_data = file_resp.json()
    raw_content = base64.b64decode(file_data["content"]).decode("utf-8")
    
    return {
        "logs": logs[-3500:],  # Tail last 3500 chars to fit within context
        "target_file": file_path,
        "file_content": raw_content,
        "file_sha": file_data["sha"]
    }

def diagnose_and_fix_node(state: AgentState) -> dict:
    # Initialize Groq with Llama 3.3 / Llama 3.1
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )
    structured_llm = llm.with_structured_output(FixSchema)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an automated DevOps engineer and Python expert. "
                   "Analyze the CI/CD failure logs and the source code, identify the bug, "
                   "and produce the complete fixed file."),
        ("user", "Target File: {file_path}\n\nCurrent Code:\n```python\n{code}\n```\n\nFailure Logs:\n{logs}")
    ])
    
    chain = prompt | structured_llm
    fix: FixSchema = chain.invoke({
        "file_path": state["target_file"],
        "code": state["file_content"],
        "logs": state["logs"]
    })
    
    return {
        "fixed_code": fix.fixed_code,
        "branch_name": fix.branch_name,
        "pr_title": fix.pr_title,
        "pr_body": fix.pr_body
    }

def apply_patch_and_pr_node(state: AgentState) -> dict:
    repo = state["repo"]
    branch = state["branch_name"]
    
    # 1. Create a new branch off the failing commit
    ref_url = f"https://api.github.com/repos/{repo}/git/refs"
    ref_payload = {
        "ref": f"refs/heads/{branch}",
        "sha": state["commit"]
    }
    requests.post(ref_url, headers=HEADERS, json=ref_payload)
    
    # 2. Update the target file with fixed code
    update_url = f"https://api.github.com/repos/{repo}/contents/{state['target_file']}"
    encoded_code = base64.b64encode(state["fixed_code"].encode("utf-8")).decode("utf-8")
    update_payload = {
        "message": state["pr_title"],
        "content": encoded_code,
        "sha": state["file_sha"],
        "branch": branch
    }
    requests.put(update_url, headers=HEADERS, json=update_payload)
    
    # 3. Open a Pull Request back to main
    pr_url = f"https://api.github.com/repos/{repo}/pulls"
    pr_payload = {
        "title": state["pr_title"],
        "body": state["pr_body"],
        "head": branch,
        "base": "main"
    }
    pr_resp = requests.post(pr_url, headers=HEADERS, json=pr_payload)
    print("PR Response Status:", pr_resp.status_code)
    
    return {}

# --- 4. Assemble Graph ---
workflow = StateGraph(AgentState)
workflow.add_node("fetch_context", fetch_context_node)
workflow.add_node("diagnose_and_fix", diagnose_and_fix_node)
workflow.add_node("apply_patch_and_pr", apply_patch_and_pr_node)

workflow.set_entry_point("fetch_context")
workflow.add_edge("fetch_context", "diagnose_and_fix")
workflow.add_edge("diagnose_and_fix", "apply_patch_and_pr")
workflow.add_edge("apply_patch_and_pr", END)

healing_app = workflow.compile()