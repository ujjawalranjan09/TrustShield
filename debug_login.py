import sys
sys.path.insert(0, 'backend')

# Test login flow in isolation
import asyncio
from app.services.auth.jwt_service import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.database import SessionLocal, AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def test_login():
    from sqlalchemy.ext.asyncio import AsyncSession

    email = 'testlive999@example.com'

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).filter(User.email == email))
        user = result.scalars().first()

        if user:
            print(f'User found: {user.id}, {user.email}, {user.role}')
            print(f'Hash: {user.hashed_password[:50]}...')

            # Verify password
            ok = verify_password('TestPass123!', user.hashed_password)
            print(f'Password verify: {ok}')

            # Create tokens
            access_token = create_access_token({
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }, token_version=user.token_version or 1)
            print(f'Access token: {access_token[:50]}...')

            import uuid
            family_id = str(uuid.uuid4())
            refresh_token = create_refresh_token({"sub": str(user.id)}, family_id=family_id)
            print(f'Refresh token: {refresh_token[:50]}...')

            # Decode
            decoded = decode_token(refresh_token)
            print(f'Decoded: {decoded}')
        else:
            print(f'User {email} not found!')

asyncio.run(test_login())
