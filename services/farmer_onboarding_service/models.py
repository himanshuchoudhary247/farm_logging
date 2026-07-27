from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class FarmerDetails(BaseModel):
    name: Optional[str] = None
    aadharNo: Optional[str] = None
    aadharPhoto: Optional[str] = None
    gender: Optional[str] = None
    fatherOrSpouseName: Optional[str] = None
    phone: Optional[str] = None
    alternateMobile: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str = "India"
    hasPanCard: Optional[str] = None
    panNo: Optional[str] = None
    dob: Optional[str] = None
    religion: Optional[str] = None
    caste: Optional[str] = None
    education: Optional[str] = None
    otherEducation: Optional[str] = None
    occupation: Optional[str] = None
    otherOccupation: Optional[str] = None
    farmingExperience: Optional[str] = None
    landHolding: Optional[float] = None
    organizations: Optional[str] = None
    otherOrganizations: Optional[str] = None
    hasGovernmentId: Optional[str] = None
    governmentIdPhoto: Optional[str] = None


FARMER_FIELDS = list(FarmerDetails.model_fields.keys())


class FarmDetails(BaseModel):
    farmName: str = ""
    email: str = ""
    farmPhone: str = ""
    alternatePhone: str = ""
    address: str = ""
    farmCity: str = ""
    district: str = ""
    farmPincode: Optional[int] = None
    farmState: str = ""
    country: str = "India"
    totalAnimalCapacity: Optional[int] = None
    currentAnimalCount: int = 0
    sheepCount: int = 0
    goatCount: int = 0
    image: str = ""
    notes: str = ""


FARM_FIELDS = list(FarmDetails.model_fields.keys())


class OnboardingRequest(BaseModel):
    text: str
    existing: Optional[dict[str, Any]] = None
    language: str = "en"


class OnboardingResponse(BaseModel):
    farmer: dict[str, Any] = Field(default_factory=dict)
    farm: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    follow_up_question: Optional[str] = None
    complete: bool = False
    confidence: Optional[float] = None
    confirm_fields: list[str] = Field(default_factory=list)
