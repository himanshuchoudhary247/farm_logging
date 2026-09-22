"""Lightweight voice-led appointment intake supervisor."""

from .service import AppointmentSupervisor, SUPPORTED_LANGUAGES

# Real bug, found in code review: main.py and chat_orchestrator/adk_router.py
# each constructed their own AppointmentSupervisor() -- two separate objects
# with two separate per-session RLock dicts (the lock this session's audit
# added specifically to serialize concurrent reads/writes to the same
# draft.json). A request landing on main.py's instance and one landing on
# adk_router.py's instance for the same farmer_id+session_id could still
# race each other, reproducing the exact lost-update bug that lock was
# built to eliminate. One shared singleton, constructed once at import
# time and reused everywhere, closes that gap.
default_supervisor = AppointmentSupervisor()

__all__ = ["AppointmentSupervisor", "SUPPORTED_LANGUAGES", "default_supervisor"]
