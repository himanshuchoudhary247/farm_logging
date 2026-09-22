"""Conversational "Add Animal" registration -- see service.py for design."""

from .service import AnimalRegistrationSupervisor, SUPPORTED_LANGUAGES

# Same rationale as appointment_supervisor's default_supervisor (a real
# lost-update race this session found in code review, fixed by ensuring
# every caller shares ONE instance and its per-session lock dict). Applied
# here from day one rather than as a follow-up fix.
default_supervisor = AnimalRegistrationSupervisor()

__all__ = ["AnimalRegistrationSupervisor", "SUPPORTED_LANGUAGES", "default_supervisor"]
