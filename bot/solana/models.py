"""
Models for Solana operations.
"""
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class WalletInfo(BaseModel):
    """Information about a wallet."""
    address: str
    secret_key: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    balance: Optional[float] = None
    
class TransferOp(BaseModel):
    """A transfer operation in the schedule."""
    from_address: str
    to_address: str
    amount: float
    token_mint: str
    estimated_time: datetime
    execution_time: Optional[datetime] = None
    status: str = "pending"  # pending, in_progress, completed, failed
    tx_hash: Optional[str] = None
    retry_count: int = 0
    fee_lamports: Optional[int] = None
    error_message: Optional[str] = None
    
class Schedule(BaseModel):
    """A schedule of transfers."""
    id: str
    mother_wallet: str
    child_wallets: List[str]
    token_mint: str
    total_volume: float
    service_fee_total: float
    transfers: List[TransferOp]
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
class FeeEstimate(BaseModel):
    """An estimate of the current fee."""
    lamports: int
    timestamp: datetime = Field(default_factory=datetime.now)
    is_spike: bool = False 