"""Session repository - database operations for negotiation sessions."""
import json
import secrets
from datetime import datetime
from ..database.connection import get_db
from ..models import (
    NegotiationSession, ProviderNegotiation, NegotiationMessage,
    NegotiationStrategy, ProviderPersonality
)


class SessionRepo:
    """Repository for session database operations."""

    @staticmethod
    async def create(
        user_id: str | None,
        item_description: str,
        target_price: float,
        max_price: float,
        strategy: NegotiationStrategy,
        providers: list[dict]
    ) -> NegotiationSession:
        """Create a new negotiation session with providers."""
        session_id = secrets.token_urlsafe(16)
        now = datetime.now().isoformat()

        async with get_db() as db:
            # Insert session
            await db.execute(
                """INSERT INTO negotiation_sessions
                   (id, user_id, item_description, target_price, max_price, strategy, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, item_description, target_price, max_price, strategy.value, now)
            )

            # Insert provider negotiations
            provider_negotiations = []
            for p in providers:
                pn_id = secrets.token_urlsafe(8)
                await db.execute(
                    """INSERT INTO provider_negotiations
                       (id, session_id, company_id, initial_price, current_price, min_price)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (pn_id, session_id, p["provider_id"], p["initial_price"],
                     p["initial_price"], p["min_price"])
                )
                provider_negotiations.append(ProviderNegotiation(
                    provider_id=p["provider_id"],
                    provider_name=p["provider_name"],
                    personality=p["personality"],
                    initial_price=p["initial_price"],
                    current_price=p["initial_price"],
                    min_price=p["min_price"],
                ))

            await db.commit()

        return NegotiationSession(
            session_id=session_id,
            user_id=user_id,
            item_description=item_description,
            target_price=target_price,
            max_price=max_price,
            strategy=strategy,
            providers=provider_negotiations,
            created_at=now,
        )

    @staticmethod
    async def get(session_id: str) -> NegotiationSession | None:
        """Get session by ID with all providers and messages."""
        async with get_db() as db:
            # Get session
            cursor = await db.execute(
                """SELECT id, user_id, item_description, target_price, max_price,
                          strategy, status, best_deal_company_id, best_deal_price,
                          total_rounds, created_at
                   FROM negotiation_sessions WHERE id = ?""",
                (session_id,)
            )
            session_row = await cursor.fetchone()
            if not session_row:
                return None

            session = dict(session_row)

            # Get provider negotiations with company info
            cursor = await db.execute(
                """SELECT pn.id, pn.company_id, pn.initial_price, pn.current_price,
                          pn.min_price, pn.status, pn.rounds,
                          c.name, c.personality
                   FROM provider_negotiations pn
                   JOIN companies c ON pn.company_id = c.id
                   WHERE pn.session_id = ?""",
                (session_id,)
            )
            pn_rows = await cursor.fetchall()

            providers = []
            best_deal = None
            for pn_row in pn_rows:
                pn = dict(pn_row)

                # Get messages for this provider negotiation
                msg_cursor = await db.execute(
                    """SELECT role, action, amount, message, timestamp
                       FROM messages WHERE provider_negotiation_id = ?
                       ORDER BY timestamp""",
                    (pn["id"],)
                )
                msg_rows = await msg_cursor.fetchall()
                messages = [
                    NegotiationMessage(
                        role=m["role"],
                        action=m["action"],
                        amount=m["amount"],
                        message=m["message"],
                        timestamp=m["timestamp"]
                    )
                    for m in msg_rows
                ]

                provider = ProviderNegotiation(
                    provider_id=pn["company_id"],
                    provider_name=pn["name"],
                    personality=ProviderPersonality(pn["personality"]),
                    initial_price=pn["initial_price"],
                    current_price=pn["current_price"],
                    min_price=pn["min_price"],
                    status=pn["status"],
                    messages=messages,
                    rounds=pn["rounds"],
                )
                providers.append(provider)

                # Track best deal
                if pn["company_id"] == session["best_deal_company_id"]:
                    best_deal = provider

        return NegotiationSession(
            session_id=session["id"],
            user_id=session["user_id"],
            item_description=session["item_description"],
            target_price=session["target_price"],
            max_price=session["max_price"],
            strategy=NegotiationStrategy(session["strategy"]),
            providers=providers,
            status=session["status"],
            best_deal=best_deal,
            total_rounds=session["total_rounds"],
            created_at=session["created_at"],
        )

    @staticmethod
    async def update_provider(
        session_id: str,
        provider_id: str,
        current_price: float | None = None,
        status: str | None = None,
        rounds: int | None = None
    ) -> None:
        """Update a provider negotiation status."""
        async with get_db() as db:
            updates = []
            params = []
            if current_price is not None:
                updates.append("current_price = ?")
                params.append(current_price)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if rounds is not None:
                updates.append("rounds = ?")
                params.append(rounds)

            if updates:
                params.extend([session_id, provider_id])
                await db.execute(
                    f"""UPDATE provider_negotiations
                        SET {', '.join(updates)}
                        WHERE session_id = ? AND company_id = ?""",
                    params
                )
                await db.commit()

    @staticmethod
    async def add_message(
        session_id: str,
        provider_id: str,
        role: str,
        action: str,
        amount: float | None,
        message: str
    ) -> None:
        """Add a message to a provider negotiation."""
        async with get_db() as db:
            # Get provider_negotiation_id
            cursor = await db.execute(
                """SELECT id FROM provider_negotiations
                   WHERE session_id = ? AND company_id = ?""",
                (session_id, provider_id)
            )
            row = await cursor.fetchone()
            if not row:
                return

            pn_id = row["id"]
            timestamp = datetime.now().isoformat()

            await db.execute(
                """INSERT INTO messages (provider_negotiation_id, role, action, amount, message, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pn_id, role, action, amount, message, timestamp)
            )
            await db.commit()

    @staticmethod
    async def complete_session(
        session_id: str,
        best_deal_company_id: str | None,
        best_deal_price: float | None,
        total_rounds: int
    ) -> None:
        """Mark session as completed with best deal."""
        async with get_db() as db:
            await db.execute(
                """UPDATE negotiation_sessions
                   SET status = 'completed', best_deal_company_id = ?,
                       best_deal_price = ?, total_rounds = ?
                   WHERE id = ?""",
                (best_deal_company_id, best_deal_price, total_rounds, session_id)
            )
            await db.commit()

    @staticmethod
    async def cancel_session(session_id: str) -> None:
        """Cancel a session."""
        async with get_db() as db:
            await db.execute(
                "UPDATE negotiation_sessions SET status = 'cancelled' WHERE id = ?",
                (session_id,)
            )
            await db.commit()

    @staticmethod
    async def get_user_sessions(user_id: str, limit: int = 20) -> list[dict]:
        """Get user's negotiation history."""
        async with get_db() as db:
            cursor = await db.execute(
                """SELECT id, item_description, target_price, max_price, strategy,
                          status, best_deal_company_id, best_deal_price, total_rounds, created_at
                   FROM negotiation_sessions
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    async def save_result(
        user_id: str | None,
        session_id: str,
        company_id: str,
        initial_price: float,
        final_price: float,
        strategy: str,
        rounds_taken: int
    ) -> None:
        """Save negotiation result for analytics."""
        savings_amount = initial_price - final_price
        savings_percent = (savings_amount / initial_price) * 100 if initial_price > 0 else 0

        async with get_db() as db:
            await db.execute(
                """INSERT INTO negotiation_results
                   (user_id, session_id, company_id, initial_price, final_price,
                    savings_amount, savings_percent, strategy, rounds_taken)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, session_id, company_id, initial_price, final_price,
                 savings_amount, savings_percent, strategy, rounds_taken)
            )
            await db.commit()
