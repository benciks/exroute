import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

class Route(Base):
  __tablename__ = "routes"
  id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
  user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
  instructions: Mapped[str] = mapped_column(Text, nullable=False)
  distance_km: Mapped[float] = mapped_column(Float, nullable=False)
  duration_min: Mapped[float] = mapped_column(Float, nullable=False)
  polyline: Mapped[str] = mapped_column(Text, nullable=False)
  waypoints: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
