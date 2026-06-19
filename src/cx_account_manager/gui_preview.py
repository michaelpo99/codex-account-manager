from __future__ import annotations

from cx_account_manager.gui_app import AccountRow


def sample_accounts() -> list[AccountRow]:
    return [
        AccountRow(
            alias="fova3000",
            current=False,
            scope="work",
            email="fova3000@amail.com",
            plan="team",
            primary_used=1,
            primary_reset="2026-06-19 18:50",
            secondary_used=35,
            secondary_reset="2026-06-25 10:08",
            rank=1,
        ),
        AccountRow(
            alias="michaelpo",
            current=True,
            scope="work",
            email="michaelpo@fovatech.com",
            plan="team",
            primary_used=29,
            primary_reset="2026-06-19 18:21",
            secondary_used=20,
            secondary_reset="2026-06-25 10:05",
            rank=2,
        ),
        AccountRow(
            alias="fova_co01",
            current=False,
            scope="work",
            email="fova.co01@amail.com",
            plan="team",
            primary_used=62,
            primary_reset="2026-06-19 16:27",
            secondary_used=27,
            secondary_reset="2026-06-25 09:59",
            rank=3,
        ),
        AccountRow(
            alias="pomichael",
            current=False,
            scope="personal",
            email="pomichael@amail.com",
            plan="plus",
            primary_used=1,
            primary_reset="2026-06-19 18:44",
            secondary_used=9,
            secondary_reset="2026-06-25 18:36",
            rank=4,
            error="Token metadata sample error text that should clip cleanly",
        ),
    ]
