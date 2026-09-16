import duckdb, time, pandas as pd, sys

REG = sys.argv[1] if len(sys.argv) > 1 else "northern-ca"

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
con.sql("SET s3_region='us-west-2'; SET s3_url_style='path';")
BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

t0 = time.time()
con.sql(f"CREATE TEMP TABLE tracts AS SELECT GEOID, geometry, bbox FROM '{BASE}/strata/{REG}/{REG}-census-tracts.parquet'")
# centroid convention: a building is assigned to the tract containing its centroid (avoids
# double-counting footprints that straddle a tract line; roads use length-clipped intersection
# instead because a line has no single natural point, but a building footprint does).
con.sql(f"""
CREATE TEMP TABLE ov_bldg AS
SELECT ST_Centroid(geometry) AS pt
FROM '{BASE}/reference/{REG}/{REG}-overture-buildings.parquet'
""")
con.sql(f"""
CREATE TEMP TABLE ms_bldg AS
SELECT ST_Centroid(geometry) AS pt
FROM '{BASE}/reference/{REG}/{REG}-microsoft-buildings.parquet'
""")
print("load", time.time() - t0)

t0 = time.time()
ov_cnt = con.sql("""
SELECT t.GEOID, count(*) AS overture_bldg_n
FROM tracts t JOIN ov_bldg b
ON t.bbox.xmin <= ST_X(b.pt) AND t.bbox.xmax >= ST_X(b.pt)
AND t.bbox.ymin <= ST_Y(b.pt) AND t.bbox.ymax >= ST_Y(b.pt)
AND ST_Contains(t.geometry, b.pt)
GROUP BY t.GEOID
""").df()
print("overture bldg join", time.time() - t0, len(ov_cnt))

t0 = time.time()
ms_cnt = con.sql("""
SELECT t.GEOID, count(*) AS ms_bldg_n
FROM tracts t JOIN ms_bldg b
ON t.bbox.xmin <= ST_X(b.pt) AND t.bbox.xmax >= ST_X(b.pt)
AND t.bbox.ymin <= ST_Y(b.pt) AND t.bbox.ymax >= ST_Y(b.pt)
AND ST_Contains(t.geometry, b.pt)
GROUP BY t.GEOID
""").df()
print("ms bldg join", time.time() - t0, len(ms_cnt))

geoids = con.sql("SELECT GEOID FROM tracts").df()
df = geoids.merge(ov_cnt, on="GEOID", how="left").merge(ms_cnt, on="GEOID", how="left")
df["overture_bldg_n"] = df["overture_bldg_n"].fillna(0).astype(int)
df["ms_bldg_n"] = df["ms_bldg_n"].fillna(0).astype(int)
df["building_defined"] = df["ms_bldg_n"] > 0
df["building_gap"] = 0.0
mask = df["building_defined"]
df.loc[mask, "building_gap"] = 1 - (df.loc[mask, "overture_bldg_n"] / df.loc[mask, "ms_bldg_n"]).clip(upper=1.0)

n_undef = (~df["building_defined"]).sum()
print(f"building undefined: {n_undef}/{len(df)}")
print(f"total overture={df['overture_bldg_n'].sum()}  total ms={df['ms_bldg_n'].sum()}")
print(df["building_gap"][mask].describe())

df.to_csv(f"{REG}_building_gap.csv", index=False)
