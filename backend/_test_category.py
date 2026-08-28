from app.core.database import SessionLocal
from app.models import Category
from app.services.post_service import _is_valid_category

db = SessionLocal()
print("Categories in DB:")
for c in db.query(Category).all():
    print(f"  id={c.id} name={c.name!r} slug={c.slug!r}")

print()
print("Validation tests:")
tests = ["校园圈", "default", "food", "普通", "invalid_xyz"]
for t in tests:
    print(f"  {t!r}: {_is_valid_category(db, t)}")
