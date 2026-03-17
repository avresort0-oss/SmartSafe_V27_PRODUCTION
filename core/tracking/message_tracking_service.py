"""
SmartSafe V27 - Message Tracking Service
Core service for tracking WhatsApp messages, delivery status, and responses
"""

from __future__ import annotations
import abc
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Protocol
from queue import Queue, Empty

logger = logging.getLogger(__name__)


def _env_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


@dataclass
class TrackedMessage:
    """Enhanced message structure for comprehensive tracking"""
    message_id: str
    contact_phone: str
    message_content: str
    contact_name: Optional[str] = None
    sent_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delivery_status: str = "pending"  # pending, sent, delivered, read, failed
    account_id: Optional[str] = None
    campaign_id: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None
    response_received: bool = False
    response_timestamp: Optional[datetime] = None
    response_content: Optional[str] = None
    response_type: Optional[str] = None  # text, image, document, etc.
    sentiment_score: Optional[float] = None
    retry_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageEvent:
    """Message status change event for real-time updates"""
    message_id: str
    event_type: str  # sent, delivered, read, failed, response_received
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)


class DbAdapter(Protocol):
    """A protocol defining the interface for database interaction."""

    def execute(self, sql: str, params: tuple = ()) -> 'DbCursor':
        ...

    def commit(self) -> None:
        ...

    def close(self) -> None:
        ...

    def get_sql(self, key: str) -> str:
        ...


class DbCursor(Protocol):
    """A protocol for database cursors."""

    def fetchone(self) -> Optional[Dict[str, Any]]:
        ...

    def fetchall(self) -> List[Dict[str, Any]]:
        ...


