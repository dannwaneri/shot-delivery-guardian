#!/usr/bin/env python3
"""
Cross-platform deployment script for Shot-Delivery Guardian.
Builds Docker images, pushes to Container Registry / Artifact Registry,
and deploys each microservice and the Gemini AI agent to Google Cloud Run.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_env():
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k not in os.environ:
                os.environ[k] = v


def run_cmd(cmd, cwd=None, capture=False):
    print(f"\n[EXEC] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    is_shell = True if os.name == "nt" else isinstance(cmd, str)
    if capture:
        res = subprocess.run(
            cmd, cwd=cwd or ROOT_DIR, shell=is_shell, capture_output=True, text=True, check=True
        )
        return res.stdout.strip()
    else:
        subprocess.run(cmd, cwd=cwd or ROOT_DIR, shell=is_shell, check=True)


def main():
    load_env()
    project_id = os.environ.get("GCP_PROJECT_ID")
    region = os.environ.get("GCP_REGION", "us-central1")
    otlp_endpoint = os.environ.get("GRAFANA_OTLP_ENDPOINT", "")
    instance_id = os.environ.get("GRAFANA_INSTANCE_ID", "")
    otlp_token = os.environ.get("GRAFANA_OTLP_TOKEN", "")
    grafana_url = os.environ.get("GRAFANA_STACK_URL", "")
    service_account_token = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")

    if not project_id:
        print("ERROR: GCP_PROJECT_ID is not set in .env")
        sys.exit(1)

    print(f"Deploying Shot-Delivery Guardian to Google Cloud Run (Project: {project_id}, Region: {region})")

    # 1. Configure Docker for GCR
    print("\n--- 1. Authenticating Docker with GCR ---")
    run_cmd(["gcloud", "auth", "configure-docker", "gcr.io", "--quiet", "--project", project_id])

    # 2. Deploy Pipeline Services
    def deploy_service(name: str, dockerfile: str, extra_env: str = ""):
        image = f"gcr.io/{project_id}/shot-{name}"
        env_vars = (
            f"GCP_PROJECT_ID={project_id},"
            f"OTLP_ENDPOINT={otlp_endpoint},"
            f"GRAFANA_INSTANCE_ID={instance_id},"
            f"GRAFANA_OTLP_TOKEN={otlp_token}"
        )
        if extra_env:
            env_vars += f",{extra_env}"

        print(f"\n>>> Building and deploying pipeline stage: shot-{name} <<<")
        run_cmd(["docker", "build", "-f", dockerfile, "-t", image, "."])
        run_cmd(["docker", "push", image])
        run_cmd([
            "gcloud", "run", "deploy", f"shot-{name}",
            "--image", image,
            "--region", region,
            "--project", project_id,
            "--allow-unauthenticated",
            "--set-env-vars", env_vars
        ])

    deploy_service("scheduler", "pipeline/scheduler/Dockerfile")
    deploy_service("ingest", "pipeline/ingest/Dockerfile")
    deploy_service("render", "pipeline/render/Dockerfile")
    deploy_service("color", "pipeline/color/Dockerfile")
    deploy_service("qc", "pipeline/qc/Dockerfile")
    deploy_service("delivery", "pipeline/delivery/Dockerfile")

    # 3. Deploy Chaos Service with live URLs
    print("\n--- Getting live URLs for Ingest and Scheduler ---")
    ingest_url = run_cmd(
        ["gcloud", "run", "services", "describe", "shot-ingest", "--region", region, "--project", project_id, "--format=value(status.url)"],
        capture=True
    )
    scheduler_url = run_cmd(
        ["gcloud", "run", "services", "describe", "shot-scheduler", "--region", region, "--project", project_id, "--format=value(status.url)"],
        capture=True
    )

    deploy_service(
        "chaos",
        "pipeline/chaos/Dockerfile",
        f"INGEST_URL={ingest_url}/ingest,SCHEDULER_URL={scheduler_url}/shots"
    )

    # 4. Deploy Guardian Agent
    print("\n>>> Building and deploying: shot-agent <<<")
    agent_image = f"gcr.io/{project_id}/shot-agent"
    run_cmd(["docker", "build", "-f", "agent/Dockerfile", "-t", agent_image, "."])
    run_cmd(["docker", "push", agent_image])

    agent_env = (
        f"GRAFANA_STACK_URL={grafana_url},"
        f"GRAFANA_SERVICE_ACCOUNT_TOKEN={service_account_token},"
        f"GCP_PROJECT_ID={project_id},"
        f"GCP_REGION={region}"
    )
    if "GEMINI_API_KEY" in os.environ:
        agent_env += f",GEMINI_API_KEY={os.environ['GEMINI_API_KEY']}"

    run_cmd([
        "gcloud", "run", "deploy", "shot-agent",
        "--image", agent_image,
        "--region", region,
        "--project", project_id,
        "--allow-unauthenticated",
        "--set-env-vars", agent_env
    ])

    agent_url = run_cmd(
        ["gcloud", "run", "services", "describe", "shot-agent", "--region", region, "--project", project_id, "--format=value(status.url)"],
        capture=True
    )

    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE!")
    print(f"Agent URL: {agent_url}/investigate")
    print("Next step: run python infra/pubsub_setup.py to wire Pub/Sub message queues.")
    print("=" * 60)


if __name__ == "__main__":
    main()
