import sys; sys.path.insert(0,'.')
from app.core.database import SessionLocal
from sqlalchemy import select
from app.models import PetCategory, PetProduct

with SessionLocal() as db:
    cats = db.scalars(select(PetCategory).order_by(PetCategory.sort_order)).all()
    print('=== CATEGORIES ===')
    for c in cats:
        print(f'  id={c.id} name={c.name}')
    prods = db.scalars(select(PetProduct).order_by(PetProduct.id)).all()
    print('=== PRODUCTS ===')
    for p in prods:
        cat = db.get(PetCategory, p.category_id)
        cname = cat.name if cat else "?"
        print(f'  id={p.id} name={p.name} kind={p.kind or 1} cat={cname} price={p.price} aff_gain={p.affinity_gain or 0} stock={p.stock}')
