import sys, os
os.chdir('C:\\Users\\dell\\OneDrive\\Desktop\\TrustShield\\backend')
sys.path.insert(0, '.')
from app.database import sync_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from app.services.auth.jwt_service import hash_password
from datetime import datetime, timezone

inspector = inspect(sync_engine)
tables = inspector.get_table_names()
print('Tables:', tables)

session = Session(sync_engine)
try:
    result = session.execute(text("SELECT id, email FROM users WHERE email='admin@trustshield.io'"))
    existing = result.fetchone()
    if existing:
        print('User already exists:', existing[0], existing[1])
        user_id = existing[0]
    else:
        result = session.execute(
            text("INSERT INTO users (email, hashed_password, full_name, role, is_active, token_version, created_at, updated_at) VALUES (:email, :pwd, :name, :role, 1, 1, :now, :now)"),
            {'email': 'admin@trustshield.io', 'pwd': hash_password('admin123'), 'name': 'Admin User', 'role': 'super_admin', 'now': datetime.now(timezone.utc)}
        )
        session.commit()
        user_id = result.lastrowid
        print('Created user with id:', user_id)

    # Now generate JWT
    from jose import jwt
    import uuid
    payload = {
        'sub': str(user_id),
        'email': 'admin@trustshield.io',
        'role': 'super_admin',
        'type': 'access',
        'jti': str(uuid.uuid4()),
        'token_version': 1,
        'exp': datetime.now(timezone.utc).timestamp() + 3600
    }
    token = jwt.encode(payload, 'dev-secret-change-in-production-only-for-local-dev-testing-123456', algorithm='HS256')
    print('TOKEN:', token)
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()
    session.rollback()
finally:
    session.close()
