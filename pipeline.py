import duckdb, time, pandas as pd, sys

REG = sys.argv[1] if len(sys.argv) > 1 else "northern-ca"

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
con.sql("SET s3_region='us-west-2'; SET s3_url_style='path';")
BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

t0 = time.time()
con.sql(f"CREATE TEMP TABLE tracts AS SELECT GEOID, geometry, bbox FROM '{BASE}/strata/{REG}/{REG}-census-tracts.parquet'")
con.sql(f"CREATE TEMP TABLE tiger AS SELECT geometry, bbox FROM '{BASE}/reference/{REG}/{REG}-census-tiger-roads.parquet' WHERE MTFCC IN ('S1100','S1200')")
con.sql(f"CREATE TEMP TABLE overture_rd AS SELECT geometry, bbox FROM '{BASE}/reference/{REG}/{REG}-overture-roads.parquet' WHERE subtype='road' AND class IN ('motorway','trunk','primary','secondary')")
con.sql(f"CREATE TEMP TABLE ms_bldg AS SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-microsoft-buildings.parquet'")
con.sql(f"CREATE TEMP TABLE ov_bldg AS SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-overture-buildings.parquet'")
con.sql(f"CREATE TEMP TABLE ov_pois AS SELECT geometry AS pt, categories.primary AS cat_primary FROM '{BASE}/reference/{REG}/{REG}-overture-pois.parquet'")
print("load done", time.time()-t0)

# --- transport (road) gap ---
t0=time.time()
tiger_len = con.sql("""
SELECT t.GEOID, sum(ST_Length(ST_Transform(ST_Intersection(r.geometry,t.geometry),'EPSG:4326','EPSG:5070',always_xy:=true))) AS tiger_len_m
FROM tracts t JOIN tiger r
ON t.bbox.xmin<=r.bbox.xmax AND t.bbox.xmax>=r.bbox.xmin AND t.bbox.ymin<=r.bbox.ymax AND t.bbox.ymax>=r.bbox.ymin AND ST_Intersects(t.geometry,r.geometry)
GROUP BY t.GEOID""").df()
ov_len = con.sql("""
SELECT t.GEOID, sum(ST_Length(ST_Transform(ST_Intersection(r.geometry,t.geometry),'EPSG:4326','EPSG:5070',always_xy:=true))) AS overture_len_m
FROM tracts t JOIN overture_rd r
ON t.bbox.xmin<=r.bbox.xmax AND t.bbox.xmax>=r.bbox.xmin AND t.bbox.ymin<=r.bbox.ymax AND t.bbox.ymax>=r.bbox.ymin AND ST_Intersects(t.geometry,r.geometry)
GROUP BY t.GEOID""").df()
print("road join", time.time()-t0)

geoids = con.sql("SELECT GEOID FROM tracts").df()
df = geoids.merge(tiger_len, on="GEOID", how="left").merge(ov_len, on="GEOID", how="left")
df["tiger_len_m"] = df["tiger_len_m"].fillna(0.0)
df["overture_len_m"] = df["overture_len_m"].fillna(0.0)
df["transport_defined"] = df["tiger_len_m"] > 0
df["transport_gap"] = 0.0
mask = df["transport_defined"]
df.loc[mask, "transport_gap"] = 1 - (df.loc[mask,"overture_len_m"]/df.loc[mask,"tiger_len_m"]).clip(upper=1.0)

n_undef = (~df["transport_defined"]).sum()
print(f"transport undefined: {n_undef}/{len(df)}  (README says northern-ca=218/591)")

df.to_csv(f"{REG}_partial.csv", index=False)
