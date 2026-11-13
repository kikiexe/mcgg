"""
GameState and Action Models using Pydantic
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class ShopSlot(BaseModel):
    slot: int = Field(..., ge=1, le=5, description="Index slot 1 sampai 5")
    hero_name: str = Field(..., description="Nama hero yang terdeteksi")
    cost: int = Field(default=1, description="Biaya gold hero")
    is_empty: bool = Field(default=False, description="Apakah slot sudah dibeli / kosong")

class GameState(BaseModel):
    round: str = Field(default="1-1", description="Babak saat ini, misal: '1-1', '1-2', '1-3'")
    timer_seconds: int = Field(default=30, description="Sisa waktu fase persiapan (detik)")
    gold: int = Field(default=0, ge=0, description="Jumlah saldo gold saat ini")
    level: int = Field(default=3, ge=3, le=10, description="Level commander saat ini")
    shop: List[ShopSlot] = Field(default_factory=list, description="5 Slot kartu di shop")
    current_phase: Literal["PREPARATION", "COMBAT", "GOGO_CARD", "ITEM_SELECTION"] = Field(
        default="PREPARATION", description="Fase game saat ini"
    )

class ActionCommand(BaseModel):
    action: Literal[
        "BUY_HERO",
        "DEPLOY",
        "EQUIP_ITEM",
        "CLOSE_SHOP",
        "REROLL",
        "LEVEL_UP",
        "PICK_ITEM",
        "PICK_GOGO_CARD",
        "END_TURN"
    ] = Field(..., description="Tipe tindakan yang diambil")
    slot: Optional[int] = Field(default=None, description="Nomor slot (1-5 shop/card, 1-8 bench/bag)")
    reasoning: str = Field(..., description="Alasan strategis mengapa tindakan ini diambil")

class TurnDecision(BaseModel):
    strategic_plan: str = Field(..., description="Rencana gambaran besar (kombo yang diincar)")
    policy_source: Literal["llm", "offline_heuristic", "fast_rule"] = Field(
        default="llm", description="Sumber kebijakan keputusan (llm, offline_heuristic, atau fast_rule)"
    )
    actions: List[ActionCommand] = Field(default_factory=list, description="Urutan tindakan yang harus dieksekusi")
