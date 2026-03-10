"""Call manager - tracks active calls and their state."""
import asyncio
import secrets
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator
from ..config import logger


class CallStatus(str, Enum):
    """Call status enumeration."""
    INITIATING = "initiating"
    RINGING = "ringing"
    CONNECTED = "connected"
    NEGOTIATING = "negotiating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TranscriptEntry:
    """Single entry in call transcript."""
    role: str  # "agent" or "human"
    text: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VoiceCall:
    """Active voice call state."""
    call_id: str
    session_id: str
    provider_id: str
    provider_name: str
    phone_number: str
    twilio_sid: str | None = None
    status: CallStatus = CallStatus.INITIATING
    transcript: list[TranscriptEntry] = field(default_factory=list)
    negotiation_context: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    connected_at: datetime | None = None
    ended_at: datetime | None = None
    outcome: str | None = None  # "accepted", "rejected", "no_answer", etc.
    final_price: float | None = None

    def add_transcript(self, role: str, text: str):
        """Add entry to transcript."""
        self.transcript.append(TranscriptEntry(role=role, text=text))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "call_id": self.call_id,
            "session_id": self.session_id,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "phone_number": self.phone_number,
            "status": self.status.value,
            "transcript": [
                {"role": t.role, "text": t.text, "timestamp": t.timestamp.isoformat()}
                for t in self.transcript
            ],
            "created_at": self.created_at.isoformat(),
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "outcome": self.outcome,
            "final_price": self.final_price,
        }


class CallManager:
    """Manages active voice calls."""

    def __init__(self):
        self._calls: dict[str, VoiceCall] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def create_call(
        self,
        session_id: str,
        provider_id: str,
        provider_name: str,
        phone_number: str,
        negotiation_context: dict,
    ) -> VoiceCall:
        """Create a new call tracking entry."""
        call_id = secrets.token_urlsafe(12)

        call = VoiceCall(
            call_id=call_id,
            session_id=session_id,
            provider_id=provider_id,
            provider_name=provider_name,
            phone_number=phone_number,
            negotiation_context=negotiation_context,
        )

        async with self._lock:
            self._calls[call_id] = call
            self._subscribers[call_id] = []

        logger.info(f"Call created: {call_id} for provider {provider_name}")
        return call

    async def get_call(self, call_id: str) -> VoiceCall | None:
        """Get call by ID."""
        return self._calls.get(call_id)

    async def update_status(self, call_id: str, status: CallStatus) -> None:
        """Update call status and notify subscribers."""
        call = self._calls.get(call_id)
        if not call:
            return

        call.status = status

        if status == CallStatus.CONNECTED:
            call.connected_at = datetime.now()
        elif status in (CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.CANCELLED):
            call.ended_at = datetime.now()

        await self._notify_subscribers(call_id, {
            "type": "status",
            "status": status.value,
            "call": call.to_dict(),
        })

        logger.info(f"Call {call_id} status: {status.value}")

    async def add_transcript_entry(
        self, call_id: str, role: str, text: str
    ) -> None:
        """Add transcript entry and notify subscribers."""
        call = self._calls.get(call_id)
        if not call:
            return

        call.add_transcript(role, text)

        await self._notify_subscribers(call_id, {
            "type": "transcript",
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })

    async def complete_call(
        self,
        call_id: str,
        outcome: str,
        final_price: float | None = None,
    ) -> None:
        """Mark call as completed with outcome."""
        call = self._calls.get(call_id)
        if not call:
            return

        call.status = CallStatus.COMPLETED
        call.ended_at = datetime.now()
        call.outcome = outcome
        call.final_price = final_price

        await self._notify_subscribers(call_id, {
            "type": "completed",
            "outcome": outcome,
            "final_price": final_price,
            "call": call.to_dict(),
        })

        logger.info(f"Call {call_id} completed: {outcome}, price: {final_price}")

    async def subscribe(self, call_id: str) -> AsyncGenerator[dict, None]:
        """Subscribe to call updates."""
        queue: asyncio.Queue = asyncio.Queue()

        async with self._lock:
            if call_id not in self._subscribers:
                self._subscribers[call_id] = []
            self._subscribers[call_id].append(queue)

        try:
            # Send current state
            call = self._calls.get(call_id)
            if call:
                yield {"type": "state", "call": call.to_dict()}

            # Stream updates
            while True:
                try:
                    update = await asyncio.wait_for(queue.get(), timeout=30)
                    yield update

                    # Stop if call ended
                    if update.get("type") in ("completed", "failed", "cancelled"):
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"type": "ping"}
        finally:
            async with self._lock:
                if call_id in self._subscribers:
                    self._subscribers[call_id].remove(queue)

    async def _notify_subscribers(self, call_id: str, update: dict) -> None:
        """Notify all subscribers of an update."""
        subscribers = self._subscribers.get(call_id, [])
        for queue in subscribers:
            try:
                await queue.put(update)
            except Exception:
                pass

    async def cleanup_old_calls(self, max_age_hours: int = 24) -> int:
        """Remove old completed calls."""
        cutoff = datetime.now()
        removed = 0

        async with self._lock:
            to_remove = [
                cid for cid, call in self._calls.items()
                if call.ended_at and (cutoff - call.ended_at).total_seconds() > max_age_hours * 3600
            ]
            for cid in to_remove:
                del self._calls[cid]
                self._subscribers.pop(cid, None)
                removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} old calls")
        return removed


# Singleton instance
_call_manager: CallManager | None = None


def get_call_manager() -> CallManager:
    """Get the call manager singleton."""
    global _call_manager
    if _call_manager is None:
        _call_manager = CallManager()
    return _call_manager
