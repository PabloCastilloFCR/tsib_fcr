from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

url = URL.create(drivername="postgresql+psycopg2", host="192.168.2.195", port=5432,
                 username="guest1", password="guest1_2026_merlin", database="geonode_local_data")
engine = create_engine(url, pool_pre_ping=True)

with engine.connect() as conn:
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'merlin_rcp' AND table_name = 'edificios'
        ORDER BY ordinal_position;
    """)).fetchall()
    print("Current columns in merlin_rcp.edificios:")
    for c in cols:
        print(f"  {c[0]:<45} {c[1]}")
