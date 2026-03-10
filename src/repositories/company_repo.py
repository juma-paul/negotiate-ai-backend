"""Company repository - database operations for trucking companies."""
import json
import random
from ..database.connection import get_db
from ..models import ProviderPersonality


class CompanyRepo:
    """Repository for company database operations."""

    @staticmethod
    async def get_all_active() -> list[dict]:
        """Get all active companies."""
        async with get_db() as db:
            cursor = await db.execute(
                """SELECT id, name, contact_phone, contact_email, service_areas,
                          fleet_info, personality, base_rate_multiplier,
                          min_discount_threshold, rating, is_active
                   FROM companies WHERE is_active = 1
                   ORDER BY rating DESC"""
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_by_id(company_id: str) -> dict | None:
        """Get company by ID."""
        async with get_db() as db:
            cursor = await db.execute(
                """SELECT id, name, contact_phone, contact_email, service_areas,
                          fleet_info, personality, base_rate_multiplier,
                          min_discount_threshold, rating, is_active
                   FROM companies WHERE id = ?""",
                (company_id,)
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    async def get_random_providers(count: int, base_price: float) -> list[dict]:
        """Get random companies as providers with calculated pricing."""
        async with get_db() as db:
            cursor = await db.execute(
                """SELECT id, name, contact_phone, personality, base_rate_multiplier,
                          min_discount_threshold, rating, service_areas, fleet_info
                   FROM companies WHERE is_active = 1
                   ORDER BY RANDOM()
                   LIMIT ?""",
                (count,)
            )
            rows = await cursor.fetchall()

        providers = []
        for row in rows:
            company = dict(row)
            personality = ProviderPersonality(company["personality"])

            # Calculate initial price based on company's rate multiplier
            multiplier = company["base_rate_multiplier"]
            # Add some variance (+/- 10%)
            variance = random.uniform(0.9, 1.1)
            initial_price = base_price * multiplier * variance

            # Calculate minimum acceptable price based on discount threshold
            min_threshold = company["min_discount_threshold"]
            min_price = base_price * min_threshold

            providers.append({
                "provider_id": company["id"],
                "provider_name": company["name"],
                "personality": personality,
                "initial_price": round(initial_price, 2),
                "min_price": round(min_price, 2),
                "phone": company["contact_phone"],
                "rating": company["rating"],
                "service_areas": json.loads(company["service_areas"]),
                "fleet_info": json.loads(company["fleet_info"]),
            })

        return providers

    @staticmethod
    async def get_by_service_area(area: str, count: int = 5) -> list[dict]:
        """Get companies that serve a specific area."""
        async with get_db() as db:
            cursor = await db.execute(
                """SELECT id, name, contact_phone, personality, rating, service_areas
                   FROM companies
                   WHERE is_active = 1 AND service_areas LIKE ?
                   ORDER BY rating DESC
                   LIMIT ?""",
                (f'%"{area}"%', count)
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
