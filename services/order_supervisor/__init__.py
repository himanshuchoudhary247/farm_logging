from services.order_supervisor.service import OrderSupervisor

# One shared instance, so the per-session locks are shared by every request.
default_supervisor = OrderSupervisor()

__all__ = ["OrderSupervisor", "default_supervisor"]
