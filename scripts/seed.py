"""
Seed Script — Create demo org, admin user, and sample data
"""
import asyncio
import os
import uuid
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://rag_user:password@localhost:5432/rag_assistant")


async def seed():
    engine = create_async_engine(DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    from shared.models.organization import Organization
    from shared.models.user import User

    async with Session() as session:
        # Create demo organization
        org = Organization(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Enterprise Demo Corp",
            slug="enterprise-demo",
            plan="enterprise",
            settings={
                "departments": ["Legal", "HR", "Finance", "IT", "Sales", "Engineering", "Marketing"],
                "default_llm_provider": "openai",
                "max_file_size_mb": 100,
            },
            max_documents=100000,
            max_users=1000,
            max_storage_gb=1000,
        )
        session.add(org)

        # Create admin user
        admin = User(
            org_id=org.id,
            email="admin@enterprise.dev",
            full_name="System Admin",
            role="admin",
            is_active=True,
        )
        session.add(admin)

        # Create sample employees
        sample_users = [
            ("sarah.kim@enterprise.dev", "Sarah Kim", "manager"),
            ("john.doe@enterprise.dev", "John Doe", "employee"),
            ("mike.ross@enterprise.dev", "Mike Ross", "employee"),
            ("emma.legal@enterprise.dev", "Emma Legal", "manager"),
            ("viewer.user@enterprise.dev", "Viewer User", "viewer"),
        ]
        for email, name, role in sample_users:
            u = User(org_id=org.id, email=email, full_name=name, role=role, is_active=True)
            session.add(u)

        await session.commit()

        print("\n✅ Seed data created successfully!")
        print("=" * 50)
        print(f"  Organization: {org.name}")
        print(f"  Slug:         {org.slug}")
        print(f"  Plan:         {org.plan}")
        print()
        print("  Admin credentials:")
        print("  Email:    admin@enterprise.dev")
        print("  Password: (set in Keycloak or via /auth/register)")
        print()
        print(f"  Sample users created: {len(sample_users)}")
        print("=" * 50)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
