#!/usr/bin/env python3
"""
Query Engine for CCI Signal Database

Provides unified interface for querying CCI divergence signals from the database.
Supports both daily signal generation and historical signal queries.

Key principle: Daily signal generation is treated as a special case of
historical query where query_date = today, maximizing code reuse.

Author: Daily Executor System
Date: 2025-11-11
"""

import sys
import sqlite3
import logging
import pandas as pd
from pathlib import Path
from typing import List, Optional

from signal_types import Signal

# Configure logger
logger = logging.getLogger('DailyExecutor.QueryEngine')


class QueryEngine:
    """
    Query engine for CCI divergence signals.

    This class encapsulates all database query logic, providing a clean
    interface for both daily signal generation and historical queries.
    """

    def __init__(self, db_path: str, data_dir: str = "../data/daily"):
        """
        Initialize query engine.

        Args:
            db_path: Path to CCI signals database (cci_signals.db)
            data_dir: Directory containing K-line CSV files
        """
        import os

        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir)

        if not self.db_path.exists():
            # Enhanced error message with diagnostic information
            cwd = os.getcwd()
            resolved_path = self.db_path.resolve()

            # Try to suggest alternative paths
            parent_dir = self.db_path.parent
            suggestions = []
            if parent_dir.exists():
                suggestions = [f.name for f in parent_dir.iterdir() if f.is_file() and f.suffix == '.db']

            error_msg = (
                f"Database not found!\n"
                f"  Current Working Directory: {cwd}\n"
                f"  Relative path provided: {db_path}\n"
                f"  Resolved absolute path: {resolved_path}\n"
                f"  Path exists check: False\n"
            )

            if suggestions:
                error_msg += f"  Found .db files in parent dir: {', '.join(suggestions)}\n"
            else:
                error_msg += f"  Parent directory exists: {parent_dir.exists()}\n"

            raise FileNotFoundError(error_msg)

        logger.debug(f"QueryEngine initialized: db={self.db_path}, data={self.data_dir}")

    def _get_next_trading_day_open_price(
        self,
        stock_code: str,
        signal_date: str
    ) -> Optional[float]:
        """
        Get next trading day's open price (avoids look-ahead bias).

        CCI divergence is confirmed at signal_date close. The earliest
        possible execution is next day's open.

        Args:
            stock_code: Stock code (e.g., "600519_SH")
            signal_date: Signal date in YYYY-MM-DD format

        Returns:
            Next day's open price, or None if unavailable
        """
        try:
            csv_path = self.data_dir / f"{stock_code}.csv"
            if not csv_path.exists():
                logger.warning(f"K-line file not found: {csv_path}")
                return None

            # Read CSV with date as index
            df = pd.read_csv(csv_path, index_col=0)

            # Convert to datetime
            signal_date_dt = pd.to_datetime(signal_date)
            df.index = pd.to_datetime(df.index)

            # Check if signal_date exists
            if signal_date_dt not in df.index:
                logger.warning(f"{stock_code} @ {signal_date}: No K-line data (possibly suspended)")
                return None

            # Get index position
            signal_idx = df.index.get_loc(signal_date_dt)

            # Check if next day data exists
            if signal_idx + 1 >= len(df):
                logger.warning(f"{stock_code} @ {signal_date}: No data after signal date")
                return None

            # Get next day's open price
            next_day_open = df.iloc[signal_idx + 1]['open']

            logger.debug(f"{stock_code} @ {signal_date} → next open: {next_day_open:.2f}")

            return float(next_day_open)

        except Exception as e:
            logger.error(f"Failed to get next open price ({stock_code} @ {signal_date}): {e}")
            return None

    def fetch_signals(
        self,
        start_date: str,
        end_date: str,
        stock_codes: Optional[List[str]] = None,
        min_confidence: float = 0.0,
        use_next_day_open: bool = True
    ) -> List[Signal]:
        """
        Fetch signals within date range from database.

        This is the core query method that supports all filtering conditions.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            stock_codes: Optional list of stock codes to filter
            min_confidence: Minimum confidence threshold (0.0-1.0)
            use_next_day_open: Use next day's open price as entry price

        Returns:
            List of Signal objects
        """
        logger.info(f"Querying signals: {start_date} to {end_date}")
        logger.debug(f"Filters: stocks={len(stock_codes) if stock_codes else 'all'}, "
                    f"min_conf={min_confidence}, next_open={use_next_day_open}")

        # Build SQL query
        query = """
            SELECT
                stock_code,
                end_date as signal_date,
                confidence,
                divergence_id,
                end_price as entry_price,
                start_date,
                start_price,
                start_cci,
                end_cci,
                days_between
            FROM divergence_events
            WHERE 1=1
        """

        # Build filter conditions
        conditions = []
        params = []

        if start_date:
            conditions.append("end_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("end_date <= ?")
            params.append(end_date)

        if stock_codes:
            placeholders = ','.join(['?' for _ in stock_codes])
            conditions.append(f"stock_code IN ({placeholders})")
            params.extend(stock_codes)

        if min_confidence > 0:
            conditions.append("confidence >= ?")
            params.append(min_confidence)

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += " ORDER BY end_date, stock_code"

        # Execute query
        conn = sqlite3.connect(str(self.db_path))
        signals_df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        if len(signals_df) == 0:
            logger.warning("No signals found matching criteria")
            return []

        logger.info(f"Found {len(signals_df)} raw signals from database")

        # Process signals
        signals = []
        skipped_count = 0

        for idx, row in signals_df.iterrows():
            # Determine entry price
            if use_next_day_open:
                entry_price = self._get_next_trading_day_open_price(
                    stock_code=row['stock_code'],
                    signal_date=row['signal_date']
                )

                if entry_price is None:
                    # Fallback to original price
                    entry_price = float(row['entry_price']) if pd.notna(row['entry_price']) else 0.0
                    skipped_count += 1
                    logger.debug(f"{row['stock_code']} @ {row['signal_date']}: "
                               f"Using fallback price {entry_price:.2f}")
            else:
                entry_price = float(row['entry_price']) if pd.notna(row['entry_price']) else 0.0

            # Create signal object
            signal = Signal(
                stock_code=row['stock_code'],
                signal_date=row['signal_date'],
                confidence=float(row['confidence']),
                entry_price=entry_price,
                reason=f"CCI底背离(CCI:{row['start_cci']:.1f}→{row['end_cci']:.1f}, {row['days_between']}天)",
                divergence_id=row['divergence_id']
            )

            signals.append(signal)

        if use_next_day_open and skipped_count > 0:
            logger.warning(f"{skipped_count}/{len(signals)} signals used fallback price "
                          f"({skipped_count/len(signals)*100:.1f}%)")

        logger.info(f"Successfully generated {len(signals)} signals")

        return signals

    def get_signals_for_date(
        self,
        signal_date: str,
        stock_codes: Optional[List[str]] = None,
        min_confidence: float = 0.0,
        use_next_day_open: bool = True
    ) -> List[Signal]:
        """
        Get signals for a specific date.

        This is a convenience method for daily signal generation,
        internally calling fetch_signals with start_date = end_date.

        Args:
            signal_date: Target date (YYYY-MM-DD)
            stock_codes: Optional list of stock codes to filter
            min_confidence: Minimum confidence threshold
            use_next_day_open: Use next day's open price as entry price

        Returns:
            List of Signal objects for the specified date
        """
        return self.fetch_signals(
            start_date=signal_date,
            end_date=signal_date,
            stock_codes=stock_codes,
            min_confidence=min_confidence,
            use_next_day_open=use_next_day_open
        )
