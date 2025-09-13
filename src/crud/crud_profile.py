from sqlalchemy.orm import Session
from .. import models
from ..schemas import profile_schemas # We will create this schema next

def get_profile(db: Session) -> models.BusinessProfile:
    """
    Retrieves the business profile. In our single-tenant MVP,
    we assume there is only one profile with ID=1.
    """
    profile = db.query(models.BusinessProfile).filter(models.BusinessProfile.id == 1).first()
    # If it doesn't exist for some reason, create a default one.
    if not profile:
        profile = models.BusinessProfile(id=1, business_name="My Salon")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile

def update_profile(db: Session, profile_data: profile_schemas.ProfileUpdate) -> models.BusinessProfile:
    """Updates the business profile."""
    profile = get_profile(db) # Get the existing profile
    profile.business_name = profile_data.business_name
    profile.business_description = profile_data.business_description
    profile.address = profile_data.address
    profile.phone_number = profile_data.phone_number
    db.commit()
    db.refresh(profile)
    return profile