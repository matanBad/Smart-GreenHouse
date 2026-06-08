"""
user_model.py

Describes the shape of a user record (stored in data/users.json).

Security note: no passwords or credentials are stored at this stage.

Fields:
    user_id        : unique id for the user
    full_name      : display name
    email          : contact email
    role           : manager | owner | administrator
    account_status : active | inactive
    created_at     : ISO-8601 time the account was created
"""


def make_user(user_id, full_name, email, role, account_status="active", created_at=None):
    """Build a user dict in the canonical shape (future prompts). No passwords."""
    return {
        "user_id": user_id,
        "full_name": full_name,
        "email": email,
        "role": role,
        "account_status": account_status,
        "created_at": created_at,
    }
