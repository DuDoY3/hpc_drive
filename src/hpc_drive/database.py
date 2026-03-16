from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base  # Import Base from our snake_case models

# We need connect_args for SQLite
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL, echo=True, connect_args=connect_args
)

# This is the factory for our sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_missing_columns_sqlite():
    """
    SQLite workaround: create_all() does NOT add new columns to existing tables.
    This function inspects the actual DB schema and adds any missing columns
    from the ORM model using ALTER TABLE.
    """
    inspector = inspect(engine)
    
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue  # Table doesn't exist yet; create_all will handle it
        
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        
        for column in table.columns:
            if column.name not in existing_columns:
                # Build ALTER TABLE statement
                col_type = column.type.compile(engine.dialect)
                
                # Determine default value
                default_clause = ""
                if column.server_default is not None:
                    default_value = column.server_default.arg
                    if isinstance(default_value, str):
                        default_clause = f" DEFAULT '{default_value}'"
                    else:
                        default_clause = f" DEFAULT {default_value}"
                elif column.nullable:
                    default_clause = " DEFAULT NULL"
                elif column.default is not None:
                    # Use Python default as server default for migration
                    default_val = column.default.arg
                    if callable(default_val):
                        # Skip callable defaults (like uuid4)
                        default_clause = " DEFAULT NULL" if column.nullable else ""
                    elif isinstance(default_val, bool):
                        default_clause = f" DEFAULT {1 if default_val else 0}"
                    elif isinstance(default_val, (int, float)):
                        default_clause = f" DEFAULT {default_val}"
                    else:
                        default_clause = f" DEFAULT '{default_val}'"
                
                nullable = "" if column.nullable else " NOT NULL"
                # SQLite ALTER TABLE can't add NOT NULL without DEFAULT
                if nullable and not default_clause:
                    # Force a default for migration safety
                    default_clause = " DEFAULT ''"
                
                alter_sql = f'ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{nullable}{default_clause}'
                
                print(f"[DB MIGRATE] Adding missing column: {alter_sql}")
                try:
                    with engine.begin() as conn:
                        conn.execute(text(alter_sql))
                except Exception as e:
                    print(f"[DB MIGRATE] Warning: Could not add column {column.name} to {table_name}: {e}")


def create_db_and_tables():
    # First, add any missing columns to existing tables (SQLite workaround)
    try:
        _add_missing_columns_sqlite()
    except Exception as e:
        print(f"[DB MIGRATE] Column migration check failed (non-fatal): {e}")
    
    # This will create all tables that inherit from Base (but won't alter existing ones)
    Base.metadata.create_all(bind=engine)


# This is our new FastAPI dependency
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()