#!/usr/bin/env python3
"""
Sets up Google Cloud Pub/Sub topics and push subscriptions to connect
the Shot-Delivery Guardian pipeline stages on Cloud Run.
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


def run_cmd(cmd, capture=False):
    print(f"\n[EXEC] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    is_shell = True if os.name == "nt" else isinstance(cmd, str)
    if capture:
        res = subprocess.run(cmd, cwd=ROOT_DIR, shell=is_shell, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    else:
        subprocess.run(cmd, cwd=ROOT_DIR, shell=is_shell, check=False)


def main():
    load_env()
    project_id = os.environ.get("GCP_PROJECT_ID")
    region = os.environ.get("GCP_REGION", "us-central1")

    if not project_id:
        print("ERROR: GCP_PROJECT_ID is not set in .env")
        sys.exit(1)

    print(f"Setting up Pub/Sub topics & subscriptions (Project: {project_id}, Region: {region})")

    topics = ["shot-render", "shot-color", "shot-qc", "shot-delivery"]
    for topic in topics:
        print(f"\nCreating topic: {topic}")
        run_cmd(["gcloud", "pubsub", "topics", "create", topic, "--project", project_id])

    stages = [
        ("shot-render-sub", "shot-render", "render"),
        ("shot-color-sub", "shot-color", "color"),
        ("shot-qc-sub", "shot-qc", "qc"),
        ("shot-delivery-sub", "shot-delivery", "delivery"),
    ]

    for sub_name, topic, service in stages:
        print(f"\nCreating push subscription: {sub_name} -> shot-{service}")
        try:
            service_url = run_cmd(
                ["gcloud", "run", "services", "describe", f"shot-{service}", "--region", region, "--project", project_id, "--format=value(status.url)"],
                capture=True
            )
            push_endpoint = f"{service_url}/pubsub/push"
            print(f"Service URL: {service_url} -> Push Endpoint: {push_endpoint}")
            run_cmd([
                "gcloud", "pubsub", "subscriptions", "create", sub_name,
                "--topic", topic,
                "--push-endpoint", push_endpoint,
                "--project", project_id
            ])
        except Exception as e:
            print(f"Error setting up subscription for {service}: {e}")

    print("\n" + "=" * 60)
    print("PUBSUB SETUP COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
