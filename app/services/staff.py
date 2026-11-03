"""Parsers and validators for staff inputs: Decimal rupee / percent parsing, audit logging."""
from decimal import Decimal, InvalidOperation
from typing import Optional, Any
import json
from sqlalchemy.orm import Session
from app.models import AuditLog, User

# Currency caps: Max daily rate Rs 5,00,000 (50,000,000 paise)
MAX_RUPEES = Decimal("500000.00")
# Percentage cap: 100.00%
MAX_PERCENT = Decimal("100.00")


def parse_rupees_to_paise(val: str, cap: Decimal = MAX_RUPEES) -> int:
    """
    Parse a rupee string to integer paise strictly via Decimal.
    - Max 2 decimal places.
    - Positive (> 0).
    - Capped at `cap` (default Rs 5,00,000).
    - No float conversions.
    """
    if not val or not isinstance(val, str):
        raise ValueError("Price input must be a non-empty string.")
    clean = val.strip().replace(",", "")
    try:
        d = Decimal(clean)
    except InvalidOperation:
        raise ValueError(f"Invalid monetary format: '{val}'")
    
    if d <= 0:
        raise ValueError("Price must be strictly positive.")
    if d > cap:
        raise ValueError(f"Price exceeds maximum allowed limit of ₹{cap:,.2f}.")
    if d.as_tuple().exponent < -2:
        raise ValueError("Price cannot have more than 2 decimal places.")
        
    return int((d * 100).to_integral_value())


def parse_percent_to_bps(val: str, cap: Decimal = MAX_PERCENT) -> int:
    """
    Parse a percentage string to integer basis points strictly via Decimal.
    e.g. '10' -> 1000 bps, '12.5' -> 1250 bps.
    - Max 2 decimal places.
    - Positive (>= 0).
    - Capped at `cap` (100.00%).
    """
    if not val or not isinstance(val, str):
        raise ValueError("Percentage input must be a non-empty string.")
    clean = val.strip().replace("%", "").replace(",", "")
    try:
        d = Decimal(clean)
    except InvalidOperation:
        raise ValueError(f"Invalid percentage format: '{val}'")
        
    if d < 0:
        raise ValueError("Percentage cannot be negative.")
    if d > cap:
        raise ValueError(f"Percentage exceeds maximum allowed limit of {cap}%.")
    if d.as_tuple().exponent < -2:
        raise ValueError("Percentage cannot have more than 2 decimal places.")
        
    return int((d * 100).to_integral_value())


def log_audit_event(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    details: Optional[dict] = None
) -> AuditLog:
    """Append-only audit logging helper recording user id and role."""
    details_str = json.dumps(details) if details else None
    log_entry = AuditLog(
        user_id=user.id,
        user_role=user.role,
        user_name=user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details_str
    )
    db.add(log_entry)
    db.flush()
    return log_entry
