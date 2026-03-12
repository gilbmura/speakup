"""
seed.py - Seed default categories and SYS_ADMIN user.
Run: python seed.py
"""
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import SessionLocal, engine
from app.models import Base, User, UserRole, Category
from app.security import hash_password
from sqlalchemy import select

def seed():
    # Create tables if they don't exist yet
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ── Default categories ────────────────────────────────────────────
        default_categories = ["Roads", "Water", "Waste", "Safety", "Other"]
        for name in default_categories:
            exists = db.execute(select(Category).where(Category.name == name)).scalars().first()
            if not exists:
                db.add(Category(name=name))
                print(f"  ✓ Category '{name}' created")
            else:
                print(f"  - Category '{name}' already exists")

        # ── SYS_ADMIN user ────────────────────────────────────────────────
        admin_email = "admin@speakup.rw"
        existing_admin = db.execute(select(User).where(User.email == admin_email)).scalars().first()
        if not existing_admin:
            admin = User(
                name="System Administrator",
                email=admin_email,
                password_hash=hash_password("Admin123!"),
                role=UserRole.SYS_ADMIN,
            )
            db.add(admin)
            print(f"  ✓ SYS_ADMIN created: {admin_email} / Admin123!")
        else:
            print(f"  - Admin user already exists")

        # ── Demo authority users ──────────────────────────────────────────
        demo_users = [
            {
                "name": "Local Authority Gasabo",
                "email": "local@speakup.rw",
                "password": "Local123!",
                "role": UserRole.LOCAL_AUTHORITY,
                "district": "Gasabo",
                "sector": None,
            },
            {
                "name": "MINALOC Officer",
                "email": "minaloc@speakup.rw",
                "password": "Minaloc123!",
                "role": UserRole.MINALOC_OFFICER,
                "district": None,
                "sector": None,
            },
            {
                "name": "President Office Officer",
                "email": "presoffice@speakup.rw",
                "password": "Pres123!",
                "role": UserRole.PRESIDENT_OFFICE_OFFICER,
                "district": None,
                "sector": None,
            },
            {
                "name": "Demo Citizen",
                "email": "citizen@speakup.rw",
                "password": "Citizen123!",
                "role": UserRole.CITIZEN,
                "district": None,
                "sector": None,
            },
        ]

        for demo in demo_users:
            exists = db.execute(select(User).where(User.email == demo["email"])).scalars().first()
            if not exists:
                u = User(
                    name=demo["name"],
                    email=demo["email"],
                    password_hash=hash_password(demo["password"]),
                    role=demo["role"],
                    jurisdiction_district=demo.get("district"),
                    jurisdiction_sector=demo.get("sector"),
                )
                db.add(u)
                print(f"  ✓ Demo user: {demo['email']} / {demo['password']} [{demo['role'].value}]")
            else:
                print(f"  - User {demo['email']} already exists")

        db.commit()
        print("\n✅ Seed complete!")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🌱 Seeding SpeakUp database...\n")
    seed()