class SQLiteAdapter:
    """Database adapter for SQLite."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Performance optimizations
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")

    def execute(self, sql: str, params: tuple = ()) -> DbCursor:
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get_sql(self, key: str) -> str:
        # SQLite specific SQL if needed, for now using generic
        if key == "autoincrement_pk":
            return "INTEGER PRIMARY KEY AUTOINCREMENT"
        return ""


class PostgresAdapter:
    """Database adapter for PostgreSQL."""

    def __init__(self, dsn: str):
        import psycopg2
        from psycopg2.extras import DictCursor

        self.conn = psycopg2.connect(dsn)
        self.DictCursor = DictCursor

    def execute(self, sql: str, params: tuple = ()) -> DbCursor:
        # Translate placeholder style from '?' to '%s'
        sql_translated = sql.replace('?', '%s')
        cursor = self.conn.cursor(cursor_factory=self.DictCursor)
        cursor.execute(sql_translated, params)
        return cursor

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get_sql(self, key: str) -> str:
        if key == "autoincrement_pk":
            return "SERIAL PRIMARY KEY"
        return ""


class MessageTrackingService:
    """Central service for tracking WhatsApp messages and responses"""
    
    def __init__(self, db_adapter: Optional[DbAdapter] = None):
        if db_adapter:
            self.db = db_adapter
        else:
            # Default to SQLite if no adapter is provided
            db_path = Path(_env_setting("DB_PATH", "logs/message_tracking.db"))
            self.db = SQLiteAdapter(db_path)

        # Thread safety
        self._lock = threading.Lock()
        self._event_queue = Queue()
        self._event_callbacks: List[callable] = []

        # Background processing
        self._stop_event = threading.Event()
        self._processor_thread = None

        # Initialize database
        self._init_database()

        # Start background processor
        self._start_background_processor()
        
        logger.info("MessageTrackingService initialized")
    
    def _init_database(self):
        """Initialize SQLite database for message tracking"""
        with self._lock:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    contact_phone TEXT NOT NULL,
                    contact_name TEXT,
                    message_content TEXT NOT NULL,
                    sent_timestamp TEXT NOT NULL,
                    delivery_status TEXT DEFAULT 'pending',
                    account_id TEXT,
                    campaign_id TEXT,
                    success BOOLEAN DEFAULT FALSE,
                    error_message TEXT,
                    response_received BOOLEAN DEFAULT FALSE,
                    response_timestamp TEXT,
                    response_content TEXT,
                    response_type TEXT,
                    sentiment_score REAL,
                    retry_count INTEGER DEFAULT 0,
                    last_updated TEXT NOT NULL
                )
            """)

            autoincrement_pk = self.db.get_sql("autoincrement_pk")
            self.db.execute(f"""
                CREATE TABLE IF NOT EXISTS message_events (
                    id {autoincrement_pk},
                    message_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    data TEXT,
                    FOREIGN KEY (message_id) REFERENCES messages(message_id)
                )
            """)

            # Indexes for performance
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_messages_phone ON messages(contact_phone)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_messages_campaign ON messages(campaign_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(delivery_status)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_messages_response ON messages(response_received)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_message ON message_events(message_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON message_events(timestamp)")
            
            # Optimizations for time-based and sorted queries
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_messages_sent_time ON messages(sent_timestamp DESC)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_messages_campaign_time ON messages(campaign_id, sent_timestamp DESC)")

            self.db.execute(f"""
                CREATE TABLE IF NOT EXISTS spam_analytics (
                    id {autoincrement_pk},
                    message_id TEXT NOT NULL,
                    spam_score REAL NOT NULL,
                    is_spam BOOLEAN NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
                )
            """)
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_spam_analytics_message ON spam_analytics(message_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_spam_analytics_timestamp ON spam_analytics(timestamp)")

            self.db.commit()
    
    def _start_background_processor(self):
        """Start background thread for processing events"""
        def _process_events():
            while not self._stop_event.is_set():
                try:
                    event = self._event_queue.get(timeout=1.0)
                    self._process_event(event)
                except Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
        
        self._processor_thread = threading.Thread(target=_process_events, daemon=True)
        self._processor_thread.start()
    
    def _process_event(self, event: MessageEvent):
        """Process a message event and update database"""
        try:
            # Update message based on event type
            if event.event_type == "sent":
                self.db.execute("""
                    UPDATE messages 
                    SET delivery_status = 'sent', success = TRUE, last_updated = ?
                    WHERE message_id = ?
                """, (event.timestamp.isoformat(), event.message_id))
            
            elif event.event_type == "delivered":
                self.db.execute("""
                    UPDATE messages 
                    SET delivery_status = 'delivered', last_updated = ?
                    WHERE message_id = ?
                """, (event.timestamp.isoformat(), event.message_id))
            
            elif event.event_type == "read":
                self.db.execute("""
                    UPDATE messages 
                    SET delivery_status = 'read', last_updated = ?
                    WHERE message_id = ?
                """, (event.timestamp.isoformat(), event.message_id))
            
            elif event.event_type == "failed":
                error_msg = event.data.get("error", "Unknown error")
                self.db.execute("""
                    UPDATE messages 
                    SET delivery_status = 'failed', success = FALSE, 
                    error_message = ?, last_updated = ?
                    WHERE message_id = ?
                """, (error_msg, event.timestamp.isoformat(), event.message_id))
            
            elif event.event_type == "response_received":
                response_content = event.data.get("content", "")
                response_type = event.data.get("type", "text")
                sentiment = event.data.get("sentiment")
                
                self.db.execute("""
                    UPDATE messages 
                    SET response_received = TRUE, response_timestamp = ?,
                    response_content = ?, response_type = ?,
                    sentiment_score = ?, last_updated = ?
                    WHERE message_id = ?
                """, (
                    event.timestamp.isoformat(),
                    response_content,
                    response_type,
                    sentiment,
                    event.timestamp.isoformat(),
                    event.message_id
                ))
            
            # Store event in events table
            with self._lock:
                self.db.execute("""
                    INSERT INTO message_events (message_id, event_type, timestamp, data)
                    VALUES (?, ?, ?, ?)
                """, (
                    event.message_id,
                    event.event_type,
                    event.timestamp.isoformat(),
                    json.dumps(event.data)
                ))

                self.db.commit()

            # Notify callbacks
            self._notify_callbacks(event)

        except Exception as e:
            logger.error(f"Database error processing event {event.event_type}: {e}")
    
    def register_message(self, contact: Dict, message_content: str, 
                       account_id: Optional[str] = None,
                       campaign_id: Optional[str] = None) -> str:
        """Register a new message for tracking"""
        message_id = str(uuid.uuid4())
        
        tracked_msg = TrackedMessage(
            message_id=message_id,
            contact_phone=contact.get("phone", ""),
            contact_name=contact.get("name"),
            message_content=message_content,
            account_id=account_id,
            campaign_id=campaign_id
        )
        
        try:
            with self._lock:
                self.db.execute("""
                    INSERT INTO messages (
                        message_id, contact_phone, contact_name, message_content,
                        sent_timestamp, account_id, campaign_id, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tracked_msg.message_id,
                    tracked_msg.contact_phone,
                    tracked_msg.contact_name,
                    tracked_msg.message_content,
                    tracked_msg.sent_timestamp.isoformat(),
                    tracked_msg.account_id,
                    tracked_msg.campaign_id,
                    tracked_msg.last_updated.isoformat()
                ))
                self.db.commit()
            
            logger.info(f"Registered message {message_id} for {tracked_msg.contact_phone}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to register message: {e}")
            raise
    
    def update_message_status(self, message_id: str, status: str, 
                            error: Optional[str] = None, **data):
        """Update message delivery status"""
        event = MessageEvent(
            message_id=message_id,
            event_type=status,
            timestamp=datetime.now(timezone.utc),
            data={"error": error, **data}
        )
        self._event_queue.put(event)
    
    def record_response(self, original_message_id: str, response_content: str,
                       response_type: str = "text", sentiment: Optional[float] = None):
        """Record a response to a tracked message"""
        event = MessageEvent(
            message_id=original_message_id,
            event_type="response_received",
            timestamp=datetime.now(timezone.utc),
            data={
                "content": response_content,
                "type": response_type,
                "sentiment": sentiment
            }
        )
        self._event_queue.put(event)
    
    def get_message(self, message_id: str) -> Optional[TrackedMessage]:
        """Get tracked message by ID"""
        try:
            with self._lock:
                cursor = self.db.execute("""
                    SELECT * FROM messages WHERE message_id = ?
                """, (message_id,))
                row = cursor.fetchone()
                if row: 
                    return TrackedMessage(
                        message_id=row["message_id"],
                        contact_phone=row["contact_phone"],
                        contact_name=row["contact_name"],
                        message_content=row["message_content"],
                        sent_timestamp=datetime.fromisoformat(row["sent_timestamp"]),
                        delivery_status=row["delivery_status"],
                        account_id=row["account_id"],
                        campaign_id=row["campaign_id"],
                        success=bool(row["success"]),
                        error_message=row["error_message"],
                        response_received=bool(row["response_received"]),
                        response_timestamp=datetime.fromisoformat(row["response_timestamp"]) if row["response_timestamp"] else None,
                        response_content=row["response_content"],
                        response_type=row["response_type"],
                        sentiment_score=row["sentiment_score"],
                        retry_count=row["retry_count"],
                        last_updated=datetime.fromisoformat(row["last_updated"])
                    )
        except Exception as e:
            logger.error(f"Failed to get message {message_id}: {e}")
        
        return None
    
    def get_messages_by_campaign(self, campaign_id: str) -> List[TrackedMessage]:
        """Get all messages for a campaign"""
        messages = []
        try:
            with self._lock:
                cursor = self.db.execute("""
                    SELECT * FROM messages WHERE campaign_id = ? ORDER BY sent_timestamp DESC
                """, (campaign_id,))
                
                for row in cursor.fetchall():
                    messages.append(TrackedMessage(    
                        message_id=row["message_id"],
                        contact_phone=row["contact_phone"],
                        contact_name=row["contact_name"],
                        message_content=row["message_content"],
                        sent_timestamp=datetime.fromisoformat(row["sent_timestamp"]),
                        delivery_status=row["delivery_status"],
                        account_id=row["account_id"],
                        campaign_id=row["campaign_id"],
                        success=bool(row["success"]),
                        error_message=row["error_message"],
                        response_received=bool(row["response_received"]),
                        response_timestamp=datetime.fromisoformat(row["response_timestamp"]) if row["response_timestamp"] else None,
                        response_content=row["response_content"],
                        response_type=row["response_type"],
                        sentiment_score=row["sentiment_score"],
                        retry_count=row["retry_count"],
                        last_updated=datetime.fromisoformat(row["last_updated"])
                    ))
        except Exception as e:
            logger.error(f"Failed to get messages for campaign {campaign_id}: {e}")
        
        return messages
    
    def get_campaign_analytics(self, campaign_id: str) -> Dict[str, Any]:
        """Get comprehensive analytics for a campaign"""
        try:
            with self._lock:
                # Basic stats
                cursor = self.db.execute("""
                    SELECT 
                        COUNT(*) as total_messages,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as sent_count,
                        SUM(CASE WHEN delivery_status = 'delivered' THEN 1 ELSE 0 END) as delivered_count,
                        SUM(CASE WHEN delivery_status = 'read' THEN 1 ELSE 0 END) as read_count,
                        SUM(CASE WHEN response_received = 1 THEN 1 ELSE 0 END) as response_count,
                        AVG(CASE WHEN response_received = 1 THEN 
                            (julianday(response_timestamp) - julianday(sent_timestamp)) * 24 * 60 
                            ELSE NULL END) as avg_response_time_minutes
                    FROM messages WHERE campaign_id = ?
                """, (campaign_id,))
                
                stats = cursor.fetchone()
                
                # Response analytics
                cursor = self.db.execute("""
                    SELECT response_type, COUNT(*) as count, AVG(sentiment_score) as avg_sentiment
                    FROM messages 
                    WHERE campaign_id = ? AND response_received = 1
                    GROUP BY response_type
                """, (campaign_id,))
                
                response_stats = {row["response_type"]: {
                    "count": row["count"],
                    "avg_sentiment": row["avg_sentiment"]
                } for row in cursor.fetchall()}
                
                # Failure analysis
                cursor = self.db.execute("""
                    SELECT error_message, COUNT(*) as count
                    FROM messages 
                    WHERE campaign_id = ? AND success = 0
                    GROUP BY error_message
                    ORDER BY count DESC
                """, (campaign_id,))
                
                failure_analysis = {row["error_message"]: row["count"] for row in cursor.fetchall()}
                
                return { 
                    "campaign_id": campaign_id,
                    "total_messages": (stats["total_messages"] or 0) if stats else 0,
                    "sent_count": (stats["sent_count"] or 0) if stats else 0,
                    "delivered_count": (stats["delivered_count"] or 0) if stats else 0,
                    "read_count": (stats["read_count"] or 0) if stats else 0,
                    "response_count": (stats["response_count"] or 0) if stats else 0,
                    "response_rate": (stats["response_count"] / stats["sent_count"] * 100) if stats and stats["sent_count"] else 0,
                    "delivery_rate": (stats["delivered_count"] / stats["sent_count"] * 100) if stats and stats["sent_count"] else 0,
                    "read_rate": (stats["read_count"] / stats["sent_count"] * 100) if stats and stats["sent_count"] else 0,
                    "avg_response_time_minutes": (stats["avg_response_time_minutes"] or 0) if stats else 0,
                    "response_stats": response_stats,
                    "failure_analysis": failure_analysis
                }
                
        except Exception as e:
            logger.error(f"Failed to get analytics for campaign {campaign_id}: {e}")
            return {}
    
    def add_event_callback(self, callback: callable):
        """Add callback for real-time event notifications"""
        with self._lock:
            self._event_callbacks.append(callback)
    
    def _notify_callbacks(self, event: MessageEvent):
        """Notify all registered callbacks of an event"""
        with self._lock:
            for callback in self._event_callbacks:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
    
    def export_campaign_data(self, campaign_id: str, format: str = "csv") -> str:
        """Export campaign data in specified format"""
        messages = self.get_messages_by_campaign(campaign_id)
        analytics = self.get_campaign_analytics(campaign_id)
        
        if format.lower() == "csv":
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                "Message ID", "Contact Phone", "Contact Name", "Message Content",
                "Sent Timestamp", "Delivery Status", "Success", "Error Message",
                "Response Received", "Response Timestamp", "Response Content",
                "Response Type", "Sentiment Score", "Retry Count"
            ])
            
            # Write messages
            for msg in messages:
                writer.writerow([
                    msg.message_id,
                    msg.contact_phone,
                    msg.contact_name or "",
                    msg.message_content,
                    msg.sent_timestamp.isoformat(),
                    msg.delivery_status,
                    msg.success,
                    msg.error_message or "",
                    msg.response_received,
                    msg.response_timestamp.isoformat() if msg.response_timestamp else "",
                    msg.response_content or "",
                    msg.response_type or "",
                    msg.sentiment_score or "",
                    msg.retry_count
                ])
            
            # Add analytics summary
            writer.writerow([])
            writer.writerow(["CAMPAIGN ANALYTICS"])
            for key, value in analytics.items():
                writer.writerow([key, value])
            
            return output.getvalue()
        
        elif format.lower() == "json":
            export_data = {
                "campaign_analytics": analytics,
                "messages": [asdict(msg) for msg in messages]
            }
            return json.dumps(export_data, indent=2, default=str)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def log_spam_detection(self, message_id, spam_score, is_spam):
        """Log spam detection results"""
        try:
            with self._lock:
                self.db.execute("""
                    INSERT INTO spam_analytics (message_id, spam_score, is_spam, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (message_id, spam_score, is_spam, datetime.now(timezone.utc).isoformat()))
                self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log spam detection for message {message_id}: {e}")

    def get_spam_statistics(self):
        """Get spam statistics"""
        try:
            with self._lock:
                cursor = self.db.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN is_spam = 1 THEN 1 ELSE 0 END) as spam,
                        CAST(timestamp as DATE) as date
                    FROM spam_analytics
                    WHERE timestamp >= date('now', '-30 days')
                    GROUP BY DATE(timestamp)
                """)
                rows = cursor.fetchall()
                total = sum(row['total'] for row in rows) if rows else 0
                spam = sum(row['spam'] for row in rows) if rows else 0
                daily_data = {row['date']: {'total': row['total'], 'spam': row['spam']} for row in rows}
                return {'total': total, 'spam': spam, 'daily_data': daily_data}
        except Exception as e:
            logger.error(f"Failed to get spam statistics: {e}")
            return {'total': 0, 'spam': 0, 'daily_data': {}}

    def export_spam_data(self):
        """Export spam data for analysis"""
        try:
            with self._lock:
                cursor = self.db.execute("""
                    SELECT message_id, spam_score, is_spam, timestamp
                    FROM spam_analytics
                    ORDER BY timestamp DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to export spam data: {e}")
            return []

    def get_recent_messages(self, days: int = 30) -> List[TrackedMessage]:
        """Get recent messages from the last N days"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            with self._lock:
                cursor = self.db.execute("""
                    SELECT * FROM messages 
                    WHERE sent_timestamp >= ? 
                    ORDER BY sent_timestamp DESC
                """, (cutoff_date.isoformat(),))
                
                messages = []
                for row in cursor.fetchall():
                    messages.append(TrackedMessage(
                        message_id=row["message_id"],
                        contact_phone=row["contact_phone"],
                        contact_name=row["contact_name"],
                        message_content=row["message_content"],
                        sent_timestamp=datetime.fromisoformat(row["sent_timestamp"]),
                        delivery_status=row["delivery_status"],
                        account_id=row["account_id"],
                        campaign_id=row["campaign_id"],
                        success=bool(row["success"]),
                        error_message=row["error_message"],
                        response_received=bool(row["response_received"]),
                        response_timestamp=datetime.fromisoformat(row["response_timestamp"]) if row["response_timestamp"] else None,
                        response_content=row["response_content"],
                        response_type=row["response_type"],
                        sentiment_score=row["sentiment_score"],
                        retry_count=row["retry_count"],
                        last_updated=datetime.fromisoformat(row["last_updated"])
                    ))
                
                return messages
                
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []

    def cleanup_old_data(self, days: int = 30):
        """Clean up old message data"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        try:
            with self._lock:
                # Delete old events
                self.db.execute("""
                    DELETE FROM message_events 
                    WHERE timestamp < ?
                """, (cutoff_date.isoformat(),))
                
                # Delete old messages
                self.db.execute("""
                    DELETE FROM messages 
                    WHERE sent_timestamp < ?
                """, (cutoff_date.isoformat(),))
                self.db.commit()
                logger.info(f"Cleaned up message data older than {days} days")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
    
    def shutdown(self):
        """Shutdown the tracking service"""
        self._stop_event.set()
        if self._processor_thread:
            self._processor_thread.join(timeout=5)
        self.db.close()
        logger.info("MessageTrackingService shutdown")


# Global instance
_tracking_service: Optional[MessageTrackingService] = None
_service_lock = threading.Lock()


def get_tracking_service() -> MessageTrackingService:
    """Get global tracking service instance"""
    global _tracking_service
    
    with _service_lock:
        if _tracking_service is None:
            db_type = (_env_setting("DB_TYPE", "sqlite") or "sqlite").lower()
            adapter = None
            if db_type == "postgres":
                dsn = _env_setting("DB_DSN")
                if dsn:
                    adapter = PostgresAdapter(dsn)
                else:
                    logger.error("DB_TYPE is 'postgres' but DB_DSN is not set. Falling back to SQLite.")
            
            _tracking_service = MessageTrackingService(db_adapter=adapter)
        return _tracking_service
