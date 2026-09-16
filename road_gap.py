import duckdb, time
con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
con.sql("SET s3_region='us-west-2'; SET s3_url_style='path';")
BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"
REG="northern-ca"

t0=time.time()
con.sql(f"""
CREATE TEMP TABLE tracts AS
SELECT GEOID, geometry, bbox FROM '{BASE}/strata/{REG}/{REG}-census-tracts.parquet'
""")
con.sql(f"""
CREATE TEMP TABLE tiger AS
SELECT geometry, bbox FROM '{BASE}/reference/{REG}/{REG}-census-tiger-roads.parquet'
WHERE MTFCC IN ('S1100','S1200')
""")
con.sql(f"""
CREATE TEMP TABLE overture AS
SELECT geometry, bbox FROM '{BASE}/reference/{REG}/{REG}-overture-roads.parquet'
WHERE subtype='road' AND class IN ('motorway','trunk','primary','secondary')
""")
print("load", time.time()-t0)

t0=time.time()
tiger_len = con.sql("""
SELECT t.GEOID,
       sum(ST_Length(ST_Transform(ST_Intersection(r.geometry, t.geometry), 'EPSG:4326','EPSG:5070', always_xy:=true))) AS tiger_len_m
FROM tracts t
JOIN tiger r
  ON t.bbox.xmin <= r.bbox.xmax AND t.bbox.xmax >= r.bbox.xmin
 AND t.bbox.ymin <= r.bbox.ymax AND t.bbox.ymax >= r.bbox.ymin
 AND ST_Intersects(t.geometry, r.geometry)
GROUP BY t.GEOID
""").df()
print("tiger join", time.time()-t0, len(tiger_len))

t0=time.time()
ov_len = con.sql("""
SELECT t.GEOID,
       sum(ST_Length(ST_Transform(ST_Intersection(r.geometry, t.geometry), 'EPSG:4326','EPSG:5070', always_xy:=true))) AS overture_len_m
FROM tracts t
JOIN overture r
  ON t.bbox.xmin <= r.bbox.xmax AND t.bbox.xmax >= r.bbox.xmin
 AND t.bbox.ymin <= r.bbox.ymax AND t.bbox.ymax >= r.bbox.ymin
 AND ST_Intersects(t.geometry, r.geometry)
GROUP BY t.GEOID
""").df()
print("overture join", time.time()-t0, len(ov_len))

merged = tiger_len.merge(ov_len, on="GEOID", how="outer")
print(merged.head(10))
merged.to_csv("northern_ca_road_lengths.csv", index=False)
