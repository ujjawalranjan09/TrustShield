"""Bootstrap database from models instead of broken migrations."""
import sys
sys.path.insert(0, r"C:\Users\dell\OneDrive\Desktop\TrustShield\backend")

from app.database import Base, sync_engine
from app.config import DATABASE_URL

# Import all models so Base.metadata knows about them
# Import Tenant FIRST so User's ForeignKey can resolve
from app.models.tenant import Tenant
from app.models.session import RevokedSession
from app.models.entity import FlaggedEntity, EntityReport
from app.models.user import User
from app.models.intel import Bank, SharedEntity, CrossBankReport
from app.models.recovery import RecoveryCase
from app.models.scan_event import ScanEvent
from app.models.audit import AuditLog
from app.models.feedback import FeedbackLabel
from app.models.refresh_token import RefreshToken
from app.models.model_params import ModelParams
from app.models.drift import DriftLog
from app.models.ring import FraudRing
from app.models.investigation import InvestigationCase
from app.models.behavioral_signal import BehavioralSignal
from app.models.intervention import InterventionLog
from app.models.billing import Plan, Subscription, UsageLedger, UsageEvent
from app.models.shadow_prediction import ShadowPrediction
from app.models.compliance import DataAsset
from app.models.auth import Role, UserRole

print(f"Creating tables for: {DATABASE_URL}")
Base.metadata.create_all(bind=sync_engine)
print("All tables created successfully.")
