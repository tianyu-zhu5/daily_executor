#!/usr/bin/env python3
"""
Data type definitions for Daily Executor

Defines core data structures used across the signal generation
and query system to ensure consistency and type safety.

Author: Daily Executor System
Date: 2025-11-11
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """
    Represents a buy signal generated from CCI divergence detection.

    This is the unified data structure used throughout the system,
    ensuring consistency between daily signal generation, historical
    queries, and all output formats (CSV, JSON, WeChat).

    Attributes:
        stock_code: Stock code (e.g., "600519_SH", "000001_SZ")
        signal_date: Date when the signal was generated (YYYY-MM-DD)
        confidence: Signal confidence score (0.0 to 1.0)
        entry_price: Recommended entry price (next day open price)
        reason: Human-readable description of the signal reason
        divergence_id: Unique identifier for the underlying divergence event
    """
    stock_code: str
    signal_date: str
    confidence: float
    entry_price: float
    reason: str
    divergence_id: str

    def to_dict(self) -> dict:
        """Convert signal to dictionary for serialization"""
        return {
            'stock_code': self.stock_code,
            'signal_date': self.signal_date,
            'confidence': self.confidence,
            'entry_price': self.entry_price,
            'reason': self.reason,
            'divergence_id': self.divergence_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Signal':
        """Create signal from dictionary"""
        return cls(
            stock_code=data['stock_code'],
            signal_date=data['signal_date'],
            confidence=float(data['confidence']),
            entry_price=float(data['entry_price']),
            reason=data['reason'],
            divergence_id=data['divergence_id']
        )
