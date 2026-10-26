"""Explicit, repeatable local demo setup. Never resets an existing account."""

import argparse
import time
from urllib.parse import urlparse

import httpx

EMAIL = "demo@lumina.local"
PASSWORD = "LuminaDemo!2026"
SAMPLES = {
    "people-handbook.txt": (
        "HR",
        """LUMINA DEMO — FICTIONAL SAMPLE DOCUMENT

Annual leave policy
Employees receive 24 days of paid annual leave each calendar year. Submit leave requests to your manager at least five working days before the first day of leave. Managers approve requests in the people portal. Up to five unused days may carry forward until March 31 of the following year.

Remote work
Team members may work remotely up to three days per week. Keep your team calendar current and use the approved VPN when accessing company systems. Core collaboration hours are 10:00 to 15:00 local team time.

Onboarding
Your first week includes account setup, a security introduction, a meeting with your buddy, and a review of team goals. Your manager schedules a 30-day check-in.
""",
    ),
    "engineering-playbook.md": (
        "Engineering",
        """# Lumina demo engineering playbook

This is fictional sample knowledge for exploring the application.

## Release process
Every change starts in a feature branch and receives a peer review. Run unit tests, type checking, and a production build before merging. The release owner checks the staging environment and publishes release notes. If a release causes errors, revert the change and record a follow-up task.

## Incident response
The on-call engineer acknowledges an incident within 15 minutes. Identify the affected service, record a timeline, and post an update every 30 minutes. Prepare a blameless review within two working days after resolution.

## Documentation
Store setup instructions, ownership details, and troubleshooting notes with the relevant service. Review documentation during each major release.
""",
    ),
    "it-access-guide.txt": (
        "IT",
        """LUMINA DEMO — FICTIONAL IT GUIDE

Access requests
Request application access through the IT service desk. Include the system name, business reason, and your manager's approval. Standard requests are reviewed within two working days. Temporary access expires after 30 days unless renewed.

Account protection
Use a unique password and enable multi-factor authentication on company accounts. Never send credentials in chat or commit API keys to a repository. Report suspicious sign-in activity to the service desk.

Offboarding
IT revokes application sessions, removes group memberships, and reassigns owned resources after the approved offboarding request. Managers confirm that handover documentation is complete.
""",
    ),
}


def seed(api="http://127.0.0.1:8000", origin="http://localhost:3100"):
    if urlparse(api).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "Public demo credentials may only be seeded into a loopback API."
        )
    with httpx.Client(
        base_url=api.rstrip("/") + "/api/v2/", headers={"Origin": origin}, timeout=30
    ) as client:
        credentials = {"email": EMAIL, "password": PASSWORD}
        login = client.post("auth/login", json=credentials)
        if login.status_code != 200:
            created = client.post(
                "auth/register",
                json={
                    **credentials,
                    "name": "Demo Explorer",
                    "organization": "Lumina Demo",
                },
            )
            if created.status_code != 201:
                raise RuntimeError(
                    "Demo account could not be created. An existing account is never reset. Check registration settings and the allowed Origin."
                )
        existing = client.get("documents")
        existing.raise_for_status()
        names = {doc["name"] for doc in existing.json()}
        for name, (department, content) in SAMPLES.items():
            if name not in names:
                uploaded = client.post(
                    "documents",
                    data={"department": department},
                    files={"file": (name, content.encode(), "text/plain")},
                )
                uploaded.raise_for_status()
        for _ in range(60):
            docs = client.get("documents").json()
            if all(
                doc["status"] == "indexed" for doc in docs if doc["name"] in SAMPLES
            ):
                break
            if any(doc["status"] == "failed" for doc in docs):
                raise RuntimeError("A demo document could not be indexed.")
            time.sleep(0.5)
        else:
            raise RuntimeError("Demo indexing did not finish before the timeout.")
        me = client.get("me").json()
        conversations = client.get("conversations").json()
        # Demonstrate real retrieval without automatically making a paid model call.
        if (
            not any(c["title"] == "Leave policy · quick tour" for c in conversations)
            and not me["provider"]["configured"]
        ):
            conversation = client.post(
                "conversations", json={"title": "Leave policy · quick tour"}
            )
            conversation.raise_for_status()
            response = client.post(
                f"conversations/{conversation.json()['id']}/messages",
                json={
                    "query": "What is the annual leave policy and how do I request time off?",
                    "top_k": 1,
                },
            )
            response.raise_for_status()
            if "event: done" not in response.text:
                raise RuntimeError("The sample conversation did not complete.")
        print("Local demo ready: demo@lumina.local / LuminaDemo!2026")
        print("Workspace: Lumina Demo | Three explicitly fictional sample documents")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--origin", default="http://localhost:3100")
    args = parser.parse_args()
    seed(args.api, args.origin)
